#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Simple-tile connector coupons (draft KiCad boards).

Runs inside the KiCad flatpak (needs pcbnew):

    flatpak run --filesystem="$PWD" --command=python3 org.kicad.KiCad \
        hardware/experiments/simple-tile/connectors/make_coupons.py

Reads the study output (out/placement.json) so the coupons use the SAME lattice,
pad plan and mezzanine extension that the collision-checked study produced.
Builds three coupon boards under out/coupons/:

  coupon_spring.kicad_pcb   variant A reference: 2x2 vendored Kailh sockets, the
                            study's pad-row geometry (subset), demo detection
                            straps, THT probe pads wired on B.Cu
  coupon_mezz.kicad_pcb     variant B reference: 2x2 sockets + the DF12
                            C3.0/E3.0 mezzanine plug (verified KiCad library
                            footprint) on the study's certified south tab
  coupon_direct.kicad_pcb   direct-wired reference: every key terminal to its
                            own probe pads, checked with the study's engine

Every copper item (pad, track, THT annulus) is placed only where the study's
exact collision engine says it fits; items that cannot be placed cleanly are
skipped and recorded in out/coupons/coupons.json. The coupons are DRAFTS:
there is no schematic and no ERC; readiness is decided by the recorded DRC
output, not assumed.
"""
import json
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
OUT = os.path.join(HERE, "out")
COUT = os.path.join(OUT, "coupons")
sys.path.insert(0, HERE)
import study  # noqa: E402  (pure stdlib modules shared with the study)

MM = pcbnew.FromMM
FP_STOCK = "/app/extensions/Library/Footprints/footprints"
FP_REPO = os.path.join(ROOT, "hardware", "kicad", "lib",
                       "Switch_Keyboard_Hotswap_Kailh.pretty")

TRACK_W = 0.35
TP_DRILL = 1.0
TP_SIZE = 1.6
TOL = 0.3          # clearance target around added copper


# ------------------------------------------------------------------ board kit
def new_board():
    b = pcbnew.BOARD()
    b.SetCopperLayerCount(2)
    return b


def net(b, name):
    n = b.FindNet(name)
    if n is None:
        n = pcbnew.NETINFO_ITEM(b, name)
        b.Add(n)
    return n


def edge_rect(b, rect, tb=False):
    x0, y0, x1, y1 = rect
    for (a, c), (d, e) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
                           ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(MM(a), MM(c)))
        s.SetEnd(pcbnew.VECTOR2I(MM(d), MM(e)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.05))
        b.Add(s)


def text(b, x, y, s, size=1.0, layer=None, mirror=True):
    t = pcbnew.PCB_TEXT(b)
    t.SetText(s)
    t.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetLayer(layer if layer is not None else pcbnew.B_SilkS)
    if mirror and (layer or pcbnew.B_SilkS) in (pcbnew.B_SilkS, pcbnew.B_Fab):
        t.SetMirrored(True)
    b.Add(t)
    return t


def load_fp(b, libdir, name, ref, value, x, y, side="B", rot=0):
    fp = pcbnew.FootprintLoad(libdir, name)
    if fp is None:
        raise RuntimeError(f"footprint load failed: {libdir} :: {name}")
    fp.SetReference(ref)
    fp.SetValue(value)
    b.Add(fp)                       # NOTE: Add before flip; flipping orphan FP segfaults
    fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    if rot:
        fp.SetOrientationDegrees(rot)
    if side == "B":
        fp.SetLayerAndFlip(pcbnew.B_Cu)
    return fp
def smd_pad(b, ref, x, y, w, h, netname, side=pcbnew.B_Cu, shape=pcbnew.PAD_SHAPE_RECT):
    fp = pcbnew.FOOTPRINT(b)
    fp.SetReference(ref)
    fp.SetValue(ref)
    b.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I(MM(0), MM(0)))
    p = pcbnew.PAD(fp)
    p.SetNumber("1")
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetShape(shape)
    p.SetSize(pcbnew.VECTOR2I(MM(w), MM(h)))
    ls = pcbnew.LSET()
    ls.AddLayer(side)
    ls.AddLayer(pcbnew.B_Mask if side == pcbnew.B_Cu else pcbnew.F_Mask)
    p.SetLayerSet(ls)
    p.SetNet(net(b, netname))
    fp.Add(p)
    p.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    fp.SetBoardOnly(True)
    fp.SetExcludedFromBOM(True)
    fp.SetExcludedFromPosFiles(True)
    return fp


def tht_probe(b, ref, x, y, netname):
    """Probe pad on B.Cu (all-SMD: the vendored switch courtyard makes drilled
    probe pads impossible in the lanes - recorded in the coupon notes).
    Probing a seated tile needs a chassis window; noted in the report."""
    return smd_pad(b, ref, x, y, TP_SIZE, TP_SIZE, netname)


def track(b, a, c, netname):
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(pcbnew.VECTOR2I(MM(a[0]), MM(a[1])))
    t.SetEnd(pcbnew.VECTOR2I(MM(c[0]), MM(c[1])))
    t.SetWidth(MM(TRACK_W))
    t.SetLayer(pcbnew.B_Cu)
    t.SetNet(net(b, netname))
    b.Add(t)
    return t


def npth(b, x, y, d):
    fp = pcbnew.FOOTPRINT(b)
    fp.SetReference("MH")
    b.Add(fp)
    p = pcbnew.PAD(fp)
    p.SetNumber("")
    p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetSize(pcbnew.VECTOR2I(MM(d), MM(d)))
    p.SetDrillSize(pcbnew.VECTOR2I(MM(d), MM(d)))
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.B_Cu)
    ls.AddLayer(pcbnew.F_Cu)
    p.SetLayerSet(ls)
    fp.Add(p)
    p.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    fp.SetBoardOnly(True)
    fp.SetExcludedFromBOM(True)
    return fp


# ------------------------------------------------------- collision-checked put
class Coupon:
    """A 2x2-key coupon using the study's Tile engine for collision checks."""

    def __init__(self, name, bottom_ext=0.0, north_ext=0.0):
        self.name = name
        self.par = study.replace(study.Params(), rows=2, cols=2,
                                 bottom_ext=bottom_ext)
        fp = study.parse_kicad_mod(study.VENDORED_FP)
        fp_tr = study.parse_kicad_mod(study.VENDORED_FP_TRIM)
        # translate the study tile so the coupon outline starts at (0,0)
        self.tile = study.Tile(self.par, fp, "rect", fp_tr)
        xs = [q[0] for q in self.tile.outline]
        ys = [q[1] for q in self.tile.outline]
        self.dx, self.dy = -min(xs), -min(ys) + north_ext
        self.tile.centre = {k: (x + self.dx, y + self.dy)
                            for k, (x, y) in self.tile.centre.items()}
        self.tile.outline = [(x + self.dx, y + self.dy) for x, y in self.tile.outline]
        if hasattr(self.tile, "_obs_cache"):
            del self.tile._obs_cache
        self.board = new_board()
        # study policy: copper-to-edge = edge_clear + outline tolerance (0.4 mm),
        # tighter than KiCad's default 0.5 mm for these coupons
        try:
            self.board.GetDesignSettings().m_CopperEdgeClearance = \
                MM(self.par.edge_clear + self.par.board_edge_tol)
        except Exception as e:
            print("NOTE: could not set edge clearance rule:", e)
        self.skipped = []
        xs = [q[0] for q in self.tile.outline]
        ys = [q[1] for q in self.tile.outline]
        self.brect = (min(xs), min(ys), max(xs), max(ys))
        edge_rect(self.board, self.brect)

    def W(self):
        return self.brect[2] - self.brect[0]

    def H(self):
        return self.brect[3] - self.brect[1]

    def tile_to_board(self, x, y):
        return x, y

    def free_rect(self, r, extra=TOL, ignore=()):
        t2 = [o for o in self.tile._obs() if o["tag"] not in ignore]
        best = 1e9
        self.last_blocker = None
        for o in t2:
            bb = o["bbox"]
            d_bb = study.dist_rect_rect(r, bb)
            if d_bb - o["clr"] - extra >= best:
                continue
            if o["kind"] == "circle":
                d = study.dist_rect_circle(r, o["x"], o["y"], o["r"])
            elif o["kind"] == "rect":
                d = study.dist_rect_rect(r, o["rect"])
            else:
                d = study.dist_rect_poly(r, o["pts"])
            if d - o["clr"] - extra < best:
                best = d - o["clr"] - extra
                self.last_blocker = o["tag"]
                self.last_blocker_val = round(d - o["clr"] - extra, 3)
        e = self.tile.edge_slack(r)
        if e < self.par.edge_clear + self.par.board_edge_tol - 1e-6:
            self.last_blocker = "edge"
            self.last_blocker_val = round(e, 3)
            return False
        return best >= 0

    def add_obstacle(self, o):
        self.tile._obs().append(o)

    def place_smd(self, ref, x, y, w, h, netname):
        r = study.Rect(x - w / 2, y - h / 2, x + w / 2, y + h / 2)
        if not self.free_rect(r):
            self.skipped.append({"what": f"pad {ref} {netname}", "at": [x, y]})
            return None
        self.add_obstacle({"kind": "rect", "clr": 0.0, "tag": ref,
                           "rect": r, "bbox": r})
        return smd_pad(self.board, ref, x, y, w, h, netname)

    def place_tp(self, ref, x, y, netname):
        r = study.Rect(x - TP_SIZE / 2, y - TP_SIZE / 2, x + TP_SIZE / 2, y + TP_SIZE / 2)
        if not self.free_rect(r, extra=0.2):
            self.skipped.append({"what": f"tp {ref} {netname}", "at": [x, y]})
            return None
        ob = {"kind": "circle", "clr": 0.0, "tag": ref, "x": x, "y": y,
              "r": TP_SIZE / 2, "bbox": r}
        self.add_obstacle(ob)
        return tht_probe(self.board, ref, x, y, netname)

    def place_track_hv(self, a, c, netname, ignore=()):
        """Horizontal then vertical dogleg; each segment checked."""
        pts = [a, (c[0], a[1]), c]
        for (u, v) in zip(pts, pts[1:]):
            if abs(u[0] - v[0]) < 1e-9 and abs(u[1] - v[1]) < 1e-9:
                continue
            r = study.Rect(min(u[0], v[0]) - TRACK_W / 2, min(u[1], v[1]) - TRACK_W / 2,
                           max(u[0], v[0]) + TRACK_W / 2, max(u[1], v[1]) + TRACK_W / 2)
            if not self.free_rect(r, extra=0.2, ignore=ignore):
                self.skipped.append({"what": f"track {netname}", "from": a, "to": c})
                return None
        for (u, v) in zip(pts, pts[1:]):
            if abs(u[0] - v[0]) < 1e-9 and abs(u[1] - v[1]) < 1e-9:
                continue
            track(self.board, u, v, netname)
            w = TRACK_W / 2
            r = study.Rect(min(u[0], v[0]) - w, min(u[1], v[1]) - w,
                           max(u[0], v[0]) + w, max(u[1], v[1]) + w)
            self.add_obstacle({"kind": "rect", "clr": 0.0, "tag": f"trk {netname}",
                               "rect": r, "bbox": r})
        return True

    def check_route(self, pts, ignore=()):
        segs = []
        for u, v in zip(pts, pts[1:]):
            if abs(u[0] - v[0]) < 1e-9 and abs(u[1] - v[1]) < 1e-9:
                continue
            if abs(u[0] - v[0]) > 1e-9 and abs(u[1] - v[1]) > 1e-9:
                return None                     # not orthogonal
            w = TRACK_W / 2
            r = study.Rect(min(u[0], v[0]) - w, min(u[1], v[1]) - w,
                           max(u[0], v[0]) + w, max(u[1], v[1]) + w)
            if not self.free_rect(r, extra=0.2, ignore=ignore):
                self.last_route_blocker = f"{self.last_blocker}={getattr(self, 'last_blocker_val', '?')}@{r.as_list()}"
                return None
            segs.append((u, v, r))
        return segs

    def commit_route(self, segs, netname):
        for u, v, r in segs:
            track(self.board, u, v, netname)
            self.add_obstacle({"kind": "rect", "clr": 0.0, "tag": f"trk {netname}",
                               "rect": r, "bbox": r})

    def place_mounts(self):
        x0, y0, x1, y1 = self.brect
        for mx, my in ((x0 + 3, y0 + 3), (x1 - 3, y1 - 3)):
            r = study.Rect(mx - 1.6, my - 1.6, mx + 1.6, my + 1.6)
            if self.free_rect(r, extra=0.2):
                npth(self.board, mx, my, 2.2)
                self.add_obstacle({"kind": "circle", "clr": 0.0, "tag": "MH",
                                   "x": mx, "y": my, "r": 1.1,
                                   "bbox": study.Rect(*r.as_list())})

    def place_keys(self):
        # vendored footprint is authored with pads on B.Cu already (sockets sit on
        # the solder side); place AS AUTHORED (side="A" = no flip)
        for (i, k), (x, y) in sorted(self.tile.centre.items()):
            name = ("SW_Hotswap_Kailh_MX_1.00u_EdgeTrim"
                    if self.tile.pad_variant.get((i, k)) == "edgetrim"
                    else "SW_Hotswap_Kailh_MX_1.00u")
            fp = load_fp(self.board, FP_REPO, name, f"SW{i}{k}", "Kailh hotswap", x, y,
                         side="A")
            for p in fp.Pads():
                if p.GetNumber() == "1":
                    p.SetNet(net(self.board, f"K{i}{k}_R"))
                elif p.GetNumber() == "2":
                    p.SetNet(net(self.board, f"K{i}{k}_C"))

    def drop_fp(self, fp):
        try:
            self.board.Remove(fp)
        except Exception:
            pass

    def save(self):
        path = os.path.join(COUT, f"{self.name}.kicad_pcb")
        self.board.Save(path)
        rules = {"max_error": 0.005,
                 "min_clearance": 0.2,
                 "min_connection": 0.2,
                 "min_copper_edge_clearance": self.par.edge_clear + self.par.board_edge_tol,
                 "min_groove_width": 0.0,
                 "min_hole_clearance": 0.25,
                 "min_hole_to_hole": 0.25,
                 "min_microvia_diameter": 0.2,
                 "min_microvia_drill": 0.1,
                 "min_resolved_spokes": 1,
                 "min_silk_clearance": 0.0,
                 "min_text_height": 0.8,
                 "min_text_thickness": 0.08,
                 "min_through_hole_diameter": 0.3,
                 "min_track_width": 0.15,
                 "min_via_annular_width": 0.15,
                 "min_via_diameter": 0.6,
                 "solder_mask_to_copper_clearance": 0.0,
                 "use_height_for_length_calcs": True}
        pro = {"board": {"design_settings": {"defaults": {},
                                             "diff_pair_dimensions": [],
                                             "rules": rules},
                         "layer_presets": []},
               "meta": {"filename": f"{self.name}.kicad_pro", "version": 1},
               "sheets": []}
        json.dump(pro, open(os.path.join(COUT, f"{self.name}.kicad_pro"), "w"))
        return path


