#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# run_board_pnr.sh -- real synthesis + place&route of the fpga workstream's
# tile RTL (READ-ONLY inputs) against THIS workstream's production board
# pin maps:
#   hw/.../fpga/board/constraints/tile_gw1nz_board.cst  (GW1NZ-LV1QN48)
#   hw/.../fpga/board/constraints/tile_up5k_board.pcf   (iCE40UP5K-SG48)
#
# This answers the remaining legality question: does nextpnr actually accept
# the vendor-verified production pin map (26 tile IO on real package pads,
# clk_pin on the GCLKT_0 pad 47, JTAG/config/strap pins reserved, pin 9
# excluded) and what Fmax/fit do we get?  It does NOT close board-level
# 20 MHz system timing (that needs interconnect + controller drive data).
#
# Run (from anywhere):  tools/oss.sh fpga/board/tools/run_board_pnr.sh
# (the oss.sh wrapper mounts the repo at /work and drops us in the matching
# relative path; run from the repo root or this folder).
set -euo pipefail
cd "$(dirname "$0")/.."                      # .../fpga/board
OUT=out/pnr
BUILD="$OUT/build"
LOGS="$OUT/logs"
mkdir -p "$BUILD" "$LOGS"

GW_CHIPDB=/opt/oss-cad-suite/share/nextpnr/himbaechel/gowin/chipdb-GW1NZ-1.bin
GW_DEVICE=GW1NZ-LV1QN48C6/I5
RTL=../rtl
CST_GW=constraints/tile_gw1nz_board.cst
PCF_UP=constraints/tile_up5k_board.pcf
GHDL_FLAGS="--std=08"
SUMMARY="$OUT/summary.txt"
: > "$SUMMARY"

{
  echo "date_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "yosys:    $(yosys -V 2>/dev/null)"
  echo "nextpnr:  $(nextpnr-himbaechel --version 2>/dev/null | head -1)"
  echo "constraints: $CST_GW / $PCF_UP (production, vendor-verified)"
} | tee -a "$SUMMARY"

rc_all=0

# Optional narrowing for constraint-only iterations (default: both):
#   RUN_VARIANTS="gw1nz" run_board_pnr.sh   # skip the up5k leg entirely
RUN_VARIANTS=${RUN_VARIANTS:-"gw1nz up5k"}

# ---- gw1nz, both snapshot modes, production cst ---------------------------
if [[ " $RUN_VARIANTS " == *" gw1nz "* ]]; then
for mode in fall track; do
  [ "$mode" = track ] && top=top_gw1nz_track || top=top_gw1nz
  tag="gw1nz_${mode}_boardcst"
  echo "== $tag ==" | tee -a "$SUMMARY"
  if yosys -m ghdl \
      -p "ghdl $GHDL_FLAGS $RTL/tile_fpga.vhdl $RTL/${top}.vhdl -e $top; \
          synth_gowin -top $top -json $BUILD/$tag.json" \
      > "$LOGS/${tag}_yosys.log" 2>&1; then :; else
    echo "$tag YOSYS FAIL" | tee -a "$SUMMARY"; rc_all=1; continue
  fi
  if nextpnr-himbaechel --chipdb "$GW_CHIPDB" --device "$GW_DEVICE" \
      --json "$BUILD/$tag.json" --vopt cst="$CST_GW" \
      --write "$BUILD/${tag}_pnr.json" --freq 20 \
      > "$LOGS/${tag}_nextpnr.log" 2>&1; then :; else
    echo "$tag NEXTPNR FAIL (see log: pin legality / timing errors)" \
      | tee -a "$SUMMARY"; rc_all=1; continue
  fi
  if gowin_pack -d "$GW_DEVICE" -o "$BUILD/$tag.fs" \
      "$BUILD/${tag}_pnr.json" > "$LOGS/${tag}_pack.log" 2>&1; then
    echo "$tag .fs: $(stat -c%s "$BUILD/$tag.fs") bytes" | tee -a "$SUMMARY"
  else
    echo "$tag GOWIN_PACK FAIL" | tee -a "$SUMMARY"; rc_all=1; continue
  fi
done

fi                                          # end RUN_VARIANTS gw1nz

# ---- up5k, both snapshot modes, production pcf (pack-legality; SG48 board
# itself is placement-NOFIT - this checks the verified pin MAP only) -------
if [[ " $RUN_VARIANTS " == *" up5k "* ]]; then
for mode in fall track; do
  [ "$mode" = track ] && top=top_ice40up_track || top=top_ice40up
  tag="up5k_${mode}_boardpcf"
  echo "== $tag ==" | tee -a "$SUMMARY"
  if yosys -m ghdl \
      -p "ghdl $GHDL_FLAGS $RTL/tile_fpga.vhdl $RTL/${top}.vhdl -e $top; \
          synth_ice40 -top $top -json $BUILD/$tag.json" \
      > "$LOGS/${tag}_yosys.log" 2>&1; then :; else
    echo "$tag YOSYS FAIL" | tee -a "$SUMMARY"; rc_all=1; continue
  fi
  if nextpnr-ice40 --up5k --package sg48 \
      --json "$BUILD/$tag.json" --pcf "$PCF_UP" \
      --asc "$BUILD/$tag.asc" --freq 20 \
      > "$LOGS/${tag}_nextpnr.log" 2>&1; then
    icepack "$BUILD/$tag.asc" "$BUILD/$tag.bin"
    echo "$tag .bin: $(stat -c%s "$BUILD/$tag.bin") bytes" | tee -a "$SUMMARY"
  else
    echo "$tag NEXTPNR FAIL (see log: pin legality / timing errors)" \
      | tee -a "$SUMMARY"; rc_all=1; continue
  fi
done
fi                                          # end RUN_VARIANTS up5k

# ---- digest: pin acceptance, utilization, Fmax ----------------------------
{
  echo
  echo "== pin-legality + utilization + timing digest =="
  tags=()
  for v in $RUN_VARIANTS; do
    for mode in fall track; do
      [ "$v" = gw1nz ] && tags+=("gw1nz_${mode}_boardcst") \
                       || tags+=("up5k_${mode}_boardpcf")
    done
  done
  for tag in "${tags[@]}"; do
    f="$LOGS/${tag}_nextpnr.log"
    [ -f "$f" ] || continue
    echo "--- $tag ---"
    grep -E "IO_LOC|IO_PORT|constraint|Unconstrained|is not valid|cannot place" "$f" | head -5 || true
    grep -E "utilisation:" -A14 "$f" | grep -E "LUT|DFF|IO|OSC|HFOSC|BLK|DSP" | head -8 || true
    grep -E "Max frequency" "$f" || true
  done
} | tee -a "$SUMMARY"

if grep -qE "ERROR" "$LOGS"/*.log 2>/dev/null; then
  echo "errors present (see out/pnr/logs/)" | tee -a "$SUMMARY"
  echo "BOARD-PNR FAIL" | tee -a "$SUMMARY"
  exit 1
fi
[ "$rc_all" = 0 ] && echo "BOARD-PNR PASS (4 runs, production pin maps)" \
  | tee -a "$SUMMARY" || echo "BOARD-PNR FAIL" | tee -a "$SUMMARY"
exit "$rc_all"
