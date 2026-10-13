#!/usr/bin/env python3
"""Generate KiCad candidate placement boards for the discrete-spld variants.

Output per variant: boards/<variant>/tile_<variant>.kicad_pcb with
  * the stepped tile outline + 12 Kailh MX hot-swap key footprints on the
    18.36 mm equilateral lattice (P = 18.3597, R = 15.9),
  * 28 chassis contact pads + 6 detection-strap pads at the exact positions
    from connectors/out/placement.json (the authoritative drop-in geometry),
  * all logic ICs, passives (10k pulls, 100R key series, 33R series),
    decoupling (100n per IC + 4u7 bulk) and labelled test points placed on
    the BOTTOM side in the collision-free space between key sockets,
  * every pad bound to its net from circuits/<variant>.json (authoritative
    connectivity; the circuit JSONs themselves are simulation-proven).

Nothing is routed.  The board states are PLACEMENT prototypes: the check
report prints the honest counts (0 routed, N nets unrouted) plus independent
courtyard-collision and off-board checks; `kicad-cli pcb drc` is run on top
when available for an independent second opinion.
"""
import json
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import rotation_study as rs

BASE = os.path.join(os.path.dirname(__file__), '..')
REPO = os.path.abspath(os.path.join(BASE, '..', '..', '..', '..'))
CONN = os.path.join(REPO, 'hardware/experiments/simple-tile/connectors/out/placement.json')
CONN_NEXT = os.path.join(REPO, 'hardware/experiments/simple-tile/connector-next/out/study.json')
FLAT_FP = '/app/extensions/Library/Footprints/footprints'
VENDORED_FP = os.path.join(REPO, 'hardware/kicad/lib/Switch_Keyboard_Hotswap_Kailh.pretty')

P = 18.359738560230102   # lattice pitch (mm) - connectors study
R = 15.9                 # row spacing (mm)

# footprint sources within the flatpak / repo
FP_SRC = {
    'Package_SO:SOIC-16_3.9x9.9mm_P1.27mm':
        f'{FLAT_FP}/Package_SO.pretty/SOIC-16_3.9x9.9mm_P1.27mm.kicad_mod',
    'Package_SO:SSOP-8_2.95x2.8mm_P0.65mm':
        f'{FLAT_FP}/Package_SO.pretty/SSOP-8_2.95x2.8mm_P0.65mm.kicad_mod',
    'Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm':
        f'{FLAT_FP}/Package_SO.pretty/TSSOP-24_4.4x7.8mm_P0.65mm.kicad_mod',
    'Package_SO:TSSOP-16_4.4x5mm_P0.65mm':
        f'{FLAT_FP}/Package_SO.pretty/TSSOP-16_4.4x5mm_P0.65mm.kicad_mod',
    'Package_TO_SOT_SMD:SOT-23-5':
        f'{FLAT_FP}/Package_TO_SOT_SMD.pretty/SOT-23-5.kicad_mod',
    'Resistor_SMD:R_0603_1608Metric':
        f'{FLAT_FP}/Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod',
    'Capacitor_SMD:C_0603_1608Metric':
        f'{FLAT_FP}/Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod',
    'Capacitor_SMD:C_1206_3216Metric':
        f'{FLAT_FP}/Capacitor_SMD.pretty/C_1206_3216Metric.kicad_mod',
    'TestPoint:TestPoint_Pad_D1.0mm':
        f'{FLAT_FP}/TestPoint.pretty/TestPoint_Pad_D1.0mm.kicad_mod',
    'Switch_Keyboard_Hotswap_Kailh:SW_Hotswap_Kailh_MX_1.00u':
        f'{VENDORED_FP}/SW_Hotswap_Kailh_MX_1.00u.kicad_mod',
    'Switch_Keyboard_Hotswap_Kailh:SW_Hotswap_Kailh_MX_1.00u_EdgeTrim':
        f'{VENDORED_FP}/SW_Hotswap_Kailh_MX_1.00u_EdgeTrim.kicad_mod',
}

_cache = {}


def _arc_convert(fp_text):
    """Convert old-format fp_arc (start/end/angle) to KiCad-10 (start/mid/end).
    Sweep geometry computed exactly; used for the vendored Kailh footprint
    (written in an older KiCad format)."""
    import math as m

    def mid_of(sx, sy, ex, ey, deg):
        th = m.radians(deg)
        vx, vy = ex - sx, ey - sy
        L = m.hypot(vx, vy)
        if L < 1e-9 or abs(th) < 1e-9:
            return (sx + vx / 2, sy + vy / 2)
        # center on the perpendicular bisector; side by sweep sign
        r = L / (2 * m.sin(abs(th) / 2))
        a = L / (2 * m.tan(abs(th) / 2))
        mx, my = (sx + ex) / 2, (sy + ey) / 2
        nx, ny = -vy / L, vx / L
        # KiCad angle>0: CW on screen (y down); center sits on left normal
        sgn = 1 if deg > 0 else -1
        cx, cy = mx + sgn * a * nx, my + sgn * a * ny
        # arc midpoint = center + r * unit(mid-chord direction away from center)
        dx, dy = mx - cx, my - cy
        dl = m.hypot(dx, dy)
        if dl < 1e-9:
            return (mx, my)
        return (cx + dx / dl * r, cy + dy / dl * r)

    repl_map = {}
    for blk in _sexpr_blocks(fp_text, 'fp_arc'):
        mm = re.search(r'\(start (-?[\d.]+) (-?[\d.]+)\)\s*'
                       r'\(end (-?[\d.]+) (-?[\d.]+)\)\s*'
                       r'\(angle (-?[\d.]+)\)', blk)
        if not mm:
            repl_map[blk] = blk
            continue
        sx, sy, ex, ey, deg = (float(mm.group(k)) for k in range(1, 6))
        mx, my = mid_of(sx, sy, ex, ey, deg)
        rest = blk[mm.end():].rstrip()
        assert rest.endswith(')')
        rest = rest[:-1]   # drop the block's closing paren
        repl_map[blk] = (f'(fp_arc (start {sx} {sy}) (mid {mx:.4f} {my:.4f}) '
                         f'(end {ex} {ey}){rest})')
    out = fp_text
    for a, b in repl_map.items():
        out = out.replace(a, b)
    return out


def read_fp(libref):
    """Footprint file contents, cached; flatpak paths read via flatpak cat."""
    if libref in _cache:
        return _cache[libref]
    src = FP_SRC[libref]
    if src.startswith('/app/'):
        out = subprocess.run(['flatpak', 'run', '--command=cat',
                              'org.kicad.KiCad', src],
                             capture_output=True, text=True, check=True).stdout
    else:
        out = open(src).read()
    _cache[libref] = out
    return out