def pad_row_plan(plan, want):
    by_sig = {p["sig"]: p for p in plan["pads"]}
    pitch = plan["pitch"]
    idx = {s: i for i, s in enumerate(plan["pads"] and [q["sig"] for q in plan["pads"]])}
    return by_sig, idx, pitch


# ------------------------------------------------------------------ coupons
def coupon_spring(place):
    cp = Coupon("coupon_spring")
    cp.place_keys()
    va = place["variant_a"]["stepped"]
    rail = next(l for l in va["plan"] if l["group"] == "bottom")   # the J103 rail
    d = va["pad_d"]
    pitch = va["pitch"]
    pads = rail["pads"]                     # real rev-A bottom group, real geometry
    n = len(pads)
    yb = cp.brect[3] - cp.par.edge_clear - cp.par.board_edge_tol - d / 2 - 0.6
    ymax = max(c[1] for c in cp.tile.centre.values())
    ytp = ymax + 2.0 + cp.par.clr_hole + 0.3 + TP_SIZE / 2   # clear of centre-hole keep-out
    x0 = cp.W() / 2 - (n - 1) * pitch / 2
    for j, q in enumerate(pads):
        x = x0 + j * pitch
        s = q["role"]
        if cp.place_smd(f"P{s.replace('.', '_')}", x, yb, d, d, s) is None:
            continue
        tp = cp.place_tp(f"TP{s.replace('.', '_')}", x, ytp, s)
        if tp is not None:
            if cp.place_track_hv((x, yb - d / 2), (x, ytp), s,
                                 ignore={f"P{s.replace('.', '_')}",
                                        f"TP{s.replace('.', '_')}"}) is None:
                cp.drop_fp(tp)
    # demo detection straps at third-points (engine-checked local search)
    w_, h_ = cp.par.strap_pad_w, cp.par.strap_pad_h
    m = cp.par.edge_clear + cp.par.board_edge_tol
    x0, y0, x1, y1 = cp.brect
    demos = [("STRAP0", x1 / 3, y0 + m + h_ / 2 + 0.2, "H"),
             ("STRAP1", x1 * 2 / 3, y0 + m + h_ / 2 + 0.2, "H"),
             ("STRAP2", x1 - m - w_ / 2 - 0.2, y1 * 2 / 3, "V")]
    for n, (nm, xn, yn, orient) in enumerate(demos):
        pax = w_ + 1.0
        found = None
        for off in (k * 0.25 for k in range(0, 48)):
            for s_ in (off, -off):
                if orient == "H":
                    a_, b_ = (xn + s_ - pax / 2, yn), (xn + s_ + pax / 2, yn)
                else:
                    a_, b_ = (xn, yn + s_ - pax / 2), (xn, yn + s_ + pax / 2)
                ra = study.Rect(a_[0] - w_ / 2, a_[1] - h_ / 2, a_[0] + w_ / 2, a_[1] + h_ / 2)
                rb = study.Rect(b_[0] - w_ / 2, b_[1] - h_ / 2, b_[0] + w_ / 2, b_[1] + h_ / 2)
                if cp.free_rect(ra) and cp.free_rect(rb):
                    found = (a_, b_)
                    break
            if found:
                break
        if not found:
            cp.skipped.append({"what": f"strap {nm}", "at": [xn, yn]})
            continue
        a_, b_ = found
        fa = cp.place_smd(f"ST{n}a", a_[0], a_[1], w_, h_, nm)
        fb = cp.place_smd(f"ST{n}b", b_[0], b_[1], w_, h_, nm)
        if fa is None or fb is None or \
                cp.place_track_hv(a_, b_, nm, ignore={f"ST{n}a", f"ST{n}b"}) is None:
            # strap demo without a tile-internal tie is an incomplete circuit:
            # remove the pair honestly so the DRC gate sees the real state
            for fx in (fa, fb):
                if fx is not None:
                    cp.drop_fp(fx)
            cp.skipped.append({"what": f"strap {nm} tie", "at": [a_[0], a_[1]]})
            continue
        # lateral TP (off the strap axis, away from the switch holes)
        if orient == "H":
            tx, ty = b_[0] + w_ / 2 + 1.6, b_[1]
            if tx + TP_SIZE / 2 > x1 - m:
                tx = a_[0] - w_ / 2 - 1.6
        else:
            tx, ty = a_[0] - w_ / 2 - 1.6, b_[1]
            if tx - TP_SIZE / 2 < x0 + m:
                tx = b_[0] + w_ / 2 + 1.6
        tp = cp.place_tp(f"TPST{n}", tx, ty, nm)
        if tp is not None:
            if cp.place_track_hv(b_, (tx, ty), nm,
                                 ignore={f"ST{n}a", f"ST{n}b", f"TPST{n}"}) is None:
                cp.drop_fp(tp)
    text(cp.board, 2, cp.brect[1] + 3, "COUPON A: chassis spring pad row "
         f"(pitch {pitch} mm) + demo detect straps; keys for fit only. DRAFT - no ERC")
    text(cp.board, 2, cp.brect[3] - 1.4, "study: connectors/out/placement.json")
    cp.place_mounts()
    return cp


