#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Rev C: free windows along each board edge (bottom side) for tile-to-tile contacts.

For every Edge.Cuts segment of the key board, points are sampled along the edge at depths
0.5 / 2 / 4 mm inside the board. A point is free when it is outside every switch hole
(+0.5 mm keep-out for the switch posts that stick out below the board), outside every
hot-swap socket pad/courtyard (+0.3 mm), and >= 0.3 mm from the outline itself.
The report lists the contiguous free windows per edge and depth, and the gap to the
neighbouring tile across that edge (lattice: right +80/0 mm, up +10/-51.96 mm).
Run with KiCad's Python on production/revc/revc_folded.kicad_pcb.
"""
import math, os, sys
import pcbnew
TOMM, MM = pcbnew.ToMM, pcbnew.FromMM
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
b = pcbnew.LoadBoard(os.path.join(ROOT, "production", "revc", "revc_folded.kicad_pcb"))
holes, boxes = [], []
for f in b.GetFootprints():
    if not f.GetReference().startswith("SW"):
        continue
    for p in f.Pads():
        c = p.GetPosition()
        if p.HasHole():
            holes.append((TOMM(c.x), TOMM(c.y), TOMM(p.GetDrillSizeX()) / 2 + 0.5))
        else:
            bb = p.GetBoundingBox()
            boxes.append((TOMM(bb.GetX()) - .3, TOMM(bb.GetY()) - .3, TOMM(bb.GetRight()) + .3, TOMM(bb.GetBottom()) + .3))
    bb = f.GetCourtyard(pcbnew.B_CrtYd).BBox()
    boxes.append((TOMM(bb.GetX()) - .3, TOMM(bb.GetY()) - .3, TOMM(bb.GetRight()) + .3, TOMM(bb.GetBottom()) + .3))
outline = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(outline, False)
def free(x, y):
    if not outline.Contains(pcbnew.VECTOR2I(MM(x), MM(y))):
        return False
    if any(math.hypot(x - hx, y - hy) < r for hx, hy, r in holes):
        return False
    return not any(x0 < x < x1 and y0 < y < y1 for x0, y0, x1, y1 in boxes)
segs = []
for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts:
        s, e = d.GetStart(), d.GetEnd()
        segs.append(((TOMM(s.x), TOMM(s.y)), (TOMM(e.x), TOMM(e.y))))
cx = sum(p[0] for s in segs for p in s) / (2 * len(segs)); cy = sum(p[1] for s in segs for p in s) / (2 * len(segs))
print("| edge segment | length | depth | free windows (mm) |")
print("|---|---|---|---|")
for (x0, y0), (x1, y1) in sorted(segs):
    L = math.hypot(x1 - x0, y1 - y0)
    if L < 3:
        continue
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    nx, ny = -uy, ux                                   # a normal; make it point inside
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    if not outline.Contains(pcbnew.VECTOR2I(MM(mx + nx), MM(my + ny))):
        nx, ny = -nx, -ny
    for depth in (0.5, 2.0, 4.0):
        wins, start = [], None
        n = int(L / 0.1)
        for i in range(n + 1):
            s = i * 0.1
            ok = 0.3 < s < L - 0.3 and free(x0 + ux * s + nx * depth, y0 + uy * s + ny * depth)
            if ok and start is None:
                start = s
            if (not ok or i == n) and start is not None:
                if s - start >= 1.0:
                    wins.append(f"{s - start:.1f}")
                start = None
        side = "top" if abs(uy) < 0.1 and my < cy - 20 else "bottom" if abs(uy) < 0.1 else "left" if mx < cx else "right"
        print(f"| {side} ({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f}) | {L:.1f} | {depth} | {', '.join(wins) or '-'} |")