def _kailh_bcourtyard_close(fp_text):
    """The vendored Kailh socket's B.CrtYd is two OPEN polyline arms (socket
    contact keep-out arms) -> KiCad flags 'malformed_courtyard'.  In OUR board
    copy only, replace them with one closed rect covering the arms' bbox
    ((-6.05,-6.85)..(4.85,-0.75): a conservative superset of the arms; the
    placement model is unchanged because the island map was already carved
    from the socket obstacles).  The vendored library file is not touched.
    """
    blocks = _sexpr_blocks(fp_text, 'fp_line') + _sexpr_blocks(fp_text, 'fp_arc')
    xs, ys = [], []
    rm = []
    for blk in blocks:
        if 'B.CrtYd' not in blk:
            continue
        rm.append(blk)
        for x, y in re.findall(r'\((?:start|end|mid)\s+(-?[\d.]+)\s+(-?[\d.]+)', blk):
            xs.append(float(x)); ys.append(float(y))
    if not rm:
        return fp_text
    for blk in rm:
        fp_text = fp_text.replace(blk, '', 1)
    # closed courtyard = the arms' chain rendered as one fp_poly, using the
    # same polygon the placement engine models (COURT_POLY)
    from rotation_study import COURT_POLY
    pts = ' '.join(f'(xy {x:.3f} {y:.3f})' for x, y in COURT_POLY)
    closed = (f'\t(fp_poly (pts {pts}) (layer "B.CrtYd") (width 0.05) '
              f'(fill none)\n\t\t(uuid "b1ac10a1-b0a4-4d00-9c00-d3fd00c00a77"))\n')
    # insert right before the first pad
    i = fp_text.index('(pad')
    return fp_text[:i] + closed + fp_text[i:]


def read_fp_board(libref):
    """read_fp + format normalization for embedding into our v10 board."""
    t = _arc_convert(read_fp(libref))
    if libref.startswith('Switch_Keyboard_Hotswap_Kailh:'):
        t = _kailh_bcourtyard_close(t)
        # the F.CrtYd +/-7.25 square is the FRONT-side switch keep-out; these
        # tiles have a pure-key front face (every F item is another identical
        # key on the same P=18.36 lattice, minimum spacing 18.36 > 14.5), so
        # the square has no function here; dropping it makes KiCad's court
        # check use the real (closed polygon) B-side courtyard only.
        for blk in _sexpr_blocks(t, 'fp_line'):
            if 'F.CrtYd' in blk:
                t = t.replace(blk, '', 1)
    return t


def _sexpr_blocks(text, tag):
    """Yield balanced-paren blocks starting with "(tag "."""
    out, i = [], 0
    needle = f'({tag}'
    while True:
        j = text.find(needle, i)
        if j < 0:
            break
        depth = 0
        k = j
        while k < len(text):
            ch = text[k]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    out.append(text[j:k + 1])
                    break
            k += 1
        i = k + 1
    return out


def courtyard_bbox(fp_text, layer='F'):
    """Bounding box of the footprint courtyard on the given side layer.
    Falls back to pad extents + 0.5 mm and says so."""
    want = f'"{layer}.CrtYd"'
    alt = f'{layer}.CrtYd'
    xs, ys = [], []
    for kind in ('fp_line', 'fp_rect', 'fp_poly', 'fp_circle', 'fp_arc'):
        for blk in _sexpr_blocks(fp_text, kind):
            if want not in blk and alt not in blk:
                continue
            for xm, ym in re.findall(
                    r'\((?:start|end|at|xy|center)\s+(-?[\d.]+)\s+(-?[\d.]+)', blk):
                xs.append(float(xm)); ys.append(float(ym))
    if not xs:
        for xm, ym in re.findall(
                r'\(pad\s+"?[0-9A-Za-z]+"?\s+\w+\s+\w+\s+\(at\s+(-?[\d.]+)\s+(-?[\d.]+)', fp_text):
            xs.append(float(xm)); ys.append(float(ym))
        if not xs:
            return (0, 0, 0, 0, 'EMPTY')
        return (min(xs) - 0.5, min(ys) - 0.5, max(xs) + 0.5, max(ys) + 0.5,
                'padbbox+0.5mm')
    return (min(xs), min(ys), max(xs), max(ys), f'{layer}-courtyard')


def parse_pads(fp_text):
    """pad number -> (x, y) from library text."""
    return {num: (float(x), float(y)) for num, x, y in re.findall(
        r'\(pad\s+"?(\d+)"?\s+\w+\s+\w+\s+\(at\s+(-?[\d.]+)\s+(-?[\d.]+)', fp_text)}


SEXPR_NUM = re.compile(r'\(net\s+\d+\s+"[^"]*"\)')

_PAD_RE = re.compile(
    r'\(pad\s+"?(\d+)"?\s+(\w+)\s+(\w+)\s+\(at\s+(-?[\d.]+)\s+(-?[\d.]+)'
    r'(?:\s+(-?[\d.]+))?\)\s+\(size\s+(-?[\d.]+)\s+(-?[\d.]+)\)')


def parse_pads_rect(fp_text):
    """pad number -> (cx, cy, w, h, rot) (any pad class)."""
    out = {}
    for num, at, shape, x, y, rot, w, h in _PAD_RE.findall(fp_text):
        out[num] = (float(x), float(y), float(w), float(h),
                    float(rot) if rot else 0.0)
    return out


_RECT_CACHE = {}


def _pads_rect_cached(libref):
    if libref not in _RECT_CACHE:
        _RECT_CACHE[libref] = parse_pads_rect(read_fp(libref))
    return _RECT_CACHE[libref]


def seg_hits_box(s, e, b):
    """Does segment s->e touch axis-aligned box b?  (crisp, no libs)"""
    (x1, y1), (x2, y2) = s, e
    x0, y0, x3, y3 = b
    for px, py in ((x1, y1), (x2, y2)):
        if x0 <= px <= x3 and y0 <= py <= y3:
            return True
    if max(x1, x2) < x0 or min(x1, x2) > x3 or max(y1, y2) < y0 or min(y1, y2) > y3:
        return False

    def _seg_int(a1, a2, b1, b2):
        d = ((b2[0] - b1[0]) * (a2[1] - a1[1]) - (b2[1] - b1[1]) * (a2[0] - a1[0]))
        if abs(d) < 1e-12:
            return False
        t = ((b1[0] - a1[0]) * (a2[1] - a1[1]) - (b1[1] - a1[1]) * (a2[0] - a1[0])) / d
        u = ((b1[0] - a1[0]) * (b2[1] - a1[1]) - (b1[1] - a1[1]) * (b2[0] - a1[0])) / d
        return 0 <= t <= 1 and 0 <= u <= 1
    for a, bb in (((x0, y0), (x3, y0)), ((x3, y0), (x3, y3)),
                  ((x3, y3), (x0, y3)), ((x0, y3), (x0, y0))):
        if _seg_int((x1, y1), (x2, y2), a, bb):
            return True
    return False


