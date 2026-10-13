#!/usr/bin/env python3
"""Bounded manual repair of residual opens on the KRT-adopted variant-A board.

    flatpak run --filesystem=<repo> --command=python3 org.kicad.KiCad \
        layout/repair_opens.py

Strict-geometry only: track 0.2 mm, clearance 0.2 mm to all foreign copper
(incl. zone fills), via 0.6/0.3 with same-net SMD-pad clearance 0.3,
hole-to-hole 0.25, board edge 0.6.  Anything that cannot be joined legally
prints NO-CORRIDOR and is left open (reported, not hidden).

Passes:
  GND    : the B.Cu pour fragmented into islands after KRT's edits and one
           zone-zone unconnected pair remains in DRC; stitch each small B.Cu
           GND island to the In1 GND plane with a 0.6/0.3 via at the first
           legal position inside the island fill (same net).
  signals: per DRC-identified open link (endpoints from the DRC report), try
           (a) straight B segment, (b) straight F segment, (c) via hop at A +
           straight on F + via hop back at B.  First fully-legal candidate
           wins; NO-CORRIDOR otherwise.

Caller verifies with kicad-cli DRC afterwards and reverts the file if any
new error appears.
"""
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, 'tile_variant_a_routed.kicad_pcb')
MM = pcbnew.FromMM
W2 = MM(0.2)
CLR = MM(0.2)

sys.path.insert(0, HERE)
from build_4layer import via_fits, outline_ok  # noqa: E402


def v(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(x * 0 + y))