def coupon_mezz(place, mezz):
    pair = place["variant_b"]["stepped"]["df12_pair30"]
    ext = pair.get("min_bottom_extension_mm") or 0.0
    cp = Coupon("coupon_mezz", bottom_ext=ext)
    cp.place_keys()
    info = mezz["df12_plug30"]
    name = info["name"]
    cb = info["courtyard_bbox_fpside"]
    tw, th = cb["x1"] - cb["x0"], cb["y1"] - cb["y0"]
    # search downward for a courtyard position the exact engine accepts
    x = cp.W() / 2
    ys = cp.brect[3] - th / 2 - 1.0
    placed, hit = None, None
    while ys > cp.brect[1] + (cp.par.rows - 1) * cp.par.R() + 3:
        r = study.Rect(x - tw / 2, ys - th / 2, x + tw / 2, ys + th / 2)
        if cp.free_rect(r, extra=0.5):
            placed, hit = ys, r
            break
        ys -= 0.25
    if placed is None:
        raise RuntimeError("coupon_mezz: no collision-free connector position")
    fp = load_fp(cp.board, os.path.join(FP_STOCK, "Connector_Hirose.pretty"),
                 name, "J1", "DF12E3.0-30DP (tile plug)", x, placed)
    # assign nets to all contacts so DRC compares like with like; resolve the
    # exact board-side pad positions from the placed footprint (post-flip)
    probe = {"1", "15", "16", "30"}          # the four row ends of the 2x15
    padpos = {}
    for p in fp.Pads():
        if p.GetNumber():
            p.SetNet(net(cp.board, f"J1.{p.GetNumber()}"))
            pos = p.GetPosition()
            padpos[p.GetNumber()] = (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y),
                                     pcbnew.ToMM(p.GetSizeX()), pcbnew.ToMM(p.GetSizeY()))
    # register only the copper pads as obstacles (the courtyard is not copper);
    # the four probed corner pads stay register-free so stubs do not self-collide
    for p in fp.Pads():
        if p.GetNumber() and p.GetNumber() not in probe:
            px, py, pw, ph = padpos[p.GetNumber()]
            pr = study.Rect(px - pw / 2, py - ph / 2, px + pw / 2, py + ph / 2)
            cp.add_obstacle({"kind": "rect", "clr": 0.0, "tag": f"J1.{p.GetNumber()}",
                             "rect": pr, "bbox": pr})
    # probe the four geometric corner pads of the two contact rows; stubs exit
    # along the row, away from the row end (measured from the placed footprint)
    for pn in probe:
        px, py, pw, ph = padpos[pn]
        side = -1 if px < x else 1
        tpx = px + side * 3.6
        tp = cp.place_tp(f"TP_P{pn}", tpx, py, f"J1.{pn}")
        if tp is not None:
            cp.place_track_hv((px + side * pw / 2, py), (tpx, py), f"J1.{pn}",
                              ignore={f"TP_P{pn}"})
    text(cp.board, 2, cp.brect[1] + 3,
         f"COUPON B: mezzanine plug {name}, south tab +{ext} mm (study-certified)")
    text(cp.board, 2, cp.brect[3] - 1.4,
         "DRAFT - corner-pad TPs only, no full fan-out escape, no ERC")
    cp.place_mounts()
    return cp


