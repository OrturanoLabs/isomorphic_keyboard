#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# regen_batch.sh -- fpga-01 session-5b ONE guarded regeneration battery
# (board r6: adds series-termination positions R7..R11). Each heavy step
# goes through tools/resource_guard.py individually (single-job lock,
# deadline enforcement); steps run strictly serially.
set -euo pipefail
cd "$(dirname "$0")/.."                            # .../fpga/board
ST=../..                                          # .../simple-tile
export RESOURCE_GUARD_DEADLINE="2026-10-15T12:10:00+02:00"
RG="python3 $ST/tools/resource_guard.py"
KC=/home/marco/Documents/OrturanoLabs/isomorphic_keyboard/tools/kicad-cli.sh

echo "== 1/5 board_gen (r6 regen: GK1..GK7 self-checks) =="
$RG --timeout 1500 -- python3 kicad/board_gen.py

echo "== 2/5 board_net_check (N1..N10 + negative controls) =="
python3 tools/board_net_check.py

echo "== 3/5 sch_gen (schematic regen, SCH0 self-check) =="
$RG --timeout 120 -- python3 kicad/sch_gen.py

echo "== 4/5 schematic_check (S1..S7, fresh ERC, S6 straps+series) =="
python3 tools/schematic_check.py

echo "== 5/5 KiCad DRC both variants =="
$RG --timeout 240 -- "$KC" pcb drc --format json \
    -o out/kicad/tile_gw1nz.drc.json out/kicad/tile_gw1nz.kicad_pcb
$RG --timeout 240 -- "$KC" pcb drc --format json \
    -o out/kicad/tile_up5k.drc.json out/kicad/tile_up5k.kicad_pcb
echo "REGEN BATCH DONE"