def main():
    board = pcbnew.LoadBoard(BOARD)
    board.BuildConnectivity()

    items = [p for fp in board.GetFootprints() for p in fp.Pads()]
    items += list(board.GetTracks())

    # spatial grid over item bboxes inflated 3 mm (covers fat pads/wide tracks)
    CELL = 2.0
    grid = {}

    def cells_of_bbox(bb):
        x0 = pcbnew.ToMM(bb.GetLeft()) - 3.0
        y0 = pcbnew.ToMM(bb.GetTop()) - 3.0
        x1 = pcbnew.ToMM(bb.GetRight()) + 3.0
        y1 = pcbnew.ToMM(bb.GetBottom()) + 3.0
        cx0, cy0 = int(math.floor(x0 / CELL)), int(math.floor(y0 / CELL))
        cx1, cy1 = int(math.floor(x1 / CELL)), int(math.floor(y1 / CELL))
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                yield (cx, cy)

    for idx, it in enumerate(items):
        for c in cells_of_bbox(it.GetBoundingBox()):
            grid.setdefault(c, []).append(idx)

    def query(x, y, r):
        out = []
        cx0, cy0 = int(math.floor((x - r) / CELL)), int(math.floor((y - r) / CELL))
        cx1, cy1 = int(math.floor((x + r) / CELL)), int(math.floor((y + r) / CELL))
        seen = set()
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                for i in grid.get((cx, cy), ()):
                    if i not in seen:
                        seen.add(i)
                        out.append(items[i])
        return out

    def add_item(it):
        items.append(it)
        for c in cells_of_bbox(it.GetBoundingBox()):
            grid.setdefault(c, []).append(len(items) - 1)

    # zone fills: precomputed, inflated for track samples (0.30) and vias (0.50)
    # (GetFilledPolysList on a layer the zone is not on aborts the process in
    # this KiCad build -> guard with IsOnLayer; Clone() downcasts to SHAPE ->
    # rebuild the polyset from its outlines; holes dropped = conservative)
    def inflate(fl, amount):
        cp = pcbnew.SHAPE_POLY_SET()
        for i in range(fl.OutlineCount()):
            cp.AddOutline(fl.Outline(i))
        cp.Inflate(MM(amount), 16, MM(0.01))
        return cp

    infl_tr = {}   # layer -> [(net, polyset)]
    infl_via = {}
    fills_raw = {}
    for z in board.Zones():
        nn = z.GetNetname()
        lay = z.GetLayer()
        fl = z.GetFilledPolysList(lay)
        if fl is None or fl.OutlineCount() == 0:
            continue
        fills_raw[(id(z), lay)] = (nn, fl)
        infl_tr.setdefault(lay, []).append((nn, inflate(fl, 0.30)))
        infl_via.setdefault(lay, []).append((nn, inflate(fl, 0.50)))

    def fill_blocks_track(pt, nn, lay):
        for net, fl in infl_tr.get(lay, ()):
            if net != nn and fl.Contains(pt):
                return True
        return False

    def fill_blocks_via(pt, nn):
        for lay in infl_via:
            for net, fl in infl_via[lay]:
                if net != nn and fl.Contains(pt):
                    return True
        return False

    def seg_ok(p, q, nn, lay, nnet):
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(p)
        tr.SetEnd(q)
        tr.SetWidth(W2)
        tr.SetLayer(lay)
        tr.SetNet(nnet)
        p0 = (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))
        p1 = (pcbnew.ToMM(q.x), pcbnew.ToMM(q.y))
        L = math.dist(p0, p1)
        cand = query((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2,
                     L / 2 + 3.0)
        for it in cand:
            if it.GetNetCode() == nnet.GetNetCode():
                continue
            if isinstance(it, pcbnew.PAD):
                if not it.IsOnLayer(lay):
                    continue
                if tr.GetEffectiveShape(lay).Collide(
                        it.GetEffectiveShape(lay), CLR):
                    return False
            else:
                if it.Type() != pcbnew.PCB_VIA_T and it.GetLayer() != lay:
                    continue
                if tr.GetEffectiveShape(lay).Collide(
                        it.GetEffectiveShape(lay), CLR):
                    return False
            d = None
            ip = None
            if it.Type() == pcbnew.PCB_VIA_T:
                d = pcbnew.ToMM(it.GetDrill())
                ip = it.GetPosition()
            elif isinstance(it, pcbnew.PAD) and it.HasHole():
                d = pcbnew.ToMM(it.GetDrillSizeX())
                ip = it.GetPosition()
            if d:
                ipx, ipy = pcbnew.ToMM(ip.x), pcbnew.ToMM(ip.y)
                if L == 0:
                    dd = math.dist(p0, (ipx, ipy))
                else:
                    t = ((ipx - p0[0]) * (p1[0] - p0[0]) +
                         (ipy - p0[1]) * (p1[1] - p0[1])) / (L * L)
                    t = max(0.0, min(1.0, t))
                    dd = math.dist((ipx, ipy),
                                   (p0[0] + (p1[0] - p0[0]) * t,
                                    p0[1] + (p1[1] - p0[1]) * t))
                if dd < d / 2 + 0.3:
                    return False
        steps = max(1, int(L / 0.25) + 1)
        for i in range(steps + 1):
            sx = p0[0] + (p1[0] - p0[0]) * i / steps
            sy = p0[1] + (p1[1] - p0[1]) * i / steps
            if fill_blocks_track(v(sx, sy), nn, lay):
                return False
        for i in range(3):
            sx = p0[0] + (p1[0] - p0[0]) * i / 2
            sy = p0[1] + (p1[1] - p0[1]) * i / 2
            if not outline_ok(board, v(sx, sy), margin=0.6 + 0.1):
                return False
        return True

    def via_ok(pos, nn, nnet):
        cand = query(pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), 3.0)
        via = via_fits(board, cand, pos, nnet.GetNetCode())
        if via is None:
            return None
        if not outline_ok(board, pos, margin=0.5 + 0.3):
            return None
        if fill_blocks_via(pos, nn):
            return None
        return via

    def add_seg(p, q, nn, lay, nnet):
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(p)
        tr.SetEnd(q)
        tr.SetWidth(W2)
        tr.SetLayer(lay)
        tr.SetNet(nnet)
        board.Add(tr)
        add_item(tr)
        return tr

    report = []

    # ------------------------------------------------ GND island stitching
    gnd_net = board.FindNet('GND')
    gnd_added = 0
    gnd_islands_seen = 0
    for z in list(board.Zones()):
        if z.GetNetname() != 'GND' or z.GetLayer() != pcbnew.B_Cu:
            continue
        fl = z.GetFilledPolysList(pcbnew.B_Cu)
        for oi in range(fl.OutlineCount()):
            gnd_islands_seen += 1
            ps = pcbnew.SHAPE_POLY_SET()
            ps.AddOutline(fl.Outline(oi))
            bb = ps.BBox()
            x0 = pcbnew.ToMM(bb.GetX())
            x1 = pcbnew.ToMM(bb.GetRight())
            y0 = pcbnew.ToMM(bb.GetY())
            y1 = pcbnew.ToMM(bb.GetBottom())
            done = False
            for margin in (0.4, 0.3):
                if done:
                    break
                xx = x0 + margin
                while xx <= x1 - margin + 1e-9 and not done:
                    yy = y0 + margin
                    while yy <= y1 - margin + 1e-9:
                        pt = v(xx, yy)
                        if ps.Contains(pt):
                            via = via_ok(pt, 'GND', gnd_net)
                            if via is not None:
                                via.SetNet(gnd_net)
                                board.Add(via)
                                add_item(via)
                                gnd_added += 1
                                done = True
                                break
                        yy += 0.25
                    xx += 0.25
    report.append(f'GND: {gnd_islands_seen} B.Cu islands seen, '
                  f'{gnd_added} stitching vias added')

    # ------------------------------------------------ signal link prober
    links = [  # (net, pointA, pointB) from reports_drc_krt1.json
        ('flag_d', (51.16, 3.775), (60.112, 2.312)),
        ('T_endcol', (26.015, -2.47), (4.901, 6.252)),
        ('latch_drv', (0.648, 4.5), (19.56, 5.4)),
        ('latch_drv', (19.56, 5.4), (42.184, 4.91)),
        ('W', (11.636, 0.374), (11.26, 3.125)),
        ('W', (-3.59, 2.475), (11.26, 3.125)),
        ('W', (32.91, 3.775), (55.3, 2.65)),
        ('flag_and', (29.51, 3.125), (47.76, 3.775)),
        ('SWN1', (12.515, 7.53), (30.765, 7.53)),
        ('SWN1', (24.202, -5.08), (30.765, 7.53)),
        ('SWN3', (51.75, 7.1), (60.921, -5.08)),
    ]
    LAYERS = (('B', pcbnew.B_Cu), ('F', pcbnew.F_Cu))
    fixed = 0
    for nn, (ax, ay), (bx, by) in links:
        A, Bp = v(ax, ay), v(bx, by)
        nnet = board.FindNet(nn)
        solved = False
        for lname, lay in LAYERS:
            if seg_ok(A, Bp, nn, lay, nnet):
                add_seg(A, Bp, nn, lay, nnet)
                report.append(f'{nn}: straight on {lname} '
                              f'({ax},{ay})->({bx},{by})')
                solved = True
                break
        if not solved:
            dx, dy = bx - ax, by - ay
            L = math.hypot(dx, dy) or 1.0
            ux, uy = dx / L, dy / L
            for da in (0.6, 1.0, 1.5, 2.0, 2.5, 3.0):
                va = v(ax + ux * da, ay + uy * da)
                via1 = via_ok(va, nn, nnet)
                if via1 is None or not seg_ok(A, va, nn, pcbnew.B_Cu, nnet):
                    continue
                for db in (0.6, 1.0, 1.5, 2.0, 2.5, 3.0):
                    vb = v(bx - ux * db, by - uy * db)
                    via2 = via_ok(vb, nn, nnet)
                    if via2 is None:
                        continue
                    if not seg_ok(va, vb, nn, pcbnew.F_Cu, nnet):
                        continue
                    if not seg_ok(vb, Bp, nn, pcbnew.B_Cu, nnet):
                        continue
                    add_seg(A, va, nn, pcbnew.B_Cu, nnet)
                    add_seg(va, vb, nn, pcbnew.F_Cu, nnet)
                    add_seg(vb, Bp, nn, pcbnew.B_Cu, nnet)
                    for vvia in (via1, via2):
                        vvia.SetNet(nnet)
                        board.Add(vvia)
                        add_item(vvia)
                    report.append(f'{nn}: via-hop path '
                                  f'({ax},{ay})->({bx},{by})')
                    solved = True
                    break
                if solved:
                    break
        if not solved:
            report.append(f'{nn}: NO-CORRIDOR ({ax},{ay})->({bx},{by})')
        else:
            fixed += 1

    pcbnew.SaveBoard(BOARD, board)
    print('saved', BOARD)
    for r in report:
        print(r)
    print(f'signal links fixed: {fixed}/{len(links)}; GND vias: {gnd_added}')


if __name__ == '__main__':
    main()
