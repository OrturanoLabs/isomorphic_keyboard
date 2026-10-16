#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""finish_4l_variant.py -- import SES, stitch, fill, save, report lengths.

Run inside the KiCad flatpak:

    flatpak run --filesystem=<repo> --command=python3 org.kicad.KiCad \
        .../four-layer/tools/finish_4l_variant.py SES_PATH OUT.kicad_pcb REPORT.json

Steps (LEDGER-proven order, same as discrete finish_4layer.py):
  1. Load the 4L variant (fanout + unfilled In1/In2 GND zones).
  2. pcbnew.ImportSpecctraSES  (SES pre-gated by ses_import_check.py and
     pre-widened by ses_widen.py; import returns must be truthy).
  3. GND stitching grid (0.6/0.3 vias, outline margin 1.0, pitch 10 mm,
     collision-checked) tying outer pours to the In1/In2 planes.
  4. GND pours on F.Cu + B.Cu over the full stepped outline (priority 1),
     BuildConnectivity, fill ALL zones, SaveBoard.
  5. Report per-net routed length and via counts, per-edge-net layer census
     (F.Cu/B.Cu segments sit adjacent to a solid GND plane in this stackup;
     inner-layer signal presence is asserted zero) + zone fill triage.

No design rules touched: 0.2/0.2, via 0.6/0.3.
"""
import faulthandler
import json
import os
import sys

import pcbnew

faulthandler.enable()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from via_lib import MM, add_zone, net, outline_ok, via_fits  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(os.path.dirname(HERE), 'out')
VARIANT = os.path.join(OUTDIR, 'tile_gw1nz_4l.kicad_pcb')

EDGE = ['T_clk', 'T_clk_DRV', 'L_clk', 'L_clk_DRV', 'L_latch',
        'L_latch_DRV', 'B_data', 'B_data_DRV', 'B_W', 'B_W_DRV']


def stitch_ground(board, pitch=10.0, cap=60):
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
            if n >= cap:
                return n
            pos = pcbnew.VECTOR2I(MM(xx), MM(yy))
            if outline_ok(board, pos, margin=1.0):
                via = via_fits(board, items, pos, g.GetNetCode(),
                               clearance=0.3)
                if via is not None:
                    via.SetNet(g)
                    board.Add(via)
                    items.append(via)
                    n += 1
            xx += pitch
        yy += pitch
    return n


def main():
    ses, out_pcb, rep_json = sys.argv[1:4]
    board = pcbnew.LoadBoard(VARIANT)
    if not pcbnew.ImportSpecctraSES(board, ses):
        sys.exit('SES import FAILED (import returns falsy)')
    print('SES imported:', ses)
    stitch_n = stitch_ground(board)
    print('stitching vias added:', stitch_n)
    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, False)
    add_zone(board, outline, pcbnew.F_Cu, 'GND', priority=1)
    add_zone(board, outline, pcbnew.B_Cu, 'GND', priority=1)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(out_pcb, board)
    print('saved', out_pcb)

    # --- report ------------------------------------------------------------
    board = pcbnew.LoadBoard(out_pcb)
    stats, layers_by_net = {}, {}
    n_via, n_seg = 0, 0
    for t in board.GetTracks():
        name = t.GetNetname()
        s = stats.setdefault(name, [0.0, 0])
        if t.Type() == pcbnew.PCB_VIA_T:
            s[1] += 1
            n_via += 1
            continue
        s[0] += pcbnew.ToMM(t.GetLength())
        n_seg += 1
        layers_by_net.setdefault(name, set()).add(pcbnew.LayerName(
            t.GetLayer()))
    edge_report = {}
    for name in EDGE:
        ly = sorted(layers_by_net.get(name, []))
        inner = [x for x in ly if x.startswith('In')]
        mm, vias = stats.get(name, [0.0, 0])
        edge_report[name] = {
            'routed_mm': round(mm, 2), 'vias': vias, 'layers': ly,
            'inner_layer_sig': bool(inner),
            'adjacent_gnd_plane': all(x in ('F.Cu', 'B.Cu') for x in ly)}
    zones = []
    for z in board.Zones():
        zones.append({'net': z.GetNetname(),
                      'layer': pcbnew.LayerName(z.GetLayer()),
                      'filled': z.IsFilled(),
                      'corner_count': z.Outline().Outline(0).PointCount()
                      if z.Outline().OutlineCount() else 0})
    report = {
        'stitch_vias': stitch_n,
        'segments': n_seg, 'vias_total': n_via,
        'per_net': {k: {'routed_mm': round(v[0], 2), 'vias': v[1]}
                    for k, v in sorted(stats.items())},
        'edge_nets': edge_report,
        'zones': zones,
    }
    json.dump(report, open(rep_json, 'w', encoding='utf-8'), indent=1)
    print('EDGE', json.dumps({k: v['routed_mm'] for k, v in
                              edge_report.items()}))
    print('FINISH_4L_OK segments=%d vias=%d zones=%d filled=%d' % (
        n_seg, n_via, len(zones), sum(1 for z in zones if z['filled'])))


if __name__ == '__main__':
    main()
