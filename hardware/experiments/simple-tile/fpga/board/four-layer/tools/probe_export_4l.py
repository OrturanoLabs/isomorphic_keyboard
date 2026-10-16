#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""probe_export_4l.py -- staged ExportSpecctraDSN probe for the 4L variant.

    flatpak run --filesystem=<repo> --command=python3 org.kicad.KiCad \
        probe_export_4l.py BOARD STAGE OUT.dsn

STAGE: asis | nozones | notracks (nozones deletes zones; notracks also
deletes all tracks/vias). Each stage is a separate flatpak invocation so a
segfault in one leaves the other runs intact (batch-5 lesson: bisect
export crashes in separate processes; faulthandler on).
"""
import faulthandler
import sys

import pcbnew

faulthandler.enable()

board_p, stage, out_p = sys.argv[1:4]
board = pcbnew.LoadBoard(board_p)
if stage in ('nozones', 'notracks'):
    for z in list(board.Zones()):
        board.Delete(z)
    print('zones deleted ->', len(list(board.Zones())))
if stage == 'notracks':
    for t in list(board.GetTracks()):
        board.Delete(t)
    print('tracks deleted ->', len(list(board.GetTracks())))
pcbnew.ExportSpecctraDSN(board, out_p)
print('PROBE_EXPORT_OK stage=%s out=%s' % (stage, out_p))
