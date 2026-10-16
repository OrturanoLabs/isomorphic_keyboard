#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
# chain_ground.sh -- ONE guard admission: post-import attach (pcbnew,
# flatpak) -> kicad-cli DRC on the new ground board. Serial, 2 GiB/CPU1
# scope from resource_guard outside; flatpak delegator warnings allowed.
set -euo pipefail
D=hardware/experiments/simple-tile/fpga/board
O=$D/four-layer/out
KC=/home/marco/Documents/OrturanoLabs/isomorphic_keyboard/tools/kicad-cli.sh
cd /home/marco/Documents/OrturanoLabs/isomorphic_keyboard
flatpak run --filesystem=/home/marco/Documents/OrturanoLabs/isomorphic_keyboard \
  --command=python3 org.kicad.KiCad \
  "$D/four-layer/tools/postimport_attach.py" \
  "$O/tile_gw1nz_4l_repaired.kicad_pcb" \
  "$O/tile_gw1nz_4l_ground.kicad_pcb" \
  "$O/postimport_attach_report.json"
$KC pcb drc --format json -o "$O/tile_gw1nz_4l_ground.drc.json" \
  "$O/tile_gw1nz_4l_ground.kicad_pcb"
echo CHAIN_GROUND_DONE
