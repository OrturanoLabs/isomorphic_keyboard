#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""connector-next coupons (DRAFT KiCad boards; concept, not fab-ready).

Runs inside the KiCad flatpak (needs pcbnew):

    flatpak run --filesystem="$REPO" --command=python3 org.kicad.KiCad \
        hardware/experiments/simple-tile/connector-next/make_coupons_next.py

Builds three coupon boards under out/coupons_next/:

  coupon_agg19.kicad_pcb    the tile-bottom aggregated contact plan: 19 round
                            spring-target pads in the two chassis tier rails
                            (15 SIG + 4 GND-class) exactly where the connector-
                            next study's exact engine placed them, every pad
                            probed to an SMD test point. 4x2 vendored Kailh
                            sockets carry the mechanical obstacle field.
  coupon_mezz20.kicad_pcb   in-production 20-pos mezzanine alternative: the
                            Harwin Gecko MVX2005L0X male (stock footprint,
                            MEASURED through-board tails) on the study's
                            certified +4.5 mm south tab; corner pads probed.
                            (DF12-20 would fit the pin budget too but the DF12
                            series page is bannered 'Planned End of Life'.)
  coupon_backplane.kicad_pcb  passive backplane slot-section concept: three
                            slots (an L), each with the 19 spring seats at the
                            study tier geometry, the DEDICATED detect-GND stubs
                            routed per boundary (never plane-bonded), and test
                            points on every net.