def coupon_direct(place):
    """Direct-wired reference: each key terminal individually routed to its own
    probe pad with an engine-checked orthogonal route. Top-row keys route NORTH
    to a top probe row on a small outline extension; bottom-row keys route
    SOUTH. Anything unroutable is recorded."""
    cp = Coupon("coupon_direct", north_ext=4.0)
    cp.place_keys()
    ytp_s = cp.brect[3] - 3.2
    ytp_n = cp.brect[1] + 3.2
    rows_y = sorted({y for _, y in cp.tile.centre.values()})
    lane_mid_s = ((rows_y[0] + 2.5) + (rows_y[1] - 7.1)) / 2
    lane_mid_n = (cp.brect[1] + 1.0 + (rows_y[0] - 7.1)) / 2    # north free strip
    m_ = cp.par.edge_clear + cp.par.board_edge_tol
    for (i, k), (x, y) in sorted(cp.tile.centre.items()):
        north = (k == 0)
        ytp = ytp_n if north else ytp_s
        lane_mid = lane_mid_n if north else lane_mid_s
        for side, a in (("R", (x - 7.085, y - 3.79 if north else y - 1.29)),
                        ("C", (x + 7.0, y - 5.08))):        # pad2 east edge, on-copper
            tag = f"SW[{i},{k}] pad1" if side == "R" else f"SW[{i},{k}] pad2"
            nn = f"K{i}{k}_{side}"
            done = False
            offs = [o * 0.5 for o in range(0, 24)]
            offs = offs + [-o for o in offs[1:]]
            ok_sign = 1 if north else -1
            for dx in offs:
                xe = a[0] + dx
                if xe + TP_SIZE / 2 > cp.brect[2] - m_ or xe - TP_SIZE / 2 < m_:
                    continue
                for pts in ([a, (a[0], ytp)],
                            [a, (a[0], ytp)] if north else
                            [a, (xe, a[1]), (xe, ytp)],
                            [a, (a[0], lane_mid), (xe, lane_mid), (xe, ytp)]):
                    ign = {tag, f"TP{nn}"}
                    segs = cp.check_route(pts, ignore=ign)
                    dbg = os.environ.get("COUPON_DEBUG") == "1"
                    if dbg:
                        print(f"  {nn} dx={dx:+.1f} tmpl={len(pts)} "
                              f"segs_ok={segs is not None} block={cp.last_route_blocker}")
                    if segs is None:
                        continue
                    # TP must also fit before committing the route
                    tr = study.Rect(xe - TP_SIZE / 2, ytp - TP_SIZE / 2,
                                    xe + TP_SIZE / 2, ytp + TP_SIZE / 2)
                    if not cp.free_rect(tr, extra=0.2, ignore=ign):
                        continue
                    # reserve TP as obstacle, then commit
                    cp.add_obstacle({"kind": "circle", "clr": 0.0, "tag": f"TP{nn}",
                                     "x": xe, "y": ytp, "r": TP_SIZE / 2, "bbox": tr})
                    tht_probe(cp.board, f"TP{nn}", xe, ytp, nn)
                    cp.commit_route(segs, nn)
                    done = True
                    break
                if done:
                    break
            if not done:
                cp.skipped.append({"what": f"route {nn}", "from": list(a)})
    text(cp.board, 2, cp.brect[1] + 1.6, "COUPON C: direct-wired reference, one pair "
         "per key, no matrix; row0 to the top probe row, row1 to the bottom row; "
         "route templates + skips in coupons.json")
    cp.place_mounts()
    return cp


def main():
    os.makedirs(COUT, exist_ok=True)
    place = json.load(open(os.path.join(OUT, "placement.json")))
    mezz = json.load(open(os.path.join(OUT, "mezzanine_measures.json")))
    out = {}
    for cp in (coupon_spring(place), coupon_mezz(place, mezz), coupon_direct(place)):
        path = cp.save()
        n_fp = len(list(cp.board.GetFootprints()))
        n_tr = len(list(cp.board.GetTracks()))
        out[cp.name] = {"file": os.path.relpath(path, ROOT),
                        "outline_mm": [round(cp.W(), 2), round(cp.H(), 2)],
                        "footprints": n_fp, "tracks": n_tr,
                        "skipped": cp.skipped}
        print(f"{cp.name}: {cp.W():.1f} x {cp.H():.1f} mm, footprints={n_fp}, "
              f"tracks={n_tr}, skipped={len(cp.skipped)}")
    json.dump(out, open(os.path.join(COUT, "coupons.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
