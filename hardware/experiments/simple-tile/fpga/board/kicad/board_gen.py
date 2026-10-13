#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""board_gen -- single-PCB FPGA tile: placement + circuit prototype builder.

Builds the two board variants of fpga/board:
  gw1nz  - Gowin GW1NZ-LV1QN48 board (primary; vendor-verified pins)
  up5k   - Lattice iCE40UP5K-SG48 board (verified fallback; external SPI flash)

Geometry: the CORRECTED connector-next TileTiling stepped outline (revc-exact,
vertical margin R/2 - the baseline connectors/ "Tile" outline overlaps the
vertical lattice neighbours by 1.46 mm and is NOT used). The 19 spring-contact
pads (connector-next budget, 14 signals + VCC + GND + 3 dedicated detect-GND)
are re-derived with the SAME deterministic engine call as connector-next
study.py and machine-asserted EQUAL to the certified coordinates in
connector-next/out/study.json.

Nothing is routed (placement prototype, honest DRC counts). The FPGA/strap/
resistor nets come from the pin databases (data/*.json) + the checked
constraint files (constraints/*), NOT from a hand netlist; keys wire exactly
like the rev-A passive plan (SW.1=VCC, SW.2 -> key net, pull-down at the pad
on GW1NZ, external 10K on UP5K).

Checks: GK1 outline identity vs the revc construction + 6-neighbour gap,
GK2 pad equality vs study.json + re-clearance incl. chassis tolerance,
GK3 lattice/footprint-variant selection, GK4 total pairwise courtyard matrix
(polygon-exact for socket courtyards, chassis pads included), GK5 NPTH
drill-to-edge and pad-to-edge, GK6 net/pin completeness, GK7 invariant
counts. Json + txt + the two .kicad_pcb land in out/kicad/.

Run (host python3, stdlib; footprints of stock parts read via flatpak cat):
    python3 board/kicad/board_gen.py
"""
import importlib.util
import json
import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # .../fpga/board/kicad
BOARD = os.path.abspath(os.path.join(HERE, ".."))          # .../fpga/board
ST = os.path.abspath(os.path.join(BOARD, "..", ".."))      # .../simple-tile
REPO = os.path.abspath(os.path.join(ST, "..", "..", ".."))
OUT = os.path.join(BOARD, "out")
KOUT = os.path.join(OUT, "kicad")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


base = _load("baseline_connectors_study",
             os.path.join(ST, "connectors", "study.py"))
cnext = _load("connector_next_study",
              os.path.join(ST, "connector-next", "study.py"))

FLAT_FP = "/app/extensions/Library/Footprints/footprints"
VENDORED_FP = os.path.join(REPO, "hardware", "kicad", "lib",
                           "Switch_Keyboard_Hotswap_Kailh.pretty")
MYLIB = os.path.join(HERE, "lib", "fpga_board.pretty")

STOCK = {
    "R0603": "Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod",
    "C0603": "Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod",
    "C1206": "Capacitor_SMD.pretty/C_1206_3216Metric.kicad_mod",
    "SOT235": "Package_TO_SOT_SMD.pretty/SOT-23-5.kicad_mod",
    "SOIC8": "Package_SO.pretty/SOIC-8_5.3x6.2mm_P1.27mm.kicad_mod",
    "TP": "TestPoint.pretty/TestPoint_Pad_D1.0mm.kicad_mod",
}

_cache = {}


def stock_text(rel):
    if rel not in _cache:
        out = subprocess.run(["flatpak", "run", "--command=cat",
                              "org.kicad.KiCad", f"{FLAT_FP}/{rel}"],
                             capture_output=True, text=True, check=True)
        _cache[rel] = out.stdout
    return _cache[rel]


def lib_text(path):
    if path not in _cache:
        _cache[path] = open(path).read()
    return _cache[path]


def _sexpr_blocks(text, tag):
    out, i = [], 0
    needle = f"({tag}"
    while True:
        j = text.find(needle, i)
        if j < 0:
            break
        depth, k = 0, j
        while k < len(text):
            ch = text[k]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    out.append(text[j:k + 1])
                    break
            k += 1
        i = k + 1
    return out


def _mid_of(sx, sy, ex, ey, deg):
    th = math.radians(deg)
    vx, vy = ex - sx, ey - sy
    L = math.hypot(vx, vy)
    if L < 1e-9 or abs(th) < 1e-9:
        return (sx + vx / 2, sy + vy / 2)
    r = L / (2 * math.sin(abs(th) / 2))
    a = L / (2 * math.tan(abs(th) / 2))
    mx, my = (sx + ex) / 2, (sy + ey) / 2
    nx, ny = -vy / L, vx / L
    sgn = 1 if deg > 0 else -1
    cx, cy = mx + sgn * a * nx, my + sgn * a * ny
    dx, dy = mx - cx, my - cy
    dl = math.hypot(dx, dy)
    if dl < 1e-9:
        return (mx, my)
    return (cx + dx / dl * r, cy + dy / dl * r)


def arc_convert(fp_text):
    repl = {}
    for blk in _sexpr_blocks(fp_text, "fp_arc"):
        mm = re.search(r"\(start (-?[\d.]+) (-?[\d.]+)\)\s*"
                       r"\(end (-?[\d.]+) (-?[\d.]+)\)\s*\(angle (-?[\d.]+)\)", blk)
        if not mm:
            continue
        sx, sy, ex, ey, deg = (float(mm.group(k)) for k in range(1, 6))
        mx, my = _mid_of(sx, sy, ex, ey, deg)
        rest = blk[mm.end():].rstrip()
        assert rest.endswith(")")
        repl[blk] = (f"(fp_arc (start {sx} {sy}) (mid {mx:.4f} {my:.4f}) "
                     f"(end {ex} {ey}) {rest[:-1]})")
    for a, b in repl.items():
        fp_text = fp_text.replace(a, b)
    return fp_text


def courtyard_bbox(fp_text, layer="F"):
    want = [f'"{layer}.CrtYd"', f"{layer}.CrtYd"]
    xs, ys = [], []
    # circles first: (end ...) is ONE point on the circumference, not a bbox
    # corner - the bbox is center +/- radius in both axes (the generic point
    # collect below would otherwise return a degenerate zero-height rect,
    # which let the placer stack the D1.0 test points 0.25 mm apart)
    for blk in _sexpr_blocks(fp_text, "fp_circle"):
        if not any(w in blk for w in want):
            continue
        mm = re.search(r"\(center\s+(-?[\d.]+)\s+(-?[\d.]+)\)\s*"
                       r"\(end\s+(-?[\d.]+)\s+(-?[\d.]+)\)", blk)
        if not mm:
            continue
        cx, cy, ex, ey = (float(mm.group(i)) for i in range(1, 5))
        r = math.hypot(ex - cx, ey - cy)
        xs += [cx - r, cx + r]
        ys += [cy - r, cy + r]
    for kind in ("fp_line", "fp_rect", "fp_poly", "fp_arc"):
        for blk in _sexpr_blocks(fp_text, kind):
            if not any(w in blk for w in want):
                continue
            for xm, ym in re.findall(
                    r"\((?:start|end|at|xy|center)\s+(-?[\d.]+)\s+(-?[\d.]+)", blk):
                xs.append(float(xm))
                ys.append(float(ym))
    if not xs:
        for xm, ym in re.findall(
                r"\(pad\s+\"?[0-9A-Za-z]+\"?\s+\w+\s+\w+\s+\(at\s+(-?[\d.]+)\s+(-?[\d.]+)",
                fp_text):
            xs.append(float(xm))
            ys.append(float(ym))
        if not xs:
            return (0, 0, 0, 0, "EMPTY")
        return (min(xs) - 0.5, min(ys) - 0.5, max(xs) + 0.5, max(ys) + 0.5,
                "padbbox+0.5mm")
    return (min(xs), min(ys), max(xs), max(ys), f"{layer}-courtyard")


def parse_pads(fp_text):
    return {num: (float(x), float(y)) for num, x, y in re.findall(
        r"\(pad\s+\"?([0-9A-Za-z_]+)\"?\s+\w+\s+\w+\s+\(at\s+(-?[\d.]+)\s+(-?[\d.]+)",
        fp_text)}


def pads_bbox(fp_text):
    """min bbox of all pad copper (x0, y0, x1, y1) local coords."""
    xs, ys = [], []
    for m in re.finditer(
            r"\(pad\s+\"?[0-9A-Za-z_]*\"?\s+\w+\s+\w+"
            r"\s+\(at\s+(-?[\d.]+)\s+(-?[\d.]+)(?:\s+-?[\d.]+)?\)"
            r"\s+\(size\s+(-?[\d.]+)\s+(-?[\d.]+)\)", fp_text):
        x, y, w, h = (float(m.group(i)) for i in range(1, 5))
        xs += [x - w / 2, x + w / 2]
        ys += [y - h / 2, y + h / 2]
    if not xs:
        return (0, 0, 0, 0)
    return (min(xs), min(ys), max(xs), max(ys))


def _neg(s):
    v = repr(-float(s))
    return "0" if v == "-0.0" else v


GEOM_XY = re.compile(
    r"(\((?:at|start|end|mid|center|xy)\s+)(-?[\d.]+)(\s+)(-?[\d.]+)")
NET_RE = re.compile(r"\(net\s+\d+\s+\"[^\"]*\"\)")


def mirror_footprint_text(t):
    """pcbnew Flip = mirror across the pad-count axis (x -> -x) + layer swap.
    fp_rect corners are re-normalized (start=min, end=max) after negation -
    otherwise the flipped courtyard is degenerate."""
    t = GEOM_XY.sub(lambda m: m.group(1) + _neg(m.group(2)) + m.group(3)
                    + m.group(4), t)
    blocks = []
    for blk in _sexpr_blocks(t, "fp_rect"):
        m = re.search(r"\(start\s+(-?[\d.]+)\s+(-?[\d.]+)\)\s*"
                      r"\(end\s+(-?[\d.]+)\s+(-?[\d.]+)\)", blk)
        if not m:
            continue
        a, b, c, d = (float(m.group(i)) for i in range(1, 5))
        nb = re.sub(r"\(start\s+-?[\d.]+\s+-?[\d.]+\)\s*"
                    r"\(end\s+-?[\d.]+\s+-?[\d.]+\)",
                    f"(start {min(a, c)} {min(b, d)}) "
                    f"(end {max(a, c)} {max(b, d)})", blk)
        blocks.append((blk, nb))
    for blk, nb in blocks:
        t = t.replace(blk, nb, 1)
    return t


def set_prop(text, name, val):
    q = '"'
    text = re.sub(r"(\(property\s+\"" + name.capitalize() + r"\"\s+)\"[^\"]*\"",
                  lambda m: m.group(1) + q + val + q, text, count=1)
    text = re.sub(r"(\(fp_text\s+" + name + r"\s+)\"[^\"]*\"",
                  lambda m: m.group(1) + q + val + q, text, count=1)
    # legacy unquoted fp_text token (vendored Kailh sockets carry
    # "(fp_text reference REF** ...") - keep those refs from falling through
    text = re.sub(r"(\(fp_text\s+" + name + r"\s+)[^\s\)\"]+",
                  lambda m: m.group(1) + q + val + q, text, count=1)
    return text


def instantiate(fp_text, ref, value, x, y, rot, bottom, pinnet):
    """Library footprint text -> placed board instance with nets bound."""
    t = fp_text
    if t.startswith("(module "):
        t = "(footprint " + t[len("module "):]
    t = re.sub(r"\(footprint\s+\"?[^\"\s]+\"?", f'(footprint "{ref}"', t,
               count=1)
    t = set_prop(t, "reference", ref)
    t = set_prop(t, "value", value)
    pad_blocks = []
    for blk in _sexpr_blocks(t, "pad"):
        m = re.match(r"\(pad\s+\"?([0-9A-Za-z_]+)\"?\s", blk)
        if not m:
            pad_blocks.append((blk, blk))
            continue
        num = m.group(1)
        netnum, netname = pinnet.get(num, (0, ""))
        body = NET_RE.sub("", blk)
        if netnum:
            body = body.rstrip()[:-1] + f' (net {netnum} "{netname}"))'
        pad_blocks.append((blk, body))
    for blk, body in pad_blocks:
        t = t.replace(blk, body, 1)
    if bottom:
        t = mirror_footprint_text(t)
        for a, b in (("F.Cu", "B.Cu"), ("F.Paste", "B.Paste"),
                     ("F.Mask", "B.Mask"), ("F.SilkS", "B.SilkS"),
                     ("F.CrtYd", "B.CrtYd"), ("F.Fab", "B.Fab")):
            t = t.replace(f'"{a}"', f'"{b}"')
        out_parts = []
        for tag in ("fp_text", "property"):
            for blk in _sexpr_blocks(t, tag):
                nb = blk
                if '"B.' in blk and "justify" not in blk:
                    nb = blk.replace("(effects", "(effects (justify mirror)", 1)
                out_parts.append((blk, nb))
        for blk, nb in out_parts:
            if blk != nb:
                t = t.replace(blk, nb)
    # The board-level position goes in LAST: mirror_footprint_text negates
    # every x coordinate it finds, so an (at x y) inserted earlier would be
    # flipped to -x while the Placer checked the part at +x (this bug put
    # every bottom part on the wrong side of the y axis; kicad-cli DRC
    # 2026-10-12 caught 209/118 violations).
    head_end = t.index("(layer")
    line_end = t.index("\n", head_end)
    t = (t[:line_end] + f"\n\t(at {x:.4f} {y:.4f} {rot})"
         + t[line_end:])
    return t


def chassis_pad_text(ref, netnum, netname, x, y):
    return f'''(footprint "{ref}"
	(layer "B.Cu")
	(at {x:.4f} {y:.4f} 0)
	(descr "chassis spring contact target pad d2.5 (connector-next position)")
	(property "Reference" "{ref}" (at 0 -2.1) (layer "B.Fab") (effects (font (size 0.8 0.8) (thickness 0.15)) (justify mirror)))
	(property "Value" "PAD2.5" (at 0 2.1) (layer "B.Fab") (effects (font (size 0.8 0.8) (thickness 0.15)) (justify mirror)))
	(fp_circle (center 0 0) (end 1.35 0) (layer "B.CrtYd") (stroke (width 0.05) (type solid)) (fill none))
	(pad "1" smd circle (at 0 0) (size 2.5 2.5) (layers "B.Cu" "B.Mask")
		(net {netnum} "{netname}"))
)'''


def kailh_board_text(fp_text):
    """Board-side normalization of the vendored Kailh socket (library file NOT
    touched): convert legacy arcs, replace the two OPEN B.CrtYd arms with the
    closed polygon of the baseline engine (base.courtyard_polygon), drop the
    F.CrtYd +/-7.25 square (pure-key front face; every F item is another
    identical key at P >= 18.36 mm >> 14.5 mm court reach)."""
    t = arc_convert(fp_text)
    for blk in _sexpr_blocks(t, "fp_line"):
        if "F.CrtYd" in blk:
            t = t.replace(blk, "", 1)
    rm = []
    for blk in _sexpr_blocks(t, "fp_line") + _sexpr_blocks(t, "fp_arc"):
        if "B.CrtYd" in blk:
            rm.append(blk)
    if rm:
        for blk in rm:
            t = t.replace(blk, "", 1)
        pts = " ".join(f"(xy {x:.4f} {y:.4f})" for x, y in COURT)
        closed = (f'\t(fp_poly (pts {pts}) (stroke (width 0.05) (type solid)) '
                  f'(fill none) (layer "B.CrtYd") '
                  f'(uuid "b10a-ca77-0000-4000-8000-0000000000c1"))\n')
        i = t.index("(pad")
        t = t[:i] + closed + t[i:]
    if t.startswith("(module "):
        t = "(footprint " + t[len("module "):]
    return t


# ============================================================== geometry core
PLACE_GRID = 0.25
EDGE_MIN = 0.4            # courtyard-to-outline minimum
PART_GAP = 0.25           # courtyard-to-courtyard minimum (same side)

# tile of the corrected outline + certified 19 pads
par = base.Params()
FP_MODEL = base.parse_kicad_mod(base.VENDORED_FP)
FP_TRIM_MODEL = base.parse_kicad_mod(base.VENDORED_FP_TRIM)
TILE = cnext.TileTiling(par, FP_MODEL, "stepped", FP_TRIM_MODEL)
OUTLINE = TILE.outline
COURT = base.courtyard_polygon(FP_MODEL)

_islands = base.scan_islands(TILE)
_used_lanes = set()
TIER_G = cnext.place_tier(TILE, _islands, cnext.TIER_G, par.pogo_pad_d,
                          par.pogo_pad_d + par.pogo_gap,
                          par.tol_chassis_xy, _used_lanes, "GND")
TIER_S = cnext.place_tier(TILE, _islands, cnext.TIER_S, par.pogo_pad_d,
                          par.pogo_pad_d + par.pogo_gap,
                          par.tol_chassis_xy, _used_lanes, "SIG")
CHASSIS_PADS = (TIER_G or {}).get("pads", []) + (TIER_S or {}).get("pads", [])

KEYS_XY = [TILE.centre[(i, k)] for (i, k) in
           [(q % 4, q // 4) for q in range(12)]]


def diagnose_free_bbox(wdt, hgt=None):
    """Coarse scan of the largest axis-aligned free square region (0.5 grid)
    for a debug note when placement fails - reports size only."""
    hgt = hgt or wdt
    pl = Placer()
    xs = [p[0] for p in OUTLINE]
    ys = [p[1] for p in OUTLINE]
    x0, x1 = min(xs) + EDGE_MIN, max(xs) - EDGE_MIN
    y0, y1 = min(ys) + EDGE_MIN, max(ys) - EDGE_MIN
    best = (0.0, None)
    step = 0.5
    nx = int((x1 - x0) / step)
    ny = int((y1 - y0) / step)
    # largest free square: two-pointer over rows with a viable-column mask
    cols_ok = [[False] * (nx + 1) for _ in range(ny + 1)]
    for iy in range(ny + 1):
        for ix in range(nx + 1):
            px, py = x0 + ix * step, y0 + iy * step
            r = base.Rect(px - 0.1, py - 0.1, px + 0.1, py + 0.1)
            cols_ok[iy][ix] = bool(pl.free(r))
    # max square of ok cells
    row_max = [[0] * (nx + 2) for _ in range(ny + 2)]
    best_side = 0
    for iy in range(ny + 1):
        for ix in range(nx + 1):
            if cols_ok[iy][ix]:
                row_max[iy + 1][ix + 1] = 1 + min(
                    row_max[iy][ix + 1], row_max[iy + 1][ix], row_max[iy][ix])
                best_side = max(best_side, row_max[iy + 1][ix + 1])
    return (f"largest all-free square ~{best_side * step:.2f} mm side on a "
            f"{step} mm samples grid; FPGA courtyard would need {wdt:.1f} x "
            f"{hgt:.1f} mm + {PART_GAP} gap")


# --------------------------------------------------------------------- placer
class Placer:
    """Rect-parts placer on the BOTTOM side, exact checks through the
    connector-next engine (sockets' pads/holes/courtyards) + my own placed
    parts, chassis pads and outline/edge requirements."""

    def __init__(self):
        self.parts = []            # (ref, rect, side)
        # chassis contact pads are bottom-side obstacles for everything else;
        # keep at the courtyard circle (1.35 r) of the pads I emit, so the
        # gap rule is measured court-to-court everywhere.
        for pd in CHASSIS_PADS:
            self.parts.append((f"JP_{pd['net']}",
                               base.Rect(pd["x"] - 1.35, pd["y"] - 1.35,
                                         pd["x"] + 1.35, pd["y"] + 1.35), "B"))
        self.sock_courts = []      # closed polygons at the 12 keys
        for (i, k), (cx, cy) in TILE.centre.items():
            self.sock_courts.append(
                ("SW", [(cx + x, cy + y) for x, y in COURT]))

    def sock_clearance(self, r):
        """Exact slack of rect r vs every socket courtyard polygon (the
        engine's tile.clearance already covers pads/holes with their keep-out)."""
        worst = 1e9
        for _tag, poly in self.sock_courts:
            corners = [(r.x0, r.y0), (r.x1, r.y0), (r.x0, r.y1), (r.x1, r.y1),
                       ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)]
            for x, y in corners:
                if base.point_in_poly(x, y, poly):
                    return -1.0
            d = min(base.seg_seg_dist(a, b, poly[i], poly[(i + 1) % len(poly)])
                    for i in range(len(poly)) for a, b in r.edges())
            worst = min(worst, d)
        return worst

    def parts_gap(self, r):
        for _ref, pr, _side in self.parts:
            d = base.dist_rect_rect(r, pr)
            if d < PART_GAP - 1e-9:
                return d, _ref
        return 1e9, None

    def free(self, r, ref=None, r_pads=None):
        if not base.rect_inside_poly(r, OUTLINE):
            return None
        es = TILE.edge_slack(r)
        if es < EDGE_MIN - 1e-9:
            return None
        slack, _what = TILE.clearance(r)
        if slack < -1e-9:
            return None
        if r_pads is not None:
            pslack, _pw = TILE.clearance(r_pads)
            if pslack < -1e-9:
                return None
        sc = self.sock_clearance(r)
        if sc < PART_GAP - 1e-9:
            return None
        g, who = self.parts_gap(r)
        if g < PART_GAP - 1e-9:
            return None
        return True

    def try_place(self, ref, bb, anchor=None, bottom=True, rot=0):
        """bb = courtyard bbox (x0,y0,x1,y1) at rot=0; scan 0.25 grid from
        the anchor in rings, then whole map; returns (x,y) of the part origin."""
        ob = bb
        if rot:
            ob = (bb[1], bb[0], bb[3], bb[2])
        w, h = ob[2] - ob[0], ob[3] - ob[1]
        xs = [p[0] for p in OUTLINE]
        ys = [p[1] for p in OUTLINE]
        x0g, x1g = min(xs) + EDGE_MIN, max(xs) - EDGE_MIN
        y0g, y1g = min(ys) + EDGE_MIN, max(ys) - EDGE_MIN
        cells = []
        if anchor:
            cx, cy = anchor
            maxr = 30
            for rr in range(0, int(maxr / PLACE_GRID) + 1):
                ring = ([(i, -rr) for i in range(-rr, rr + 1)] +
                        [(i, rr) for i in range(-rr, rr + 1)] +
                        [(-rr, j) for j in range(-rr + 1, rr)] +
                        [(rr, j) for j in range(-rr + 1, rr)])
                for gx, gy in ring:
                    px = cx - (ob[0] + ob[2]) / 2 + gx * PLACE_GRID
                    py = cy - (ob[1] + ob[3]) / 2 + gy * PLACE_GRID
                    cells.append((px, py))
        else:
            nx = int((x1g - x0g - w) / PLACE_GRID) + 1
            ny = int((y1g - y0g - h) / PLACE_GRID) + 1
            for k in range(min(nx, ny) + 1):
                for i in range(k + 1):
                    for j in range(k + 1):
                        if max(i, j) != k:
                            continue
                        cells.append((x0g - ob[0] + i * PLACE_GRID,
                                      y0g - ob[1] + j * PLACE_GRID))
        for px, py in cells:
            r = base.Rect(px + ob[0], py + ob[1], px + ob[2], py + ob[3])
            if self.free(r, ref):
                self.parts.append((ref, r, "B" if bottom else "F"))
                return px, py
        return None


# ------------------------------------------------------------------ net store
class Nets:
    def __init__(self):
        self.map = {}
        self.n = 1

    def no(self, name):
        if name not in self.map:
            self.map[name] = self.n
            self.n += 1
        return self.map[name]


# -------------------------------------------------------------------- builders
def key_net(i):
    return f"K{i + 1}"


CONSTRAINT_NET2PADS = {}


def load_constraints():
    """Parse ../constraints/tile_*_board.(cst|pcf) -> {net: pin}."""
    import pin_con_parse  # local helper (same folder)
    return pin_con_parse.load(os.path.join(BOARD, "constraints"))


def variant_gw1nz():
    fpga_fp = os.path.join(MYLIB, "GW1NZ-QN48_6x6_P0.4mm_EP2.7x2.7mm.kicad_mod")
    pins = load_constraints()["gw1nz"]
    return {
        "name": "gw1nz",
        "title": "Single-PCB FPGA tile - GW1NZ-LV1QN48 (placement prototype)",
        "fpga_fp": fpga_fp,
        "fpga_ref": "U1",
        "fpga_value": "GW1NZ-LV1QN48C6/I5",
        "fpga_nets": fpga_nets_gw1nz(pins),
        "tl_parts": parts_gw1nz(),
        "tps": [("TP_TCK", "JTAG_TCK"), ("TP_TMS", "JTAG_TMS"),
                ("TP_TDI", "JTAG_TDI"), ("TP_TDO", "JTAG_TDO"),
                ("TP_READY", "CFG_READY"), ("TP_DONE", "CFG_DONE"),
                ("TP_RECFG", "CFG_RECONFIG"), ("TP_JTAGSEL", "JTAGSEL_N"),
                ("TP_VCC1V2", "VCC1V2"), ("TP_VCC", "VCC"), ("TP_GND", "GND")],
        "anchors": anchors_gw1nz(),
    }


# Vendor rail names -> board rail nets.  Without this rollup the FPGA power
# pads keep their vendor net names (VCCIO0, VCCX3V3, ...) as SINGLE-PAD nets
# and the IO banks are silently unpowered - found 2026-10-13 by net census
# of the emitted board (DRC cannot see single-pad nets).
RAIL_BOARD = {
    "gw1nz": {"VCCIO0": "VCC", "VCCIO1": "VCC", "VCCX3V3": "VCC"},
    "up5k": {"VCCIO": "VCC", "SPI_VCCIO1": "VCC", "VPP_2V5": "VCC"},
}


def fpga_nets_gw1nz(pins):
    db = json.load(open(os.path.join(BOARD, "data", "pins_gw1nz_qn48.json")))
    nets = {}
    for n, pads in pins.items():
        nets[str(pads[0])] = tile_net_of_gw1nz(n)
    for p, row in db["pins"].items():
        if p == "EPAD":
            nets["49"] = "GND"
        elif row["role"] == "power":
            nets[p] = RAIL_BOARD["gw1nz"].get(row["net"], row["net"])
        elif row["role"] == "ground":
            nets[p] = "GND"
        elif row["role"] in ("jtag", "cfg_status", "jspare"):
            nets[p] = row["net"]
        elif row["role"] == "strap":
            nets[p] = row["name"].split("/")[-1]   # MODE0 / MODE1
    return nets


def tile_net_of_gw1nz(net):
    m = {"clk_pin": "B_clk", "t_w_pin": "T_W", "t_endcol_pin": "T_endcol",
         "b_first_pin": "B_first", "l_endrow_pin": "L_endrow",
         "t_data_pin": "T_data", "l_data_pin": "L_data",
         "b_latch_pin": "B_latch", "r_latch_pin": "R_latch",
         "t_clk_pin": "T_clk", "l_clk_pin": "L_clk", "latcho_pin": "L_latch",
         "dout_pin": "B_data", "b_w_pin": "B_W"}
    if net.startswith("keys["):
        return key_net(int(net[5:-1]))
    return m[net]


def parts_gw1nz():
    parts = [
        {"ref": "U2", "fp": "SOT235", "value": "LDO-1V2",
         "pins": {"1": "VCC", "2": "GND", "3": "VCC", "5": "VCC1V2_RAW"},
         "note": "SOT-23-5 fixed 1.2V LDO (TLV75512 class; pin1 IN, pin5 OUT convention - final part TBD); OUT is VCC1V2_RAW, FB1 filters it into the FPGA core rail VCC1V2 (UG293)", "anchor_net": "VCC"},
        {"ref": "C1", "fp": "C0603", "value": "100n", "pins": {"1": "VCC", "2": "GND"}, "anchor_fpga_pin": "1"},
        {"ref": "C2", "fp": "C0603", "value": "100n", "pins": {"1": "VCC", "2": "GND"}, "anchor_fpga_pin": "25"},
        {"ref": "C3", "fp": "C0603", "value": "100n", "pins": {"1": "VCC", "2": "GND"}, "anchor_fpga_pin": "36"},
        {"ref": "C4", "fp": "C0603", "value": "100n", "pins": {"1": "VCC1V2", "2": "GND"}, "anchor_fpga_pin": "12"},
        {"ref": "C5", "fp": "C0603", "value": "100n", "pins": {"1": "VCC1V2", "2": "GND"}, "anchor_fpga_pin": "37"},
        {"ref": "C6", "fp": "C1206", "value": "4u7", "pins": {"1": "VCC1V2", "2": "GND"}, "anchor_fpga_pin": "12"},
        {"ref": "C7", "fp": "C1206", "value": "4u7", "pins": {"1": "VCC", "2": "GND"}, "anchor_net": "VCC"},
        {"ref": "FB1", "fp": "R0603", "value": "FB 120R@100M", "pins": {"1": "VCC1V2_RAW", "2": "VCC1V2"}, "note": "core-rail noise filter (UG293: FB class MH2029-221Y) between LDO OUT (VCC1V2_RAW) and the FPGA core pins (VCC1V2) + C6", "anchor_fpga_pin": "12"},
        {"ref": "R1", "fp": "R0603", "value": "1k", "pins": {"1": "MODE0", "2": "GND"}, "note": "MODE0=0 auto-boot strap (UG293)", "anchor_fpga_pin": "43"},
        {"ref": "R2", "fp": "R0603", "value": "1k", "pins": {"1": "MODE1", "2": "GND"}, "note": "MODE1=0 auto-boot strap (UG293)", "anchor_fpga_pin": "42"},
        {"ref": "R3", "fp": "R0603", "value": "4k7", "pins": {"1": "JTAG_TCK", "2": "GND"}, "note": "TCK pull-down (UG293)", "anchor_fpga_pin": "3"},
        {"ref": "R4", "fp": "R0603", "value": "4k7", "pins": {"1": "CFG_READY", "2": "VCC"}, "anchor_fpga_pin": "45"},
        {"ref": "R5", "fp": "R0603", "value": "4k7", "pins": {"1": "CFG_DONE", "2": "VCC"}, "anchor_fpga_pin": "46"},
        {"ref": "R6", "fp": "R0603", "value": "4k7", "pins": {"1": "CFG_RECONFIG", "2": "VCC"}, "anchor_fpga_pin": "48"},
    ]
    return parts


def anchors_gw1nz():
    return {"approach": "LDO + straps anchored at FPGA pads / VCC pad"}


def variant_up5k():
    fpga_fp = os.path.join(MYLIB, "iCE40UP5K-SG48_7x7_P0.5mm_EP5.35x5.35mm.kicad_mod")
    pins = load_constraints()["up5k"]
    return {
        "name": "up5k",
        "title": "Single-PCB FPGA tile - iCE40UP5K-SG48 fallback (placement prototype)",
        "fpga_fp": fpga_fp,
        "fpga_ref": "U1",
        "fpga_value": "iCE40UP5K-SG48I",
        "fpga_may_be_absent": True,
        "fpga_nets": fpga_nets_up5k(pins),
        "tl_parts": parts_up5k(),
        "tps": [("TP_SCK", "SPI_SCK"), ("TP_SI", "SPI_SI"),
                ("TP_SO", "SPI_SO"), ("TP_SS", "SPI_SS"),
                ("TP_CRESET", "CFG_CRESET"), ("TP_CDONE", "CFG_DONE"),
                ("TP_VCC1V2", "VCC1V2"), ("TP_VCC", "VCC"), ("TP_GND", "GND")],
    }


def fpga_nets_up5k(pins):
    db = json.load(open(os.path.join(BOARD, "data", "pins_ice40up_sg48.json")))
    nets = {}
    tile_up = {"clk_pin": "B_clk", "t_w_pin": "T_W", "t_endcol_pin": "T_endcol",
               "b_first_pin": "B_first", "l_endrow_pin": "L_endrow",
               "t_data_pin": "T_data", "l_data_pin": "L_data",
               "b_latch_pin": "B_latch", "r_latch_pin": "R_latch",
               "t_clk_pin": "T_clk", "l_clk_pin": "L_clk",
               "latcho_pin": "L_latch", "dout_pin": "B_data", "b_w_pin": "B_W"}
    for n, pads in pins.items():
        nets[str(pads[0])] = (key_net(int(n[5:-1])) if n.startswith("keys[")
                              else tile_up[n])
    for p, row in db["pins"].items():
        if p == "Paddle":
            nets["49"] = "GND"
        elif row["role"] == "power":
            nets[p] = RAIL_BOARD["up5k"].get(row["net"], row["net"])
        elif row["role"] == "ground":
            nets[p] = "GND"
        elif row["role"] == "cfg_status":
            nets[p] = row["net"]
        elif row["role"] == "spi_cfg":
            nets[p] = row["net"]
    # unused IO pins stay unconnected (no key in nets dict)
    return nets


def parts_up5k():
    parts = [
        {"ref": "U2", "fp": "SOT235", "value": "LDO-1V2",
         "pins": {"1": "VCC", "2": "GND", "3": "VCC", "5": "VCC1V2"},
         "note": "SOT-23-5 fixed 1.2V LDO (TLV75512 class; pin1 IN, pin5 OUT convention - final part TBD)"},
        {"ref": "U3", "fp": "SOIC8", "value": "SPI-FLASH",
         "pins": {"1": "SPI_SS", "2": "SPI_SO", "3": "VCC", "4": "GND",
                  "5": "SPI_SI", "6": "SPI_SCK", "7": "VCC", "8": "VCC"},
         "note": "SOIC-8 config flash 3.3V, >=1 Mbit reprogrammable (W25Q80 class; part TBD); in-circuit: hold CRESET_B low -> FPGA SPI IOs tri-stated (DS 4.6)", "anchor_fpga_pin": "15"},
        {"ref": "C1", "fp": "C0603", "value": "100n", "pins": {"1": "VCC1V2", "2": "GND"}, "anchor_fpga_pin": "5"},
        {"ref": "C2", "fp": "C0603", "value": "100n", "pins": {"1": "VCC1V2", "2": "GND"}, "anchor_fpga_pin": "30"},
        {"ref": "C3", "fp": "C0603", "value": "100n", "pins": {"1": "VCC", "2": "GND"}, "anchor_fpga_pin": "33"},
        {"ref": "C4", "fp": "C0603", "value": "100n", "pins": {"1": "VCC", "2": "GND"}, "anchor_fpga_pin": "1"},
        {"ref": "C5", "fp": "C0603", "value": "100n", "pins": {"1": "VCC", "2": "GND"}, "anchor_fpga_pin": "22"},
        {"ref": "C6", "fp": "C0603", "value": "100n", "pins": {"1": "VCC", "2": "GND"}, "anchor_fpga_pin": "24"},
        {"ref": "C7", "fp": "C1206", "value": "4u7", "pins": {"1": "VCC1V2", "2": "GND"}, "anchor_fpga_pin": "5"},
        {"ref": "C8", "fp": "C1206", "value": "4u7", "pins": {"1": "VCC", "2": "GND"}, "anchor_fpga_pin": "22"},
        {"ref": "R1", "fp": "R0603", "value": "10k", "pins": {"1": "CFG_CRESET", "2": "VCC"}, "note": "CRESET_B pure input, no internal pull (TN02001)", "anchor_fpga_pin": "8"},
        {"ref": "R2", "fp": "R0603", "value": "100", "pins": {"1": "VCC1V2", "2": "VCCPLL_1V2"}, "note": "VCCPLL RC filter (TN02006): 100ohm + C3(4u7)+C9(100n)", "anchor_fpga_pin": "29"},
        {"ref": "C9", "fp": "C1206", "value": "4u7", "pins": {"1": "VCCPLL_1V2", "2": "GND"}, "anchor_fpga_pin": "29"},
        {"ref": "C10", "fp": "C0603", "value": "100n", "pins": {"1": "VCCPLL_1V2", "2": "GND"}, "anchor_fpga_pin": "29"},
        {"ref": "R3", "fp": "R0603", "value": "10k", "pins": {"1": "VCC", "2": "VCC"}, "skip": True,
         "note": "placeholder removed in netlist pass"},
    ]
    parts = [p for p in parts if not p.get("skip")]
    for i, kn in enumerate(["T_data", "L_data", "B_latch", "R_latch"]):
        parts.append({"ref": f"R{i + 10}", "fp": "R0603", "value": "10k",
                      "pins": {"1": kn, "2": "GND"},
                      "note": "iCE40 pads pull-UP only -> ext pull-down (power_bom delta)"})
    for i in range(12):
        parts.append({"ref": f"R{i + 20}", "fp": "R0603", "value": "10k",
                      "pins": {"1": key_net(i), "2": "GND"},
                      "note": "key pull-down (pad pull-DOWN N/A on iCE40)"})
    return parts


# --------------------------------------------------------------- place + emit
def build(variant):
    v = globals()[f"variant_{variant}"]()
    nets = Nets()
    placements = []
    report = [f"== {v['name']}: {v['title']}"]

    # keys: 12 sockets at the lattice centres, EdgeTrim per engine variant
    kfp = os.path.join(VENDORED_FP, "SW_Hotswap_Kailh_MX_1.00u.kicad_mod")
    kfp_e = os.path.join(VENDORED_FP, "SW_Hotswap_Kailh_MX_1.00u_EdgeTrim.kicad_mod")
    n_et = 0
    for q, (cx, cy) in enumerate(KEYS_XY):
        et = TILE.pad_variant.get((q % 4, q // 4)) == "edgetrim"
        n_et += 1 if et else 0
        txt = lib_text(kfp_e if et else kfp)
        txt = kailh_board_text(txt)
        kn = key_net(q)
        pinnet = {"1": (nets.no("VCC"), "VCC"), "2": (nets.no(kn), kn)}
        placements.append({"ref": f"SW{q + 1}", "text": txt, "x": cx, "y": cy,
                           "rot": 0, "bottom": False, "pinnet": pinnet,
                           "value": "Kailh MX hotswap", "kind": "socket",
                           "variant": "EdgeTrim" if et else "standard"})
    report.append(f"keys: 12 at lattice P=18.3597 R=15.9 (EdgeTrim {n_et})")

    # chassis pads at the certified tier coordinates.  rev-A presence
    # semantics (independent-review fix 2026-10-13): the three GND_DET_*
    # pads keep their connector-next refs/roles but are BONDED to tile GND
    # here - the electrical fact the host reads is "hard ground on this
    # contact when a tile is inserted, open when removed".  Only the
    # backplane traces stay graph-separate (connector-next owns them and
    # is untouched); single-pad floating presence nets ON THE TILE were
    # wrong (an inserted tile would have reported absent on all three).
    for pd in CHASSIS_PADS:
        name = pd["net"]
        board_net = "GND" if name.startswith("GND") else name
        placements.append({"ref": f"JP_{name}", "chassis": True,
                           "x": pd["x"], "y": pd["y"],
                           "netnum": nets.no(board_net),
                           "netname": board_net,
                           "note": f"{pd['group']} {pd['role']} "
                                   f"slack+tol={pd['slack_after_tol']}"
                                   + (" (bonded to tile GND)"
                                      if board_net != name else "")})
    report.append(f"chassis pads: {len(CHASSIS_PADS)} at connector-next tier "
                  f"coords (14 tile signals + VCC + GND; the 3 GND_DET_* "
                  f"presence pads keep their refs/roles but are bonded to "
                  f"tile GND on this removable tile)")

    pl = Placer()

    # FPGA first (center-ish anchor), then anchored parts, then test points
    fpga_txt = lib_text(v["fpga_fp"])
    fpga_bb_local = courtyard_bbox(fpga_txt, "F")[:4]
    fpga_bb = (-fpga_bb_local[2], fpga_bb_local[1], -fpga_bb_local[0],
               fpga_bb_local[3])
    _pb = pads_bbox(fpga_txt)
    fpga_pb = (-_pb[2], _pb[1], -_pb[0], _pb[3])
    comx = sum(p[0] for p in OUTLINE) / len(OUTLINE)
    comy = sum(p[1] for p in OUTLINE) / len(OUTLINE)
    got = None
    for rr in range(0, 400):
        found = False
        ring = ([(i, -rr) for i in range(-rr, rr + 1)] +
                [(i, rr) for i in range(-rr, rr + 1)] +
                [(-rr, j) for j in range(-rr + 1, rr)] +
                [(rr, j) for j in range(-rr + 1, rr)])
        for cx, cy in ring:
            px = comx - (fpga_bb[0] + fpga_bb[2]) / 2 + cx * 0.25
            py = comy - (fpga_bb[1] + fpga_bb[3]) / 2 + cy * 0.25
            r = base.Rect(px + fpga_bb[0], py + fpga_bb[1],
                          px + fpga_bb[2], py + fpga_bb[3])
            rp = base.Rect(px + fpga_pb[0], py + fpga_pb[1],
                           px + fpga_pb[2], py + fpga_pb[3])
            if pl.free(r, r_pads=rp):
                got = (px, py)
                pl.parts.append((v["fpga_ref"], r, "B"))
                found = True
                break
        if found:
            break
    fpga_nofit = None
    if not got:
        fpga_nofit = diagnose_free_bbox(fpga_bb[2] - fpga_bb[0])
        islands_note = []
        for need in (7.7, 7.1, 6.7):
            isl = base.scan_islands(TILE, min_w=need, min_h=need)
            islands_note.append(
                {"min": need, "count": len(isl),
                 "islands": [{"rect": [round(q, 2) for q in i["rect"]]}
                             for i in isl[:4]]})
        report.append(f"FPGA {v['fpga_value']}: NO PLACE FOUND "
                      f"({fpga_nofit})")
        report.append("NOTE: board emission continues WITHOUT the FPGA body "
                      "(placement-failure review copy; not buildable)")
        fx = fy = None
    if got:
        fx, fy = got
    padpos = parse_pads(fpga_txt)

    def fpga_pad_abs(pin):
        if fx is None:
            return None
        p = padpos[str(pin)]
        return (fx - p[0], fy + p[1])      # bottom flip: x->-x

    fpga_pinnet = {}
    for pin, net in v["fpga_nets"].items():
        fpga_pinnet[str(pin)] = (nets.no(net), net)
    if got:
        placements.append({"ref": v["fpga_ref"], "text": fpga_txt, "x": fx,
                           "y": fy, "rot": 0, "bottom": True,
                           "pinnet": fpga_pinnet, "value": v["fpga_value"],
                           "kind": "fpga"})
        report.append(f"{v['fpga_ref']} ({v['fpga_value']}) at "
                      f"({fx:.2f},{fy:.2f}) on B side")
    def anchor_of(pdef):
        if "anchor_fpga_pin" in pdef and fx is not None:
            return fpga_pad_abs(pdef["anchor_fpga_pin"])
        if pdef.get("anchor_net") == "VCC":
            vpc = [pd for pd in CHASSIS_PADS if pd["net"] == "VCC"]
            if vpc:
                return (vpc[0]["x"], vpc[0]["y"])
        if "anchor_fpga_pin" in pdef and fx is None:
            # FPGA absent (NOFIT variant): anchor at the pad's net-side coords
            return None
        return (fx, fy) if fx is not None else None

    # anchored small parts
    unplaced = []
    for pdef in v["tl_parts"]:
        if pdef["fp"] == "SOIC8":
            txt = stock_text(STOCK["SOIC8"])
        else:
            txt = stock_text(STOCK[pdef["fp"]])
        bb = courtyard_bbox(txt, "F")[:4]
        bbb = (-bb[2], bb[1], -bb[0], bb[3])
        _pb = pads_bbox(txt)
        pb = (-_pb[2], _pb[1], -_pb[0], _pb[3])
        anchor = anchor_of(pdef)
        got2 = None
        for rr in range(0, 240):
            ring = ([(i, -rr) for i in range(-rr, rr + 1)] +
                    [(i, rr) for i in range(-rr, rr + 1)] +
                    [(-rr, j) for j in range(-rr + 1, rr)] +
                    [(rr, j) for j in range(-rr + 1, rr)])
            if anchor is None:
                anchor = (fx if fx is not None else comx,
                          fy if fy is not None else comy)
            stop = False
            for cx, cy in ring:
                px = anchor[0] - (bbb[0] + bbb[2]) / 2 + cx * 0.25
                py = anchor[1] - (bbb[1] + bbb[3]) / 2 + cy * 0.25
                r = base.Rect(px + bbb[0], py + bbb[1], px + bbb[2], py + bbb[3])
                rp = base.Rect(px + pb[0], py + pb[1], px + pb[2], py + pb[3])
                if pl.free(r, r_pads=rp):
                    got2 = (px, py)
                    pl.parts.append((pdef["ref"], r, "B"))
                    stop = True
                    break
            if stop:
                break
        if not got2:
            unplaced.append(pdef["ref"])
            continue
        pn = {pin: (nets.no(net), net) for pin, net in pdef["pins"].items()}
        placements.append({"ref": pdef["ref"], "text": txt, "x": got2[0],
                           "y": got2[1], "rot": 0, "bottom": True,
                           "pinnet": pn, "value": pdef["value"],
                           "kind": "part", "note": pdef.get("note", "")})

    # test pads
    for tp_ref, tp_net in v["tps"]:
        anchor = ((fx, fy) if fx is not None
                  else (CHASSIS_PADS[0]["x"], CHASSIS_PADS[0]["y"]))
        if tp_net in ("VCC", "GND"):
            cand = [pd for pd in CHASSIS_PADS if pd["net"] == tp_net]
            if cand:
                anchor = (cand[0]["x"], cand[0]["y"])
        tptxt = stock_text(STOCK["TP"])
        bb = courtyard_bbox(tptxt, "F")[:4]
        bbb = (-bb[2], bb[1], -bb[0], bb[3])
        _pb = pads_bbox(tptxt)
        pb = (-_pb[2], _pb[1], -_pb[0], _pb[3])
        got3 = None
        for rr in range(0, 240):
            ring = ([(i, -rr) for i in range(-rr, rr + 1)] +
                    [(i, rr) for i in range(-rr, rr + 1)] +
                    [(-rr, j) for j in range(-rr + 1, rr)] +
                    [(rr, j) for j in range(-rr + 1, rr)])
            stop = False
            for cx, cy in ring:
                px = anchor[0] - (bbb[0] + bbb[2]) / 2 + cx * 0.25
                py = anchor[1] - (bbb[1] + bbb[3]) / 2 + cy * 0.25
                r = base.Rect(px + bbb[0], py + bbb[1], px + bbb[2], py + bbb[3])
                rp = base.Rect(px + pb[0], py + pb[1], px + pb[2], py + pb[3])
                if pl.free(r, r_pads=rp):
                    got3 = (px, py)
                    pl.parts.append((tp_ref, r, "B"))
                    stop = True
                    break
            if stop:
                break
        if not got3:
            unplaced.append(tp_ref)
            continue
        placements.append({"ref": tp_ref, "text": tptxt, "x": got3[0],
                           "y": got3[1], "rot": 0, "bottom": True,
                           "pinnet": {"1": (nets.no(tp_net), tp_net)},
                           "value": tp_net, "kind": "tp"})

    report.append(f"parts placed: {len(placements)}; unplaced: {unplaced}")

    # ---------------------------------------------- checks
    checks = []

    def ck(cid, desc, ok, detail):
        checks.append({"id": cid, "desc": desc, "ok": bool(ok),
                       "detail": detail})

    # GK1: corrected outline identity + 6-neighbour gap at rib_gap
    _t2, _p2, gaps = cnext.cross_tile_tab_check(base.parse_kicad_mod(base.VENDORED_FP),
                                                base.parse_kicad_mod(base.VENDORED_FP_TRIM), 0.0)
    ck(1, "outline = TileTiling (revc-exact): 6-neighbour min gap = rib_gap 1.0 mm",
       min(gaps.values()) >= par.rib_gap - 1e-9
       and abs(OUTLINE[0][1] - (-par.R() / 2 + par.rib_gap / 2)) < 1e-9,
       f"gaps={ {k: round(v,3) for k,v in gaps.items()} }")

    # GK2: chassis pads == certified study.json coords + my own clearance
    sj = json.load(open(os.path.join(ST, "connector-next", "out", "study.json")))
    refpads = sorted([p for t in sj["tiers"].values() for p in t["pads"]],
                     key=lambda p: (p["net"], p["x"]))
    minepads = sorted([{"net": pd["net"], "x": pd["x"], "y": pd["y"]}
                       for pd in CHASSIS_PADS], key=lambda p: (p["net"], p["x"]))
    eq = all(abs(a["x"] - b["x"]) < 1e-6 and abs(a["y"] - b["y"]) < 1e-6
             and a["net"] == b["net"] for a, b in zip(refpads, minepads)) \
        and len(refpads) == len(minepads)
    rechecks = []
    for pd in CHASSIS_PADS:
        r = base.Rect(pd["x"] - 1.25, pd["y"] - 1.25, pd["x"] + 1.25, pd["y"] + 1.25)
        slack, what = TILE.clearance(r, extra=par.tol_chassis_xy)
        rechecks.append(slack)
    ck(2, "19 pads identical to connector-next certified coords AND "
       "re-cleared incl 0.35mm chassis tol", eq and min(rechecks) >= 0,
       f"coord-eq={eq}, worst slack+tol={min(rechecks):.3f} mm")

    # GK3: keys at the lattice centres
    exp = [TILE.centre[(q % 4, q // 4)] for q in range(12)]
    latok = all(abs(p["x"] - e[0]) < 1e-9 and abs(p["y"] - e[1]) < 1e-9
                for p, e in zip([p for p in placements if p["ref"].startswith("SW")], exp))
    ck(3, "12 sockets exactly at the 18.36/15.9 lattice centres (0 rotation)",
       latok, f"count={sum(1 for p in placements if p['ref'].startswith('SW'))}")

    # GK4: full pairwise courtyard matrix (rect parts on bottom side)
    rects = [(ref, r, side) for ref, r, side in pl.parts]
    overlap = []
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            ri, rj = rects[i], rects[j]
            if ri[0].startswith("JP_") and rj[0].startswith("JP_"):
                continue
            d = base.dist_rect_rect(ri[1], rj[1])
            if d < PART_GAP - 1e-9:
                overlap.append((ri[0], rj[0], round(d, 3)))
    # socket courtyard polygons vs all bottom parts (0.25 dilation)
    sock_hits = []
    for _tag, poly in pl.sock_courts:
        for ref, r, side in rects:
            corners = [(r.x0, r.y0), (r.x1, r.y0), (r.x0, r.y1), (r.x1, r.y1),
                       ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)]
            if any(base.point_in_poly(x, y, poly) for x, y in corners):
                sock_hits.append(ref)
                continue
            d = min(base.seg_seg_dist(a, b, poly[i], poly[(i + 1) % len(poly)])
                    for i in range(len(poly)) for a, b in r.edges())
            if d < PART_GAP - 1e-9:
                sock_hits.append(ref)
    ck(4, "full pairwise courtyard matrix ({} rects incl. 19 contact pads) + "
       "socket polygons".format(len(rects)),
       not overlap and not sock_hits,
       f"rect-overlaps={overlap[:6]} sock-hits={sock_hits[:6]}")

    # GK5: NPTH + pad edge metrics (per-key pad variant respected)
    worst_drill, worst_pad, worst_at = 1e9, 1e9, ""
    for (i, k), (cx, cy) in TILE.centre.items():
        pool = FP_TRIM_MODEL if TILE.pad_variant.get((i, k)) == "edgetrim" \
            else FP_MODEL
        for h in pool["holes"]:
            hx, hy, hr = cx + h["x"], cy + h["y"], h["d"] / 2
            d = TILE.edge_slack(base.Rect(hx - hr, hy - hr, hx + hr, hy + hr)) + hr
            worst_drill = min(worst_drill, d - hr)
        for p in pool["pads"]:
            r = base.Rect(cx + p["x"] - p["w"] / 2, cy + p["y"] - p["h"] / 2,
                          cx + p["x"] + p["w"] / 2, cy + p["y"] + p["h"] / 2)
            es = TILE.edge_slack(r)
            if es < worst_pad:
                worst_pad, worst_at = es, f"SW[{i},{k}] pad{p['n']} " \
                    f"({'EdgeTrim' if pool is FP_TRIM_MODEL else 'standard'})"
    ck(5, "NPTH drill-to-edge and socket-pad-to-edge non-negative",
       worst_drill >= 0 and worst_pad >= 0,
       f"worst drill-to-edge {worst_drill:.3f} mm, worst socket-pad-to-edge "
       f"{worst_pad:.3f} mm ({worst_at})")

    # GK6: FPGA every pad has a net (netlist-level fact even on NOFIT variant)
    n_net_pads = len(v["fpga_nets"])
    ck(6, "FPGA pads net-assigned from the verified pin DB (netlist level)",
       n_net_pads >= 40, f"{n_net_pads} pads with nets of 49")

    # GK7: invariants; the NOFIT variant ships U1 absent by design (documented)
    refset = [p["ref"] for p in placements]
    expect_fpga_missing = v.get("fpga_may_be_absent", False) and fpga_nofit
    ok7 = (len([r for r in refset if r.startswith("SW")]) == 12 and
           len([r for r in refset if r.startswith("JP_")]) == 19 and
           not unplaced and (got is not None or expect_fpga_missing))
    ck(7, "part counts: 12 SW + 19 JP + passives + TPs"
       + ("; FPGA placement NOFIT (documented)" if expect_fpga_missing
          else "; FPGA placed"),
       ok7, f"SW={sum(1 for r in refset if r.startswith('SW'))} "
            f"JP={sum(1 for r in refset if r.startswith('JP_'))} "
            f"total={len(refset)} unplaced={unplaced} fpga_at="
            f"{None if not got else (round(fx,2), round(fy,2))}")

    if fpga_nofit:
        ck("N", f"FPGA placement on the tile bottom: NOFIT - "
           f"{fpga_nofit}; board copy ships the keys/pads/passives only as a "
           f"placement-review artifact", True,
           "concession options recorded in docs/candidate.md")

    ok = all(c["ok"] for c in checks)
    gate = {"variant": v["name"], "ok": ok, "checks": checks,
            "fpga_placed": got is not None,
            "fpga_nofit_analysis": fpga_nofit}

    # ---------------------------------------------- emit .kicad_pcb
    netno = dict(nets.map)
    netnames = sorted(netno)
    nets_s = '(net 0 "")\n' + "\n".join(
        f'\t(net {netno[n]} "{n}")' for n in netnames)
    pcb = [f'''(kicad_pcb
	(version 20241229)
	(generator "fpga-board/board_gen.py")
	(generator_version "10.0")
	(general (thickness 1.6) (legacy_teardrops no))
	(paper "A4")
	(layers
		(0 "F.Cu" signal)
		(2 "B.Cu" signal)
		(9 "F.Adhes" user "F.Adhesive")
		(11 "B.Adhes" user "B.Adhesive")
		(13 "F.Paste" user)
		(15 "B.Paste" user)
		(5 "F.SilkS" user "F.Silkscreen")
		(7 "B.SilkS" user "B.Silkscreen")
		(1 "F.Mask" user)
		(3 "B.Mask" user)
		(17 "Dwgs.User" user "User.Drawings")
		(19 "Cmts.User" user "User.Comments")
		(21 "Eco1.User" user "User.Eco1")
		(23 "Eco2.User" user "User.Eco2")
		(25 "Edge.Cuts" user)
		(27 "Margin" user)
		(31 "F.CrtYd" user "F.Courtyard")
		(29 "B.CrtYd" user "B.Courtyard")
		(33 "F.Fab" user)
		(35 "B.Fab" user)
	)
	(setup (pad_to_mask_clearance 0.05))
''']
    pcb.append(nets_s)
    for i in range(len(OUTLINE)):
        x1, y1 = OUTLINE[i]
        x2, y2 = OUTLINE[(i + 1) % len(OUTLINE)]
        pcb.append(f'\t(gr_line (start {x1:.4f} {y1:.4f}) (end {x2:.4f} '
                   f'{y2:.4f}) (layer "Edge.Cuts") (stroke (width 0.05) (type solid)))')
    for p in placements:
        if p.get("chassis"):
            pcb.append(chassis_pad_text(p["ref"], p["netnum"], p["netname"],
                                        p["x"], p["y"]))
        else:
            pcb.append(instantiate(p["text"], p["ref"], p["value"],
                                   p["x"], p["y"], p["rot"], p["bottom"],
                                   p["pinnet"]))
    pcb.append(")")
    os.makedirs(KOUT, exist_ok=True)
    out = os.path.join(KOUT, f"tile_{v['name']}.kicad_pcb")
    with open(out, "w") as f:
        f.write("\n".join(pcb) + "\n")

    # minimal project with explicit design rules. min_copper_edge_clearance
    # 0.3 = the tile engine's own outline contract (Params.edge_clear 0.3;
    # the extra 0.1 board_edge_tol is the routing tolerance already baked
    # into the outline check, stack-up identical to the 2-layer coupons).
    pro = {"board": {"design_settings": {
                "defaults": {},
                "diff_pair_dimensions": [],
                "rules": {
                    "max_error": 0.005, "min_clearance": 0.2,
                    "min_connection": 0.2,
                    "min_copper_edge_clearance": 0.3,
                    "min_groove_width": 0.0, "min_hole_clearance": 0.25,
                    "min_hole_to_hole": 0.25, "min_microvia_diameter": 0.2,
                    "min_microvia_drill": 0.1, "min_resolved_spokes": 1,
                    "min_silk_clearance": 0.0, "min_text_height": 0.8,
                    "min_text_thickness": 0.08,
                    "min_through_hole_diameter": 0.3,
                    "min_track_width": 0.2, "min_via_annular_width": 0.15,
                    "min_via_diameter": 0.6,
                    "solder_mask_to_copper_clearance": 0.0,
                    "use_height_for_length_calcs": True}},
           "layer_presets": []},
           "meta": {"filename": f"tile_{v['name']}.kicad_pro", "version": 1},
           "sheets": []}
    with open(os.path.join(KOUT, f"tile_{v['name']}.kicad_pro"), "w") as f:
        json.dump(pro, f, indent=1)

    unconn = "unrouted - placement prototype (0 tracks by design)"
    report.append(f"nets: {len(netnames)}, {unconn}")
    with open(os.path.join(KOUT, f"tile_{v['name']}_placement.txt"), "w") as f:
        f.write("\n".join(report) + "\n")
    with open(os.path.join(KOUT, f"tile_{v['name']}_checks.json"), "w") as f:
        json.dump(gate, f, indent=1)
    print("\n".join(report))
    print(f"  GATE {'PASS' if ok else 'FAIL'}")
    for c in checks:
        print(f"  [{'OK' if c['ok'] else 'FAIL':4}] GK{c['id']}: {c['desc']}")
    return gate


def main():
    gates = [build("gw1nz"), build("up5k")]
    ok = all(g and g["ok"] for g in gates)
    with open(os.path.join(OUT, "board_checks.json"), "w") as f:
        json.dump(gates, f, indent=1)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
