#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# Synthesis + actual place & route for the simple-tile FPGA candidate,
# BOTH snapshot modes (SNAP_MODE: fall / track) on all three device targets.
#
#   hardware/experiments/simple-tile/fpga/synth/run_synth.sh
#
# Flows (inside the OSS CAD Suite container, via tools/oss.sh):
#   gw1nz : yosys(ghdl+synth_gowin) -> nextpnr-himbaechel(chipdb-GW1NZ-1,
#           device GW1NZ-LV1QN48C6/I5, cst + SDC attempt) -> gowin_pack (.fs)
#   up5k  : yosys(ghdl+synth_ice40) -> nextpnr-ice40 --up5k --package sg48
#           -> icepack (.bin) + icetime report
#   lp8k  : same for --lp8k --package cm81 (TinyFPGA BX device)
#
# Logs + netlists + bitstreams land in results/ (git-ignored build/).
# These establish TOOL-LEVEL interior Fmax and fit only; they do NOT close
# 20 MHz system timing (board interconnect / controller drive-return unknown)
# and they do NOT sign off the async latch/sysclk crossings -- the SDC marks
# those asynchronous (declared, not closed).

set -euo pipefail
cd "$(dirname "$0")"

ROOT_REL=../../../../..
BUILD=results/build
LOGS=results/logs

if [ "${FPGA_SYNTH_INSIDE:-0}" != "1" ]; then
  mkdir -p "$LOGS"
  IMAGE="${OSS_IMAGE:-localhost/oss-cad-suite:2026-09-26}"
  if command -v podman >/dev/null 2>&1 && podman image exists "$IMAGE"; then
    DIGEST="$(podman image inspect --format='{{.Id}}' "$IMAGE" 2>/dev/null || echo unknown)"
    echo "container $IMAGE id $DIGEST" > "$LOGS/mode.log"
    exec "$ROOT_REL/tools/oss.sh" env FPGA_SYNTH_INSIDE=1 OSS_DIGEST="$DIGEST" \
      bash ./run_synth.sh "$@"
  fi
  echo "container image $IMAGE not found, trying host tools" | tee "$LOGS/mode.log"
fi

mkdir -p "$BUILD" "$LOGS"
{
  echo "date_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ "${FPGA_SYNTH_INSIDE:-0}" = "1" ]; then
    echo "mode:     container ${OSS_IMAGE:-localhost/oss-cad-suite:2026-09-26}"
    echo "image_id: ${OSS_DIGEST:-unknown}"
  fi
  echo "yosys:    $(yosys -V 2>/dev/null)"
  echo "nextpnr:  $(nextpnr-himbaechel --version 2>/dev/null | head -1)"
  echo "kernel:   $(uname -srmo)"
} | tee "$LOGS/env.log"

GW_CHIPDB=/opt/oss-cad-suite/share/nextpnr/himbaechel/gowin/chipdb-GW1NZ-1.bin
GW_DEVICE=GW1NZ-LV1QN48C6/I5
GHDL_FLAGS="--std=08"
REPORT="$LOGS/summary.txt"
SDC_LOG="$LOGS/gw1nz_sdc.log"
: > "$REPORT"

# SDC acceptance probe (recorded, not fatal): does nextpnr-himbaechel take
# the declared-interior clocks + async clock groups file?
test_sdc() {
  set +e
  nextpnr-himbaechel --chipdb "$GW_CHIPDB" --device "$GW_DEVICE" \
    --json "$BUILD/gw1nz_fall.json" --vopt cst=tile_gw1nz.cst \
    --sdc tile_gw1nz.sdc --pack-only \
    > "$SDC_LOG" 2>&1
  echo "$?"
  set -e
}