def point_box_dist(px, py, b):
    dx = max(b[0] - px, 0, px - b[2])
    dy = max(b[1] - py, 0, py - b[3])
    return math.hypot(dx, dy)


_GEOM_XY = re.compile(r'(\((?:at|start|end|mid|center|xy)\s+)(-?[\d.]+)(\s+)(-?[\d.]+)')


def _neg(s):
    v = repr(-float(s))
    return '0' if v == '-0.0' else v


def mirror_footprint_text(t):
    """Mirror a footprint's geometry across the Y axis (x -> -x), the way
    pcbnew flips a footprint to the bottom side.  Applies to pads, drawings,
    text/property positions.  Sizes/widths are untouched."""
    return _GEOM_XY.sub(lambda m: m.group(1) + _neg(m.group(2))
                        + m.group(3) + m.group(4), t)


def instantiate(fp_text, ref, value, x, y, rot, bottom, netmap, pinnet):
    """Turn a library footprint into a placed pcb instance with nets."""
    # localized edits: header ref/value + placement + pad nets + layer flip;
    # old-format vendored libs use 'module' - normalize the header too
    t = fp_text
    if t.startswith('(module '):
        t = '(footprint ' + t[len('module '):]
    # flip the SOURCE LIBRARY geometry first (before the placement line is
    # injected): mirror x -> -x, exactly what pcbnew's Flip does.  Mirroring
    # is NOT optional: without it a real chip's pins land on mirrored copper.
    if bottom:
        t = mirror_footprint_text(t)
    t = re.sub(r'\(footprint\s+"?[^"\s]+"?', f'(footprint "{ref}"', t, count=1)
    # set reference and value texts (KiCad-10 property style AND old fp_text)
    def set_prop(name, val, text):
        text = re.sub(r'(\(property\s+"' + name.capitalize() + r'"\s+)"[^"]*"',
                      r'\1"' + val + '"', text, count=1)
        pat = re.compile(r'(\(fp_text\s+' + name + r'\s+)"?[^"\s)]*"?')
        return pat.sub(r'\1"' + val + '"', text, count=1)
    t = set_prop('reference', ref, t)
    t = set_prop('value', value, t)
    # placement
    t = re.sub(r'(\(footprint\s+"[^"]+"\s*\n(?:\s*\([^)]*\)\s*\n)*?\s*)\(at\s+[\d.-]+\s+[\d.-]+(\s+[\d.-]+)?\)',
               lambda m: m.group(0), t)
    # simpler: inject placement right after the header's (layer ...) line
    head_end = t.index('(layer')
    line_end = t.index('\n', head_end)
    t = (t[:line_end] + f'\n\t(at {x:.4f} {y:.4f} {rot})\n\t(descr "placed by board_gen")'
         + t[line_end:])
    # pad nets: robust balanced-paren rewrite (handles old single-line pads)
    pad_blocks = []
    for blk in _sexpr_blocks(t, 'pad'):
        m = re.match(r'\(pad\s+"?([0-9A-Za-z_]+)"?\s', blk)
        if not m:
            pad_blocks.append((blk, blk))
            continue
        num = m.group(1)
        netnum, netname = pinnet.get(num, (0, ''))
        body = SEXPR_NUM.sub('', blk)
        if netnum:
            assert body.rstrip().endswith(')')
            body = body.rstrip()[:-1] + f' (net {netnum} "{netname}"))'
        pad_blocks.append((blk, body))
    for blk, body in pad_blocks:
        if blk != body:
            t = t.replace(blk, body, 1)
        else:
            t = t.replace(blk, body, 1)
    if bottom:
        # swap all front layers to the back (geometry already mirrored above)
        for a, b in (('F.Cu', 'B.Cu'), ('F.Paste', 'B.Paste'),
                     ('F.Mask', 'B.Mask'), ('F.SilkS', 'B.SilkS'),
                     ('F.CrtYd', 'B.CrtYd'), ('F.Fab', 'B.Fab')):
            t = t.replace(f'"{a}"', f'"{b}"')
        # back-side text needs mirror justification
        out_parts = []
        for tag in ('fp_text', 'property'):
            for blk in _sexpr_blocks(t, tag):
                nb = blk
                if '"B.' in blk and 'justify' not in blk:
                    nb = blk.replace('(effects', '(effects (justify mirror)', 1)
                out_parts.append((blk, nb))
        for blk, nb in out_parts:
            if blk != nb:
                t = t.replace(blk, nb)
    return t


class ChassisPad:
    LIB = ('ChassisPad_2.5mm', 'd=2.5mm round SMD pad + 1.0mm drill-free '
           '(spring contact target, connectors study variant A)')

    @staticmethod
    def text(ref, netnum, netname, x, y):
        return f'''(footprint "{ref}"
	(layer "B.Cu")
	(at {x:.4f} {y:.4f} 0)
	(descr "chassis spring contact pad (placement study position)")
	(fp_text reference "{ref}" (at 0 -2.1) (layer "B.Fab") (effects (font (size 0.8 0.8) (thickness 0.15)) (justify mirror)))
	(fp_text value "PAD2.5" (at 0 2.1) (layer "B.Fab") (effects (font (size 0.8 0.8) (thickness 0.15)) (justify mirror)))
	(fp_circle (center 0 0) (end 1.35 0) (layer "B.CrtYd") (width 0.05) (fill none))
	(pad "1" smd circle (at 0 0) (size 2.5 2.5) (layers "B.Cu" "B.Mask")
		(net {netnum} "{netname}"))
)'''

    @staticmethod
    def strap_text(netnum, netname, x, y):
        return f'''(footprint "STRAP_gen"
	(layer "B.Cu")
	(at {x:.4f} {y:.4f} 0)
	(descr "detection strap pad (placement study position)")
	(fp_text reference "JP" (at 0 -1.8) (layer "B.Fab") (effects (font (size 0.7 0.7) (thickness 0.12)) (justify mirror)))
	(fp_text value "STRAP" (at 0 1.8) (layer "B.Fab") (effects (font (size 0.7 0.7) (thickness 0.12)) (justify mirror)))
	(fp_rect (start -1.3 -0.9) (end 1.3 0.9) (layer "B.CrtYd") (width 0.05) (fill none))
	(pad "1" smd rect (at 0 0) (size 2.0 1.2) (layers "B.Cu" "B.Mask")
		(net {netnum} "{netname}"))
)'''


