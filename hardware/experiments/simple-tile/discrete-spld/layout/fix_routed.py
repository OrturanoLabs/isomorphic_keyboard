#!/usr/bin/env python3
"""Post-route legal fixups for the routed variant-A board (no rule changes).

  1. widen every track segment below the 0.2 mm rule up to 0.2 (freerouting
     left 0.15 mm fanout/routing segments; widening is then DRC-checked:
     any clearance that breaks becomes a real reported error, not hidden);
  2. the two GND vias closer than the 0.5 mm edge rule (freerouting's own
     fanout vias) are DELETED; if that opens the GND net, the KRT repair
     pass that follows will restore connectivity - the open count is printed
     before and after by the caller's DRC runs.

    flatpak run --filesystem=<repo> --command=python3 org.kicad.KiCad \
        layout/fix_routed.py
"""
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, 'tile_variant_a_routed.kicad_pcb')
MM = pcbnew.FromMM

EDGE_VIAS = [(63.0608, 5.3077), (7.3911, -6.7825)]  # from DRC report


def main():
    board = pcbnew.LoadBoard(BOARD)
    board.BuildConnectivity()
    widened = 0
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            continue
        if t.GetWidth() < MM(0.1999):
            t.SetWidth(MM(0.2))
            widened += 1
    print('tracks widened to 0.2 mm:', widened)
    removed = 0
    for t in list(board.GetTracks()):
        if t.Type() != pcbnew.PCB_VIA_T:
            continue
        x, y = pcbnew.ToMM(t.GetPosition().x), pcbnew.ToMM(t.GetPosition().y)
        if any(abs(x - ex) < 0.01 and abs(y - ey) < 0.01
               for ex, ey in EDGE_VIAS) and t.GetNetname() == 'GND':
            board.Delete(t)
            removed += 1
    print('edge-clearance GND vias removed:', removed)
    pcbnew.SaveBoard(BOARD, board)
    print('saved', BOARD)


if __name__ == '__main__':
    main()
