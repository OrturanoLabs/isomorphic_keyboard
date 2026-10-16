#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# chain_build.sh -- one guard admission for the whole build chain:
#   pcbnew build_4l_variant -> pcbnew export_dsn -> dsn_check -> dsn_fix_types
# (flatpak start-up memory is shared inside one admission window instead of
# paying three separate admissions under pressure.)
set -euo pipefail
FL="flatpak run --filesystem=/home/marco/Documents/OrturanoLabs/isomorphic_keyboard --command=python3 org.kicad.KiCad"
D=hardware/experiments/simple-tile/fpga/board
O=$D/four-layer/out
cd /home/marco/Documents/OrturanoLabs/isomorphic_keyboard
echo "== 1/4 build_4l_variant (pcbnew) =="
$FL $D/four-layer/tools/build_4l_variant.py
echo "== 2/4 export_dsn (pcbnew) =="
$FL $D/tools/export_dsn.py "$O/tile_gw1nz_4l.kicad_pcb" "$O/tile_gw1nz_4l.dsn"
echo "== 3/4 dsn_check (host) =="
python3 $D/tools/dsn_check.py "$O/tile_gw1nz_4l.kicad_pcb" "$O/tile_gw1nz_4l.dsn" "$O/dsn_check_4l.json"
echo "== 4/4 dsn_fix_types (host) =="
python3 $D/four-layer/tools/dsn_fix_types.py "$O/tile_gw1nz_4l.dsn" "$O/fanout_sites.json" "$O/tile_gw1nz_4l_router.dsn" "$O/dsn_fix_types.json"
echo "CHAIN_BUILD_DONE"
