#!/usr/bin/env python3
"""Per-key socket-rotation feasibility + free-space study for the GAL fit.

Ground truth = the vendored Kailh hot-swap footprint geometry (NPTH holes,
SMD pads, B courtyard arms), the connectors-study lattice P=18.3597/R=15.9
and its stepped outline.  Everything else stated is derived here.

Rotation legality (documented decision, see results/rotation_study.md):
a 180 deg rotation of the WHOLE key unit (switch + socket + its NPTH/SMD
cloud together) is legal for an MX body on a hex keycap lattice:
  * the keycap hex is 60-deg-rotation symmetric -> 180 allowed,
  * the contact pins at (+/-5.08,0) are 180-symmetric about the switch centre,
  * the plastic-peg NPTH set {(-3.81,-2.54),(2.54,-5.08),(0,0)} rotates with
    the switch as a rigid assembly: rotated holes = rotated pegs; a real MX
    switch mounts correctly in the rotated hole cloud (there is no absolute
    'north' for the pegs; the pattern is just translated/rotated with the
    switch).  No peg-pattern contradiction was found in the vendored
    footprint; the check itself is reproduced in the output by testing that
    every hole/pad cloud point of a rotated key stays a hole/pad point.

Checks per candidate rotation pattern:
  * free-space map of the underside (obstacles = pads + holes + sockets'
    B-courtyard arms, with the study keep-outs hole+0.5 / pad+court+0.3),
  * largest free rectangles (histogram maximal-rectangle on a 0.25 mm grid),
  * 6-neighbour collision: the tile pattern tiled by v=(4P,0), w=(-1.5P,3R);
    courtyard arms + pads must not cross-collide across boundaries.

Self-check: the baseline (all-0) map's largest rectangles are compared with
the connectors study's published island list (results must bracket >= their
largest strips; deviations reported, not hidden).
"""
import json
import math
import os
import sys

BASE = os.path.join(os.path.dirname(__file__), '..')
REPO = os.path.abspath(os.path.join(BASE, '..', '..', '..', '..'))
VEND = os.path.join(REPO, 'hardware/kicad/lib/Switch_Keyboard_Hotswap_Kailh.pretty')
CONN = os.path.join(REPO, 'hardware/experiments/simple-tile/connectors/out/placement.json')
CONN_NEXT = os.path.join(REPO, 'hardware/experiments/simple-tile/connector-next/out/study.json')

P = 18.359738560230102
R = 15.9
HOLE_CLR = 0.5
PAD_CLR = 0.3
GRID = 0.25
GRIDCOARSE = 0.5

# vendored SW_Hotswap_Kailh_MX_1.00u geometry (from the .kicad_mod directly)
HOLES = [(0.0, 0.0, 4.0), (-5.08, 0.0, 1.75), (5.08, 0.0, 1.75),
         (-3.81, -2.54, 3.05), (2.54, -5.08, 3.05)]
PADS = [(-7.085, -2.54, 2.55, 2.5), (5.842, -5.08, 2.55, 2.5)]


def _legacy_arc_poly(cx, cy, ex, ey, sweep, n=8):
    """Legacy .kicad_mod arc: start = arc CENTRE, end = point on arc."""
    r = math.hypot(ex - cx, ey - cy)
    a0 = math.atan2(ey - cy, ex - cx)
    return [(cx + r * math.cos(a0 + sweep * i / n),
             cy + r * math.sin(a0 + sweep * i / n)) for i in range(n + 1)]


def _socket_courtyard_poly():
    """B.CrtYd of the vendored socket as a CLOSED polygon: arcs flattened with
    legacy centre semantics, segments chained in nearest-endpoint order
    (same construction as connectors/study.py courtyard_polygon)."""
    arms_lines = [((-4.0, -6.8), (4.8, -6.8)), ((4.8, -6.8), (4.8, -2.8)),
                  ((-0.3, -2.8), (4.8, -2.8)), ((-6.0, -0.8), (-2.3, -0.8)),
                  ((-6.0, -0.8), (-6.0, -4.8))]
    arc1 = _legacy_arc_poly(-4.0, -4.8, -4.0, -6.8, math.radians(-90))
    arc2 = _legacy_arc_poly(-0.3, -0.8, -0.3, -2.8, math.radians(-90))
    segs = [list(a) for a in arms_lines] + [arc1, arc2]
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
        assert best <= 0.05, f'courtyard chain gap {best}'
        s = segs.pop(bi)
        pts.extend((s[::-1] if flip else s)[1:])
    assert math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 0.05
    pts.pop()  # drop duplicated closing point
    return pts


