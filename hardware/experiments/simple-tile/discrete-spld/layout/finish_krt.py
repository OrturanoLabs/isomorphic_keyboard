#!/usr/bin/env python3
"""Stage-3 finisher for the KRT-adopted variant-A 4-layer board.

    flatpak run --filesystem=<repo> --command=python3 org.kicad.KiCad \
        layout/finish_krt.py

Context (2026-10-13): krt_attempt/pass_out.kicad_pcb (KRT pass-1 +
plane-finalize state, container exited during the reconciliation pass) was
adopted as layout/tile_variant_a_routed.kicad_pcb.  KRT's own trailer says
"Open in KiCad and press 'B' to refill zones": this script does exactly that
refill with pcbnew, saves, then prints the same per-net routed-length/via
report finish_4layer.py prints (readiness input).  No design rule touched,
no copper added or removed.
"""
import os

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD_OUT = os.path.join(HERE, 'tile_variant_a_routed.kicad_pcb')


def main():
    board = pcbnew.LoadBoard(BOARD_OUT)
    board.BuildConnectivity()
    zones = list(board.Zones())
    print('zones before refill:', [(z.GetNetname(), z.GetLayer())
                                   for z in zones])
    pcbnew.ZONE_FILLER(board).Fill(zones)
    pcbnew.SaveBoard(BOARD_OUT, board)
    print('saved (refilled)', BOARD_OUT)

    board = pcbnew.LoadBoard(BOARD_OUT)
    watch = sorted({'B_clk', 'B_latch', 'B_data', 'B_first', 'B_W', 'R_latch',
                    'T_clk', 'T_data', 'T_W', 'T_endcol',
                    'L_clk', 'L_data', 'L_latch', 'L_endrow',
                    'T_clk_drv', 'L_clk_drv', 'latch_drv', 'data_drv',
                    'B_W_drv', 'W', 'DS_net', 'CHAIN', 'nRST', 'Tc',
                    'flag_and', 'flag_d', 'VCC', 'GND'})
    stats = {}
    widths = {}
    for t in board.GetTracks():
        n = t.GetNetname()
        s = stats.setdefault(n, [0.0, 0])
        if t.Type() == pcbnew.PCB_VIA_T:
            s[1] += 1
            continue
        s[0] += pcbnew.ToMM(t.GetLength())
        w = round(pcbnew.ToMM(t.GetWidth()), 4)
        widths.setdefault(w, 0)
        widths[w] += 1
    print('net,routed_mm,vias')
    for n in watch:
        if n in stats:
            print(f'{n},{stats[n][0]:.2f},{stats[n][1]}')
    print(f'total routed (all nets): '
          f'{sum(s[0] for s in stats.values()):.1f} mm, '
          f'vias {sum(s[1] for s in stats.values())}')
    print('track width histogram (mm: count):',
          dict(sorted(widths.items())))
    via_sizes = {}
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            key = (round(pcbnew.ToMM(t.GetWidth()), 3),
                   round(pcbnew.ToMM(t.GetDrillValue()), 3))
            via_sizes[key] = via_sizes.get(key, 0) + 1
    print('via (diameter, drill): count:',
          dict(sorted(via_sizes.items())))


if __name__ == '__main__':
    main()
