#!/usr/bin/env python3
"""Stage 2 for the discrete-spld variant-A 4-layer build.

    flatpak run --filesystem=<repo> --command=python3 org.kicad.KiCad \
        layout/finish_4layer.py [ses_path]

Imports the Freerouting session into layout/tile_variant_a_4l.kicad_pcb,
adds a GND stitching-via grid (outer layers get GND pours so the far side
of the tile is not a floating return path), fills all zones and saves
layout/tile_variant_a_routed.kicad_pcb.  Then prints per-net routed length
and via counts for the interface/clock nets (used by the readiness report).

No design rule is touched.  Yardsticks after this step: kicad-cli DRC,
tools/scripts/check_via_in_pad.py, layout/net_binding_check.py --errata.
"""
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD_4L = os.path.join(HERE, 'tile_variant_a_4l.kicad_pcb')
BOARD_OUT = os.path.join(HERE, 'tile_variant_a_routed.kicad_pcb')
MM = pcbnew.FromMM

from build_4layer import net, add_zone, via_fits, outline_ok  # noqa: E402


def stitch_ground(board, pitch=5.0):
    """Sparse GND stitching grid tying outer pours to the In1 plane."""
    items = [p for fp in board.GetFootprints()
             for p in fp.Pads()] + list(board.GetTracks())
    g = board.FindNet('GND')
    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, False)
    bb = outline.BBox()
    x0, y0 = pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY())
    x1, y1 = pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())
    n = 0
    yy = y0 + pitch / 2
    while yy < y1:
        xx = x0 + pitch / 2
        while xx < x1:
            pos = pcbnew.VECTOR2I(MM(xx), MM(yy))
            if outline_ok(board, pos, margin=1.0):
                via = via_fits(board, items, pos, g.GetNetCode(), clearance=0.3)
                if via is not None:
                    via.SetNet(g)
                    board.Add(via)
                    items.append(via)
                    n += 1
            xx += pitch
        yy += pitch
    print('stitching vias added:', n)


def main():
    ses = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        HERE, 'tile_variant_a_4l.ses')
    board = pcbnew.LoadBoard(BOARD_4L)
    if not pcbnew.ImportSpecctraSES(board, ses):
        sys.exit('SES import FAILED')
    print('SES imported:', ses)
    stitch_ground(board)
    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, False)
    add_zone(board, outline, pcbnew.F_Cu, 'GND', priority=1)
    add_zone(board, outline, pcbnew.B_Cu, 'GND', priority=1)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(BOARD_OUT, board)
    print('saved', BOARD_OUT)

    # ---- per-net routed-length + via report ------------------------------
    board = pcbnew.LoadBoard(BOARD_OUT)
    watch = sorted({'B_clk', 'B_latch', 'B_data', 'B_first', 'B_W', 'R_latch',
                    'T_clk', 'T_data', 'T_W', 'T_endcol',
                    'L_clk', 'L_data', 'L_latch', 'L_endrow',
                    'T_clk_drv', 'L_clk_drv', 'latch_drv', 'data_drv', 'B_W_drv',
                    'W', 'DS_net', 'CHAIN', 'nRST', 'Tc',
                    'flag_and', 'flag_d', 'VCC', 'GND'})
    stats = {}
    for t in board.GetTracks():
        n = t.GetNetname()
        s = stats.setdefault(n, [0.0, 0])
        if t.Type() == pcbnew.PCB_VIA_T:
            s[1] += 1
        else:
            s[0] += pcbnew.ToMM(t.GetLength())
    print('net,routed_mm,vias')
    for n in watch:
        if n in stats:
            print(f'{n},{stats[n][0]:.2f},{stats[n][1]}')
    print(f'total routed (all nets): '
          f'{sum(s[0] for s in stats.values()):.1f} mm, '
          f'vias {sum(s[1] for s in stats.values())}')


if __name__ == '__main__':
    main()
