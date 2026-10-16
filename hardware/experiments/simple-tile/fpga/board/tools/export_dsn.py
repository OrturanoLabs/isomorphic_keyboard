#!/usr/bin/env python3
"""export_dsn.py -- Specctra DSN export feasibility run (FPGA-02 prep).

Run INSIDE the KiCad flatpak (pcbnew API is the in-tree proven DSN path,
see the discrete layout board_4layer recipe + docs/LEDGER.md):

  flatpak run --filesystem=<repo> --command=python3 org.kicad.KiCad \
      fpga/board/tools/export_dsn.py

Reads out/kicad/tile_gw1nz.kicad_pcb (NEVER writes it) and exports
out/route/tile_gw1nz.dsn. This is preparation evidence that the router
input path works on the current r6 board; it routes nothing and changes
no design artifact.
"""
import faulthandler
import os
import sys

import pcbnew

faulthandler.enable()

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD_DIR = os.path.dirname(HERE)
PCB = os.path.join(BOARD_DIR, "out", "kicad", "tile_gw1nz.kicad_pcb")
OUTDIR = os.path.join(BOARD_DIR, "out", "route")


def main():
    pcb = sys.argv[1] if len(sys.argv) > 1 else PCB
    if len(sys.argv) > 2:
        dsn = sys.argv[2]
    else:
        dsn = os.path.join(OUTDIR,
                           os.path.basename(pcb).replace(".kicad_pcb", ".dsn"))
    os.makedirs(os.path.dirname(dsn) or ".", exist_ok=True)
    board = pcbnew.LoadBoard(pcb)
    pcbnew.ExportSpecctraDSN(board, dsn)
    fps = list(board.GetFootprints())
    nets = set()
    pads = 0
    for fp in fps:
        for pad in fp.Pads():
            pads += 1
            nn = pad.GetNetname()
            if nn:
                nets.add(nn)
    tracks = len(list(board.GetTracks()))
    print(f"EXPORT_DSN_OK pcb_nets={len(nets)} footprints={len(fps)} "
          f"pads={pads} tracks={tracks} out={dsn} "
          f"bytes={os.path.getsize(dsn)}")


if __name__ == "__main__":
    main()
