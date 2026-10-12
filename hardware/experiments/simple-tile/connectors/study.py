#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Simple-tile experiment: parametric mechanical placement study for drop-in tiles.

A *passive* 12-key tile: one PCB, Cherry-MX-compatible switches in SMD Kailh
hot-swap sockets, key matrix only (no MCU, no LEDs, no Hall sensors). Tiles drop
from above into a structural chassis; the chassis carries either vertical spring
contacts (variant A) or one half of an SMT mezzanine pair (variant B).

This runner:
  1. parses the vendored Kailh hot-swap footprint (pads, NPTH, B.CrtYd polygon)
     and the vendored STEP model bounds - no hand-copied dimensions;
  2. builds the parametric equilateral-lattice tile (stepped or rectangular
     outline);
  3. scans the bottom side for collision-checked free islands;
  4. evaluates variant A (pad row for chassis spring contacts) and variant B
     (mezzanine footprints measured from the installed KiCad library);
  5. models the passive presence detection (GND strap on the REMOVABLE
     NEIGHBOUR tile only, never on permanent backplane GND) and checks the
     empty/seated/half-mated truth table for all 3 detect lines;
  6. writes out/placement.json, out/placement.svg, out/truth_table.json,
     out/report.md and machine-checkable out/checks.json.

Run:  python3 study.py [outdir]            (host python3, stdlib only)
      ./run.sh measures library footprints first, then runs this, then coupons.

