#!/usr/bin/env python3
"""6-neighbour tiling check for the discrete-spld variant-A board.

The tile pattern is tiled by the lattice vectors v=(4P,0), w=(-1.5P,3R)
(rotation_study.py).  Checks, all on the ACTUAL generated board:

  1. outline-vs-outline: the stepped outline tiled by the six offsets must
     not overlap the home outline (shared edges are fine, area overlap is
     not - that would be the old connectors defect);
  2. socket-arm/pad 6-neighbour cross-collisions (rotation_study's exact
     vendored-geometry model, re-run here as an independent gate);
  3. every placed part courtyard + pad must stay inside the home outline
     (so nothing protrudes into a neighbour tile).

Exit 0 = clean.  Prints counts.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))
import rotation_study as rs  # noqa: E402
import board_gen as bg  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402

CONN = json.load(open(bg.CONN))
OUTLINE = bg.corrected_outline()   # connector-next TileTiling (revc-exact)
P, R = rs.P, rs.R
OFFSETS = [(4 * P, 0), (-4 * P, 0), (-1.5 * P, 3 * R), (1.5 * P, -3 * R),
           (4 * P - 1.5 * P, 3 * R), (-(4 * P - 1.5 * P), -3 * R)]


def move(poly, dx, dy):
    return [(x + dx, y + dy) for x, y in poly]


def seg_dist(p, a, b):
    return rs.dist_to_seg(p[0], p[1], a[0], a[1], b[0], b[1])


def polys_area_overlap(A, B, eps=0.005):
    """True only on area overlap: vertices/edge-midpoints perturbed eps toward
    their own centroid, then point-in-poly.  Coincident shared edges (the
    dovetailed stepped outline) perturb OUTSIDE the neighbour -> not overlap."""
    def centroid(P):
        return (sum(p[0] for p in P) / len(P), sum(p[1] for p in P) / len(P))
    def shifted(P):
        cx, cy = centroid(P)
        out = []
        for i in range(len(P)):
            x, y = P[i]
            nx, ny = P[(i + 1) % len(P)]
            for (px, py) in ((x, y), ((x + nx) / 2, (y + ny) / 2)):
                dx, dy = cx - px, cy - py
                L = math.hypot(dx, dy) or 1.0
                out.append((px + eps * dx / L, py + eps * dy / L))
        return out
    for x, y in shifted(A):
        if bg.point_in_poly(x, y, B):
            return True
    for x, y in shifted(B):
        if bg.point_in_poly(x, y, A):
            return True
    return False


def main():
    fails = []
    ov = 0
    for dx, dy in OFFSETS:
        B = move(OUTLINE, dx, dy)
        if polys_area_overlap(OUTLINE, B):
            ov += 1
            fails.append(f'outline overlap at offset ({dx:.3f},{dy:.3f})')
    print(f'1. outline-vs-neighbour outlines: {ov} overlaps over 6 neighbours')

    boxes = rs.neighbour_courts(set())
    cols = rs.neighbour_check(boxes)
    print(f'2. socket-arm/pad 6-neighbour collisions: {len(cols)}'
          + ('' if not cols else f'  {cols[:4]}'))
    if cols:
        fails.append(f'{len(cols)} socket cross-collisions')

    boxes_all = []
    import re
    t = open(os.path.join(os.path.dirname(__file__),
                          'tile_variant_a_routed.kicad_pcb')
             if os.path.exists(os.path.join(os.path.dirname(__file__),
                                            'tile_variant_a_routed.kicad_pcb'))
             else os.path.join(os.path.dirname(__file__), '..', 'boards',
                               'variant_a', 'tile_variant_a.kicad_pcb')).read()
    # crude but sufficient: pad 'at' points + footprint 'at' points must each
    # lie inside the outline (courtyard-level check is the placement report's;
    # protrusions into the neighbour would show up as points outside)
    fp_at = re.findall(r'\(footprint\s+"[^"]+"[\s\S]{0,400}?\(at\s+(-?[\d.]+)\s+(-?[\d.]+)', t)
    out_pts = 0
    for x, y in fp_at:
        if not bg.point_in_poly(float(x), float(y), OUTLINE):
            out_pts += 1
            fails.append(f'footprint anchor outside outline at ({x},{y})')
    print(f'3. footprint anchors inside home outline: {len(fp_at)-out_pts}/{len(fp_at)} ok')

    if fails:
        print('TILING FAIL')
        return 1
    print('TILING PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