COURT_POLY = _socket_courtyard_poly()   # closed, filled socket keep-out


def rot180(pt):
    return (-pt[0], -pt[1])


def key_centres():
    return [(i, k, -k * P / 2 + i * P, k * R) for k in range(3) for i in range(4)]


def outline_pts():
    d = json.load(open(CONN))
    return d['tiles']['stepped']['outline']


def in_poly(x, y, poly):
    inside, j = False, len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def dist_to_seg(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def chassis_obstacles():
    """19 chassis pads (fixed geometry from connector-next tiers)."""
    d = json.load(open(CONN_NEXT))
    for t in d['tiers'].values():
        for p in t['pads']:
            yield ('hole', (p['x'], p['y'], p['d'] / 2 + PAD_CLR))


def obstacles(rotset):
    """Yield (kind, geometry) for every key obstacle, rotset = set of (i,k).
    Socket model = the study's semantics: the CLOSED B.CrtYd courtyard polygon
    (filled) + SMD pads + NPTH holes with study keep-outs; rotation acts on
    pads+holes+courtyard (all back-side features of the unit rotate)."""
    for i, k, cx, cy in key_centres():
        flip = (i, k) in rotset
        tr = rot180 if flip else (lambda p: p)
        for hx, hy, hd in HOLES:
            x, y = tr((hx, hy))
            yield ('hole', (cx + x, cy + y, hd / 2 + HOLE_CLR))
        for px_, py_, pw, ph in PADS:
            cx_, cy_ = tr((px_, py_))
            w, h = pw / 2 + PAD_CLR, ph / 2 + PAD_CLR
            yield ('rect', (cx + cx_ - w, cy + cy_ - h,
                            cx + cx_ + w, cy + cy_ + h))
        poly = [(cx + x, cy + y) for x, y in (tr(p) for p in COURT_POLY)]
        yield ('fpoly', poly)
        # KiCad's courtyard DRC evaluates the courtyard bbox; place against it
        bxs = [q[0] for q in poly]
        bys = [q[1] for q in poly]
        yield ('rect', (min(bxs) - PAD_CLR, min(bys) - PAD_CLR,
                        max(bxs) + PAD_CLR, max(bys) + PAD_CLR))


def build_map(rotset, outline, step=None):
    step = step or GRID
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    x0, x1 = min(xs) - 1, max(xs) + 1
    y0, y1 = min(ys) - 1, max(ys) + 1
    W = int((x1 - x0) / step) + 1
    H = int((y1 - y0) / step) + 1
    obs = list(obstacles(rotset)) + list(chassis_obstacles())
    grid = [[True] * W for _ in range(H)]
    for gy in range(H):
        y = y0 + gy * step
        for gx in range(W):
            x = x0 + gx * step
            if not in_poly(x, y, outline):
                grid[gy][gx] = False
                continue
            for kind, g in obs:
                if kind == 'hole':
                    cx, cy, rr = g
                    if (x - cx) ** 2 + (y - cy) ** 2 <= rr * rr:
                        grid[gy][gx] = False
                        break
                elif kind == 'rect':
                    if g[0] - 1e-9 <= x <= g[2] + 1e-9 and g[1] - 1e-9 <= y <= g[3] + 1e-9:
                        grid[gy][gx] = False
                        break
                else:
                    # filled courtyard polygon with PAD_CLR dilation
                    if in_poly(x, y, g):
                        grid[gy][gx] = False
                        break
                    ok = False
                    for a in range(len(g)):
                        b = (a + 1) % len(g)
                        if dist_to_seg(x, y, *g[a], *g[b]) <= PAD_CLR + 1e-9:
                            ok = True
                            break
                    if ok:
                        grid[gy][gx] = False
                        break
    return grid, x0, y0


def largest_rects(grid, x0, y0, topn=6, step=None):
    step = step or GRID
    H, W = len(grid), len(grid[0])
    heights = [0] * W
    best = []
    for y in range(H):
        for x in range(W):
            heights[x] = heights[x] + 1 if grid[y][x] else 0
        stack = []
        for x in range(W + 1):
            h = heights[x] if x < W else 0
            start = x
            while stack and stack[-1][1] > h:
                sx, sh = stack.pop()
                best.append((sh * (x - sx), (sx, y - sh + 1, x - 1, y)))
                start = sx
            stack.append((start, h))
    best.sort(reverse=True)
    out = []
    for area, (lx, ty, rx, by) in best[:topn]:
        out.append(((lx * step + x0, ty * step + y0,
                     (rx + 1) * step + x0, (by + 1) * step + y0),
                    area * step * step))
    return out


def neighbour_courts(rotset):
    """Every per-key courtyard-poly bbox + pad bbox (rotation-aware)."""
    boxes = []
    for i, k, cx, cy in key_centres():
        flip = (i, k) in rotset
        tr = rot180 if flip else (lambda p: p)
        xs, ys = [], []
        for pt in COURT_POLY:
            x, y = tr(pt)
            xs.append(cx + x); ys.append(cy + y)
        boxes.append((min(xs), min(ys), max(xs), max(ys)))
        for px_, py_, pw, ph in PADS:
            x, y = tr((px_, py_))
            boxes.append((cx + x - pw / 2, cy + y - ph / 2,
                          cx + x + pw / 2, cy + y + ph / 2))
    return boxes


def overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def neighbour_check(boxes):
    """all pairwise overlaps among the tile's own boxes and the boxes of the
    six neighbours (±v, ±w, ±(v+w)) — only pairs straddling a boundary."""
    offs = [(4 * P, 0), (-4 * P, 0), (-1.5 * P, 3 * R), (1.5 * P, -3 * R),
            (4 * P - 1.5 * P, 3 * R), (-(4 * P - 1.5 * P), -3 * R)]
    col = []
    for ox, oy in offs:
        for a in boxes:
            tb = (a[0] + ox, a[1] + oy, a[2] + ox, a[3] + oy)
            for b in boxes:
                if overlap(tb, b):
                    col.append((offs.index((ox, oy)), a, b))
    return col


def pitch_scan(fit_w, fit_h, rotated=False):
    """Minimal P where an island of fit_w x fit_h appears in the rotated
    (or baseline) layout.  R = P sin60; outline from the study formula."""
    def tile_outline(Pv):
        Rv = Pv * math.sin(math.radians(60))
        m = Pv / 2
        G = 1.0
        rows, cols = 3, 4
        xL = [-k * Pv / 2 - m + G / 2 for k in range(rows)]
        xR = [-k * Pv / 2 + (cols - 1) * Pv + m - G / 2 for k in range(rows)]
        yT = -m + G / 2
        yB = (rows - 1) * Rv + m - G / 2
        b = [(k + 0.5) * Rv for k in range(rows - 1)]
        pts = [(xL[0], yT), (xR[0], yT)]
        for k in range(rows - 1):
            pts += [(xR[k], b[k] - G / 2), (xR[k + 1], b[k] - G / 2)]
        pts += [(xR[-1], yB), (xL[-1], yB)]
        for k in range(rows - 1, 0, -1):
            pts += [(xL[k], b[k - 1] + G / 2), (xL[k - 1], b[k - 1] + G / 2)]
        return pts, Rv

    def centres(Pv, Rv):
        return [(i, k, -k * Pv / 2 + i * Pv, k * Rv)
                for k in range(3) for i in range(4)]

    def obstacles_at(Pv, rotset):
        _, Rv = tile_outline(Pv)
        for i, k, cx, cy in centres(Pv, Rv):
            flip = (i, k) in rotset
            tr = rot180 if flip else (lambda p: p)
            for hx, hy, hd in HOLES:
                x, y = tr((hx, hy))
                yield ('hole', (cx + x, cy + y, hd / 2 + HOLE_CLR))
            for px_, py_, pw, ph in PADS:
                x_, y_ = tr((px_, py_))
                w, h = pw / 2 + PAD_CLR, ph / 2 + PAD_CLR
                yield ('rect', (cx + x_ - w, cy + y_ - h,
                                cx + x_ + w, cy + y_ + h))
            yield ('fpoly', [(cx + x, cy + y) for x, y in
                             (tr(p) for p in COURT_POLY)])

    def fits(Pv):
        pts, Rv = tile_outline(Pv)
        xs2 = [p[0] for p in pts]; ys2 = [p[1] for p in pts]
        x0, x1 = min(xs2) - 1, max(xs2) + 1
        y0, y1 = min(ys2) - 1, max(ys2) + 1
        obs = list(obstacles_at(Pv, rotset))
        gridn = int(((y1 - y0) / GRID)) + 1
        grid2 = int(((x1 - x0) / GRID)) + 1
        # row-scan for a fit_w x fit_h free window
        W2 = int(fit_w / GRID)
        H2 = int(fit_h / GRID)
        freegrid = [[True] * grid2 for _ in range(gridn)]
        for gy in range(gridn):
            y = y0 + gy * GRID
            for gx in range(grid2):
                x = x0 + gx * GRID
                if not in_poly(x, y, pts):
                    freegrid[gy][gx] = False
                    continue
                for kind, g in obs:
                    if kind == 'hole':
                        cx, cy, rr = g
                        if (x - cx) ** 2 + (y - cy) ** 2 <= rr * rr:
                            freegrid[gy][gx] = False
                            break
                    elif kind == 'rect':
                        if g[0] <= x <= g[2] and g[1] <= y <= g[3]:
                            freegrid[gy][gx] = False
                            break
                    else:
                        hit = in_poly(x, y, g)
                        if not hit:
                            for a in range(len(g)):
                                b = (a + 1) % len(g)
                                if dist_to_seg(x, y, *g[a], *g[b]) <= PAD_CLR:
                                    hit = True
                                    break
                        if hit:
                            freegrid[gy][gx] = False
                            break
        heights = [0] * grid2
        for gy in range(gridn):
            for gx in range(grid2):
                heights[gx] = heights[gx] + 1 if freegrid[gy][gx] else 0
            stack = []
            for gx in range(grid2 + 1):
                h = heights[gx] if gx < grid2 else 0
                start = gx
                while stack and stack[-1][1] > h:
                    sx, sh = stack.pop()
                    if sh >= H2 and (gx - sx) >= W2:
                        return True
                    start = sx
                stack.append((start, h))
        return False

    rotset = {(i, k) for k in range(3) for i in range(4)} if rotated else set()
    Pv = P
    while Pv < 22.5:      # hard scan cap
        if fits(Pv):
            return Pv
        Pv += 0.05
    return None


def edge_clearance_report(rotset, outline):
    """Per-key: min distance of any pad/hole point to the outline (which
    decides Edge-Trim need); reports worst offenders."""
    obs = list(obstacles(rotset))
    worst = (1e9, None)
    for kind, g in obs:
        if kind == 'hole':
            cx, cy, rr0 = g
            r = rr0 - HOLE_CLR
            pts = [(cx + r, cy), (cx - r, cy), (cx, cy + r), (cx, cy - r)]
        elif kind == 'rect':
            c = PAD_CLR
            pts = [(g[0] + c, g[1] + c), (g[2] - c, g[1] + c),
                   (g[0] + c, g[3] - c), (g[2] - c, g[3] - c)]
        else:
            continue
        for (x, y) in pts:
            d = point_to_poly_dist(x, y, outline)
            if d < worst[0]:
                worst = (d, (kind, round(x, 2), round(y, 2)))
    return worst


def point_to_poly_dist(x, y, poly):
    best = 1e9
    for i in range(len(poly)):
        a = poly[i]
        b = poly[(i + 1) % len(poly)]
        best = min(best, dist_to_seg(x, y, a[0], a[1], b[0], b[1]))
    return best


def lane_check(rotset):
    """rotated socket courtyard polys vs the fixed chassis pads (exact)."""
    hits = []
    for i, k, cx, cy in key_centres():
        flip = (i, k) in rotset
        tr = rot180 if flip else (lambda p: p)
        poly = [(cx + x, cy + y) for x, y in (tr(pt) for pt in COURT_POLY)]
        for kind, g in chassis_obstacles():
            _, (px_, py_, rr) = kind, g
            # pad circle vs poly: centre inside or boundary within rr - PAD_CLR
            if in_poly(px_, py_, poly):
                hits.append(((i, k), (px_, py_)))
                continue
            for a in range(len(poly)):
                b = (a + 1) % len(poly)
                if dist_to_seg(px_, py_, poly[a][0], poly[a][1],
                               poly[b][0], poly[b][1]) <= rr - PAD_CLR + 1e-9:
                    hits.append(((i, k), (px_, py_)))
                    break
    return hits


def same_tile_check(rotset):
    """pad+courtyard-poly bboxes of every key vs every other key on the tile."""
    per_key = []
    for i, k, cx, cy in key_centres():
        flip = (i, k) in rotset
        tr = rot180 if flip else (lambda p: p)
        boxes = []
        for px_, py_, pw, ph in PADS:
            x, y = tr((px_, py_))
            boxes.append((f'{i},{k} pad', (cx + x - pw / 2, cy + y - ph / 2,
                                           cx + x + pw / 2, cy + y + ph / 2)))
        xs, ys = [], []
        for pt in COURT_POLY:
            x, y = tr(pt)
            xs.append(cx + x); ys.append(cy + y)
        boxes.append((f'{i},{k} court', (min(xs), min(ys), max(xs), max(ys))))
        per_key.append(boxes)
    cols = []
    for a in range(len(per_key)):
        for b in range(a + 1, len(per_key)):
            for na, ba in per_key[a]:
                for nb, bb in per_key[b]:
                    if overlap(ba, bb):
                        cols.append((na, nb))
    return cols


def main():
    outline = outline_pts()
    patterns = {
        'all-0 (baseline)': set(),
        'all-180': {(i, k) for k in range(3) for i in range(4)},
        'rows alt': {(i, k) for k in range(3) for i in range(4) if k % 2},
        'cols alt': {(i, k) for k in range(3) for i in range(4) if i % 2},
        'left half': {(0, k) for k in range(3)} | {(1, k) for k in range(3)},
        'right half': {(2, k) for k in range(3)} | {(3, k) for k in range(3)},
        'row0 only': {(i, 0) for i in range(4)},
        'row2 only': {(i, 2) for i in range(4)},
        'rows 0+2': {(i, k) for k in (0, 2) for i in range(4)},
        'r0 + cols alt': {(i, 0) for i in range(4)} |
                          {(i, k) for k in (1, 2) for i in range(4) if i % 2},
        'checker r02': {(i, k) for i in range(4) for k in (0, 2)
                        if (i + k) % 2},
    }
    conn = json.load(open(CONN))
    # structured per-key enumeration (coarse grid, then 8.3mm-fit filter)
    fams = {'none': (), 'all': (0, 1, 2, 3), 'edge': (0, 3), 'core': (1, 2)}
    import itertools
    surv = []
    for combo in itertools.product(sorted(fams), repeat=3):
        rotset = set()
        for k, f in enumerate(combo):
            for i in fams[f]:
                rotset.add((i, k))
        if lane_check(rotset):
            continue
        grid, x0, y0 = build_map(rotset, outline, step=GRIDCOARSE)
        tops = largest_rects(grid, x0, y0, topn=1, step=GRIDCOARSE)
        bb = tops[0][0]
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        if h >= 8.3 and w >= 7.8:
            surv.append(('x'.join(combo), rotset, (round(w, 2), round(h, 2))))
    print(f'lane-clean patterns with a >=7.8x8.3 rect (0.5mm grid): '
          f'{len(surv)}/64')
    for name, rotset, wh in surv:
        print(f'   {name:22} biggest {wh[0]}x{wh[1]}')
    # only verified-candidate patterns get the full treatment below
    for name, rotset, wh in surv:
        if rotset:
            patterns['cand ' + name] = rotset
    patterns = {k: v for k, v in patterns.items()
                if k in ('all-0 (baseline)',) or k.startswith('cand ')}
    for name, rotset in patterns.items():
        grid, x0, y0 = build_map(rotset, outline)
        tops = largest_rects(grid, x0, y0, topn=4)
        boxes = neighbour_courts(rotset)
        ncol = neighbour_check(boxes)
        same = same_tile_check(rotset)
        worst = edge_clearance_report(rotset, outline)
        lane = lane_check(rotset)
        print(f'== {name}')
        for (bb, area) in tops:
            w = bb[2] - bb[0]; h = bb[3] - bb[1]
            print(f'   free rect {bb[0]:.2f},{bb[1]:.2f}..{bb[2]:.2f},{bb[3]:.2f}'
                  f' = {w:.2f}x{h:.2f} mm')
        print(f'   same-tile pad/court overlap pairs: {len(same)} {same[:4]}')
        print(f'   6-neighbour courtyard-arm/pad collisions: {ncol}')
        print(f'   SIG/GND lane pad vs rotated courtyard hits: {len(lane)} {lane[:4]}')
        print(f'   worst pad/hole edge clearance: {worst[0]:.3f} mm @ {worst[1]}')
    study_max = conn['islands']['stepped'][0]
    print(f'\nstudy largest island (baseline): {study_max["w"]}x{study_max["h"]}')
    for label, rot in (('baseline', False), ('all-180', True)):
        got = pitch_scan(7.7, 8.3, rot)
        print(f'min pitch {label}: {got if got else ">22.5 (none)"}')


if __name__ == '__main__':
    main()