class TestPad:
    @staticmethod
    def text(ref, netnum, netname, x, y, label):
        return f'''(footprint "{ref}"
	(layer "B.Cu")
	(at {x:.4f} {y:.4f} 0)
	(descr "test point {label}")
	(fp_text reference "{ref}" (at 0 -1.4) (layer "B.Fab") (effects (font (size 0.6 0.6) (thickness 0.1)) (justify mirror)))
	(fp_text value "{label}" (at 0 1.4) (layer "B.Fab") (effects (font (size 0.6 0.6) (thickness 0.1)) (justify mirror)))
	(fp_circle (center 0 0) (end 0.85 0) (layer "B.CrtYd") (width 0.05) (fill none))
	(pad "1" smd circle (at 0 0) (size 1.0 1.0) (layers "B.Cu" "B.Mask")
		(net {netnum} "{netname}"))
)'''


def rects_overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def point_in_poly(x, y, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def rect_in_poly(r, poly):
    for cx, cy in ((r[0], r[1]), (r[2], r[1]), (r[0], r[3]), (r[2], r[3]),
                   ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)):
        if not point_in_poly(cx, cy, poly):
            return False
    return True


def box_edge_distance_ok(box, outline, min_d):
    """min distance from the box (all-inside) to any outline segment."""
    from rotation_study import dist_to_seg
    corners = [(box[0], box[1]), (box[2], box[1]),
               (box[0], box[3]), (box[2], box[3])]
    for (x, y) in corners:
        for i in range(len(outline)):
            a = outline[i]
            b = outline[(i + 1) % len(outline)]
            if dist_to_seg(x, y, a[0], a[1], b[0], b[1]) < min_d:
                return False
    return True


def corrected_outline():
    """The connector-next CORRECTED stepped outline (TileTiling, revc-exact:
    vertical margin R/2 - the baseline connectors/ outline used P/2 and
    overlaps its up/down neighbours by 1.46 mm, connector-next CT0).
    Imported from the connector-next study itself when available; the
    formula below is the same construction (bottom_ext=0) and both are
    cross-checked when the import path exists."""
    pts = None
    try:
        import importlib.util
        cn = os.path.join(REPO, 'hardware/experiments/simple-tile/connector-next')
        spec = importlib.util.spec_from_file_location(
            'cn_study', os.path.join(cn, 'study.py'))
        m = importlib.util.module_from_spec(spec)
        sys.path.insert(0, cn)
        sys.path.insert(0, os.path.join(cn, '..', 'connectors'))
        spec.loader.exec_module(m)
        par0 = m.base.Params()
        t = m.TileTiling(par0, m.base.parse_kicad_mod(m.base.VENDORED_FP),
                         'stepped',
                         m.base.parse_kicad_mod(m.base.VENDORED_FP_TRIM))
        pts = [(float(x), float(y)) for x, y in t.outline]
    except Exception as e:   # formula fallback (same construction)
        print(f'outline: connector-next import failed ({e}), using formula')
    G = 1.0                      # rib_gap
    mh, mv = P / 2, R / 2
    rows, cols = 3, 4
    xL = [-k * P / 2 - mh + G / 2 for k in range(rows)]
    xR = [-k * P / 2 + (cols - 1) * P + mh - G / 2 for k in range(rows)]
    yT = -mv + G / 2
    yB = (rows - 1) * R + mv - G / 2
    b = [(k + 0.5) * R for k in range(rows - 1)]
    f = [(xL[0], yT), (xR[0], yT)]
    for k in range(rows - 1):
        f += [(xR[k], b[k] - G / 2), (xR[k + 1], b[k] - G / 2)]
    f += [(xR[-1], yB), (xL[-1], yB)]
    for k in range(rows - 1, 0, -1):
        f += [(xL[k], b[k - 1] + G / 2), (xL[k - 1], b[k - 1] + G / 2)]
    if pts is not None:
        for a_, b_ in zip(pts, f):
            assert abs(a_[0] - b_[0]) < 1e-6 and abs(a_[1] - b_[1]) < 1e-6, \
                f'outline mismatch {a_} vs {b_}'
        return pts
    return f