Every copper item is placed only where an exact collision engine allows;
skips are recorded. Readiness is decided by the recorded DRC output (run.sh
gates 0 errors AND 0 unconnected), never assumed.
"""
import importlib.util
import json
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
OUT = os.path.join(HERE, "out")
COUT = os.path.join(OUT, "coupons_next")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


base = _load("baseline_connectors_study",
             os.path.join(HERE, "..", "connectors", "study.py"))
budget = _load("connector_next_budget", os.path.join(HERE, "budget.py"))
cnext = _load("connector_next_study", os.path.join(HERE, "study.py"))

MM = pcbnew.FromMM
FP_STOCK = "/app/extensions/Library/Footprints/footprints"
FP_REPO = os.path.join(ROOT, "hardware", "kicad", "lib",
                       "Switch_Keyboard_Hotswap_Kailh.pretty")

TRACK_W = 0.35
TP_SIZE = 1.6
PAD_D = 2.5
SEAT_W, SEAT_H = 2.25, 3.70   # DRG-03072/03073 recommended PCB pad layout


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


def edge_rect(b, rect):
    x0, y0, x1, y1 = rect
    for (a_, c_), (d_, e_) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
                               ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(MM(a_), MM(c_)))
        s.SetEnd(pcbnew.VECTOR2I(MM(d_), MM(e_)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.05))
        b.Add(s)


def text(b, x, y, s, size=1.0):
    t = pcbnew.PCB_TEXT(b)
    t.SetText(s)
    t.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetLayer(pcbnew.B_SilkS)
    t.SetMirrored(True)
    b.Add(t)
    return t


def smd_pad(b, ref, x, y, w, h, netname, shape=pcbnew.PAD_SHAPE_RECT):
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
    ls.AddLayer(pcbnew.B_Cu)
    ls.AddLayer(pcbnew.B_Mask)
    p.SetLayerSet(ls)
    p.SetNet(net(b, netname))
    fp.Add(p)
    p.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    fp.SetBoardOnly(True)
    fp.SetExcludedFromBOM(True)
    fp.SetExcludedFromPosFiles(True)
    return fp


def track(b, a, c, netname, layer=pcbnew.B_Cu):
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(pcbnew.VECTOR2I(MM(a[0]), MM(a[1])))
    t.SetEnd(pcbnew.VECTOR2I(MM(c[0]), MM(c[1])))
    t.SetWidth(MM(TRACK_W))
    t.SetLayer(layer)
    t.SetNet(net(b, netname))
    b.Add(t)
    return t


class Field:
    """Obstacle field + collision-checked placement (Rect obstacles only)."""

    def __init__(self, edge_slack_min=0.4, edge_poly=None):
        self.obs = []
        self.skipped = []
        self.last = None
        self.edge_slack_min = edge_slack_min
        self.edge_poly = edge_poly

    def add(self, r, tag, clr=0.0):
        self.obs.append({"rect": r, "tag": tag, "clr": clr})

    def free(self, r, extra=0.25, ignore=()):
        for o in self.obs:
            if o["tag"] in ignore:
                continue
            if base.dist_rect_rect(r, o["rect"]) - o["clr"] - extra < 0:
                self.last = o["tag"]
                return False
        if self.edge_poly:
            d = min(base.seg_seg_dist(a, b, self.edge_poly[i],
                                      self.edge_poly[(i + 1) % len(self.edge_poly)])
                    for i in range(len(self.edge_poly)) for a, b in r.edges())
            if d < self.edge_slack_min - 1e-9:
                self.last = "edge"
                return False
        return True

    def pad(self, b, ref, x, y, w, h, netname, circle_=False, quiet=False):
        r = base.Rect(x - w / 2, y - h / 2, x + w / 2, y + h / 2)
        if not self.free(r):
            if not quiet:
                self.skipped.append({"what": f"pad {ref} {netname}",
                                     "at": [round(x, 2), round(y, 2)],
                                     "blocker": self.last})
            return None
        self.add(r, ref)
        return smd_pad(b, ref, x, y, w, h, netname,
                       pcbnew.PAD_SHAPE_CIRCLE if circle_ else pcbnew.PAD_SHAPE_RECT)

    def tp(self, b, ref, x, y, netname):
        fp = self.pad(b, ref, x, y, TP_SIZE, TP_SIZE, netname)
        return fp

    def route_vhv(self, b, a, jog_x, via_y, c, netname, ignore=()):
        """S1: (a)->(a.x, via_y); S2: jog along (jog_x, via_y); S3: down to
        (jog_x, c.y); S4: into c. Each segment collision-checked."""
        w = TRACK_W / 2
        pts = [a, (a[0], via_y), (jog_x, via_y), (jog_x, c[1]), c]
        segs = []
        for u, v in zip(pts, pts[1:]):
            if abs(u[0] - v[0]) < 1e-9 and abs(u[1] - v[1]) < 1e-9:
                continue
            r = base.Rect(min(u[0], v[0]) - w, min(u[1], v[1]) - w,
                          max(u[0], v[0]) + w, max(u[1], v[1]) + w)
            if not self.free(r, extra=0.15, ignore=ignore):
                return None
            segs.append((u, v, r))
        for u, v, r in segs:
            track(b, u, v, netname)
            self.add(r, f"trk {netname}")
        return True

    def route_hv(self, b, a, c, netname, ignore=()):
        w = TRACK_W / 2
        pts = [a, (c[0], a[1]), c]
        segs = []
        for u, v in zip(pts, pts[1:]):
            if abs(u[0] - v[0]) < 1e-9 and abs(u[1] - v[1]) < 1e-9:
                continue
            r = base.Rect(min(u[0], v[0]) - w, min(u[1], v[1]) - w,
                          max(u[0], v[0]) + w, max(u[1], v[1]) + w)
            if not self.free(r, extra=0.15, ignore=ignore):
                return None
            segs.append((u, v, r))
        for u, v, r in segs:
            track(b, u, v, netname)
            self.add(r, f"trk {netname}")
        return True


def cp_edge(par):
    return par.edge_clear + par.board_edge_tol


# ----------------------------------------------------------- coupon A: agg19
def coupon_agg19(study_out):
    """2x4-key coupon bottom side with the aggregated 19-pad two-tier plan."""
    par = base.replace(base.Params(), rows=2, cols=4, bottom_ext=16.0)
    tile = base.Tile(par, base.parse_kicad_mod(base.VENDORED_FP), "rect",
                     base.parse_kicad_mod(base.VENDORED_FP_TRIM))
    dx = -min(q[0] for q in tile.outline)
    dy = -min(q[1] for q in tile.outline)
    tile.outline = [(x + dx, y + dy) for x, y in tile.outline]
    tile.centre = {k: (x + dx, y + dy) for k, (x, y) in tile.centre.items()}
    if hasattr(tile, "_obs_cache"):
        del tile._obs_cache

    b = new_board()
    try:
        b.GetDesignSettings().m_CopperEdgeClearance = MM(0.4)
    except Exception:
        pass
    xs = [q[0] for q in tile.outline]
    ys = [q[1] for q in tile.outline]
    brect = (min(xs), min(ys), max(xs), max(ys))
    edge_rect(b, brect)
    field = Field(edge_poly=tile.outline)
    for o in tile.obstacles():
        if o["kind"] == "rect":
            field.add(o["rect"], f"obs:{o['tag']}", clr=o["clr"])
        elif o["kind"] == "circle":
            r = o["r"] + o["clr"] + 0.1
            field.add(base.Rect(o["x"] - r, o["y"] - r, o["x"] + r, o["y"] + r),
                      f"obs:{o['tag']}H", clr=0.0)
        else:
            xs2 = [q[0] for q in o["pts"]]
            ys2 = [q[1] for q in o["pts"]]
            r = base.Rect(min(xs2), min(ys2), max(xs2), max(ys2))
            # polygon approximated as its bbox + clearance: conservative
            field.add(base.Rect(r.x0 - o["clr"], r.y0 - o["clr"],
                                r.x1 + o["clr"], r.y1 + o["clr"]),
                      f"obs:{o['tag']}P", clr=0.0)

    # keys for mechanical reference
    for (i, k), (x, y) in sorted(tile.centre.items()):
        name = ("SW_Hotswap_Kailh_MX_1.00u_EdgeTrim"
                if tile.pad_variant.get((i, k)) == "edgetrim"
                else "SW_Hotswap_Kailh_MX_1.00u")
        fp = pcbnew.FootprintLoad(FP_REPO, name)
        fp.SetReference(f"SW{i}{k}")
        b.Add(fp)
        fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))

    islands = base.scan_islands(tile)
    tol = par.tol_chassis_xy
    pitch = par.pogo_pad_d + par.pogo_gap
    used = set()
    tiers = {}
    for tag, nets in (("SIG", cnext.TIER_S), ("GND", cnext.TIER_G)):
        # place the tier INTO THE COUPON with the study's own placer
        tier = None
        span_extra = 2 * tol
        span = (len(nets) - 1) * pitch + PAD_D + span_extra
        for isl in sorted(islands, key=lambda i: -i["rect"][3]):
            x0, y0, x1, y1 = isl["rect"]
            if (x1 - x0) >= span and (y1 - y0) >= PAD_D + span_extra and \
                    tuple(isl["rect"]) not in used:
                cx0 = (x0 + x1) / 2 - (len(nets) - 1) * pitch / 2
                cy = (y0 + y1) / 2
                ok = True
                rr = []
                for j, n in enumerate(nets):
                    r = base.Rect(cx0 + j * pitch - PAD_D / 2, cy - PAD_D / 2,
                                  cx0 + j * pitch + PAD_D / 2, cy + PAD_D / 2)
                    if not field.free(r, extra=0.15):
                        ok = False
                        break
                    rr.append((cx0 + j * pitch, cy))
                if ok:
                    used.add(tuple(isl["rect"]))
                    tier = {"lane": isl["rect"], "pads": rr, "nets": nets}
                    break
        tiers[tag] = tier

    placed = []
    for tag, tier in tiers.items():
        if tier is None:
            field.skipped.append({"what": f"tier {tag} not placeable on coupon"})
            continue
        lane_y = tier["pads"][0][1]
        for (x, y), n in zip(tier["pads"], tier["nets"]):
            ref = f"P{n}"
            fp = field.pad(b, ref, x, y, PAD_D, PAD_D, n, circle_=True)
            if fp is None:
                placed.append((x, y, n, None, ref))
                continue
            # TP apron lives in the bottom_ext region, south of the rails;
            # jog candidates dodge the OTHER tier when crossing it
            done = None
            apron_y = brect[3] - cp_edge(par) - TP_SIZE / 2
            for row in (apron_y, apron_y - 3.4):
                for jog in (0.0, -1.2, 1.2, -2.4, 2.4, -3.6, 3.6, -5.4, 5.4,
                            7.2, -7.2):
                    tx = x + jog
                    ty = row
                    fpk = field.pad(b, f"TP{n}", tx, ty, TP_SIZE, TP_SIZE, n,
                                    quiet=True)
                    if fpk is not None and field.route_vhv(
                            b, (x, y + PAD_D / 2), tx, (y + row) / 2,
                            (tx, ty), n, ignore={ref, f"TP{n}"}):
                        done = (tx, ty)
                        break
                    if fpk is not None:
                        try:
                            b.Remove(fpk)
                        except Exception:
                            pass
                        field.obs = [o for o in field.obs if o["tag"] != f"TP{n}"]
                if done:
                    break
                if fpk is not None:
                    try:
                        b.Remove(fpk)
                    except Exception:
                        pass
                    field.obs = [o for o in field.obs if o["tag"] != f"TP{n}"]
            placed.append((x, y, n, done, ref))

    text(b, brect[0] + 2, brect[1] + 3,
         "COUPON A': aggregated 19-contact undersprings target - 2 tier rails "
         "(15 SIG + 4 GND-class) per connector-next study; pads dia 2.5 mm")
    text(b, brect[0] + 2, brect[3] - 2,
         "DRAFT - no ERC; TP=SMD on B.Cu; unprobed pads listed as skips")
    skips = [s for s in field.skipped] + [
        {"what": f"TP for {n}", "at": [round(x, 1), round(y, 1)]}
        for x, y, n, done_, r in placed if done_ is None]
    return {"name": "coupon_agg19", "board": b, "brect": brect,
            "pads_placed": len(placed), "pads_probed": sum(1 for *_, d, r in placed if d),
            "skipped": skips}


# ---------------------------------------------------------- coupon B: mezz20
def coupon_mezz20(study_out):
    par = base.Params()
    ext = (study_out.get("mezzanine", {}).get("gecko_pair20_THT", {})
           .get("min_bottom_extension_mm"))
    ext = ext or 0.0
    par2 = base.replace(par, rows=2, cols=4, bottom_ext=ext)
    tile = base.Tile(par2, base.parse_kicad_mod(base.VENDORED_FP), "rect",
                     base.parse_kicad_mod(base.VENDORED_FP_TRIM))
    dx = -min(q[0] for q in tile.outline)
    dy = -min(q[1] for q in tile.outline)
    tile.outline = [(x + dx, y + dy) for x, y in tile.outline]
    tile.centre = {k: (x + dx, y + dy) for k, (x, y) in tile.centre.items()}
    if hasattr(tile, "_obs_cache"):
        del tile._obs_cache

    b = new_board()
    try:
        b.GetDesignSettings().m_CopperEdgeClearance = MM(0.4)
    except Exception:
        pass
    xs = [q[0] for q in tile.outline]
    ys = [q[1] for q in tile.outline]
    brect = (min(xs), min(ys), max(xs), max(ys))
    edge_rect(b, brect)
    for (i, k), (x, y) in sorted(tile.centre.items()):
        name = ("SW_Hotswap_Kailh_MX_1.00u_EdgeTrim"
                if tile.pad_variant.get((i, k)) == "edgetrim"
                else "SW_Hotswap_Kailh_MX_1.00u")
        fp = pcbnew.FootprintLoad(FP_REPO, name)
        fp.SetReference(f"SW{i}{k}")
        b.Add(fp)
        fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))

    mezz = json.load(open(os.path.join(OUT, "mezz_next.json")))
    info = mezz["gecko_mv20"]
    cb = info["courtyard_bbox_fpside"]
    tw, th = cb["x1"] - cb["x0"], cb["y1"] - cb["y0"]
    cx = (brect[0] + brect[2]) / 2
    cy = brect[3] - th / 2 - 0.8
    _f2 = Field()
    for o in tile.obstacles():
        bb = o["bbox"]
        _f2.add(base.Rect(bb.x0 - o["clr"], bb.y0 - o["clr"],
                          bb.x1 + o["clr"], bb.y1 + o["clr"]), f"o:{o['tag']}")
    placed_y = None
    scan = brect[3] - th / 2 - 0.8
    while scan > brect[1] + th / 2 + 1.0:
        r = base.Rect(cx - tw / 2, scan - th / 2, cx + tw / 2, scan + th / 2)
        if _f2.free(r, extra=0.5):
            placed_y = scan
            break
        scan -= 0.25
    if placed_y is None:
        raise RuntimeError("coupon_mezz20: no collision-free courtyard position")
    cy = placed_y
    libdir = os.path.join(FP_STOCK, "Connector_Harwin.pretty")
    fp = pcbnew.FootprintLoad(libdir, info["name"])
    if fp is None:
        raise RuntimeError("gecko footprint load failed")
    fp.SetReference("J1")
    fp.SetValue("G125-MVX2005L0X (tile plug, THT tails)")
    b.Add(fp)                       # Add before flip (orphan flip segfaults)
    fp.SetPosition(pcbnew.VECTOR2I(MM(cx), MM(cy)))
    fp.SetLayerAndFlip(pcbnew.B_Cu) # plug lives on the tile underside
    # nets: assign the aggregated schedule to the 20 pads (documented schedule)
    order19 = cnext.TIER_S + cnext.TIER_G
    netmap = {str(i + 1): order19[i] for i in range(19)}
    netmap["20"] = "GND"
    padpos = {}
    for p in fp.Pads():
        if p.GetNumber():
            p.SetNet(net(b, f"J1.{netmap.get(p.GetNumber(), 'NC')}:{p.GetNumber()}"))
            pos = p.GetPosition()
            padpos[p.GetNumber()] = (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y))
    # corner pads probed OUTWARD from their own row (direction derived from
    # the measured pad cloud, never assumed); skipped if no clean TP window
    field = Field()
    rows = {}
    for pn, (px, py) in padpos.items():
        rows.setdefault(round(py, 2), []).append(px)
    skipped_probe = []
    for pn in ("1", "10", "11", "20"):
        if pn not in padpos:
            continue
        px, py = padpos[pn]
        rx = sorted(rows[round(py, 2)])
        # outward = away from the row's pad span, along the row axis
        side = -1 if px <= (rx[0] + rx[-1]) / 2 else 1
        edge_x = rx[0] if side < 0 else rx[-1]
        nn = f"J1.{netmap.get(pn, 'NC')}:{pn}"
        done = False
        for hop in (2.2, 3.2, 4.2, 5.2):
            tpx = edge_x + side * hop
            fpk = field.tp(b, f"TP_P{pn}", tpx, py, nn)
            if fpk is not None:
                track(b, (px, py), (tpx, py), nn)
                field.add(base.Rect(min(px, tpx) - 0.2, py - 0.2,
                                    max(px, tpx) + 0.2, py + 0.2), f"trk {pn}")
                done = True
                break
        if not done:
            skipped_probe.append({"what": f"probe TP_P{pn}"})
    text(b, brect[0] + 2, brect[1] + 3,
         f"COUPON B': Gecko-20 mezzanine plug (THT tails, in production), "
         f"ISOLATED-tile certified south tab +{ext} mm; corner pads probed")
    text(b, brect[0] + 2, brect[3] - 2,
         "DRAFT - no ERC; branch judged NOFIT at placement level by the study "
         "(shrunk-board drill/pad clearance fails) - concept geometry only")
    return {"name": "coupon_mezz20", "board": b, "brect": brect,
            "tab_mm": ext, "skipped": skipped_probe}


# ------------------------------------------------------ coupon C: backplane
def coupon_backplane(study_out):
    """3-slot L section of the passive backplane; dedicated detect stubs."""
    par = base.Params()
    P, R = par.P(), par.R()
    tier_g = study_out["tiers"]["GND"]
    tier_s = study_out["tiers"]["SIG"]
    # pad plans relative to ONE common origin (both tiers together) so the
    # study's tier separation survives into the coupon
    _all = tier_g["pads"] + tier_s["pads"]
    _cx = sum(p["x"] for p in _all) / len(_all)
    _cy = sum(p["y"] for p in _all) / len(_all)
    plans = [(p["x"] - _cx, p["y"] - _cy, p["net"]) for p in _all]

    b = new_board()
    try:
        b.GetDesignSettings().m_CopperEdgeClearance = MM(0.4)
    except Exception:
        pass
    field = Field()
    # slot origins: S=(0,0); up=(P/2,-3R); right=(4P,0)
    slots = {"S": (0.0, 0.0), "A": (P / 2, -3 * R), "R": (4 * P, 0.0)}
    outline_pts = []
    seatxy = {}
    seatref = {}

    # backplane net naming: detect pads on a shared boundary form ONE net
    # (the budget.py boundary unions); every other seat keeps its slot net
    STUBS = [("A", "GND_DET_B", "S", "T_endcol"),
             ("S", "GND_DET_T", "A", "B_first"),
             ("S", "GND_DET_R", "R", "L_endrow")]
    stub_net_of = {}
    for (ss_, sn, ds_, dn) in STUBS:
        nn = f"STUBDET.{ss_}.{sn}>{ds_}.{dn}"
        stub_net_of[(ss_, sn)] = nn
        stub_net_of[(ds_, dn)] = nn

    def seatnet(sname, n):
        return stub_net_of.get((sname, n), f"S{sname}.{n}")
    for sname, (ox, oy) in slots.items():
        for k, (px, py, n) in enumerate(plans):
            x, y = ox + px, oy + py
            netname = seatnet(sname, n)
            fp = field.pad(b, f"P{sname}{k}", x, y, SEAT_W, SEAT_H, netname)
            if fp is not None:
                seatxy[(sname, n)] = (x, y)
                seatref[(sname, n)] = f"P{sname}{k}"
        outline_pts += [(ox + px, oy + py) for px, py, _ in plans]

    # board outline = convex hull of all seat circles + margin
    xs = [q[0] for q in outline_pts]
    ys = [q[1] for q in outline_pts]
    bx = (min(xs) - 9, min(ys) - 9, max(xs) + 9, max(ys) + 9)
    edge_rect(b, bx)
    field.edge_poly = [(bx[0], bx[1]), (bx[1] is None and 0 or bx[2], bx[1]),
                       (bx[2], bx[3]), (bx[0], bx[3])]
    field.edge_poly = [(bx[0], bx[1]), (bx[2], bx[1]),
                       (bx[2], bx[3]), (bx[0], bx[3])]

    # test points: every seat net gets a TP EXCEPT the stub endpoints: those
    # are connected through the stub wire itself (no per-pad TP -> nothing
    # crowds the escape corridors); detect stubs additionally get wire TPs
    probed = 0
    stubbed_pads = set(stub_net_of)
    for sname, (ox, oy) in slots.items():
        for k, (px, py, n) in enumerate(plans):
            if (sname, n) in stubbed_pads:
                continue
            x, y = ox + px, oy + py
            nn = seatnet(sname, n) if (sname, n) in seatxy else None
            if nn is None:
                continue
            done = False
            for tdy in (3.9, 5.2, 6.5, 8.0, 10.0, 12.0, -3.9, -5.2, -6.5, -8.0,
                        -10.0, -12.0):
                for tdx in (0.0, 1.2, -1.2, 2.4, -2.4, 4.0, -4.0):
                    tx, ty = x + tdx, y + tdy
                    fpk = field.pad(b, f"TP{sname}{n}", tx, ty, TP_SIZE, TP_SIZE,
                                    nn, quiet=True)
                    if fpk is not None and field.route_vhv(
                            b, (x, y + PAD_D / 2 if ty > y else y - PAD_D / 2),
                            tx, (y + ty) / 2, (tx, ty), nn,
                            ignore={f"TP{sname}{n}", f"P{sname}{k}"}):
                        done = True
                        break
                    if fpk is not None:
                        try:
                            b.Remove(fpk)
                        except Exception:
                            pass
                        field.obs = [o for o in field.obs
                                     if o["tag"] != f"TP{sname}{n}"]
                if done:
                    break
            probed += int(done)
            if not done:
                field.skipped.append({"what": f"TP {sname}.{n}",
                                      "at": [round(x, 1), round(y, 1)]})
    # detective stubs (budget.py graph semantics):
    #   S slot GND_DET_T -> slot-above B_first ; here S is BELOW A means:
    #   A.GND_DET_B -> S.T_endcol ; S.GND_DET_T -> A.B_first ;
    #   S.GND_DET_R -> R.L_endrow
    stubs = [("A", "GND_DET_B", "S", "T_endcol"),
             ("S", "GND_DET_T", "A", "B_first"),
             ("S", "GND_DET_R", "R", "L_endrow")]
    stub_traces = []
    for src_s, src_n, dst_s, dst_n in stubs:
        a = seatxy.get((src_s, src_n))
        c = seatxy.get((dst_s, dst_n))
        if not a or not c:
            field.skipped.append({"what": f"stub {src_s}.{src_n}->{dst_s}.{dst_n}",
                                  "why": "seat missing"})
            continue
        # honest router: collision-check every segment before commit; try
        # direct V-H-V offsets first, then escape-Z templates that leave the
        # pad carpets via the free inter-slot corridors; if nothing works the
        # stub is recorded UNROUTED (never forced)
        w = TRACK_W / 2
        refs = {seatref.get((src_s, src_n), "-"), seatref.get((dst_s, dst_n), "-")}
        all_x = [q[0] for q in seatxy.values()]
        all_y = [q[1] for q in seatxy.values()]
        xe = max(all_x) + 4.5
        xw = min(all_x) - 4.5

        def templates():
            for off in (0.0, 1.4, -1.4, 2.8, -2.8, 4.2, -4.2, 6.0, -6.0,
                        8.0, -8.0, 12.0, -12.0, 16.0, -16.0, 24.0, -24.0):
                vy = (a[1] + c[1]) / 2 + off
                yield [a, (a[0], vy), (c[0], vy), c]
            for esc in (3.0, 5.0, 8.0, 12.0):
                for sa in (1, -1):
                    ye = a[1] + sa * esc
                    for xt in (xe, xw, (a[0] + c[0]) / 2):
                        for hop in (3.0, 5.0, 8.0):
                            for sc in (1, -1):
                                ym2 = c[1] + sc * hop
                                yield [a, (a[0], ye), (xt, ye), (xt, ym2),
                                       (c[0], ym2), c]

        routed = None
        for pts in templates():
            segs = []
            okall = True
            for u, v in zip(pts, pts[1:]):
                if abs(u[0] - v[0]) < 1e-9 and abs(u[1] - v[1]) < 1e-9:
                    continue
                r = base.Rect(min(u[0], v[0]) - w, min(u[1], v[1]) - w,
                              max(u[0], v[0]) + w, max(u[1], v[1]) + w)
                if not field.free(r, extra=0.15, ignore=refs):
                    okall = False
                    break
                segs.append((u, v, r))
            if okall:
                for u, v, r in segs:
                    track(b, u, v, stub_net_of[(src_s, src_n)])
                    field.add(r, f"trk stub {src_s}.{src_n}")
                routed = pts
                break
        stub_traces.append({"from": f"{src_s}.{src_n}", "to": f"{dst_s}.{dst_n}",
                            "net_on_backplane": stub_net_of[(src_s, src_n)],
                            "bonded_through_removable_tile": True,
                            "routed": routed is not None})


    for st in stub_traces:
        a = seatxy.get(tuple(st["from"].split(".")))
        c5 = st["from"].split(".")
        own_ref = seatref.get((c5[0], c5[1]), f"P{c5[0]}?")
        if a:
            placed_tp = None
            for oxx, oyy in ((3.2, -4.6), (-3.2, -4.6), (6.4, -4.6), (0.0, -6.6),
                             (3.2, 4.6), (-3.2, 4.6), (8.0, -4.6), (-8.0, -4.6),
                             (11.0, -4.6), (-11.0, -4.6), (14.0, -4.6),
                             (-14.0, -4.6), (8.0, 4.6), (-8.0, 4.6),
                             (11.0, 4.6), (-11.0, 4.6)):
                fpk = field.pad(b, f"TPD{st['from']}", a[0] + oxx, a[1] + oyy,
                                TP_SIZE, TP_SIZE,
                                seatnet(*tuple(st["from"].split("."))),
                                quiet=True)
                _same_stub_trk = f"trk stub {c5[0]}.{c5[1]}"
                if fpk is not None and field.route_vhv(
                        b, (a[0], a[1] - PAD_D / 2), a[0] + oxx,
                        a[1] + oyy / 2, (a[0] + oxx, a[1] + oyy),
                        seatnet(*tuple(st["from"].split("."))),
                        ignore={f"TPD{st['from']}", own_ref, _same_stub_trk}):
                    placed_tp = True
                    break
                if fpk is not None:
                    try:
                        b.Remove(fpk)
                    except Exception:
                        pass
                    field.obs = [o for o in field.obs
                                 if o["tag"] != f"TPD{st['from']}"]
            if not placed_tp:
                field.skipped.append({"what": f"detect-TP {st['from']}"})

    text(b, bx[0] + 2, bx[1] + 3,
         "COUPON C': passive backplane slot section (3 slots, L): 19 spring "
         "seats per slot; DEDICATED detect-GND stubs per boundary - bonded to "
         "GND only through the removable tile (never the backplane plane)")
    text(b, bx[0] + 2, bx[3] - 2,
         "DRAFT - no ERC; seat pads dia 2.5 mm; TP=SMD on B.Cu")
    return {"name": "coupon_backplane", "board": b, "brect": bx,
            "stub_traces": stub_traces, "probed": probed,
            "seats": len(seatxy), "skipped": field.skipped}


def save(cp):
    os.makedirs(COUT, exist_ok=True)
    path = os.path.join(COUT, f"{cp['name']}.kicad_pcb")
    cp["board"].Save(path)
    rules = {"max_error": 0.005, "min_clearance": 0.2, "min_connection": 0.2,
             "min_copper_edge_clearance": 0.4, "min_groove_width": 0.0,
             "min_hole_clearance": 0.25, "min_hole_to_hole": 0.25,
             "min_microvia_diameter": 0.2, "min_microvia_drill": 0.1,
             "min_resolved_spokes": 1, "min_silk_clearance": 0.0,
             "min_text_height": 0.8, "min_text_thickness": 0.08,
             "min_through_hole_diameter": 0.3, "min_track_width": 0.15,
             "min_via_annular_width": 0.15, "min_via_diameter": 0.6,
             "solder_mask_to_copper_clearance": 0.0,
             "use_height_for_length_calcs": True}
    pro = {"board": {"design_settings": {"defaults": {},
                                         "diff_pair_dimensions": [],
                                         "rules": rules},
                     "layer_presets": []},
           "meta": {"filename": f"{cp['name']}.kicad_pro", "version": 1},
           "sheets": []}
    json.dump(pro, open(os.path.join(COUT, f"{cp['name']}.kicad_pro"), "w"))
    return path


def main():
    os.makedirs(COUT, exist_ok=True)
    study_out = json.load(open(os.path.join(OUT, "study.json")))
    out = {}
    for cp in (coupon_agg19(study_out), coupon_mezz20(study_out),
               coupon_backplane(study_out)):
        path = save(cp)
        x0, y0, x1, y1 = cp["brect"]
        out[cp["name"]] = {k: v for k, v in cp.items() if k not in ("board",)}
        out[cp["name"]]["file"] = os.path.relpath(path, ROOT)
        out[cp["name"]]["outline_mm"] = [round(x1 - x0, 2), round(y1 - y0, 2)]
        out[cp["name"]]["footprints"] = len(list(cp["board"].GetFootprints()))
        out[cp["name"]]["tracks"] = len(list(cp["board"].GetTracks()))
        print(f"{cp['name']}: {x1 - x0:.1f} x {y1 - y0:.1f} mm, "
              f"fp={out[cp['name']]['footprints']}, "
              f"trk={out[cp['name']]['tracks']}, skip={len(cp['skipped'])}")
    json.dump(out, open(os.path.join(COUT, "coupons.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
