#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Rev C: is there ANY position for a through-hole right-angle 2.54 mm edge connector on
the single-board tile? (exhaustive search, geometry only)

A right-angle THT connector needs
  * its pin row (the THT pads, 1.7 mm) where the TOP side is free: not inside a switch body
    (14 x 14 mm + 0.25 mm), not on a switch hole (+0.5 mm), not on a socket pad (+0.3 mm);
  * a free corridor on the BOTTOM from the pin row to the board edge, as wide as the pin
    row +- 1.6 mm (the plastic body and the bent pins lie there): no switch hole / post,
    no hot-swap socket pad or courtyard.
Edges: left/right connectors are 1x6 columns (pins along y, mating along x), top/bottom
connectors are 1x8 rows (pins along x, mating along y). The search slides the pin row over
the whole board on a 0.25 mm grid and reports every feasible position (or none).
PITCH=1.27 (env) repeats the search for 1.27 mm THT (1.0 mm pads, narrower body).
Run with KiCad's Python on production/revc/revc_folded.kicad_pcb.
"""
import math
import os
import pcbnew

PITCH = float(os.environ.get("PITCH", "2.54"))
PAD_R = 0.85 if PITCH > 2 else 0.5
HALF_BODY = 1.6 if PITCH > 2 else 1.0

TOMM, MM = pcbnew.ToMM, pcbnew.FromMM
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
b = pcbnew.LoadBoard(os.path.join(ROOT, "production", "revc", "revc_folded.kicad_pcb"))
outline = pcbnew.SHAPE_POLY_SET()
b.GetBoardPolygonOutlines(outline, False)

bodies, holes, bottom_boxes = [], [], []
for f in b.GetFootprints():
    if not f.GetReference().startswith("SW"):
        continue
    c = None
    for p in f.Pads():
        q = p.GetPosition()
        if p.HasHole():
            r = TOMM(p.GetDrillSizeX()) / 2
            holes.append((TOMM(q.x), TOMM(q.y), r + 0.5))
            if abs(r - 2.0) < 0.01:
                c = (TOMM(q.x), TOMM(q.y))
        else:
            bb = p.GetBoundingBox()
            bottom_boxes.append((TOMM(bb.GetX()) - .3, TOMM(bb.GetY()) - .3, TOMM(bb.GetRight()) + .3, TOMM(bb.GetBottom()) + .3))
    bb = f.GetCourtyard(pcbnew.B_CrtYd).BBox()
    bottom_boxes.append((TOMM(bb.GetX()) - .3, TOMM(bb.GetY()) - .3, TOMM(bb.GetRight()) + .3, TOMM(bb.GetBottom()) + .3))
    bodies.append((c[0] - 7.25, c[1] - 7.25, c[0] + 7.25, c[1] + 7.25))


def inside(x, y):
    return outline.Contains(pcbnew.VECTOR2I(MM(x), MM(y)))


def top_ok(x, y, r=None):
    r = PAD_R if r is None else r
    # the whole 1.7 mm pad, plus 0.3 mm copper-to-edge clearance, must be on the board
    rr = r + 0.3
    if not all(inside(x + rr * math.cos(a), y + rr * math.sin(a)) for a in [k * math.pi / 4 for k in range(8)]):
        return False
    if any(x0 - r < x < x1 + r and y0 - r < y < y1 + r for x0, y0, x1, y1 in bodies):
        return False
    return not any(math.hypot(x - hx, y - hy) < hr + r for hx, hy, hr in holes)


def bottom_ok(x, y):
    if any(math.hypot(x - hx, y - hy) < hr for hx, hy, hr in holes):
        return False
    return not any(x0 < x < x1 and y0 < y < y1 for x0, y0, x1, y1 in bottom_boxes)


def corridor_ok(pins, direction):
    """From every pin, walk on the bottom in `direction` until leaving the board, with the
    body half-width around the pin row; everything met must be free."""
    dx, dy = direction
    xs = [p[0] for p in pins]; ys = [p[1] for p in pins]
    for s in [i * 0.25 for i in range(0, 200)]:
        pts = []
        if dx:   # pins along y, corridor along x
            for y in [min(ys) - HALF_BODY + k * 0.4 for k in range(int((max(ys) - min(ys) + 2 * HALF_BODY) / 0.4) + 1)]:
                pts.append((xs[0] + dx * s, y))
        else:
            for x in [min(xs) - HALF_BODY + k * 0.4 for k in range(int((max(xs) - min(xs) + 2 * HALF_BODY) / 0.4) + 1)]:
                pts.append((x, ys[0] + dy * s))
        on_board = [p for p in pts if inside(*p)]
        if not on_board:
            return True                       # reached the edge with a clear corridor
        if not all(bottom_ok(*p) for p in on_board):
            return False
    return False


def search(n, along, direction, x_range, y_range):
    hits = []
    x = x_range[0]
    while x <= x_range[1]:
        y = y_range[0]
        while y <= y_range[1]:
            pins = [(x, y + PITCH * i) if along == "y" else (x + PITCH * i, y) for i in range(n)]
            if all(top_ok(*p) for p in pins) and corridor_ok(pins, direction):
                hits.append((round(x, 2), round(y, 2)))
            y += 0.25
        x += 0.25
    return hits


X, Y = (105, 207), (43, 98)
for name, n, along, d in (("left  (1x6, mates towards -x)", 6, "y", (-1, 0)),
                          ("right (1x6, mates towards +x)", 6, "y", (1, 0)),
                          ("top   (1x8, mates towards -y)", 8, "x", (0, -1)),
                          ("bottom(1x8, mates towards +y)", 8, "x", (0, 1))):
    h = search(n, along, d, X, Y)
    print(f"{name}: {len(h)} feasible pin-row positions" + (f", e.g. {h[:3]}" if h else ""))