for d in gw1nz:top_gw1nz up5k:top_ice40up lp8k:top_ice40lp; do
  fam="${d%%:*}"; top="${d##*:}"
  for mode in fall track; do
    # ghdl plugin takes no -g; the _track tops are the same wrap with the
    # generic default flipped to "track" (rtl/top_*_track.vhdl)
    if [ "$mode" = track ]; then topx="${top}_track"; else topx="$top"; fi
    tag="${fam}_${mode}"
    echo "== $tag ($topx) ==" | tee -a "$REPORT"
    if [ "$fam" = gw1nz ]; then
      set -x
      yosys -m ghdl \
        -p "ghdl $GHDL_FLAGS ../rtl/tile_fpga.vhdl ../rtl/${topx}.vhdl -e $topx; \
            synth_gowin -top $topx -json $BUILD/$tag.json" \
        > "$LOGS/${tag}_yosys.log" 2>&1
      nextpnr-himbaechel --chipdb "$GW_CHIPDB" --device "$GW_DEVICE" \
        --json "$BUILD/$tag.json" --vopt cst=tile_gw1nz.cst \
        --write "$BUILD/${tag}_pnr.json" --freq 20 \
        > "$LOGS/${tag}_nextpnr.log" 2>&1
      gowin_pack -d "$GW_DEVICE" -o "$BUILD/$tag.fs" "$BUILD/${tag}_pnr.json" \
        > "$LOGS/${tag}_pack.log" 2>&1
      set +x
      echo "$tag .fs: $(stat -c%s "$BUILD/$tag.fs") bytes" | tee -a "$REPORT"
    else
      pkg=sg48; [ "$fam" = lp8k ] && pkg=cm81
      dev=--up5k; [ "$fam" = lp8k ] && dev=--lp8k
      pcf=tile_$fam.pcf
      set -x
      yosys -m ghdl \
        -p "ghdl $GHDL_FLAGS ../rtl/tile_fpga.vhdl ../rtl/${topx}.vhdl -e $topx; \
            synth_ice40 -top $topx -json $BUILD/$tag.json" \
        > "$LOGS/${tag}_yosys.log" 2>&1
      nextpnr-ice40 "$dev" --package "$pkg" \
        --json "$BUILD/$tag.json" --pcf "$pcf" \
        --asc "$BUILD/$tag.asc" --freq 20 \
        > "$LOGS/${tag}_nextpnr.log" 2>&1
      icepack "$BUILD/$tag.asc" "$BUILD/$tag.bin"
      icetime -d "${fam}" -p "$pcf" "$BUILD/$tag.asc" \
        > "$LOGS/${tag}_icetime.log" 2>&1 || true
      set +x
      echo "$tag .bin: $(stat -c%s "$BUILD/$tag.bin") bytes" | tee -a "$REPORT"
    fi
  done
done

# SDC attempt AFTER fall json exists
sdc_rc="$(test_sdc)"
{
  echo
  echo "== sdc attempt (gw1nz, --pack-only): rc=$sdc_rc =="
  grep -E "Info: .*clock|ERROR|Warning" "$SDC_LOG" | head -12 || true
} | tee -a "$REPORT"

# ---------------------------------------------------------------- digest
{
  echo
  echo "== utilization / timing digest =="
  for d in gw1nz up5k lp8k; do
    for mode in fall track; do
      tag="${d}_${mode}"
      echo "--- $tag ---"
      grep -E "SB_LUT4|SB_DFF|LUT4 |DFF |^ +[0-9]+ +[A-Z]" "$LOGS/${tag}_yosys.log" | sort -u | head -6 || true
      grep -E "utilisation:" -A12 "$LOGS/${tag}_nextpnr.log" | grep -E "LUT|DFF|IO|OSC|HFOSC|LC" | head -5 || true
      grep -E "Max frequency" "$LOGS/${tag}_nextpnr.log" || true
    done
  done
  grep -E "Timing estimate" "$LOGS"/*_icetime.log 2>/dev/null || true
} | tee -a "$REPORT"

if grep -q "ERROR" "$LOGS"/*_yosys.log "$LOGS"/*_nextpnr.log 2>/dev/null; then
  echo "errors present (see logs)" | tee -a "$REPORT"
  echo "SYNTH FAIL" | tee -a "$REPORT"
  exit 1
fi
echo "SYNTH PASS (6 variants produced bitstreams)" | tee -a "$REPORT"