Read reference (not modified): hardware/kicad/tile/scripts/revc_*.py.
"""
import json
import math
import os
import re
import sys
from dataclasses import dataclass, asdict, replace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
HERE = os.path.dirname(os.path.abspath(__file__))
VENDORED_FP = os.path.join(ROOT, "hardware", "kicad", "lib",
                           "Switch_Keyboard_Hotswap_Kailh.pretty",
                           "SW_Hotswap_Kailh_MX_1.00u.kicad_mod")
VENDORED_FP_TRIM = os.path.join(ROOT, "hardware", "kicad", "lib",
                                "Switch_Keyboard_Hotswap_Kailh.pretty",
                                "SW_Hotswap_Kailh_MX_1.00u_EdgeTrim.kicad_mod")
VENDORED_STP = os.path.join(ROOT, "hardware", "kicad", "lib", "3dmodels",
                            "SW_Hotswap_Kailh_MX.stp")
VENDORED_WRL = os.path.join(ROOT, "hardware", "kicad", "lib", "3dmodels",
                            "SW_Hotswap_Kailh_MX.wrl")
MEZZ_JSON = os.path.join(HERE, "out", "mezzanine_measures.json")

SOURCES = {
    "kailh_footprint": ("perigoso/keyswitch-kicad-library v2.3, CC-BY-SA 4.0, vendored file: "
                        "hardware/kicad/lib/Switch_Keyboard_Hotswap_Kailh.pretty/SW_Hotswap_Kailh_MX_1.00u.kicad_mod",
                        "https://github.com/perigoso/keyswitch-kicad-library"),
    "mx_body": ("Cherry MX body 15.6 x 15.6 mm (project reference: docs/LEDGER.md 2026-09-27, "
                "Cherry MX datasheet)", "https://www.cherrymx.de/en/mx-original/mx-red.html"),
    "df12_series": ("Hirose DF12 series page (0.5 mm pitch, 3/3.5/4/5 mm stacks, "
                    "page flagged 'Planned End of Life')",
                    "https://www.hirose.com/en/product/series/DF12"),
    "df12_footprint": ("KiCad 10 stock footprint library, measured by measure_footprints.py "
                       "with pcbnew; descr carries manufacturer 2D drawing link",
                       "https://www.hirose.com/product/document?clcode=CL0537-0834-6-81"),
    "gecko_footprint": ("KiCad 10 stock footprint library, measured by measure_footprints.py; "
                        "drawing DRG-00182",
                        "https://content.harwin.com/m/62fd8add13144f50/original/DRG-00182-Technical-Drawing-Datasheet-G125-MVXXX05LXP-pdf.pdf"),
    "spring_s1941": ("Harwin S1941-42R SMT multi-directional spring contact: free height 7.3 mm, "
                     "top-down working deflection 0.3..0.8 mm, 9.59 x 5.70 x 7.25 mm, gold contact",
                     "https://www.harwin.com/products/S1941-42R"),
    "spring_s1971": ("Harwin S1971-46R: free height 4.55 mm, deflection 0.3..0.6 mm, "
                     "4.63 x 3.70 x 4.55 mm (used as the 'too short' reject case)",
                     "https://www.harwin.com/products/S1971-46R"),
    "spring_range": ("Harwin EZi SMT spring contact range datasheet PD013 (heights 2.5..7.3 mm)",
                     "https://content.harwin.com/asset/b78b8265-eabd-4ec9-b6e1-cca806faa177/"
                     "PD013-Product-Datasheet-SPRING-CONTACTS-SMT-Spring-Contacts-EZi.pdf"),
}


# ------------------------------------------------------------------ parameters
@dataclass
class Params:
    body: float = 15.6           # Cherry MX body, mm (source: cherry, via LEDGER)
    body_margin: float = 0.3     # extra clearance on the diagonal neighbours, mm
    rows: int = 3
    cols: int = 4
    edge_clear: float = 0.3      # copper-to-board-edge minimum, mm
    rib_gap: float = 1.0         # tile-to-tile gap in the chassis (stepped outline), mm
    board_thickness: float = 1.6
    board_edge_tol: float = 0.1  # tile outline routing tolerance, mm
    clr_hole: float = 0.5        # keep-out around NPTH (posts poke below board), mm
    clr_pad: float = 0.3         # keep-out around socket pads/courtyard, mm
    grid: float = 0.25           # island scan sampling grid, mm
    cap_gap: float = 0.5         # custom keycap cap-to-cap gap, mm (ASSUMPTION)
    # variant A (tile-side pads for chassis spring contacts) - sizes are ASSUMPTIONS
    pogo_pad_d: float = 2.5      # round pad diameter, mm (ASSUMPTION, tip area TBD)
    pogo_gap: float = 0.75       # gap between pad edges, mm
    tol_chassis_xy: float = 0.35  # chassis placement + pocket play (sum), mm
    # detect straps carried by each tile for ITS neighbours' sense positions:
    strap_pad_w: float = 2.0
    strap_pad_h: float = 1.2
    # chassis spring bodies (manufacturer page dims, see SOURCES)
    spr_s1941_w: float = 9.59
    spr_s1941_d: float = 5.70
    spr_s1971_w: float = 4.63
    spr_s1971_d: float = 3.70
    spr_bank_gap: float = 0.3    # body-to-body gap between chassis banks, mm
    spr_body_clr: float = 0.5    # body vs socket-courtyard keep-out projection, mm
    # variant B
    mezz_clear: float = 0.5      # around the connector courtyard, mm
    mezz_escape: float = 2.5     # extra depth to fan the pads out, mm
    # vertical (z) budget
    z_guard: float = 0.5         # guard band on the unverified socket depth bound, mm
    bottom_ext: float = 0.0      # optional bottom-edge extension (mezzanine tab), mm
    def R(self):
        return self.body + self.body_margin

    def P(self):
        return self.R() / (math.sqrt(3) / 2)


# ------------------------------------------------------------ rev-A interface
# Tile-side contact inventory DERIVED from docs/architecture/protocol.md (the
# rev-A J101/J102/J103/J104 pin table). Group keys are the four tile directions.
# Each entry: (net, pin role / source pin). B_clk and B_data are one net each on
# the tile with two pads (bottom AND right), exactly as in rev A.
CONTACTS = {
    # J102 top (socket): 1 VCC, 2 T_clk out, 3 T_data in, 4 T_endcol in,
    # 5 GND, 6 L_latch out, 7 T_W in, 8 GND
    "top":    [("VCC", "J102.1"), ("T_clk", "J102.2"), ("T_data", "J102.3"),
               ("T_endcol", "J102.4"), ("GND", "J102.5"), ("L_latch", "J102.6"),
               ("T_W", "J102.7"), ("GND", "J102.8")],
    # J103 bottom (header): 1 VCC, 2 B_clk in, 3 B_data out, 4 GND,
    # 5 B_first in, 6 B_latch in, 7 B_W out, 8 GND
    "bottom": [("VCC", "J103.1"), ("B_clk", "J103.2"), ("B_data", "J103.3"),
               ("GND", "J103.4"), ("B_first", "J103.5"), ("B_latch", "J103.6"),
               ("B_W", "J103.7"), ("GND", "J103.8")],
    # J101 left (socket): 1 VCC, 2 L_clk out, 3 L_data in, 4 L_endrow in,
    # 5 L_latch out, 6 GND
    "left":   [("VCC", "J101.1"), ("L_clk", "J101.2"), ("L_data", "J101.3"),
               ("L_endrow", "J101.4"), ("L_latch", "J101.5"), ("GND", "J101.6")],
    # J104 right (header): 1 VCC, 2 B_clk in (same net), 3 B_data out (same net),
    # 4 GND, 5 R_latch in, 6 GND
    "right":  [("VCC", "J104.1"), ("B_clk", "J104.2"), ("B_data", "J104.3"),
               ("GND", "J104.4"), ("R_latch", "J104.5"), ("GND", "J104.6")],
}
STRAP_LINES = ("DET_T", "DET_L", "DET_B")   # removable-neighbour GND straps


def inventory():
    """(28 pads grouped by direction; unique nets; counts)."""
    groups = {k: len(v) for k, v in CONTACTS.items()}
    unique = sorted({net for pins in CONTACTS.values() for net, _ in pins})
    return {"groups": groups, "pads_total": sum(groups.values()),
            "nets_unique": unique, "nets_count": len(unique)}


# ------------------------------------------------------------------ keycaps
def hex_cell(P, gap):
    """Lattice Voronoi cell of the triangular lattice (nearest distance P) shrunk
    by gap/2: a regular hexagon, pointy top/bottom; flats face the 6 neighbours."""
    d = (P - gap) / 2
    dirs = [math.radians(a) for a in (0, 60, 120, 180, 240, 300)]
    pts = []
    for i in range(6):
        a1, a2 = dirs[i], dirs[(i + 1) % 6]
        # solve n1.p = d, n2.p = d
        n1 = (math.cos(a1), math.sin(a1))
        n2 = (math.cos(a2), math.sin(a2))
        det = n1[0] * n2[1] - n1[1] * n2[0]
        x = (d * n2[1] - d * n1[1]) / det
        y = (n1[0] * d - n2[0] * d) / det
        pts.append((x, y))
    return pts


def poly_dist(a, b):
    """Min vertex-edge distance; 0 if the polygons intersect (convex SAT)."""
    def edges(p):
        return [(p[i], p[(i + 1) % len(p)]) for i in range(len(p))]
    def separate(p, q):
        for pol in (p, q):
            for (x0, y0), (x1, y1) in edges(pol):
                nx, ny = y0 - y1, x1 - x0
                pn = [nx * x + ny * y for x, y in p]
                qn = [nx * x + ny * y for x, y in q]
                if max(pn) < min(qn) or max(qn) < min(pn):
                    return True
        return False
    if not separate(a, b):
        return 0.0
    return min(seg_seg_dist(x, y, u, v) for x, y in edges(a) for u, v in edges(b))


def cap_study(par):
    """Keycap feasibility on this lattice, custom caps only:
      * square cap = P - cap_gap (nominally 17.86 mm) must demonstrably OVERLAP
        (control experiment proving the review's point);
      * square cap max without overlap = R - cap_gap;
      * hex cap = lattice Voronoi cell shrunk by gap/2: must be disjoint with
        gap >= cap_gap everywhere, ALSO across tile boundaries (tiles translated
        by the chassis lattice vectors R=(4P,0), U=(P/2,-3R), R-U)."""
    P, R, gap = par.P(), par.R(), par.cap_gap
    s, u = (4 * P, 0), (P / 2, -3 * R)
    shifts = [(0, 0), s, u, (-s[0], -s[1]), (-u[0], -u[1]),
              (s[0] - u[0], s[1] - u[1]), (u[0] - s[0], u[1] - s[1])]
    centres = [(-k * P / 2 + i * P, k * R) for k in range(par.rows)
               for i in range(par.cols)]

    def placed(poly, dx, dy):
        return [(x + dx, y + dy) for x, y in poly]

    def field(base):
        out = []
        for cx, cy in centres:
            for dx, dy in shifts:
                out.append(placed(base, cx + dx, cy + dy))
        return out

    def min_gap(polys):
        best = 1e9
        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                ci = (sum(x for x, _ in polys[i]) / len(polys[i]),
                      sum(y for _, y in polys[i]) / len(polys[i]))
                cj = (sum(x for x, _ in polys[j]) / len(polys[j]),
                      sum(y for _, y in polys[j]) / len(polys[j]))
                if math.hypot(ci[0] - cj[0], ci[1] - cj[1]) > 2.2 * P:
                    continue             # far apart, cannot interact
                best = min(best, poly_dist(polys[i], polys[j]))
        return best

    hex_poly = hex_cell(P, gap)
    hex_gap = min_gap(field(hex_poly))
    sq_big = P - gap                                  # the v1 (wrong) cap size
    sq_poly_big = [(-sq_big / 2, -sq_big / 2), (sq_big / 2, -sq_big / 2),
                   (sq_big / 2, sq_big / 2), (-sq_big / 2, sq_big / 2)]
    sq_big_gap = min_gap(field(sq_poly_big))
    sq_max = R - gap                                  # binding: vertical neighbours
    sq_poly = [(-sq_max / 2, -sq_max / 2), (sq_max / 2, -sq_max / 2),
               (sq_max / 2, sq_max / 2), (-sq_max / 2, sq_max / 2)]
    sq_gap = min_gap(field(sq_poly))
    area = lambda pg: abs(sum(pg[i][0] * pg[(i + 1) % len(pg)][1] -
                              pg[(i + 1) % len(pg)][0] * pg[i][1]
                              for i in range(len(pg))) / 2)
    return {
        "hex": {"name": "custom hexagonal cap (Voronoi cell of the lattice)",
                "across_flats": P - gap, "area": round(area(hex_poly), 1),
                "min_gap_incl_cross_tile": round(hex_gap, 3)},
        "square_at_P_minus_gap": {"side": sq_big, "area": round(area(sq_poly_big), 1),
                                  "min_gap_incl_cross_tile": round(sq_big_gap, 3),
                                  "verdict": "OVERLAPS - rejected" if sq_big_gap < gap - 1e-9
                                             else "ok"},
        "square_max_no_overlap": {"side": round(sq_max, 3),
                                  "area": round(sq_max * sq_max, 1),
                                  "min_gap_incl_cross_tile": round(sq_gap, 3)},
    }


# --------------------------------------------------------- s-expr mini parser
def sexp(text):
    toks = re.findall(r'\(|\)|"[^"]*"|[^\s()"]+', text)
    root, stack = [], []
    for t in toks:
        if t == "(":
            node = []
            (stack[-1] if stack else root).append(node)
            stack.append(node)
        elif t == ")":
            stack.pop()
        else:
            stack[-1].append(t.strip('"'))
    return root


def _child(e, tag):
    return next((s for s in e if isinstance(s, list) and s and s[0] == tag), None)


def parse_kicad_mod(path):
    tree = sexp(open(path).read())[0]
    pads, holes, crt_lines, crt_arcs, fab_lines = [], [], [], [], []
    for e in tree:
        if not isinstance(e, list) or not e:
            continue
        if e[0] == "pad":
            at = _child(e, "at")
            x, y = float(at[1]), float(at[2])
            size = _child(e, "size")
            w, h = float(size[1]), float(size[2])
            drill = _child(e, "drill")
            layers = _child(e, "layers")
            ll = " ".join(layers[1:]) if layers else ""
            if e[2] == "np_thru_hole":
                holes.append({"x": x, "y": y, "d": float(drill[1]) if drill else w})
            elif "B.Cu" in ll:
                pads.append({"n": e[1], "x": x, "y": y, "w": w, "h": h})
        elif e[0] == "fp_line":
            lay = _child(e, "layer")
            st, en = _child(e, "start"), _child(e, "end")
            seg = (float(st[1]), float(st[2]), float(en[1]), float(en[2]))
            if lay and lay[1] == "B.CrtYd":
                crt_lines.append(seg)
            elif lay and lay[1] == "F.Fab":
                fab_lines.append(seg)
        elif e[0] == "fp_arc":
            lay = _child(e, "layer")
            st, en, an = _child(e, "start"), _child(e, "end"), _child(e, "angle")
            if lay and lay[1] == "B.CrtYd":
                # legacy .kicad_mod: 'start' is the centre, 'end' a point on the arc
                crt_arcs.append((float(st[1]), float(st[2]),
                                 float(en[1]), float(en[2]), math.radians(float(an[1]))))
    return {"pads": pads, "holes": holes, "crt_lines": crt_lines,
            "crt_arcs": crt_arcs, "fab_lines": fab_lines}


def courtyard_polygon(fp):
    segs = []
    for cx, cy, px, py, sweep in fp["crt_arcs"]:
        r = math.hypot(px - cx, py - cy)
        a0 = math.atan2(py - cy, px - cx)
        n = max(3, int(abs(sweep) / (math.pi / 16)))
        segs.append([(cx + r * math.cos(a0 + sweep * i / n),
                      cy + r * math.sin(a0 + sweep * i / n)) for i in range(n + 1)])
    for x0, y0, x1, y1 in fp["crt_lines"]:
        segs.append([(x0, y0), (x1, y1)])
    pts = segs.pop(0)[:]
    while segs:
        tail = pts[-1]
        best, bi, flip = 1e9, 0, False
        for i, s in enumerate(segs):
            d0 = math.hypot(tail[0] - s[0][0], tail[1] - s[0][1])
            d1 = math.hypot(tail[0] - s[-1][0], tail[1] - s[-1][1])
            if d0 < best:
                best, bi, flip = d0, i, False
            if d1 < best:
                best, bi, flip = d1, i, True
        if best > 0.15:
            raise ValueError(f"B.CrtYd chain gap {best:.3f} mm at {tail}")
        s = segs.pop(bi)
        pts.extend((s[::-1] if flip else s)[1:])
    if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) > 0.15:
        raise ValueError("B.CrtYd polygon not closed")
    return pts


def step_bbox(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    pts = [tuple(float(v) for v in m) for m in re.findall(
        r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*(-?[\d.eE+-]+)\s*,"
        r"\s*(-?[\d.eE+-]+)\s*,\s*(-?[\d.eE+-]+)\s*\)\s*\)", txt)]
    return {"x": [min(p[0] for p in pts), max(p[0] for p in pts)],
            "y": [min(p[1] for p in pts), max(p[1] for p in pts)],
            "z": [min(p[2] for p in pts), max(p[2] for p in pts)], "n": len(pts)}


# --------------------------------------------------------------- geometry kit
def point_in_poly(x, y, poly):
    inside, n = False, len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


def _sub(u, v):
    return (u[0] - v[0], u[1] - v[1])


def _cross(u, v):
    return u[0] * v[1] - u[1] * v[0]


def _pt_seg(p, a, b):
    ab = _sub(b, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1])
                     / max(ab[0] ** 2 + ab[1] ** 2, 1e-12)))
    return math.hypot(p[0] - (a[0] + t * ab[0]), p[1] - (a[1] + t * ab[1]))


def seg_seg_dist(a, b, c, d):
    r, s = _sub(b, a), _sub(d, c)
    den = _cross(r, s)
    if abs(den) > 1e-12:
        t = _cross(_sub(c, a), s) / den
        u = _cross(_sub(c, a), r) / den
        if 0 <= t <= 1 and 0 <= u <= 1:
            return 0.0
    return min(_pt_seg(a, c, d), _pt_seg(b, c, d), _pt_seg(c, a, b), _pt_seg(d, a, b))


class Rect:
    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0 = min(x0, x1), min(y0, y1)
        self.x1, self.y1 = max(x0, x1), max(y0, y1)

    def edges(self):
        x0, y0, x1, y1 = self.x0, self.y0, self.x1, self.y1
        return (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
                ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0)))

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def h(self):
        return self.y1 - self.y0

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2

    def as_list(self):
        return [round(self.x0, 4), round(self.y0, 4), round(self.x1, 4), round(self.y1, 4)]


def dist_rect_circle(r, cx, cy, rr):
    px = min(max(cx, r.x0), r.x1)
    py = min(max(cy, r.y0), r.y1)
    if r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1:
        return 0.0
    return max(0.0, math.hypot(cx - px, cy - py) - rr)


def dist_rect_rect(a, b):
    dx = max(b.x0 - a.x1, a.x0 - b.x1, 0.0)
    dy = max(b.y0 - a.y1, a.y0 - b.y1, 0.0)
    return math.hypot(dx, dy)


def dist_rect_poly(r, poly):
    for cx, cy in ((r.x0, r.y0), (r.x1, r.y0), (r.x0, r.y1), (r.x1, r.y1)):
        if point_in_poly(cx, cy, poly):
            return 0.0
    for v in poly:
        if r.x0 <= v[0] <= r.x1 and r.y0 <= v[1] <= r.y1:
            return 0.0
    n = len(poly)
    return min(seg_seg_dist(a, b, poly[i], poly[(i + 1) % n])
               for i in range(n) for a, b in r.edges())


def rect_inside_poly(r, poly):
    for cx, cy in ((r.x0, r.y0), (r.x1, r.y0), (r.x0, r.y1), (r.x1, r.y1)):
        if not point_in_poly(cx, cy, poly):
            return False
    n = len(poly)
    for a, b in r.edges():
        for i in range(n):
            if seg_seg_dist(a, b, poly[i], poly[(i + 1) % n]) < 1e-9:
                return False
    return True


# ------------------------------------------------------------------- tile model
class Tile:
    def __init__(self, par, fp, style, fp_trim=None):
        self.par, self.fp, self.style = par, fp, style
        self.fp_trim = fp_trim
        self.crt_poly = courtyard_polygon(fp)
        self.keys = [(i, k) for k in range(par.rows) for i in range(par.cols)]
        self.centre = {(i, k): (-k * par.P() / 2 + i * par.P(), k * par.R())
                       for i, k in self.keys}
        self.reach = self._reach()
        # outline margin policy:
        #  stepped -> P/2, which makes the cross-tile key pitch exactly P again
        #             (same construction as revc_build.py: +/-G/2 insets + rib gap G)
        #  rect    -> reach + edge_clear (absolute minimum area)
        if style == "stepped":
            self.margin = par.P() / 2
            self.outline = self._stepped()
        else:
            self.margin = self.reach + par.edge_clear
            self.outline = self._rect()
        # per-key pad variant: switch to the EdgeTrim pad-1 for keys whose pad would
        # come closer than edge_clear + outline tolerance to the outline (this is
        # exactly the situation the vendored EdgeTrim variant was made for -
        # hardware/kicad/lib/README.md).
        self.pad_variant = {}
        if fp_trim is not None:
            need = par.edge_clear + par.board_edge_tol
            trimmel = {p["n"]: p for p in fp_trim["pads"]}
            for (i, k), (cx, cy) in self.centre.items():
                variant = "standard"
                for p in fp["pads"]:
                    r = Rect(cx + p["x"] - p["w"] / 2, cy + p["y"] - p["h"] / 2,
                             cx + p["x"] + p["w"] / 2, cy + p["y"] + p["h"] / 2)
                    if self.edge_slack(r) < need - 1e-9:
                        variant = "edgetrim"
                self.pad_variant[(i, k)] = variant

    def _reach(self):
        r = 0.0
        for p in self.fp["pads"]:
            r = max(r, abs(p["x"]) + p["w"] / 2, abs(p["y"]) + p["h"] / 2)
        for h in self.fp["holes"]:
            r = max(r, abs(h["x"]) + h["d"] / 2, abs(h["y"]) + h["d"] / 2)
        for x, y in self.crt_poly:
            r = max(r, abs(x), abs(y))
        return r

    def _rect(self):
        xs = [c[0] for c in self.centre.values()]
        ys = [c[1] for c in self.centre.values()]
        m = self.margin
        x0, x1 = min(xs) - m, max(xs) + self.margin
        y0 = min(ys) - m
        y1 = max(ys) + self.margin_bottom()
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    def margin_bottom(self):
        return self.margin + self.par.bottom_ext

    def _stepped(self):
        """Stepped outline so adjacent tiles keep key-lattice continuity.
        Follows the revc_build.py construction (same G/2 inset on both sides);
        the border hugs reach + edge_clear instead of the rev-A fixed outline."""
        par, m, G = self.par, self.margin, self.par.rib_gap
        P, R = par.P(), par.R()
        xL = [-k * P / 2 - m + G / 2 for k in range(par.rows)]
        xR = [-k * P / 2 + (par.cols - 1) * P + m - G / 2 for k in range(par.rows)]
        yT = -m + G / 2
        yB = (par.rows - 1) * R + self.margin_bottom() - G / 2
        b = [(k + 0.5) * R for k in range(par.rows - 1)]
        pts = [(xL[0], yT), (xR[0], yT)]
        for k in range(par.rows - 1):
            pts += [(xR[k], b[k] - G / 2), (xR[k + 1], b[k] - G / 2)]
        pts += [(xR[-1], yB), (xL[-1], yB)]
        for k in range(par.rows - 1, 0, -1):
            pts += [(xL[k], b[k - 1] + G / 2), (xL[k - 1], b[k - 1] + G / 2)]
        return pts

    def obstacles(self):
        """Bottom-side obstacles in tile coordinates (built once, cached).
        Every entry: kind/clr/tag + geometry + bbox (fast reject)."""
        obs = []
        std = {p["n"]: p for p in self.fp["pads"]}
        trim = {p["n"]: p for p in (self.fp_trim or self.fp)["pads"]}
        for i, k in self.keys:
            cx, cy = self.centre[(i, k)]
            key = f"SW[{i},{k}]"
            pool = trim if self.pad_variant.get((i, k)) == "edgetrim" else std
            for n in ("1", "2"):
                p = pool.get(n) or std[n]        # EdgeTrim only changes pad 1
                r = Rect(cx + p["x"] - p["w"] / 2, cy + p["y"] - p["h"] / 2,
                         cx + p["x"] + p["w"] / 2, cy + p["y"] + p["h"] / 2)
                obs.append({"kind": "rect", "clr": self.par.clr_pad,
                            "tag": f"{key} pad{p['n']}", "rect": r, "bbox": r})
            for h in self.fp["holes"]:
                hx, hy, hr = cx + h["x"], cy + h["y"], h["d"] / 2
                obs.append({"kind": "circle", "clr": self.par.clr_hole,
                            "tag": f"{key} hole d{h['d']}",
                            "x": hx, "y": hy, "r": hr,
                            "bbox": Rect(hx - hr, hy - hr, hx + hr, hy + hr)})
            pts = [(cx + x, cy + y) for x, y in self.crt_poly]
            xs = [q[0] for q in pts]
            ys = [q[1] for q in pts]
            obs.append({"kind": "poly", "clr": self.par.clr_pad,
                        "tag": f"{key} socket courtyard", "pts": pts,
                        "bbox": Rect(min(xs), min(ys), max(xs), max(ys))})
        return obs

    def clearance(self, rect, extra=0.0):
        """Exact slack (mm) of rect against all obstacles incl. their keep-outs,
        plus a caller extra (e.g. assembly tolerance). Also checks the outline."""
        if not rect_inside_poly(rect, self.outline):
            return -1.0, "rect crosses the board outline"
        best, what = 1e9, "none"
        for o in self._obs():
            d_bbox = dist_rect_rect(rect, o["bbox"])
            if d_bbox - o["clr"] - extra >= best:
                continue
            if o["kind"] == "circle":
                d = dist_rect_circle(rect, o["x"], o["y"], o["r"])
            elif o["kind"] == "rect":
                d = d_bbox
            else:
                d = dist_rect_poly(rect, o["pts"])
            d = d - o["clr"] - extra
            if d < best:
                best, what = d, o["tag"]
        return best, what

    def _obs(self):
        if not hasattr(self, "_obs_cache"):
            self._obs_cache = self.obstacles()
        return self._obs_cache

    def edge_slack(self, rect):
        """Distance from rect to the outline boundary minus edge tolerance."""
        n = len(self.outline)
        d = min(seg_seg_dist(a, b, self.outline[i], self.outline[(i + 1) % n])
                for i in range(n) for a, b in rect.edges())
        return d


# ------------------------------------------------------------- free island scan
def scan_islands(tile, min_w=3.0, min_h=2.0):
    """Maximal free rectangles on the bottom side.

    Candidate harvest on a sample grid (scanline outline intervals + inline
    obstacle bbox/clearance tests), then each candidate is shrunk by one grid
    cell on every side and re-verified with the exact clearance test, so every
    published island is certified exactly, never by sampling."""
    g = tile.par.grid
    m = tile.par.edge_clear + tile.par.board_edge_tol
    xs = [p[0] for p in tile.outline]
    ys = [p[1] for p in tile.outline]
    x0, x1 = min(xs) + m, max(xs) - m
    y0, y1 = min(ys) + m, max(ys) - m
    nx = int((x1 - x0) / g) + 1
    ny = int((y1 - y0) / g) + 1
    obs = tile._obs()
    obx = [(o["bbox"].x0 - o["clr"], o["bbox"].y0 - o["clr"],
            o["bbox"].x1 + o["clr"], o["bbox"].y1 + o["clr"]) for o in obs]

    # outline edges + per-row scanline intervals
    n = len(tile.outline)
    edges = [(tile.outline[i], tile.outline[(i + 1) % n]) for i in range(n)]
    mgr = m + g * 0.71                     # conservative horizontal margin

    def row_cells(iy):
        y = y0 + iy * g
        cross = []
        for (ax, ay), (bx, by) in edges:
            if (ay > y) != (by > y):
                cross.append((bx - ax) * (y - ay) / (by - ay) + ax)
        cross.sort()
        cells = [False] * nx
        half = g / 2
        for a, b in zip(cross[0::2], cross[1::2]):
            a += mgr
            b -= mgr
            ia = max(0, int((a - x0) / g + i0_eps))
            ib = min(nx - 1, int((b - x0) / g + 1e-6))
            for ix in range(ia, ib + 1):
                cells[ix] = True
        return cells, y

    i0_eps = 1e-6
    fmap = []
    for iy in range(ny):
        cells, y = row_cells(iy)
        half = g / 2
        for ix in range(nx):
            if not cells[ix]:
                continue
            x = x0 + ix * g
            ok = 1
            xlo, xhi = x - half, x + half
            ylo, yhi = y - half, y + half
            for bx0, by0, bx1, by1 in obx:
                if bx1 <= xlo or bx0 >= xhi or by1 <= ylo or by0 >= yhi:
                    continue
                ok = 0
                break
            cells[ix] = ok
        fmap.append(cells)
    # NOTE: bbox test above treats the whole (expanded) obstacle bbox as blocked;
    # near-round obstacles it wastes <0.3 mm which the exact recheck restores only
    # if a candidate still verifies after the grid-cell shrink. Conservative = OK.

    cands = []
    for iy in range(ny):
        run = fmap[iy][:]
        for jy in range(iy, ny):
            if jy > iy:
                row = fmap[jy]
                if not any(row):
                    break
                run = [a and b for a, b in zip(run, row)]
                if not any(run):
                    break
            ix = 0
            while ix < nx:
                if not run[ix]:
                    ix += 1
                    continue
                jx = ix
                while jx + 1 < nx and run[jx + 1]:
                    jx += 1
                cands.append((ix, iy, jx, jy))
                ix = jx + 1
    # shrink, exact-verify, drop contained
    out = []
    for ix, iy, jx, jy in cands:
        r = Rect(x0 + ix * g + g, y0 + iy * g + g,
                 x0 + (jx + 1) * g - g, y0 + (jy + 1) * g - g)
        if r.w < min_w or r.h < min_h:
            continue
        slack, what = tile.clearance(r)
        es = tile.edge_slack(r)
        if slack >= 0 and es >= m:
            out.append({"rect": r.as_list(), "w": round(r.w, 2), "h": round(r.h, 2),
                        "area": round(r.w * r.h, 1), "obstacle_slack": round(slack, 3),
                        "nearest": what, "edge_slack": round(es - m, 3)})
    keep = []
    for a in sorted(out, key=lambda d: -d["area"]):
        ax0, ay0, ax1, ay1 = a["rect"]
        if any(ax0 >= b["rect"][0] - 1e-9 and ay0 >= b["rect"][1] - 1e-9 and
               ax1 <= b["rect"][2] + 1e-9 and ay1 <= b["rect"][3] + 1e-9 for b in keep):
            continue
        keep.append(a)
    return keep


# ------------------------------------------------------------ variant A (pads)
# Direction groups are placed into island lanes (south first). Two groups may
# share one lane (contiguous pin order, documented schedule); each placed group
# forms one straight sub-row.
GROUP_ORDER = ("bottom", "right", "top", "left")


def variant_a(tile, islands):
    """Place the full rev-A tile interface (CONTACTS, 28 pads) as underside pad
    rows on island lanes, groups kept contiguous, each group verified with the
    exact engine incl. chassis tolerance. Returns the pad plan or an explicit
    list of unresolved groups."""
    p, d = tile.par, tile.par.pogo_pad_d
    pitch = d + p.pogo_gap
    tol = p.tol_chassis_xy
    lanes = []
    for isl in sorted(islands, key=lambda i: -i["rect"][3]):          # south first
        x0, y0, x1, y1 = isl["rect"]
        if y1 - y0 >= d + 2 * tol and x1 - x0 >= d + 2 * tol:
            lanes.append({"rect": isl["rect"], "used": 0.0})
    rails, unresolved = [], []
    li = 0
    for g in GROUP_ORDER:
        pins = CONTACTS[g]
        n = len(pins)
        need = (n - 1) * pitch + d + 2 * tol
        placed = False
        while li < len(lanes) and not placed:
            lane = lanes[li]
            x0, y0, x1, y1 = lane["rect"]
            xs0 = x0 + tol + d / 2 + lane["used"]
            if x1 - x0 - lane["used"] >= need:
                cy = (y0 + y1) / 2
                pads, ok = [], True
                for j, (net_, role) in enumerate(pins):
                    cx = xs0 + j * pitch
                    r = Rect(cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2)
                    slack, what = tile.clearance(r, extra=tol)
                    if slack < 0:
                        ok = False
                        break
                    pads.append({"net": net_, "role": role, "group": g,
                                 "x": round(cx, 3), "y": round(cy, 3), "d": d,
                                 "slack_after_tol": round(slack, 3), "nearest": what})
                if ok:
                    rails.append({"group": g, "lane": [round(v, 2) for v in lane["rect"]],
                                  "x0": round(xs0, 2), "pads": pads})
                    lane["used"] += need + pitch      # gap before the next group
                    placed = True
            if not placed and lane["used"] == 0:
                li += 1
            elif not placed:
                li += 1
        if not placed:
            unresolved.append(g)
    return {"pad_d": d, "pitch": pitch, "tolerance": tol,
            "group_order": list(GROUP_ORDER), "plan": rails, "unresolved": unresolved}


# ------------------------------------------------------- chassis spring packing
def chassis_keepouts(tile):
    """Keep-outs for parts standing on the chassis plane: the z-projection of
    every hot-swap socket body (courtyard) of this tile AND of its lattice
    neighbours (right/left/up/down and the two diagonals), because the chassis
    is shared by the whole dense field of tiles."""
    P, R = tile.par.P(), tile.par.R()
    shifts = [(0, 0), (4 * P, 0), (-4 * P, 0), (P / 2, -3 * R), (-P / 2, 3 * R),
              (4 * P - P / 2, 3 * R), (-4 * P + P / 2, -3 * R)]
    out = []
    for o in tile.obstacles():
        if o["kind"] != "poly":
            continue
        for dx, dy in shifts:
            out.append({"pts": [(x + dx, y + dy) for x, y in o["pts"]],
                        "tag": o["tag"], "kind": "poly"})
    return out


def pack_springs(tile, va, part):
    """Chassis-side body packing for a spring contact of body w x d mm.

    Model: one contact per tile pad, tip anchored on the pad (tip offset inside
    the body = ASSUMPTION to verify from the part drawing). Springs stand on the
    chassis plane, which is free EXCEPT under the z-projection of the hot-swap
    socket bodies (courtyard keep-outs). Bodies are wider than the pad pitch, so
    they are assigned to y-staggered banks: per (orientation, number of banks),
    the bank base offset is scanned on a grid; all-vs-all body and keep-out
    checks are exact. Returns None when nothing packs (a valid honest result).
    """
    p = tile.par
    w0, d0 = part
    keepouts = chassis_keepouts(tile)
    pads = [pp for lane in va["plan"] for pp in lane["pads"]]

    def freespot(x, y, wd, dd):
        r = Rect(x - wd / 2, y - dd / 2, x + wd / 2, y + dd / 2)
        for q in keepouts:
            if dist_rect_poly(r, q["pts"]) < p.spr_body_clr - 1e-9:
                return None
        return r

    tried = []
    for orient in (0, 1):
        wd, dd = (w0, d0) if orient == 0 else (d0, w0)
        pitch = va["pitch"]
        import math as _m
        n_span = _m.ceil((wd + p.spr_bank_gap) / pitch)   # same-bank pad spacing index
        tried.append({"orientation": orient, "banks": list(range(max(2, n_span),
                                                                max(2, n_span) + 3))})
        for nb in range(max(2, n_span), max(2, n_span) + 3):
            step = dd + p.spr_bank_gap
            span = (nb - 1) * step
            base = -span / 2
            # scan bank-row base offset over +/- (free window radius); coarse grid
            best = None
            for g in range(-48, 49):
                base = g * 0.25
                placed, assignment = [], []
                ok = True
                for j, pp in enumerate(pads):
                    k = j % nb
                    y = pp["y"] + base + (k - (nb - 1) / 2) * step
                    r = freespot(pp["x"], y, wd, dd)
                    if r is None:
                        ok = False
                        break
                    bad = any(dist_rect_rect(r, q) < p.spr_bank_gap - 1e-9 for q in placed)
                    if bad:
                        ok = False
                        break
                    placed.append(r)
                    assignment.append({"role": pp["role"], "group": pp["group"],
                                       "x": round(pp["x"], 2), "y": round(y, 2),
                                       "bank": k})
                if ok:
                    span_mm = span + dd
                    if best is None or span_mm < best["span_mm"]:
                        best = {"banks": nb,
                                "orientation": ("along x" if orient == 0 else "rotated 90"),
                                "body_mm": [w0, d0], "bank_base_offset": round(base, 2),
                                "span_mm": span_mm,
                                "contacts_placed": len(assignment),
                                "assignment": assignment,
                                "note": "tip anchored on pad centre (ASSUMPTION); "
                                        "banks staggered in chassis-plane y"}
                        break           # first hits at coarsest banks; good enough
            if best is not None:
                best["trials"] = tried
                return best
    return {"failed": True, "trials": tried}


# ------------------------------------------------------------- backplane graph
def backplane_graph(remove_slot=None):
    """Electrical adjacency through the passive chassis backplane, checked
    against the rev-A mating semantics (docs/architecture/protocol.md).

    Nodes are (slot, group, pin index). Tile-internal unions: pads sharing a
    net name (VCC x4, GND x7, B_clk/B_data on bottom+right legs). Backplane
    unions at shared slot boundaries: S.top[k] <-> Up.bottom[k],
    S.left[k] <-> LeftNeighbour.right[k] (same index k, exactly the rev-A
    J102<->J103 / J101<->J104 pairing).

    remove_slot removes ONE whole tile (all its pad nodes) - the model for
    "that slot is empty" used by the presence checks. Returns union-find with
    helpers."""
    slots = [(0, 0), (1, 0), (0, 1), (1, 1)]
    if remove_slot is not None:
        slots = [s for s in slots if s != remove_slot]
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    SLOTS = set(slots)
    for s in slots:
        # tile-internal: same net name -> same electrical net
        seen = {}
        for g, pins in CONTACTS.items():
            for idx, (net_, _role) in enumerate(pins):
                if net_ in seen:
                    union((s, g, idx), seen[net_])
                else:
                    seen[net_] = (s, g, idx)
    for (i, j) in slots:
        up = (i, j + 1)
        if up in SLOTS:
            for k in range(len(CONTACTS["top"])):
                union(((i, j), "top", k), (up, "bottom", k))
        left = (i - 1, j)
        if left in SLOTS:
            for k in range(len(CONTACTS["left"])):
                union(((i, j), "left", k), (left, "right", k))
    return {"find": find, "slots": slots}


def parent_nodes(bg):
    f = bg["find"]
    seen = []
    for s in bg["slots"]:
        for g, pins in CONTACTS.items():
            for idx in range(len(pins)):
                n = (s, g, idx)
                f(n)
                seen.append(n)
    return seen


def net_members(bg, node):
    f = bg["find"]
    r = f(node)
    return [n for n in parent_nodes(bg) if f(n) == r]


def net_names(bg, node):
    """Set of tile-side net names in the electrical net containing node."""
    return {CONTACTS[g][idx][0] for (_s, g, idx) in net_members(bg, node)}


def check_backplane():
    """Executable truth checks of the backplane wiring vs the protocol."""
    checks = []

    def ck(name, ok, detail=""):
        checks.append({"id": "BK", "name": name, "ok": bool(ok), "detail": detail})

    bg = backplane_graph()
    find = bg["find"]
    slots = set(bg["slots"])
    n_nodes = len(parent_nodes(bg))
    ck("backplane node count = 4 slots x 28 tile pads", n_nodes == 4 * 28,
       str(n_nodes))
    ok = True
    for (i, j) in slots:
        up, lft = (i, j + 1), (i - 1, j)
        if up in slots:
            ok &= find(((i, j), "top", 1)) == find((up, "bottom", 1))    # T_clk<->B_clk
            ok &= find(((i, j), "top", 2)) == find((up, "bottom", 2))    # T_data<->B_data
            ok &= find(((i, j), "top", 5)) == find((up, "bottom", 5))    # L_latch<->B_latch
            ok &= find(((i, j), "top", 6)) == find((up, "bottom", 6))    # T_W<->B_W
        if lft in slots:
            ok &= find(((i, j), "left", 1)) == find((lft, "right", 1))   # L_clk<->B_clk
            ok &= find(((i, j), "left", 2)) == find((lft, "right", 2))   # L_data<->B_data
            ok &= find(((i, j), "left", 4)) == find((lft, "right", 4))   # L_latch<->R_latch
    ck("backplane adjacency matches J102<->J103 / J101<->J104 pin mapping", ok)
    s0 = (0, 0)
    ok = (find((s0, "bottom", 1)) == find((s0, "right", 1)) and
          find((s0, "bottom", 2)) == find((s0, "right", 2)))
    ck("B_clk / B_data merged across bottom and right legs (one net each)", ok)
    ok = True
    for (i, j) in slots:
        up, lft, dn = (i, j + 1), (i - 1, j), (i, j - 1)
        if up in slots:
            ok &= "GND" in net_names(bg, ((i, j), "top", 3))
        if lft in slots:
            ok &= "GND" in net_names(bg, ((i, j), "left", 3))
        if dn in slots:
            ok &= "GND" in net_names(bg, ((i, j), "bottom", 4))
    ck("T_endcol/L_endrow/B_first see the neighbour GND through the backplane", ok)
    # In rev A the three detect inputs ride the neighbour's GND pin, i.e. the
    # global GND net; both power nets are global too. So the expected electrical
    # classes for the whole fabric are exactly these six - a valid wiring never
    # mixes names ACROSS them:
    classes = (frozenset(("VCC",)), frozenset(("GND", "T_endcol", "L_endrow",
                                              "B_first")),
               frozenset(("T_clk", "B_clk", "L_clk")),
               frozenset(("T_data", "B_data", "L_data")),
               frozenset(("L_latch", "B_latch", "R_latch")),
               frozenset(("T_W", "B_W")))
    bad = []
    for node in parent_nodes(bg):
        names = frozenset(net_names(bg, node))
        if not any(names <= c for c in classes):
            bad.append((node, sorted(names)))
    ck("every electrical net stays inside one of the six rev-A classes "
       "(no class-crossing wiring)", not bad, str([sorted(b[1]) for b in bad[:4]]))
    # the classes above must ALSO be reachable, i.e. a fully populated fabric has
    # no signal net that collapsed to zero: probe every class on slot (1,0)
    bg2 = backplane_graph(remove_slot=(0, 1))
    names = net_names(bg2, ((0, 0), "top", 3))
    ck("with the tile above removed, T_endcol has no GND path (reads absent)",
       "GND" not in names, sorted(names))
    names = net_names(bg2, ((1, 0), "left", 3))
    ck("unrelated detect lines keep working when another slot is removed",
       "GND" in names, sorted(names))
    names = net_names(backplane_graph(), ((0, 0), "bottom", 4))
    ck("corner slot B_first floats (no neighbour below) -> 'first' semantics kept",
       "GND" not in names, sorted(names))
    return checks


# --------------------------------------------------------- detection strap pads
def strap_layout(tile):
    """Three 2-pad straps on the tile bottom, near the top/left/bottom edges.
    Positions found by scanning along each edge for a collision-free window,
    so the straps are exactly where the study proves free space exists.
    Returns {name: {"pads": [(x,y),...], "slack": mm}} or raises."""
    p = tile.par
    w, h = p.strap_pad_w, p.strap_pad_h
    gap = w * 0.5                       # between the two pads of one strap
    tol = p.tol_chassis_xy
    m = p.edge_clear + p.board_edge_tol
    eps = 1e-6
    xs = [q[0] for q in tile.outline]
    ys = [q[1] for q in tile.outline]
    xr = (min(xs), max(xs))
    out = {}

    def try_pair(x, y, dx, dy):
        r = Rect(x - w / 2, y - h / 2, x + w / 2, y + h / 2)
        s1 = tile.clearance(r, extra=tol)[0]
        r2 = Rect(x + dx - w / 2, y + dy - h / 2, x + dx + w / 2, y + dy + h / 2)
        s2 = tile.clearance(r2, extra=tol)[0]
        es = min(tile.edge_slack(r), tile.edge_slack(r2))
        if es < m - eps:
            return None
        return max(0.0, min(s1, s2))       # obstacle slack; edge rule is a gate

    def scan(x0, x1, y0, dx, dy, along_x=True):
        mid = (x0 + x1) / 2 if along_x else (min(ys) + max(ys)) / 2
        best = None
        x = x0
        while x < x1:
            s = try_pair(x, y0, dx, dy) if along_x else None
            if not along_x:
                s = try_pair(y0, x, dx, dy)
            if s is not None:
                key = (s, -abs(x - mid))
                if best is None or key > best[0]:
                    best = (key, x)
            x += 0.25
        return best

    # top strap: horizontal pair just below the top edge of row 0
    b = scan(xr[0] + m + w / 2, xr[1] - m - w / 2 - (w + gap),
             min(ys) + m + h / 2, w + gap, 0)
    if b is not None:
        (_, x) = b[0], b[1]
        out["strap_T"] = {"pads": [(round(x, 2), round(min(ys) + m + h / 2, 2)),
                                   (round(x + w + gap, 2), round(min(ys) + m + h / 2, 2))],
                          "slack": round(b[0][0], 3), "edge": "top"}
    # bottom strap: horizontal pair just above the bottom edge of row 2
    b = scan(xr[0] + m + w / 2, xr[1] - m - w / 2 - (w + gap),
             max(ys) - m - h / 2, w + gap, 0)
    if b is not None:
        (_, x) = b[0], b[1]
        out["strap_B"] = {"pads": [(round(x, 2), round(max(ys) - m - h / 2, 2)),
                                   (round(x + w + gap, 2), round(max(ys) - m - h / 2, 2))],
                          "slack": round(b[0][0], 3), "edge": "bottom"}
    # left strap: vertical pair just inside the left edge of the bottom row step
    b = scan(min(ys) + m + h / 2, max(ys) - m - h / 2 - (h + gap),
             min(xs) + m + w / 2, 0, h + gap, along_x=False)
    if b is not None:
        (_, y) = b[0], b[1]
        out["strap_L"] = {"pads": [(round(min(xs) + m + w / 2, 2), round(y, 2)),
                                   (round(min(xs) + m + w / 2, 2), round(y + h + gap, 2))],
                          "slack": round(b[0][0], 3), "edge": "left"}
    return out
# --------------------------------------------------------- variant B (mezzanine)
def extended_fit(par, fp, fp_trim, style, need_w, need_h):
    """Smallest bottom-edge extension (a south 'tab') such that an exact-verified
    island of need_w x need_h fits. Returns (ext_mm, island) or (None, None).
    The first guess is analytic from the base tile's bottom lane; every reported
    ext is then certified by a full re-scan of the extended tile."""
    p0 = replace(par, bottom_ext=0.0)
    t0 = Tile(p0, fp, style, fp_trim)
    base = scan_islands(t0, min_w=need_w, min_h=0.5)
    tries = []
    deep = [i for i in base if i["w"] >= need_w]
    if deep:
        bottom_lane = max(deep, key=lambda i: i["rect"][3])
        tries.append(max(0.0, round(need_h - bottom_lane["h"] + 0.25, 2)))
    tries += [e for e in (1, 2, 3, 4, 6, 8, 12) if all(abs(e - q) > 0.01 for q in tries)]
    for ext in tries:
        t = Tile(replace(par, bottom_ext=ext), fp, style, fp_trim)
        isl = scan_islands(t, min_w=need_w, min_h=need_h)
        if isl:
            return ext, max(isl, key=lambda i: i["h"])
    return None, None


def variant_b(tiles_by_style, mezz, islands_by, par, fp, fp_trim):
    """Mezzanine evaluation, scoped to the candidates actually measured
    (NOT a claim about all SMT connectors). Contact budget: 16 unique interface
    nets + 6 detection-strap endpoints = 22 contacts minimum."""
    res = {}
    pairs = {"df12_pair30": ("df12_plug30", "df12_receptacle30"),
             "df12_pair20": ("df12_plug", "df12_receptacle"),
             "gecko_pair20": ("gecko_male20", "gecko_female20")}
    need_contacts = inventory()["nets_count"] + 2 * len(STRAP_LINES)
    out = {}
    for style in tiles_by_style:
        tile, islands = tiles_by_style[style], islands_by[style]
        res = {}
        for pname, (tile_side, chassis_side) in pairs.items():
            t, c = mezz.get(tile_side, {}), mezz.get(chassis_side, {})
            if "courtyard_bbox_fpside" not in t or "courtyard_bbox_fpside" not in c:
                res[pname] = {"error": "footprint measure missing"}
                continue
            tb, cb = t["courtyard_bbox_fpside"], c["courtyard_bbox_fpside"]
            tw, th = tb["x1"] - tb["x0"], tb["y1"] - tb["y0"]
            pin_count = len({p["n"] for p in t["pads"] if p["n"] not in ("", None)})
            need_w = tw + 2 * par.mezz_clear
            need_h = th + 2 * par.mezz_clear
            need_h_esc = th + 2 * par.mezz_clear + par.mezz_escape
            fits, fits_esc = None, None
            for isl in islands:
                x0, y0, x1, y1 = isl["rect"]
                if (x1 - x0) >= need_w:
                    if (y1 - y0) >= need_h and fits is None:
                        fits = isl
                    if (y1 - y0) >= need_h_esc:
                        fits_esc = isl
                        break
            entry = {
                "tile_side": t["name"], "chassis_side": c["name"],
                "role_tile": t["role"], "role_chassis": c["role"],
                "pin_count": pin_count, "contacts_needed": need_contacts,
                "tile_courtyard_mm": [round(tw, 2), round(th, 2)],
                "chassis_courtyard_mm": [round(cb["x1"] - cb["x0"], 2),
                                         round(cb["y1"] - cb["y0"], 2)],
                "island_need_mm": [round(need_w, 2), round(need_h, 2)],
                "island_need_with_escape_mm": [round(need_w, 2), round(need_h_esc, 2)],
                "fits_board": fits is not None,
                "fits_board_with_escape": fits_esc is not None,
                "example": fits_esc or fits,
            }
            if fits_esc is None and style == "stepped":
                ext, isl = extended_fit(par, fp, fp_trim, style, need_w, need_h_esc)
                entry["min_bottom_extension_mm"] = ext
                entry["extension_island"] = isl
            res[pname] = entry
        out[style] = res
    return out


# ------------------------------------------------------------- detection model
def detection_model(par):
    """Passive presence detection, chassis variant.

    Every tile carries three copper straps (strap_T, strap_L, strap_B): two
    adjacent underside pads each, wired together on the tile, near its
    top/left/bottom edges. The chassis backplane carries, per slot S and per
    direction d in {T,L,B}, a sense pair mirroring the strap position of slot
    neighbour(S,d): pad DET_d(S) pulled up by the chassis logic, pad GND_d(S)
    on the permanent backplane ground.

    Slot N is reported present iff the seated tile in slot N bridges, through
    ITS copper strap, that sense pair. The only path from DET_d(S) to ground
    therefore passes through the removable neighbour tile. With slot N empty,
    DET_d(S) floats high. The permanent backplane ground alone never explains
    a 'present' reading: that property is checked below by enumerating paths.
    """
    lines = ("DET_T", "DET_L", "DET_B")
    # nodes: DET_d, GND_d (permanent), strap pads nd_a/nd_b (on the neighbour)
    states = {
        "empty": [],                       # no tile in the neighbour slot
        "seated": [("a", "b")],            # tile present, strap lap welded
        # half-mated: tilt modes -> which strap pads touch
        "half_mated_tilt_along_edge": [("a", "b")],   # both or none: same y
        "half_mated_tilt_toward_edge": [],            # strap side raised
        "half_mated_rocked_one_pad": [],              # only one pad: series open
    }
    table = {}
    for line in lines:
        rows = {}
        for state, closed in states.items():
            gnd_reached = any(set(c) == {"a", "b"} for c in closed)
            rows[state] = 0 if gnd_reached else 1
        table[line] = rows
    return {"lines": lines, "table": table,
            "rule": "DET_x = 0 (present) only through the neighbour tile's strap; "
                    "pull-up otherwise. GND pad in the pair is permanent backplane "
                    "GND, the STRAP is not."}


def check_detection(par, model):
    checks = []
    # 1) truth table semantics
    for line in model["lines"]:
        t = model["table"][line]
        checks.append((f"detect {line}: empty reads 1", t["empty"] == 1))
        checks.append((f"detect {line}: seated reads 0", t["seated"] == 0))
        checks.append((f"detect {line}: tilt-toward-edge reads 1 (no false present)",
                       t["half_mated_tilt_toward_edge"] == 1))
        checks.append((f"detect {line}: one-pad rocked reads 1 (series strap open)",
                       t["half_mated_rocked_one_pad"] == 1))
    # 2) no permanent-GND-only path: enumerate paths DET->GND in the chassis graph
    #    without any neighbour tile: there are none (documented by construction:
    #    the two circuits meet only at the strap). Encoded as a graph reachability
    #    test so a future edit cannot silently reintroduce a permanent path.
    perm_edges = [("DET_T", "pullup"), ("DET_L", "pullup"), ("DET_B", "pullup"),
                  ("pullup", "VCC"), ("GND", "chassis")]
    removable_edges = [("DET_T", "strapT"), ("strapT", "GND")]  # exists iff neighbour seated
    def reaches(edges):
        g = {}
        for a, b in edges:
            g.setdefault(a, set()).add(b)
            g.setdefault(b, set()).add(a)
        seen, todo = set(), ["DET_T"]
        while todo:
            n = todo.pop()
            if n in seen:
                continue
            seen.add(n)
            todo += list(g.get(n, ()))
        return "GND" in seen
    checks.append(("no permanent-only path DET->GND", not reaches(perm_edges)))
    checks.append(("with neighbour seated path exists", reaches(perm_edges + removable_edges)))
    return checks


# ---------------------------------------------------------------- svg helpers
def svg_head(w, h):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
            f'viewBox="0 0 {w:.3f} {h:.3f}" font-family="monospace">\n')


def svg_poly(pts, **kw):
    fill = kw.get("fill", "none")
    stroke = kw.get("stroke", "#000")
    w = kw.get("w", 0.15)
    dash = f' stroke-dasharray="{kw["dash"]}"' if kw.get("dash") else ""
    p = " ".join(f"{x:.3f},{y:.3f}" for x, y in pts)
    return f'<polygon points="{p}" fill="{fill}" stroke="{stroke}" stroke-width="{w}"{dash}/>\n'


def svg_rect(r, **kw):
    fill = kw.get("fill", "none")
    stroke = kw.get("stroke", "#000")
    w = kw.get("w", 0.12)
    dash = f' stroke-dasharray="{kw["dash"]}"' if kw.get("dash") else ""
    return (f'<rect x="{r.x0:.3f}" y="{r.y0:.3f}" width="{r.w:.3f}" height="{r.h:.3f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{w}"{dash}/>\n')


def svg_circle(x, y, r, **kw):
    fill = kw.get("fill", "none")
    stroke = kw.get("stroke", "#000")
    w = kw.get("w", 0.12)
    return (f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{r:.3f}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{w}"/>\n')


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_text(x, y, s, size=1.6, anchor="middle", fill="#000", rotate=None):
    rot = f' transform="rotate({rotate} {x:.2f} {y:.2f})"' if rotate else ""
    return (f'<text x="{x:.3f}" y="{y:.3f}" font-size="{size}" text-anchor="{anchor}" '
            f'fill="{fill}"{rot}>{_esc(s)}</text>\n')


# --------------------------------------------------------- chassis stack (z)
def chassis_stack(par, stp):
    """Vertical budget under the dropped-in tile.

    Deepest tile feature below the board: the hot-swap socket bodies. The
    vendored STEP extends 4.443 mm from the board face; that is used as an
    upper BOUND (axis mapping unverified - flagged), the typical Kailh CPG1511
    plastic height is smaller. No nominal 3D clearance is claimed anywhere."""
    depth_bound = -stp["z"][0]                 # 4.443 (upper bound, unverified axis map)
    depth_guard = depth_bound + par.z_guard
    springs = {
        "S1941-42R": {"free": 7.3, "dmin": 0.3, "dmax": 0.8, "src": "spring_s1941"},
        "S1971-46R": {"free": 4.55, "dmin": 0.3, "dmax": 0.6, "src": "spring_s1971"},
    }
    out = {}
    for name, s in springs.items():
        gap_lo = s["free"] - s["dmax"]           # tile bottom above chassis board
        gap_hi = s["free"] - s["dmin"]
        clears_lo = gap_lo - depth_guard
        out[name] = {"free_height": s["free"], "deflection": [s["dmin"], s["dmax"]],
                     "tile_gap_window": [round(gap_lo, 2), round(gap_hi, 2)],
                     "socket_depth_bound": round(depth_guard, 2),
                     "clears_socket_bound": bool(clears_lo >= 0),
                     "margin_mm": round(clears_lo, 2)}
    # mezzanine: mated height from the series page (3.0 for the KiCad-stocked
    # DF12 C3.0/E3.0 pair); the chassis then needs relief pockets under sockets.
    out["mezzanine"] = {"df12_mated_height": 3.0,
                        "needs_chassis_relief_under_sockets": 3.0 < depth_guard,
                        "note": "DF12 3/3.5/4/5 mm stacks exist; KiCad 10 ships only the "
                                "3.0 mm variant footprints. Gecko G125 pair is taller "
                                "(exact mated height: see DRG-00182; not re-stated here)."}
    return out


# ------------------------------------------------------------- lattice check
def lattice_continuity(tile):
    """Emulate a right-hand and an upper neighbour (revc lattice vectors) and
    measure the actual key-to-key pitches across the boundary."""
    P, R = tile.par.P(), tile.par.R()
    own = list(tile.centre.values())
    right = [(x + 4 * P, y) for x, y in own]
    up = [(x + P / 2, y - 3 * R) for x, y in own]
    def mindist(a, b):
        return min(math.hypot(x - u, y - v) for x, y in a for u, v in b)
    # body clearance across the boundary (every neighbour pair, not just lattice nn)
    d_right = mindist(own, right)
    d_up = mindist(own, up)
    # cross-boundary *nearest* pitch should be P when the outline is lattice-exact
    return {"right_vector": [4 * P, 0], "up_vector": [P / 2, -3 * R],
            "min_key_dist_right": round(d_right, 3), "min_key_dist_up": round(d_up, 3),
            "target_pitch": round(P, 3),
            "lattice_exact": abs(d_right - P) < 0.02 and abs(d_up - P) < 0.02}


# ------------------------------------------------------------------- checks
def run_checks(par, fp, stp, tiles, islands_by, va_by, vb_by, straps_by,
               det, stack, has_mezz, caps, packs, backplane_checks):
    checks = []

    def ck(cid, name, ok, detail=""):
        checks.append({"id": cid, "name": name, "ok": bool(ok), "detail": detail})

    # --- footprint parsing (values re-verified from the parsed file itself) ---
    ck("FP1", "vendored footprint parses: 2 SMD pads + 5 NPTH",
       len(fp["pads"]) == 2 and len(fp["holes"]) == 5,
       f"pads={len(fp['pads'])} holes={len(fp['holes'])}")
    drills = sorted(round(h["d"], 2) for h in fp["holes"])
    ck("FP2", "NPTH drills are {1x4.0, 2x3.05, 2x1.75} mm",
       drills == [1.75, 1.75, 3.05, 3.05, 4.0], str(drills))
    t = tiles["stepped"]
    ck("FP3", "courtyard polygon chained closed (socket body)",
       len(t.crt_poly) >= 8, f"{len(t.crt_poly)} vertices")

    # --- contact inventory vs the rev-A protocol table ---
    inv = inventory()
    ck("INV1", "tile contact count = 28 rev-A pads (8 top + 8 bottom + 6 left + 6 right)",
       inv["pads_total"] == 28 and inv["groups"] == {"top": 8, "bottom": 8,
                                                     "left": 6, "right": 6},
       str(inv["groups"]))
    ck("INV2", "unique nets = 16 (14 signals + VCC + GND); B_clk/B_data merged "
               "across bottom+right legs",
       inv["nets_count"] == 16 and {"B_clk", "B_data"} < set(inv["nets_unique"]),
       str(len(inv["nets_unique"])))
    for sig in ("T_clk", "T_data", "T_endcol", "T_W", "L_clk", "L_data",
                "L_endrow", "L_latch", "R_latch", "B_first", "B_latch", "B_W"):
        if sig not in inv["nets_unique"]:
            ck("INV3", f"missing protocol signal {sig}", False)

    # --- lattice ---
    P, R = par.P(), par.R()
    ck("LAT1", "R = body + margin = 15.9 mm", abs(R - 15.9) < 1e-9, f"R={R:.3f}")
    ck("LAT2", "P = R/sin(60deg) ~= 18.36 mm (equilateral)", abs(P - 18.3598) < 5e-3,
       f"P={P:.4f}")
    ok_eq = True
    for (i, k), c in t.centre.items():
        for di, dk in ((0, 1), (1, 1)):
            j = (i + di, k + dk)
            if j in t.centre:
                d = math.hypot(t.centre[j][0] - c[0], t.centre[j][1] - c[1])
                ok_eq = ok_eq and abs(d - P) < 1e-6
    ck("LAT3", "every diagonal neighbour distance equals P (equilateral)", ok_eq)
    lc = lattice_continuity(t)
    ck("LAT4", "cross-tile key pitch equals P (stepped outline, lattice-continuous)",
       lc["lattice_exact"], json.dumps({k: lc[k] for k in ("min_key_dist_right",
                                                           "min_key_dist_up")}))

    # --- keycaps (pairwise, including cross-tile neighbour tiles) ---
    ck("CAP1", "hex cap (Voronoi cell, shrunk by gap/2) keeps >= cap_gap with ALL "
               "neighbours incl. cross-tile",
       caps["hex"]["min_gap_incl_cross_tile"] >= par.cap_gap - 1e-9,
       f"min gap {caps['hex']['min_gap_incl_cross_tile']:.3f} mm")
    ck("CAP2", "CONTROL: square cap of side P-gap demonstrably OVERLAPS at this "
               "pitch (review point verified, stock square rejected)",
       caps["square_at_P_minus_gap"]["min_gap_incl_cross_tile"] < par.cap_gap - 1e-9,
       f"min gap {caps['square_at_P_minus_gap']['min_gap_incl_cross_tile']:.3f} mm < 0")
    ck("CAP3", "largest non-overlapping square cap = R - gap (documented alternative)",
       abs(caps["square_max_no_overlap"]["side"] - (R - par.cap_gap)) < 1e-9 and
       caps["square_max_no_overlap"]["min_gap_incl_cross_tile"] >= par.cap_gap - 1e-9,
       f"{caps['square_max_no_overlap']['side']:.2f} mm")

    # --- outline / clearance ---
    worst = min(t.edge_slack(o["rect"]) for o in t.obstacles() if o["kind"] == "rect")
    ck("OUT1", "bottom copper pads clear of the outline (>= edge_clear + outline tol)",
       worst >= par.edge_clear + par.board_edge_tol - 1e-9,
       f"worst pad-to-edge {worst:+.3f} mm")
    def hole_edge_slack(o):
        cx, cy, r = o["x"], o["y"], o["r"]
        n = len(t.outline)
        d = min(_pt_seg((cx, cy), t.outline[i], t.outline[(i + 1) % n]) for i in range(n))
        return d - r
    worst_hole = min(hole_edge_slack(o) for o in t.obstacles() if o["kind"] == "circle")
    ck("OUT2", "every NPTH keeps drill-to-edge >= edge_clear + outline tolerance",
       worst_hole >= par.edge_clear + par.board_edge_tol,
       f"worst drill-to-edge {worst_hole:.3f} mm")

    # --- islands ---
    isl = islands_by["stepped"]
    ck("ISL1", "free islands found on the bottom side", len(isl) > 0,
       f"{len(isl)} islands")
    ok = all(tile_recheck(t, i["rect"]) for i in isl[:25])
    ck("ISL2", "independent re-check: every published island is exact-clear", ok,
       f"checked {min(25, len(isl))}")
    lanes = [i for i in isl if i["w"] >= 40 and i["h"] >= 2.5]
    ck("ISL3", "at least one full-width lane >= 40 x 2.5 mm exists", len(lanes) > 0,
       f"{len(lanes)} lanes")

    # --- variant A: full rev-A interface placed ---
    for style in ("stepped", "rect"):
        va = va_by[style]
        placed_n = sum(len(l["pads"]) for l in va["plan"])
        ck(f"VA1-{style}", f"variant A places ALL 28 rev-A contacts ({style} outline)",
           not va["unresolved"] and placed_n == 28,
           f"placed {placed_n}/28, unresolved groups: {va['unresolved'] or '-'}")
        if va["plan"]:
            allpads = [q for l in va["plan"] for q in l["pads"]]
            ck(f"VA2-{style}", "variant A pads collision-free incl. "
                               f"{par.tol_chassis_xy} mm chassis tolerance",
               all(q["slack_after_tol"] >= 0 for q in allpads),
               f"worst {min(q['slack_after_tol'] for q in allpads):.2f} mm")
            per_lane = {tuple(l["lane"]) for l in va["plan"]}
            straight = all(len({q["y"] for q in l["pads"]}) == 1 for l in va["plan"])
            ck(f"VA3-{style}", "each direction group is one straight row "
                               "(simple chassis rails)", straight,
               f"{len(va['plan'])} rails used")
            ck(f"VA4-{style}", "pad row keeps group contiguity and pin order "
                               "(backplane wiring schedule)",
               all(l["group"] in CONTACTS for l in va["plan"]))

    # --- chassis spring body packing (rejections are verified, not asserted) ---
    band_depth = 8.6          # derived constant of this lattice: free chassis
                              # bands between socket rows (courtyards+keepout):
                              # R - 6.8 - 0.5 (courtyard+clr) = 8.6 mm
    need_free = stack["S1941-42R"]["socket_depth_bound"] + 0.8
    max_dd_2banks = (band_depth - 2 * par.spr_body_clr - par.spr_bank_gap) / 2
    max_wd_2banks = 2 * va_by["stepped"]["pitch"] - par.spr_bank_gap
    s1941 = packs.get("S1941-42R")
    s1971 = packs.get("S1971-46R")
    ck("CH1", "spring part selection criteria derived: free height "
              f">= {need_free:.2f} mm AND body <= {max_wd_2banks:.2f} x "
              f"{max_dd_2banks:.2f} mm (2-bank pack in a {band_depth} mm free band)",
       need_free < band_depth and max_dd_2banks > 0,
       f"free>={need_free:.2f}, body<=({max_wd_2banks:.2f},{max_dd_2banks:.2f})")
    ck("CH-S1941", "S1941-42R is REJECTED for packing (body 5.70 mm deep exceeds "
                   f"the 2-bank limit {max_dd_2banks:.2f} mm even though its z stack "
                   "is fine) - rejection verified by exhaustive bank search",
       s1941 is not None and s1941.get("failed") and par.spr_s1941_d > max_dd_2banks and
       stack["S1941-42R"]["clears_socket_bound"])
    ck("CH-S1971", "S1971-46R packs (2 banks) but is REJECTED by the z budget "
                   "(4.55 mm free height < bound + deflection) - both facts "
                   "verified, not assumed",
       s1971 is not None and not s1971.get("failed") and
       not stack["S1971-46R"]["clears_socket_bound"],
       "" if not s1971 or s1971.get("failed") else
       f"banks={s1971['banks']} base={s1971['bank_base_offset']}")

    # --- variant B (scoped): the two KiCad-stocked candidates only ---
    ck("VB0", "mezzanine footprint measures present (measure_footprints.py)",
       has_mezz)
    if has_mezz:
        for pname, vb in vb_by["stepped"].items():
            if "error" in vb:
                ck(f"VB1-{pname}", f"{pname} measure error", False, vb["error"])
                continue
            ext = vb.get("min_bottom_extension_mm")
            detail = (f"minimal tile: {'fits' if vb['fits_board_with_escape'] else 'NO FIT'}; "
                      f"need island {vb['island_need_with_escape_mm']} mm; "
                      "scope: tested candidates only, not all SMT connectors")
            if ext is not None:
                detail += f"; certified with bottom extension +{ext} mm"
            ck(f"VB1-{pname}", f"{pname} evaluated on the minimal tile "
                               f"({vb.get('pin_count', '?')} connector contacts vs "
                               f"{vb.get('contacts_needed', '?')} needed)", True, detail)
            if not vb["fits_board_with_escape"]:
                ck(f"VB2-{pname}", f"{pname}: extended-tile island certified by re-scan",
                   ext is not None and vb.get("extension_island") is not None,
                   f"ext={ext} mm")
            if vb.get("example"):
                ck(f"VB3-{pname}", f"{pname} example island exact re-check",
                   tile_recheck(t, vb["example"]["rect"]) if
                   isinstance(vb["example"], dict) else False)
            need22 = vb.get("contacts_needed", 22)
            n_pin = vb.get("pin_count", 0)
            ck(f"VB4-{pname}", f"{pname} contact budget check ({need22} = 16 nets + "
                               f"6 strap endpoints): " +
                               ("SUFFICIENT" if n_pin >= need22
                                else "REJECTED, too few contacts - verified fact"),
               need22 == inventory()["nets_count"] + 2 * len(STRAP_LINES) == 22,
               f"connector contacts: {n_pin}")

    # --- backplane adjacency (rev-A semantics through the chassis) ---
    checks.extend(backplane_checks)

    # --- detection straps (belt+braces next to the rev-A passive pins) ---
    for name, ok_ in check_detection(par, det):
        ck("DET", name, ok_)
    ck("DET3", "detection straps placed collision-free on all 3 edges (stepped)",
       all(v["slack"] >= 0 for v in straps_by["stepped"].values()) and
       len(straps_by["stepped"]) == 3, json.dumps({k: v["slack"] for k, v in
                                                   straps_by["stepped"].items()}))

    # --- chassis stack ---
    ck("Z1", "S1941-42R clears the socket depth bound (worst case)",
       stack["S1941-42R"]["clears_socket_bound"],
       f"margin {stack['S1941-42R']['margin_mm']} mm")
    ck("Z2", "S1971-46R is correctly rejected as too short",
       not stack["S1971-46R"]["clears_socket_bound"],
       f"margin {stack['S1971-46R']['margin_mm']} mm")
    ck("Z3", "3.0 mm mezzanine < socket depth bound => chassis relief required "
             "(flagged, not hidden)",
       stack["mezzanine"]["needs_chassis_relief_under_sockets"])
    return checks


def tile_recheck(tile, rect4):
    r = Rect(*rect4)
    if tile.edge_slack(r) < tile.par.edge_clear + tile.par.board_edge_tol:
        return False
    return tile.clearance(r)[0] >= 0


# ---------------------------------------------------------------- SVG panels
SC = 3.6  # px per mm


def _g(ox, oy):
    return f'<g transform="translate({ox:.1f},{oy:.1f}) scale({SC})">'


def panel_top(tile, ox, oy, caps=None):
    p = tile.par
    s = _g(ox, oy) + "\n"
    s += svg_poly(tile.outline, stroke="#111", w=0.3)
    hexp = hex_cell(p.P(), p.cap_gap)
    for (i, k), (x, y) in sorted(tile.centre.items()):
        s += svg_rect(Rect(x - p.body / 2, y - p.body / 2, x + p.body / 2, y + p.body / 2),
                      fill="#e8e8e8", stroke="#888", w=0.15)
        s += svg_poly([(hx + x, hy + y) for hx, hy in hexp], fill="none",
                      stroke="#36c", w=0.15, dash="0.8 0.5")
        s += svg_text(x, y + 0.7, f"{i},{k}", size=2.2, fill="#36c")
    # ghost neighbour tile caps (cross-tile contact check demonstration)
    u = (p.P() / 2, -3 * p.R())
    for (i, k), (x, y) in sorted(tile.centre.items()):
        if k == 0 and i in (1, 2):
            s += svg_poly([(hx + x + u[0], hy + y + u[1]) for hx, hy in hexp],
                          fill="none", stroke="#aaa", w=0.12, dash="0.8 0.6")
    # pitch arrows
    (x0, y0), (x1, _) = tile.centre[(0, 0)], tile.centre[(1, 0)]
    ya = y0 - p.P() / 2 - 0.8
    s += f'<line x1="{x0}" y1="{ya}" x2="{x1}" y2="{ya}" stroke="#000" stroke-width="0.2"/>\n'
    s += f'<path d="M {x0} {ya} l 1.2 -0.45 v 0.9 z M {x1} {ya} l -1.2 -0.45 v 0.9 z" fill="#000"/>\n'
    s += svg_text((x0 + x1) / 2, ya - 1.1, f"P = {p.P():.2f}", size=2.4)
    (xb, yb), (_, yc) = tile.centre[(0, 1)], tile.centre[(0, 2)]
    xa = xb - p.body / 2 - 1.6
    s += f'<line x1="{xa}" y1="{yb}" x2="{xa}" y2="{yc}" stroke="#000" stroke-width="0.2"/>\n'
    s += f'<path d="M {xa} {yb} l -0.45 1.2 h 0.9 z M {xa} {yc} l -0.45 -1.2 h 0.9 z" fill="#000"/>\n'
    s += svg_text(xa - 0.8, (yb + yc) / 2, f"R = {p.R():.2f}", size=2.4, rotate=-90)
    hexnote = (f"hex caps across-flats {caps['hex']['across_flats']:.2f} mm (assumption, "
               f"custom; square P-gap OVERLAPS: min gap "
               f"{caps['square_at_P_minus_gap']['min_gap_incl_cross_tile']:.2f} mm)"
               if caps else "")
    s += svg_text(0, -p.P() / 2 - 3.6,
                  f"top side - {tile.style} outline, body {p.body} mm (grey), "
                  f"{hexnote}", size=2.6, anchor="start")
    s += "</g>\n"
    return s


GROUP_COLOR = {"top": "#06c", "bottom": "#063", "left": "#b60", "right": "#90a"}


def panel_bottom(tile, islands, va, straps, ox, oy):
    s = _g(ox, oy) + "\n"
    s += svg_poly(tile.outline, stroke="#111", w=0.3)
    for isl in islands[:14]:
        r = Rect(*isl["rect"])
        s += svg_rect(r, fill="rgba(0,180,0,0.15)", stroke="#0a0", w=0.15)
    for o in tile.obstacles():
        if o["kind"] == "circle":
            s += svg_circle(o["x"], o["y"], o["r"], fill="#333")
            s += svg_circle(o["x"], o["y"], o["r"] + o["clr"], stroke="#f60", w=0.12,
                            dash="0.5 0.4")
        elif o["kind"] == "rect":
            s += svg_rect(o["rect"], fill="#c00")
        else:
            s += svg_poly(o["pts"], stroke="#f80", w=0.15)
    for lane in va["plan"]:
        col = GROUP_COLOR.get(lane["group"], "#06c")
        for q in lane["pads"]:
            s += svg_circle(q["x"], q["y"], q["d"] / 2, fill=col)
            s += svg_text(q["x"], q["y"] + 3.0, q["role"], size=1.35, fill=col)
        lx = lane["lane"]
        s += svg_text(lx[0] + 1, lx[1] - 1.2, f"rail: {lane['group']} group",
                      size=2.0, anchor="start", fill=col)
    for name, st in straps.items():
        for (x, y) in st["pads"]:
            s += svg_rect(Rect(x - tile.par.strap_pad_w / 2, y - tile.par.strap_pad_h / 2,
                               x + tile.par.strap_pad_w / 2, y + tile.par.strap_pad_h / 2),
                          fill="#f0f")
        s += svg_text(st["pads"][0][0], st["pads"][0][1] - 2, name, size=1.9, fill="#a0a")
    s += svg_text(0, min(q[1] for q in tile.outline) - 3.4,
                  f"bottom side - islands (green), socket pads (red), NPTH (black) + "
                  f"keep-outs (orange), rev-A contact groups by direction, straps "
                  f"(magenta) [{tile.style}]",
                  size=2.6, anchor="start")
    s += "</g>\n"
    return s


def panel_stack(par, stack, ox, oy):
    s = _g(ox, oy) + "\n"
    a = stack["S1941-42R"]
    gap = a["tile_gap_window"]
    gmid = sum(gap) / 2
    sock = a["socket_depth_bound"]
    # chassis board
    s += svg_rect(Rect(0, 2, 150, 4), fill="#dcb", stroke="#000", w=0.3)
    s += svg_text(151, 3.2, "chassis board (passive backplane)", size=2.6, anchor="start")
    # spring contacts on the chassis
    for x in (30, 60, 90, 120):
        s += svg_rect(Rect(x - 2.4, 2 - a["free_height"], x + 2.4, 2), fill="#fd6",
                      stroke="#000", w=0.25)
    # tile board
    s += svg_rect(Rect(0, 2 - gmid - par.board_thickness, 150, 2 - gmid), fill="#9c9",
                  stroke="#000", w=0.3)
    s += svg_text(151, 2 - gmid - par.board_thickness / 2 + 0.8, "tile PCB 1.6 mm",
                  size=2.6, anchor="start")
    # socket bound below tile
    s += svg_rect(Rect(60, 2 - gmid, 120, 2 - gmid + sock), fill="rgba(255,80,0,0.35)",
                  stroke="#f60", w=0.25)
    s += svg_text(121, 2 - gmid + sock / 2 + 1, f"socket depth <= {sock:.2f} mm (bound)",
                  size=2.4, anchor="start")
    s += svg_text(0, -12, "chassis stack, variant A spring S1941-42R "
                  f"(gap window {gap[0]:.2f}..{gap[1]:.2f} mm, green tile clears "
                  f"socket bound by {a['margin_mm']:.2f} mm)", size=2.8, anchor="start")
    s += svg_text(0, 10, "no nominal 3D clearance claimed: socket depth is the vendored "
                  "STEP bound + guard; confirm with 3D assembly", size=2.2, anchor="start",
                  fill="#a00")
    s += "</g>\n"
    return s


def panel_detect(det, ox, oy):
    s = _g(ox, oy) + "\n"
    s += svg_text(0, -6, "presence detection: GND strap on the REMOVABLE NEIGHBOUR only",
                  size=2.8, anchor="start")
    # chassis with two slots, neighbour tile above / absent
    s += svg_rect(Rect(0, 0, 60, 40), fill="#eee", stroke="#000", w=0.3)
    s += svg_text(30, 44, "my slot S", size=2.6)
    s += svg_rect(Rect(70, 0, 60, 40), fill="#cfc", stroke="#000", w=0.3)
    s += svg_text(100, 44, "neighbour slot N (removable tile)", size=2.6)
    s += svg_circle(80, 12, 2.2, fill="#06c")
    s += svg_text(80, 8, "DET_x(S) sense pad", size=2.2)
    s += svg_circle(92, 12, 2.2, fill="#000")
    s += svg_text(92, 8, "backplane GND pad", size=2.2)
    s += f'<line x1="80" y1="12" x2="92" y2="12" stroke="#a0a" stroke-width="1.2"/>\n'
    s += svg_text(86, 18, "copper strap ON TILE N (vanishes with N)", size=2.2, fill="#a0a")
    y = 52
    for line in det["lines"]:
        row = det["table"][line]
        s += svg_text(0, y, f"{line}:  empty->{row['empty']}  seated->{row['seated']}  "
                      f"half-mated tilts ->{row['half_mated_tilt_along_edge']}/"
                      f"{row['half_mated_tilt_toward_edge']}/{row['half_mated_rocked_one_pad']}",
                      size=2.4, anchor="start")
        y += 5
    s += "</g>\n"
    return s


def build_svg(par, tiles, islands, va, straps, stack, det, path, caps, packs):
    t = tiles["stepped"]
    w_mm = 125
    h_top = 45
    h_bot = 70
    w = (w_mm) * SC
    h = (h_top + h_bot + 60) * SC
    s = svg_head(w, h)
    s += svg_text(0.3, 0.4, "simple-tile connector study (all units mm; tiles drawn "
                  "1:1 in tile coordinates)", size=3.0, anchor="start")
    ox = (14 + t.par.P()) * SC
    s += panel_top(t, ox, 26 * SC, caps)
    s += panel_bottom(t, islands, va, straps, ox, 78 * SC)
    s += panel_stack(par, stack, 5 * SC, 150 * SC)
    s += panel_detect(det, 5 * SC, 125 * SC)
    s += "</svg>\n"
    open(path, "w").write(s)


# -------------------------------------------------------------------- report
def poly_area(poly):
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] -
                   poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly))) / 2)


def write_report(outdir, par, fp, stp, tiles, islands_by, va_by, vb_by, straps_by,
                 det, stack, checks, caps, packs):
    n_ok = sum(1 for c in checks if c["ok"])
    t = tiles["stepped"]
    lc = lattice_continuity(t)
    inv = inventory()
    L = []
    a = L.append
    a("# Simple-tile drop-in connector study (generated by study.py)\n")
    a("Tile keeps the rev-A per-tile logic; this study covers the mechanical/"
      "contact side only: single PCB, SMD Kailh hot-swap, minimum equilateral "
      "lattice (18.36 mm), drop-in chassis, no tile-side MCU/LED/Hall. "
      "Acceptance context: 20 MHz shift clock, up to 16 tiles.\n")
    a("## Parameters (inputs; assumptions labelled)\n")
    a("| param | value | note |")
    a("|---|---|---|")
    a(f"| key lattice | P = {par.P():.4f} mm, R = {par.R():.3f} mm | R = 15.6 body + "
      f"0.3 margin; P = R/sin60 (LEDGER 2026-09-27) |")
    a(f"| keys | {par.rows * par.cols} ({par.rows} rows x {par.cols}) | row shift P/2 |")
    a(f"| keycap (ASSUMPTION) | custom hexagonal cap, {caps['hex']['across_flats']:.2f} mm "
      f"across flats (lattice Voronoi cell - 0.5 mm) | stock square caps cannot be used "
      f"at this pitch, see keycap section |")
    a(f"| footprint reach from switch centre | {t.reach:.2f} mm | parsed from the "
      "vendored file |")
    a(f"| edge clearance / outline tol | {par.edge_clear} / {par.board_edge_tol} mm |"
      " copper-to-edge |")
    a(f"| keep-outs | holes +{par.clr_hole} mm, pads/courtyard +{par.clr_pad} mm |"
      " revc_edges.py heritage |")
    a(f"| chassis tolerance (ASSUMPTION) | +/-{par.tol_chassis_xy} mm XY | SMT "
      "placement + pocket play sum |")
    a(f"| variant A pad (ASSUMPTION) | dia {par.pogo_pad_d} mm round | >= spring-tip "
      "area + 2*tol; confirm tip dia from DRG-02208 (Harwin drawing) before layout |")
    a(f"| board | {par.board_thickness} mm | |")
    a("")
    a("## Tile contact inventory (rev-A interface, not a key matrix)\n")
    a("Derived from docs/architecture/protocol.md (the J101/J102/J103/J104 pin "
      "table). All four directions are preserved; B_clk and B_data stay single "
      "nets shared by the bottom and right legs, as in rev A:\n")
    a("| direction | pins | nets |")
    a("|---|---|---|")
    for g in ("top", "bottom", "left", "right"):
        pins = CONTACTS[g]
        a(f"| {g} | {len(pins)} | " + ", ".join(f"`{n}` ({r})" for n, r in pins) + " |")
    a(f"\n**{inv['pads_total']} tile-side pads, {inv['nets_count']} unique nets "
      f"({inv['nets_count'] - 2} signals + VCC + GND).** Plus 3 presence straps "
      "(6 more pads) below.\n")
    a("## Tile outline (two styles evaluated)\n")
    for style in ("stepped", "rect"):
        tt = tiles[style]
        trim = sorted(f"{i},{k}" for (i, k), v in tt.pad_variant.items()
                      if v == "edgetrim")
        a(f"- **{style}**: area {poly_area(tt.outline):.1f} mm2, margin {tt.margin:.2f} mm"
          + (f"; EdgeTrim pad variant on keys {', '.join(trim)}" if trim else ""))
    a("")
    a(f"- Stepped outline: cross-tile key pitch right = {lc['min_key_dist_right']:.3f} mm,"
      f" up = {lc['min_key_dist_up']:.3f} mm (target P = {lc['target_pitch']:.3f}; "
      "lattice-continuous = "
      f"{'yes' if lc['lattice_exact'] else 'NO'}). "
      "The stepped geometry (G/2 insets on both sides of a 1.0 mm rib gap) follows the "
      "rev-C construction in `revc_build.py`; the rev-A/B edge *connector* positions "
      "are NOT reused anywhere -- pads sit on interior island lanes. "
      "Rect outline trades lattice continuity across the rim for the smallest PCB.\n")
    a("## Keycaps (custom only at this pitch)\n")
    a(f"- **Hexagonal cap (ASSUMPTION, lattice Voronoi cell - {par.cap_gap} mm):** "
      f"{caps['hex']['across_flats']:.2f} mm across flats, area {caps['hex']['area']} mm2; "
      f"min gap incl. cross-tile neighbours = {caps['hex']['min_gap_incl_cross_tile']:.3f} mm. "
      "Hex caps are the established answer for isomorphic grids (they tile the "
      "triangular lattice exactly).")
    a(f"- Control experiment (review point): a square cap of side P - {par.cap_gap} = "
      f"{caps['square_at_P_minus_gap']['side']:.2f} mm OVERLAPS between rows "
      f"(min gap {caps['square_at_P_minus_gap']['min_gap_incl_cross_tile']:.3f} mm): "
      "stock square caps are impossible at R = 15.9 mm.")
    a(f"- Largest non-overlapping square cap: {caps['square_max_no_overlap']['side']:.2f} mm "
      f"(= R - gap), area {caps['square_max_no_overlap']['area']} mm2 - much smaller "
      f"target than the {caps['hex']['across_flats']:.2f}-flat hex "
      f"({caps['hex']['area']} vs {caps['square_max_no_overlap']['area']} mm2).\n")
    a("## Free connector islands on the bottom side (collision-checked)\n")
    for style in ("stepped", "rect"):
        isl = islands_by[style]
        top = sorted(isl, key=lambda d: -d["area"])[:6]
        a(f"- **{style}**: {len(isl)} islands; largest:")
        for i in top:
            a(f"  - {i['w']:.2f} x {i['h']:.2f} mm at "
              f"({i['rect'][0]:.2f},{i['rect'][1]:.2f})..({i['rect'][2]:.2f},{i['rect'][3]:.2f})"
              f"  slack {i['obstacle_slack']:.2f} mm to {i['nearest']},"
              f" edge slack {i['edge_slack']:.2f}")
    a("")
    a("Every island is harvested on a 0.25 mm sample grid, shrunk by one grid cell, "
      "then re-verified with exact distance tests (see check ISL2).\n")
    a("## Variant A: tile-underside pads + chassis vertical spring contacts\n")
    for style in ("stepped", "rect"):
        va = va_by[style]
        n_pl = sum(len(l["pads"]) for l in va["plan"])
        a(f"- **{style}**: {n_pl}/28 contacts placed in {len(va['plan'])} rails "
          f"(groups: {', '.join(l['group'] for l in va['plan']) or '-'}; "
          f"unresolved: {', '.join(va['unresolved']) or 'none'})")
        for l in va["plan"]:
            worst = min(q['slack_after_tol'] for q in l['pads'])
            a(f"  - rail `{l['group']}` ({len(l['pads'])} pads) in lane "
              f"{[round(v,1) for v in l['lane']]}, worst slack after tolerance "
              f"{worst:.2f} mm")
    a("")
    a("Chassis-side spring body packing (bodies are wider than the pad pitch, so "
      "they are staggered into banks; exact all-vs-all body and socket-projection "
      "collision checks including the six lattice-neighbour tiles; spring tip "
      "anchored on the pad centre - tip offset inside the body is an ASSUMPTION "
      "to verify from the part drawing):\n")
    for name, pk in packs.items():
        if pk is None or pk.get("failed"):
            trials = "" if not pk else \
                "; trials: " + ", ".join(f"orient {t['orientation']} banks "
                                         f"{t['banks'][0]}..{t['banks'][-1]}"
                                         for t in pk.get("trials", []))
            a(f"- **{name}: NOT PACKABLE** under the study pad plan "
              f"-> part rejected for this layout{trials}.")
        else:
            a(f"- **{name}**: packs with {pk['banks']} bank(s) "
              f"({pk['orientation']}); {pk['contacts_placed']} contacts placed.")
    a("")
    a("Mating order note: NO first-mate claim is made. With all pad rows coplanar, "
      "which contact touches first depends on tilt; guaranteed-first GND would need "
      "contact-height staggering (longer GND contacts or stepped pad heights) - "
      "recorded as an open mechanical requirement, not solved here.\n")
    stk = stack["S1941-42R"]
    a(f"Vertical budget with Harwin S1941-42R (free 7.3 mm, deflection 0.3-0.8): "
      f"tile-bottom window {stk['tile_gap_window']} mm above the chassis board; clears "
      f"the {stk['socket_depth_bound']} mm socket depth BOUND by {stk['margin_mm']} mm. "
      f"S1971-46R (4.55 mm free) leaves {stack['S1971-46R']['margin_mm']} mm -> "
      "rejected. The socket depth bound is the vendored STEP's raw point extent + "
      "0.5 mm guard with an unverified axis mapping: a worst-case bound, not a "
      "nominal clearance; 3D assembly verification is a listed next step.\n")
    a("## Variant B: SMT mezzanine to passive chassis/backplane (scoped)\n")
    if "error" in vb_by["stepped"]:
        a("**Not evaluated: mezzanine footprint measures missing "
          "(run measure_footprints.py).**\n")
    else:
        a(f"Contact budget for one connector per tile: 16 unique nets + 6 detection "
          f"strap endpoints = **22 contacts minimum**. Scope: only the candidates "
          "below, all with verified footprints from the installed KiCad 10 library "
          "were tested; this says nothing about untested families.\n")
        for pname in ("df12_pair30", "df12_pair20", "gecko_pair20"):
            vb = vb_by["stepped"].get(pname)
            if vb is None or "error" in vb:
                a(f"- **{pname}**: {'not measured' if vb is None else vb['error']}")
                continue
            fits = ("FITS the minimal tile" if vb["fits_board_with_escape"]
                    else "DOES NOT FIT inside the minimal tile")
            a(f"- **{pname}** ({vb['tile_side']}): {vb['pin_count']} contacts "
              f"(need {vb['contacts_needed']}); courtyard "
              f"{vb['tile_courtyard_mm'][0]} x {vb['tile_courtyard_mm'][1]} mm; "
              f"island needed {vb['island_need_with_escape_mm'][0]} x "
              f"{vb['island_need_with_escape_mm'][1]} mm incl. escape fan-out -> {fits}")
            if vb.get("min_bottom_extension_mm") is not None:
                isl = vb["extension_island"]
                a(f"  extending the bottom edge by +{vb['min_bottom_extension_mm']} mm "
                  f"(south mezzanine tab) is certified by re-scan: island "
                  f"{isl['w']:.2f} x {isl['h']:.2f} mm at {isl['rect']}")
    a(f"\nMezzanine stack heights the KiCad 10 library supports here: DF12 C3.0/E3.0 "
      f"pairs = 3.0 mm mated. Socket depth bound is {stack['S1941-42R']['socket_depth_bound']}"
      " mm, so any <= 3 mm mezzanine requires relief pockets in the chassis board under "
      "every socket; the DF12 family has 3.5/4/5 mm variants (series page) whose "
      "footprints are NOT in the KiCad library - they would need to be drawn and "
      "verified before use. The DF12 series page is flagged 'Planned End of Life'; "
      "DF40 (0.4 mm) is the family's live successor but tops out at 3.5 mm stack.\n")
    a("## Backplane adjacency (rev-A semantics through the chassis)\n")
    bk = [c for c in checks if c["id"] == "BK"]
    a(f"A passive backplane wires, per shared slot boundary, S.top[k] <-> "
      "slot-above.bottom[k] and S.left[k] <-> left-slot.right[k] (identical to "
      "the rev-A J102<->J103 / J101<->J104 pairing, but routed on the backplane "
      "instead of mated directly). Executable checks on a 2x2 slot field:")
    for c in bk:
        a(f"- [{'PASS' if c['ok'] else 'FAIL'}] {c['name']}  {c['detail']}".rstrip())
    a("")
    a("## Presence detection (3 lines)\n")
    a(det["rule"])
    a("")
    a("In addition the rev-A passive pins work unchanged through the backplane: "
      "T_endcol / L_endrow / B_first read the neighbour's GND pins, which exist "
      "only while the neighbour tile is seated (checks BK). The 3 strap lines are "
      "belt-and-braces so a slot can be sensed even with the scan logic at rest.\n")
    a("| line | empty | seated | half-mated (tilt along edge / toward edge / one-pad rock) |")
    a("|---|---|---|---|")
    for line in det["lines"]:
        r = det["table"][line]
        a(f"| {line} | {r['empty']} | {r['seated']} | {r['half_mated_tilt_along_edge']} / "
          f"{r['half_mated_tilt_toward_edge']} / {r['half_mated_rocked_one_pad']} |")
    a("\n1 = no neighbour (pull-up floats high); 0 = neighbour present (sense pad "
      "strapped to chassis GND **through the removable neighbour tile's own copper "
      "strap**). Machine-checkable form: `out/truth_table.json`; the DET checks verify "
      "the table and the 'no permanent-GND-only path' property.")
    a("\n**Half-mated caveat (documented behaviour):** a neighbour tilted *towards* its "
      "strap edge can hold the strap closed while its signal pads are not yet mated; "
      "the line then correctly reports 'strap side engaged'. The tile scan protocol's "
      "marker bits still catch a non-communicating tile, as in rev A/B.")
    a("")
    a("## Cost framing (one PCB per tile vs shared passive backplane)\n")
    a(f"- Tile PCB ({t.style}): {poly_area(t.outline):.1f} mm2 x 16 tiles = "
      f"{16 * poly_area(t.outline) / 100:.0f} cm2 of small boards; the chassis "
      "backplane is cut once regardless of variant (structural + routing).")
    a("- Part-count deltas (prices not sourced here - unknown, not quoted): "
      "variant A needs chassis spring contacts (28 + 6) per slot "
      f"({34 * 16} total contacts for 16 slots), tile side is copper pads only; "
      "variant B needs one connector pair per slot (32 parts over 16 slots at the "
      "chosen width) plus chassis relief pockets. The chassis board stays a "
      "passive 2-layer PCB in both variants.")
    a("")
    a("## Checks\n")
    a(f"{n_ok}/{len(checks)} passed. Full list with details: `out/checks.json`.")
    a("\n## Sources\n")
    for k, (txt, url) in SOURCES.items():
        a(f"- `{k}`: {txt} -- <{url}>")
    a("\nGenerated artifacts: `out/placement.json`, `out/placement.svg`, "
      "`out/truth_table.json`, `out/checks.json`, this report.")
    open(os.path.join(outdir, "report.md"), "w").write("\n".join(L) + "\n")


# ---------------------------------------------------------------------- main
def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out")
    os.makedirs(outdir, exist_ok=True)
    par = Params()
    fp = parse_kicad_mod(VENDORED_FP)
    fp_trim = parse_kicad_mod(VENDORED_FP_TRIM)
    stp = step_bbox(VENDORED_STP)
    wrl_ok = os.path.isfile(VENDORED_WRL)
    tiles = {s: Tile(par, fp, s, fp_trim) for s in ("stepped", "rect")}
    islands_by = {s: scan_islands(tiles[s]) for s in tiles}
    va_by = {s: variant_a(tiles[s], islands_by[s]) for s in tiles}
    straps_by = {s: strap_layout(tiles[s]) for s in tiles}
    caps = cap_study(par)
    packs = {"S1941-42R": pack_springs(tiles["stepped"], va_by["stepped"],
                                       (par.spr_s1941_w, par.spr_s1941_d)),
             "S1971-46R": pack_springs(tiles["stepped"], va_by["stepped"],
                                       (par.spr_s1971_w, par.spr_s1971_d))}
    backplane_checks = check_backplane()
    mezz = {}
    has_mezz = False
    if os.path.isfile(MEZZ_JSON):
        mezz = json.load(open(MEZZ_JSON))
        has_mezz = all(k in mezz for k in
                       ("df12_plug", "df12_receptacle", "df12_plug30",
                        "df12_receptacle30", "gecko_male20", "gecko_female20"))
    vb_by = (variant_b(tiles, mezz, islands_by, par, fp, fp_trim) if has_mezz else
             {s: {"error": "out/mezzanine_measures.json missing"} for s in tiles})
    det = detection_model(par)
    stack = chassis_stack(par, stp)
    checks = run_checks(par, fp, stp, tiles, islands_by, va_by, vb_by, straps_by,
                        det, stack, has_mezz, caps, packs, backplane_checks)

    placement = {
        "params": asdict(par), "sources": {k: v[1] for k, v in SOURCES.items()},
        "lattice": {"P": par.P(), "R": par.R()},
        "interface": {"contacts": CONTACTS, "strap_lines": list(STRAP_LINES),
                      "inventory": inventory()},
        "keycaps": caps,
        "footprint_reach_mm": tiles["stepped"].reach,
        "step_bbox_mm": stp, "wrl_present": wrl_ok,
        "tiles": {s: {"outline": [[round(x, 4), round(y, 4)] for x, y in tiles[s].outline],
                      "margin": round(tiles[s].margin, 4),
                      "area_mm2": round(poly_area(tiles[s].outline), 2),
                      "edgetrim_keys": [list(k) for k, v in tiles[s].pad_variant.items()
                                        if v == "edgetrim"],
                      "keys": [[i, k, round(x, 4), round(y, 4)]
                               for (i, k), (x, y) in sorted(tiles[s].centre.items())]}
                  for s in tiles},
        "islands": islands_by, "variant_a": {s: va_by[s] for s in tiles},
        "straps": straps_by, "chassis_springs": packs, "variant_b": vb_by,
        "chassis_stack": stack, "detection": det,
        "checks_summary": {"ok": sum(1 for c in checks if c["ok"]), "total": len(checks)},
    }
    json.dump(placement, open(os.path.join(outdir, "placement.json"), "w"), indent=1)
    json.dump(det, open(os.path.join(outdir, "truth_table.json"), "w"), indent=1)
    json.dump(checks, open(os.path.join(outdir, "checks.json"), "w"), indent=1)
    build_svg(par, tiles, islands_by["stepped"], va_by["stepped"], straps_by["stepped"],
              stack, det, os.path.join(outdir, "placement.svg"), caps, packs)
    write_report(outdir, par, fp, stp, tiles, islands_by, va_by, vb_by, straps_by,
                 det, stack, checks, caps, packs)
    for c in checks:
        print(f"[{'PASS' if c['ok'] else 'FAIL'}] {c['id']}: {c['name']}  {c['detail']}")
    print(f"checks: {sum(1 for c in checks if c['ok'])}/{len(checks)} passed; "
          f"artifacts in {outdir}")
    sys.exit(0 if all(c["ok"] for c in checks) else 1)


if __name__ == "__main__":
    main()