def build(variant, rotset=None):
    rotset = rotset or set()
    circ = json.load(open(os.path.join(BASE, 'circuits', f'{variant}.json')))
    conn = json.load(open(CONN))
    conn_next = json.load(open(CONN_NEXT))
    outline = corrected_outline()

    # --- nets -------------------------------------------------------------
    netnames = [''] + sorted(n for n in circ['nets'] if not n.startswith('NC_'))
    netno = {n: i for i, n in enumerate(netnames)}
    pin_net = {}
    for n, pins in circ['nets'].items():
        if n.startswith('NC_'):
            continue
        for ref, pin in pins:
            pin_net[(ref, pin)] = (netno[n], n)

    placements = []
    report = []

    # --- keys (front), rotation pattern per fusion study --------------------
    kfp = 'Switch_Keyboard_Hotswap_Kailh:SW_Hotswap_Kailh_MX_1.00u'
    kfp_e = kfp + '_EdgeTrim'
    kc = courtyard_bbox(read_fp(kfp))
    kc_e = courtyard_bbox(read_fp(kfp_e))
    n_rot = 0
    for q in range(12):
        i, k = q % 4, q // 4
        x, y = -k * P / 2 + i * P, k * R
        rot = 180 if (i, k) in rotset else 0
        n_rot += (1 if rot else 0)
        # EdgeTrim needed only for UNROTATED col-0 keys (their pad-1 lobe
        # points west); rotated col-0 keys flip the lobe east.
        et = (i == 0 and rot == 0)
        placements.append({'ref': f'SW{q + 1}', 'fp': kfp_e if et else kfp,
                           'x': x, 'y': y, 'rot': rot, 'bottom': False,
                           'cy': kc_e if et else kc,
                           'note': f'key socket rot={rot}'})
    report.append(f'keys: 12 placed, {n_rot} rotated 180 deg '
                  f'(pattern from rotation_study)')

    # --- chassis pads (BOTTOM) at connector-next coordinates -----------------
    padplan_next = [p for t in conn_next['tiers'].values() for p in t['pads']]
    pad_keep = []
    for pd in padplan_next:
        ref = f"JP_{pd['net']}"
        nn = pin_net.get((ref, '1'), (0, ''))
        assert nn[0], f'{ref} not in circuit interface'
        placements.append({'ref': ref, 'fp': 'CHASSIS_PAD', 'x': pd['x'],
                           'y': pd['y'], 'rot': 0, 'bottom': True,
                           'cy': (-1.35, -1.35, 1.35, 1.35),
                           'note': f"{pd['group']} {pd['role']}",
                           'netname': nn[1], 'netnum': nn[0],
                           'slack_after_tol_next': pd.get('slack_after_tol')})
        pad_keep.append((pd['x'] - 1.55, pd['y'] - 1.55,
                         pd['x'] + 1.55, pd['y'] + 1.55))
    report.append(f"chassis pads: {len(padplan_next)} (connector-next 19C "
                  f"aggregate, straps removed)")

    # --- free-space map -----------------------------------------------------
    grid, gx0, gy0 = rs.build_map(rotset, outline)
    GH, GW = len(grid), len(grid[0])
    G = rs.GRID
    # chassis pad keepouts into the map
    for (a, b, c, d) in pad_keep:
        x0 = int((a - gx0) / G + 0.9999); x1 = int((c - gx0) / G)
        y0 = int((b - gy0) / G + 0.9999); y1 = int((d - gy0) / G)
        for gy in range(max(0, y0), min(GH - 1, y1) + 1):
            for gx in range(max(0, x0), min(GW - 1, x1) + 1):
                grid[gy][gx] = False
    # integral image for O(1) box-free queries
    acc = [[0] * (GW + 1) for _ in range(GH + 1)]
    for gy in range(GH):
        run = 0
        for gx in range(GW):
            run += 0 if grid[gy][gx] else 1
            acc[gy + 1][gx + 1] = acc[gy][gx + 1] + run

    def box_free(x0, y0, x1, y1):
        a = int((x0 - gx0) / G + 0.99999); b = int((x1 - gx0) / G - 1e-9)
        c = int((y0 - gy0) / G + 0.99999); d = int((y1 - gy0) / G - 1e-9)
        if a > b or c > d or a < 0 or c < 0 or b >= GW or d >= GH:
            return False
        occ = acc[d + 1][b + 1] - acc[c][b + 1] - acc[d + 1][a] + acc[c][a]
        return occ == 0

    placed_boxes = list(pad_keep)

    # ---- fanout-corridor model -------------------------------------------
    # Every rail (VCC/GND) SMD pad must be able to grow a stub+via into the
    # inner planes AFTER placement (freerouting cannot attach SMD pads to
    # plane layers).  The scan's first-fit used to drop pull resistors into
    # the shallow top strip where the stub has no corridor; here we model the
    # placed copper (pad boxes + NPTH holes) and PREFER placements where at
    # least one legal corridor exists per rail pad.  Conservative: all
    # obstacles are treated as foreign nets.
    cu_obs = []        # placed copper/hole boxes (board coords)

    def add_obs_for(pl, libref=None, disc_r=None):
        """Register the placed part's pad/hole boxes."""
        pads = []
        if disc_r is not None:
            pads = [(pl['x'] - disc_r, pl['y'] - disc_r,
                     pl['x'] + disc_r, pl['y'] + disc_r)]
        elif libref:
            for num, (cx, cy, w, h, rot) in _pads_rect_cached(libref).items():
                if pl['bottom']:
                    cx = -cx
                # our placed ICs/passives have rot in (0, 90) - for 90 swap
                if pl['rot'] == 90:
                    cx, cy, w, h = -cy, cx, h, w
                pads.append((pl['x'] + cx - w / 2,
                             pl['y'] + cy - h / 2,
                             pl['x'] + cx + w / 2,
                             pl['y'] + cy + h / 2))
        cu_obs.extend(pads)

    # keys first: their SMD pads + NPTH holes are the fixed obstacle field
    for q in range(12):
        i, k = q % 4, q // 4
        kx, ky = -k * P / 2 + i * P, k * R
        for px_, py_, pw, ph in rs.PADS:
            cu_obs.append((kx + px_ - pw / 2, ky + py_ - ph / 2,
                           kx + px_ + pw / 2, ky + py_ + ph / 2))
        for hx, hy, hd in rs.HOLES:
            cu_obs.append((kx + hx - hd / 2, ky + hy - hd / 2,
                           kx + hx + hd / 2, ky + hy + hd / 2))
    # chassis contact discs
    for cd in pad_keep:
        cu_obs.append(cd)

    def corridor_ok(pl, rects, rail_pins):
        """True if every rail pad of the placed part has at least one legal
        stub+via corridor (against currently placed copper + outline)."""
        own = []
        for pn2, (cx2, cy2, w2, h2, _r) in rects.items():
            if pl['bottom']:
                cx2 = -cx2
            if pl['rot'] == 90:
                cx2, cy2 = -cy2, cx2
            own.append((pn2, (pl['x'] + cx2 - w2 / 2, pl['y'] + cy2 - h2 / 2,
                              pl['x'] + cx2 + w2 / 2, pl['y'] + cy2 + h2 / 2)))
        for pn in rail_pins:
            cx, cy, w, h, _ = rects[pn]
            if pl['bottom']:
                cx = -cx
            if pl['rot'] == 90:
                cx, cy = -cy, cx
            pp = (pl['x'] + cx, pl['y'] + cy)
            half = max(w, h) / 2
            obs = cu_obs + [b for pn2, b in own if pn2 != pn]
            ok_one = False
            for dist in (0.65, 0.9, 1.2, 1.9, 2.9):
                for kk in range(24):
                    a = 2 * math.pi * kk / 24
                    vx, vy = (pp[0] + math.cos(a) * (half + dist),
                              pp[1] + math.sin(a) * (half + dist))
                    # outline margin 0.6
                    if any(not point_in_poly(vx + dx, vy + dy, outline)
                           for dx, dy in ((0.6, 0), (-0.6, 0), (0, 0.6), (0, -0.6))):
                        continue
                    vclear = True
                    stub = (pp, (vx, vy))
                    for b in obs:
                        if point_box_dist(vx, vy, b) < 0.3 + 0.2:
                            vclear = False
                            break
                    if not vclear:
                        continue
                    sok = True
                    for b in obs:
                        ib = (b[0] - 0.325, b[1] - 0.325,
                              b[2] + 0.325, b[3] + 0.325)
                        if seg_hits_box(*stub, ib):
                            sok = False
                            break
                    if sok:
                        ok_one = True
                        break
                if ok_one:
                    break
            if not ok_one:
                return False
        return True

    def try_place(ref, fp, bb, bottom=True, want=None, anchor=None,
                  rail_pins=None):
        """anchored: expanding rings around the anchor point first (driver pin
        for series resistors, VCC pin for decoupling caps); falls back to the
        plain first-fit scan.  Rot tries 0 then 90 as before.
        rail_pins: list of pad numbers on VCC/GND for this libref; when given,
        the first corridor-capable candidate wins (fallback: first candidate,
        reported)."""
        def ok(x, y, ob):
            box = (x + ob[0], y + ob[1], x + ob[2], y + ob[3])
            if any(rects_overlap(b, box) for b in placed_boxes):
                return None
            if not rect_in_poly(box, outline):
                return None
            if not box_edge_distance_ok(box, outline, 0.5):
                return None
            # one-cell inflation closes the 0.25 mm quantisation bleed
            if not box_free(box[0] - G, box[1] - G, box[2] + G, box[3] + G):
                return None
            return box
        for rot, ob in ((0, bb), (90, (-bb[3], bb[0], -bb[1], bb[2]))):
            w, h = ob[2] - ob[0], ob[3] - ob[1]
            x_start = gx0 - ob[0]
            y_start = gy0 - ob[1]
            nx = int((GW * G - w) / G)
            ny = int((GH * G - h) / G)
            cand_pool = []   # bounded first-N geometric candidates
            KCAND = 160
            def consider(box, x, y):
                cand_pool.append((rot, ob, x, y, box))
                return len(cand_pool) >= KCAND
            if anchor is not None:
                # rings of grid cells around the anchor, nearest first
                ax = int((anchor[0] - ob[0] - gx0) / G)
                ay = int((anchor[1] - ob[1] - gy0) / G)
                RMAX = int(20.0 / G)  # search up to 20 mm from the anchor
                stop = False
                for r in range(0, RMAX + 1):
                    ring = ([(ax + i, ay - r) for i in range(-r, r + 1)] +
                            [(ax + i, ay + r) for i in range(-r, r + 1)] +
                            [(ax - r, ay + j) for j in range(-r + 1, r)] +
                            [(ax + r, ay + j) for j in range(-r + 1, r)])
                    ring.sort(key=lambda d: (d[0] - ax) ** 2 + (d[1] - ay) ** 2)
                    for cx, cy in ring:
                        ix, iy = cx, cy
                        if ix < 0 or iy < 0 or ix > nx or iy > ny:
                            continue
                        x, y = x_start + ix * G, y_start + iy * G
                        box = ok(x, y, ob)
                        if box is not None:
                            if consider(box, x, y):
                                stop = True
                                break
                    if stop:
                        break
            if anchor is None or rail_pins is not None:
                # plain scan fills the pool when no anchor; with rail pins the
                # scan is the corridor-aware fallback source after the rings
                done_scan = False
                for iy in range(ny + 1):
                    y = y_start + iy * G
                    for ix in range(nx + 1):
                        x = x_start + ix * G
                        box = ok(x, y, ob)
                        if box is None:
                            continue
                        if consider(box, x, y):
                            done_scan = True
                            break
                    if done_scan:
                        break
            # choose: first corridor-capable candidate, else first candidate
            chosen = None
            corridor_state = 'no-rail'
            if rail_pins is None:
                if cand_pool:
                    chosen = cand_pool[0]
            else:
                corridor_state = 'none'
                for c_ in cand_pool:
                    pl = {'ref': ref, 'fp': fp, 'x': c_[2], 'y': c_[3],
                          'rot': c_[0], 'bottom': bottom}
                    if corridor_ok(pl, _pads_rect_cached(fp), rail_pins):
                        chosen = c_
                        corridor_state = 'ok'
                        break
                if chosen is None and cand_pool:
                    chosen = cand_pool[0]
            if chosen is None:
                continue
            rot_, ob_, x_, y_, box = chosen
            placed_boxes.append(box)
            note = want or ''
            if rail_pins is not None and corridor_state != 'ok':
                note = (note + ' [NO FANOUT CORRIDOR]').strip()
            return {'ref': ref, 'fp': fp, 'x': x_, 'y': y_,
                    'rot': rot_, 'bottom': bottom,
                    'cy': ((-ob_[2], ob_[1], -ob_[0], ob_[3])
                           if bottom else (ob_[0], ob_[1], ob_[2], ob_[3])),
                    'note': note}
        return None

    lib_sizes = {}
    for libref in FP_SRC:
        bb = courtyard_bbox(read_fp(libref))
        lib_sizes[libref] = (bb[2] - bb[0], bb[3] - bb[1], bb)

    comp_devices = {c['ref']: c for c in circ['components']}
    # physical rail pins per package (authoritative vs the G1 circuit gap)
    PKG_VCC_PIN0 = {'Package_SO:TSSOP-16_4.4x5mm_P0.65mm': '16',
                    'Package_SO:SSOP-8_2.95x2.8mm_P0.65mm': '8',
                    'Package_TO_SOT_SMD:SOT-23-5': '5'}
    PKG_GND_PIN0 = {'Package_SO:TSSOP-16_4.4x5mm_P0.65mm': '8',
                    'Package_SO:SSOP-8_2.95x2.8mm_P0.65mm': '4',
                    'Package_TO_SOT_SMD:SOT-23-5': '3'}
    ics = [c for c in circ['components']
           if c['device'] not in ('R', 'C', 'CP', 'SW', 'PAD')]
    ics.sort(key=lambda c: -(lib_sizes[c['footprint']][0] * lib_sizes[c['footprint']][1]))
    unplaced = []
    by_ref = {}
    for c in ics:
        _, _, bb = lib_sizes[c['footprint']]
        rp = None
        if c['footprint'] in PKG_VCC_PIN0:
            rp = [PKG_GND_PIN0[c['footprint']], PKG_VCC_PIN0[c['footprint']]]
        pl = try_place(c['ref'], c['footprint'], bb, rail_pins=rp)
        if pl is None:
            unplaced.append(c['ref'] + ' (' + c['footprint'] + ')')
            continue
        placements.append(pl)
        by_ref[c['ref']] = pl
        add_obs_for(pl, libref=c['footprint'])
    report.append(f'ICs placed: {sum(1 for x in placements if x["ref"].startswith("U"))}/{len(ics)}; unplaced: {unplaced}')

    # ---- absolute pad position of a placed part ----------------------------
    # bottom-side parts are mirrored (x -> -x) exactly as pcbnew's Flip; all
    # glued logic here is bottom side at rot 0 (asserted), so abs = pos +
    # (-px, py).  Anchors feed the ring search only; the authoritative
    # distances are re-measured on the saved board by pcbnew in layout/.
    def pad_abs(ref, pin):
        pl = by_ref[ref]
        assert pl['bottom'] and pl['rot'] == 0, \
            f'{ref}: anchor transform only verified for bottom rot=0'
        return (pl['x'] - parse_pads(read_fp(pl['fp']))[pin][0],
                pl['y'] + parse_pads(read_fp(pl['fp']))[pin][1])

    def net_of(ref, pin):
        for n, pins in circ['nets'].items():
            if [ref, pin] in pins or (ref, pin) in pins:
                return n
        return None

    # ---- outbound 33R series resistors FIRST, anchored at the driver -------
    # a source termination only works right next to its driver pin (rev-B
    # lesson).  Driver = the output pin on the non-chassis-side net.
    OUTPUT_PINS = {
        'SN74LVC2G125': {'3', '6'}, 'SN74LVC2G126': {'3', '6'},
        'SN74LVC2G08': {'3', '7'}, 'SN74LVC2G32': {'3', '7'},
        'SN74LVC1G04': {'4'}, 'SN74LVC2G74': {'3', '5'},
        'SN74LV161A': {'11', '12', '13', '14', '15'}, 'SN74LVC165A': {'7', '9'},
    }
    anch_notes = []
    series = [c for c in circ['components']
              if c['device'] == 'R' and str(c.get('value', '')).startswith('33')]
    placed_series = set()
    for c in series:
        ref = c['ref']
        n1, n2 = net_of(ref, '1'), net_of(ref, '2')
        dnet = None
        for n in (n1, n2):
            pins = circ['nets'].get(n, [])
            if not any(p[0].startswith('JP_') for p in pins):
                dnet = n
        anchor = None
        note = f'{ref}: no driver resolved, unanchored'
        if dnet:
            outs = [(r, p) for r, p in circ['nets'][dnet]
                    if r in comp_devices
                    and p in OUTPUT_PINS.get(comp_devices[r]['device'], set())]
            if len(outs) == 1 and outs[0][0] in by_ref:
                anchor = pad_abs(*outs[0])
                note = (f'{ref} anchored at driver {outs[0][0]}.{outs[0][1]}'
                        f' (net {dnet})')
        _, _, bb = lib_sizes[c['footprint']]
        pl = try_place(ref, c['footprint'], bb, want='33R series',
                       anchor=anchor)
        if pl is None:
            unplaced.append(ref + ' (33R)')
            continue
        placements.append(pl)
        by_ref[ref] = pl
        placed_series.add(ref)
        add_obs_for(pl, libref=c['footprint'])
        anch_notes.append(note)
    report.append(f'33R series placement: {anch_notes}')

    # ---- decoupling caps next to their IC's VCC pin ------------------------
    # ---- decoupling caps next to their IC's VCC pin ------------------------
    # physical VCC pin per package (the circuit JSON has rail gaps, G1 in the
    # layout checkpoint; anchoring uses the true physical pin regardless)
    PKG_VCC_PIN = {'Package_SO:TSSOP-16_4.4x5mm_P0.65mm': '16',
                   'Package_SO:SSOP-8_2.95x2.8mm_P0.65mm': '8',
                   'Package_TO_SOT_SMD:SOT-23-5': '5'}
    cap_notes = []
    for c in [c for c in circ['components'] if c['device'] == 'C']:
        ref = c['ref']
        anchor = None
        why = 'no IC mapping'
        m = re.fullmatch(r'CA(\d+)', ref)
        if m:
            uref = f'UA{m.group(1)}'
            if uref in by_ref:
                ufp = comp_devices[uref]['footprint']
                if ufp in PKG_VCC_PIN:
                    anchor = pad_abs(uref, PKG_VCC_PIN[ufp])
                    why = f'anchor {uref}.{PKG_VCC_PIN[ufp]} (pkg VCC pin)'
                else:
                    why = f'{uref}: no VCC pin rule for {ufp}'
            else:
                why = f'{uref} unplaced'
        _, _, bb = lib_sizes[c['footprint']]
        pl = try_place(ref, c['footprint'], bb, want='decoupling',
                       anchor=anchor, rail_pins=['1', '2'])
        if pl is None:
            unplaced.append(ref + f' ({c["value"]})')
            cap_notes.append(f'{ref}: UNPLACED ({why})')
            continue
        placements.append(pl)
        by_ref[ref] = pl
        add_obs_for(pl, libref=c['footprint'])
        note2 = ' [NO FANOUT CORRIDOR]' if '[NO FANOUT CORRIDOR]' in pl['note'] else ''
        if anchor:
            d = math.hypot(pl['x'] - anchor[0], pl['y'] - anchor[1])
            cap_notes.append(f'{ref}: {why} -> placed d={d:.2f} mm{note2}')
        else:
            cap_notes.append(f'{ref}: {why} -> scan{note2}')
    report.append(f'decoupling placement: {cap_notes}')

    def rail_pins_of(ref):
        """pad numbers of this part that sit on VCC/GND in the circuit."""
        out = []
        for n, pins in circ['nets'].items():
            if n not in ('VCC', 'GND'):
                continue
            for r, p in pins:
                if r == ref:
                    out.append(str(p))
        return out

    for group, devs in (('bulk', ('CP',)), ('R', ('R',))):
        for c in [c for c in circ['components']
                  if c['device'] in devs and c['ref'] not in placed_series]:
            _, _, bb = lib_sizes[c['footprint']]
            rp = rail_pins_of(c['ref']) or None
            pl = try_place(c['ref'], c['footprint'], bb, rail_pins=rp)
            if pl is None:
                unplaced.append(c['ref'] + f' ({c["value"]})')
                continue
            placements.append(pl)
            by_ref[c['ref']] = pl
            add_obs_for(pl, libref=c['footprint'])

    tp_nets = ['B_clk', 'B_latch', 'B_data', 'B_first', 'B_W', 'R_latch',
               'T_clk', 'T_data', 'L_clk', 'L_data', 'L_latch', 'W',
               'latch_drv', 'data_drv', 'nRST', 'VCC', 'GND']
    tp_nets = [n for n in tp_nets if n in netno]
    tps_placed = 0
    for n in tp_nets:
        pl = try_place(f'TP_{n}', 'TestPoint:TestPoint_Pad_D1.0mm',
                       (-0.85, -0.85, 0.85, 0.85), want=n,
                       rail_pins=['1'] if n in ('VCC', 'GND') else None)
        if pl is None:
            report.append(f'TP {n}: NO PLACE')
            continue
        placements.append(pl)
        add_obs_for(pl, disc_r=0.5)
        tps_placed += 1
    report.append(f'test points placed: {tps_placed}/{len(tp_nets)}')

    # --- courtyard collision check (independent verification) ---------------
    cols = []
    pcourts = []
    for p in placements:
        bb = p['cy']
        if p['rot'] == 180 and p['ref'].startswith('SW'):
            pass  # +/-7.25 square: rotation-invariant
        r = (p['x'] + bb[0], p['y'] + bb[1], p['x'] + bb[2], p['y'] + bb[3])
        pcourts.append((p['ref'], r, p['bottom']))
    for i in range(len(pcourts)):
        for j in range(i + 1, len(pcourts)):
            ri, rj = pcourts[i], pcourts[j]
            if ri[2] != rj[2] and (ri[0].startswith('SW') or rj[0].startswith('SW')):
                continue
            if rects_overlap(ri[1], rj[1]):
                cols.append((ri[0], rj[0]))
    report.append(f'courtyard collisions (exact courts, same-side): '
                  f'{len(cols)} {cols[:8]}')

    def gap(a, b):
        gx = max(a[0] - b[2], b[0] - a[2])
        gy = max(a[1] - b[3], b[1] - a[3])
        if gx <= 0 and gy <= 0:
            return -max(gx, gy)
        return math.hypot(max(gx, 0), max(gy, 0))
    bottomparts = [(n, r) for (n, r, b) in pcourts if b]
    mingap, minpair = 1e9, None
    for i in range(len(bottomparts)):
        for j in range(i + 1, len(bottomparts)):
            g = gap(bottomparts[i][1], bottomparts[j][1])
            if g < mingap:
                mingap, minpair = g, (bottomparts[i][0], bottomparts[j][0])
    if minpair:
        report.append(f'min bottom-side courtyard gap: {mingap:.3f} mm at {minpair}')

    # sockets' courtyard polygon (closed, from the vendored B.CrtYd chain,
    # rotation-aware) vs every bottom part - exact, not bbox
    from rotation_study import COURT_POLY, rot180 as r180, dist_to_seg
    sock_cols = []
    for p in placements:
        if not p['ref'].startswith('SW'):
            continue
        tr = r180 if p['rot'] else (lambda q: q)
        poly = [(p['x'] + x, p['y'] + y)
                for x, y in (tr(pt) for pt in COURT_POLY)]
        for n, r, b in pcourts:
            if not b or n.startswith('SW'):
                continue
            # courtyard dilation test: any point of r inside poly or closer
            # than PAD_CLR(0.3) to its boundary
            pts_r = [(r[0], r[1]), (r[2], r[1]), (r[0], r[3]), (r[2], r[3]),
                     ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)]
            if any(point_in_poly(x, y, poly) for x, y in pts_r):
                sock_cols.append((p['ref'], n))
                continue
            ok = False
            for a in range(len(poly)):
                bb = (a + 1) % len(poly)
                if any(dist_to_seg(x, y, poly[a][0], poly[a][1], poly[bb][0],
                                   poly[bb][1]) <= rs.PAD_CLR
                       for x, y in pts_r):
                    ok = True
                    break
            if ok:
                sock_cols.append((p['ref'], n))
    report.append(f'bottom parts within socket courtyard(+0.3): '
                  f'{len(sock_cols)} {sock_cols[:8]}')
    off = [r_ for r_, rct, _ in pcourts if not rect_in_poly(rct, outline)]
    report.append(f'courtyards off-board: {len(off)} {off[:6]}')

    # --- emit pcb ----------------------------------------------------------
    nets_s = '(net 0 "")\n' + '\n'.join(
        f'\t(net {netno[n]} "{n}")' for n in netnames if n)
    pcb = ['''(kicad_pcb
	(version 20260206)
	(generator "pcbnew")
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
    for i in range(len(outline)):
        x1, y1 = outline[i]
        x2, y2 = outline[(i + 1) % len(outline)]
        pcb.append(f'\t(gr_line (start {x1:.4f} {y1:.4f}) (end {x2:.4f}'
                   f' {y2:.4f}) (layer "Edge.Cuts") (width 0.05))')
    for p in placements:
        rp = p['ref']
        pn = {pin: v for (r, pin), v in pin_net.items() if r == rp}
        if p['fp'] == 'CHASSIS_PAD':
            pcb.append(ChassisPad.text(rp, p['netnum'], p['netname'], p['x'], p['y']))
        elif p['ref'].startswith('TP_'):
            nname = p['note']
            nnum = netno.get(nname, 0)
            pcb.append(TestPad.text(rp, nnum, nname, p['x'], p['y'], nname))
        else:
            value = comp_devices.get(rp, {}).get('value', rp)
            pcb.append(instantiate(read_fp_board(p['fp']), rp, value,
                                   p['x'], p['y'], p['rot'], p['bottom'],
                                   netno, pn))
    pcb.append(')')
    outdir = os.path.join(BASE, 'boards', variant)
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f'tile_{variant}.kicad_pcb')
    with open(out, 'w') as f:
        f.write('\n'.join(pcb) + '\n')

    npads = sum(1 for p in placements)
    real_nets = [n for n in netnames if n]
    report.append(f'{npads} footprints placed in {out}')
    report.append(f'nets: {len(real_nets)} (+ 1 empty-net); routed: 0 '
                  f'(placement prototype - all {len(real_nets)} nets unrouted)')
    unconn_nc = sum(1 for n in circ['nets'] if n.startswith('NC_'))
    report.append(f'intentional no-connect pads (NC_* nets): {unconn_nc}')
    with open(os.path.join(outdir, 'placement_report.txt'), 'w') as f:
        f.write('\n'.join(report))
    print(f'== {variant}')
    for line in report:
        print('  ' + line)
    return out, report


ROWS_ALT = {(i, k) for k in range(3) for i in range(4) if k % 2}

if __name__ == '__main__':
    # rows-alt rotation was analysed and REJECTED: it collides rotated socket
    # courtyards with the fixed connector-next SIG lane (see
    # results/rotation_study.md).  No 180-degree pattern among 64 structured
    # candidates clears the lanes AND fits the GAL.
    build('variant_a', rotset=set())
    build('variant_b2', rotset=set())
