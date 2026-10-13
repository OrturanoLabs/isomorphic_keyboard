#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# Timing-aware FPGA-chain system validation runner (fpga/system).
#
#   hardware/experiments/simple-tile/fpga/system/run_system.sh [quick]
#
# Behaviour (mirrors the discrete timing-chain harness conventions):
#   * OSS CAD Suite container (tools/oss.sh) when present, else host ghdl.
#   * Host-side drift guard first: results/check_system_sync.py (corners vs
#     VHDL package, fitted anchors, read-only source hashes, 26-pin plan).
#   * Analyses the read-only golden references (regression/tile_reg_pkg.vhdl,
#     ../rtl/tile_fpga.vhdl) plus this experiment's pkg/tile_sys/TBs.
#   * A config passes iff GHDL exits 0 AND "SYSPASS <name>" is in its log.
#   * Negative configs MUST fail with a TIMING-FAIL:<TOKEN> in the log and no
#     SYSPASS marker, and MUST reach simulation (a compile/elab failure of a
#     negative run is an infrastructure failure, not a pass).
#   * Delay/exterior values are SYNTHETIC corners (cfg/corners.json): this is
#     EXPLORATION evidence at 20 MHz, never hardware sign-off.
#
# Tokens: SNAP-XDOM, SNAP-WINDOW, CLK-PULSE, LATCH-GLITCH, SPURIOUS-CLK,
#   MUXSEL, BW, BW-END, FIRSTBIT, STREAM, DATA-SETTLE, RELEASE-HIGH,
#   ENABLE-HIGH, W-LOWPHASE, DS-VALID, CONTENTION, SAMPLE-WINDOW,
#   TRACK-CONTRACT.

set -euo pipefail
cd "$(dirname "$0")"

REG_REL=../../regression
ROOT_REL=../../../../..
BUILD=results/build
RES=results
GFLAGS="--std=08 -fsynopsys --workdir=$BUILD"
STOP="--stop-time=60ms"

MODE="${1:-full}"   # quick: smallest positive + one negative + one unit

# ---------------------------------------------------------------- wrapper
if [ "${SYS_INSIDE:-0}" != "1" ]; then
  mkdir -p "$RES"
  if command -v python3 >/dev/null 2>&1; then
    python3 tools/extract_delays.py | tee "$RES/extract.log" || exit 1
    python3 results/check_system_sync.py | tee "$RES/sync.log" || exit 1
  else
    echo "ERROR: host python3 not found; drift guard cannot run" >&2
    exit 2
  fi
  IMAGE="${OSS_IMAGE:-localhost/oss-cad-suite:2026-09-26}"
  if command -v podman >/dev/null 2>&1 && podman image exists "$IMAGE"; then
    DIGEST="$(podman image inspect --format='{{.Id}}' "$IMAGE" 2>/dev/null || echo unknown)"
    echo "container $IMAGE id $DIGEST" > "$RES/mode.log"
    set +e
    OSS_DIGEST="$DIGEST" "$ROOT_REL/tools/oss.sh" env SYS_INSIDE=1 \
      OSS_DIGEST="$DIGEST" bash ./run_system.sh "$@"
    INNER_RC=$?
    set -e
    if [ "$MODE" != "quick" ]; then
      python3 results/make_report.py || INNER_RC=1
    fi
    exit "$INNER_RC"
  fi
  echo "container image $IMAGE not found, trying host ghdl" | tee "$RES/mode.log"
fi

if ! command -v ghdl >/dev/null 2>&1; then
  echo "ERROR: ghdl not available (no container image, no host ghdl)" >&2
  exit 2
fi

mkdir -p "$BUILD"
rm -rf "$BUILD"/*.o "$BUILD"/*.cf 2>/dev/null || true
rm -f ./chain_sys_tb ./latch_or_tb ./track_cdc_tb ./e~*.o 2>/dev/null || true

{
  echo "date_utc:     $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ "${SYS_INSIDE:-0}" = "1" ]; then
    echo "mode:         container ${OSS_IMAGE:-localhost/oss-cad-suite:2026-09-26}"
    echo "image_id:     ${OSS_DIGEST:-unknown}"
  else
    echo "mode:         host (no container image)"
  fi
  echo "ghdl_version: $(ghdl --version | head -1)"
  echo "kernel:       $(uname -srmo)"
  echo "scope:        SYNTHETIC corners exploration at 20 MHz; NOT hardware sign-off"
} | tee "$RES/env.log"

# ---------------------------------------------------------------- analysis
SRC="$REG_REL/tile_reg_pkg.vhdl vhdl/system_timing_pkg.vhdl ../rtl/tile_fpga.vhdl vhdl/tile_sys.vhdl vhdl/chain_sys_tb.vhdl vhdl/latch_or_tb.vhdl vhdl/track_cdc_tb.vhdl"
# shellcheck disable=SC2086
ghdl -a $GFLAGS $SRC

if [ "$MODE" = "quick" ]; then
  SUMMARY="$RES/summary_quick.txt"
else
  SUMMARY="$RES/summary.txt"
fi
{
  echo "== fpga-system timing-aware chain runs (20 MHz, synthetic corners) =="
  echo "ghdl: $(ghdl --version | head -1)"
} > "$SUMMARY"

pass=0
fail=0
FAILED=""

run_pos() {  # name gens -> pass iff exit 0 AND SYSPASS marker
  local name="$1"; shift
  local gens="$*"
  local log="$RES/$name.log"
  set +e
  # shellcheck disable=SC2086
  ghdl elab-run $GFLAGS chain_sys_tb -gNAME="$name" $gens $STOP >"$log" 2>&1
  local rc=$?
  set -e
  if [ "$rc" = "0" ] && grep -q "SYSPASS $name " "$log"; then
    grep "SYSSUMMARY" "$log" | sed 's/^/    /' >> "$SUMMARY" || true
    echo "PASS  $name" | tee -a "$SUMMARY"
    pass=$((pass + 1))
  else
    echo "FAIL  $name   (see $log, rc=$rc)" | tee -a "$SUMMARY"
    tail -6 "$log" | sed 's/^/        /' || true
    fail=$((fail + 1)); FAILED="$FAILED $name"
  fi
}

run_unit() {  # tb name gens -> pass iff exit 0 AND SYSPASS marker
  local tb="$1" name="$2"; shift 2
  local gens="$*"
  local log="$RES/$name.log"
  set +e
  # shellcheck disable=SC2086
  ghdl elab-run $GFLAGS "$tb" -gNAME="$name" $gens $STOP >"$log" 2>&1
  local rc=$?
  set -e
  if [ "$rc" = "0" ] && grep -q "SYSPASS $name " "$log"; then
    echo "PASS  $name" | tee -a "$SUMMARY"
    pass=$((pass + 1))
  else
    echo "FAIL  $name   (see $log, rc=$rc)" | tee -a "$SUMMARY"
    tail -6 "$log" | sed 's/^/        /' || true
    fail=$((fail + 1)); FAILED="$FAILED $name"
  fi
}

run_neg() {  # name expected_token gens... -> fail must hit the ASSERT token
  local name="$1" tok="$2"; shift 2
  local gens="$*"
  local log="$RES/$name.log"
  set +e
  # shellcheck disable=SC2086
  ghdl elab-run $GFLAGS chain_sys_tb -gNAME="$name" $gens $STOP >"$log" 2>&1
  local rc=$?
  set -e
  if grep -q "error: compilation error\|obsoleted" "$log"; then
    echo "ERROR $name: negative run did not reach simulation (see $log)" | tee -a "$SUMMARY"
    fail=$((fail + 1)); FAILED="$FAILED $name(norun)"
  elif grep -q "SYSPASS" "$log"; then
    echo "FAIL  $name: injected-timing run PASSED - hazard not caught" | tee -a "$SUMMARY"
    fail=$((fail + 1)); FAILED="$FAILED $name(notcaught)"
  elif [ "$rc" != "0" ] && grep -q "TIMING-FAIL:$tok" "$log"; then
    echo "PASS  $name (fails as designed: rc=$rc token=TIMING-FAIL:$tok)" | tee -a "$SUMMARY"
    pass=$((pass + 1))
  elif [ "$rc" != "0" ] && grep -q "TIMING-FAIL:" "$log"; then
    local got
    got=$(grep -o "TIMING-FAIL:[A-Z-]*" "$log" | head -1)
    echo "FAIL  $name: wrong token $got, expected TIMING-FAIL:$tok" | tee -a "$SUMMARY"
    fail=$((fail + 1)); FAILED="$FAILED $name(wrongtok:$got)"
  else
    echo "FAIL  $name: unexpected outcome rc=$rc (see $log)" | tee -a "$SUMMARY"
    tail -6 "$log" | sed 's/^/        /' || true
    fail=$((fail + 1)); FAILED="$FAILED $name"
  fi
}

run_neg_unit() {  # same semantics for the unit TBs
  local tb="$1" name="$2" tok="$3"; shift 3
  local gens="$*"
  local log="$RES/$name.log"
  set +e
  # shellcheck disable=SC2086
  ghdl elab-run $GFLAGS "$tb" -gNAME="$name" $gens $STOP >"$log" 2>&1
  local rc=$?
  set -e
  if grep -q "error: compilation error\|obsoleted" "$log"; then
    echo "ERROR $name: negative unit did not reach simulation (see $log)" | tee -a "$SUMMARY"
    fail=$((fail + 1)); FAILED="$FAILED $name(norun)"
  elif grep -q "SYSPASS" "$log"; then
    echo "FAIL  $name: negative unit PASSED - hazard not caught" | tee -a "$SUMMARY"
    fail=$((fail + 1)); FAILED="$FAILED $name(notcaught)"
  elif [ "$rc" != "0" ] && grep -q "TIMING-FAIL:$tok" "$log"; then
    echo "PASS  $name (fails as designed: rc=$rc token=TIMING-FAIL:$tok)" | tee -a "$SUMMARY"
    pass=$((pass + 1))
  else
    echo "FAIL  $name: unexpected outcome rc=$rc (see $log)" | tee -a "$SUMMARY"
    tail -6 "$log" | sed 's/^/        /' || true
    fail=$((fail + 1)); FAILED="$FAILED $name"
  fi
}

# ============================================================ positive runs
# corners: ""=fit, MINF="-gCORNER=0", MAXF="-gCORNER=2"; default guard 25 ns,
# 50 % duty (W-switch lands mid-high at every corner for this FPGA: measured
# TMARK WPHASE ~6 ns fit / ~13 ns max after the source rise - ample).
MINF="-gCORNER=0"
MAXF="-gCORNER=2"

if [ "$MODE" = "quick" ]; then
  run_pos pos_n1x4_fit    "-gW=1 -gH=4"
  run_neg neg_guard00_fit "SNAP-XDOM" "-gW=1 -gH=4 -gGUARD_100PS=0"
  run_unit latch_or_tb u_latch_or_a "-gSCEN=0"
else
  # full shape x corner matrix at 20 MHz, 1.5 ns synthetic hop, 50 % duty.
  # The 16-HIGH column runs with guard 50 ns: with guard 25 the latch-OR
  # forward chain (latcho+hop+padin per level) loses the per-hop race against
  # the TBUF clock chain at the max corner -- the local fall reaches the deep
  # tiles AFTER their first shift edge. Measured by this model, exercised as
  # the neg_deepxdom_max negative below. (Exploration finding, synthetic
  # corners; the discrete rev-A chain shows the analogous per-hop drift.)
  for CN in fit min max; do
    CF=""
    [ "$CN" = "min" ] && CF="$MINF"
    [ "$CN" = "max" ] && CF="$MAXF"
    run_pos pos_n1x4_$CN   "-gW=1  -gH=4  $CF"
    run_pos pos_n2x4_$CN   "-gW=2  -gH=4  $CF"
    run_pos pos_n16x4_$CN  "-gW=16 -gH=4  $CF"
    run_pos pos_n1x16_$CN  "-gW=1  -gH=16 $CF -gGUARD_100PS=500"
    run_pos pos_g4x4_$CN   "-gW=4  -gH=4  $CF"
  done
  # component-only (no hop) reference points, max corner
  run_pos pos_n16x4_r0_max "-gW=16 -gH=4  -gROUTE_100PS=0 $MAXF"
  run_pos pos_n1x16_r0_max "-gW=1  -gH=16 -gROUTE_100PS=0 $MAXF -gGUARD_100PS=500"
  # larger synthetic hop exploration (3.0 ns), max corner: needs a 30 ns
  # high phase - at 25 ns the col-1 switch W lands at +20 ns and the T_clk
  # release crosses the falling edge (RELEASE-HIGH fires, verified finding).
  run_pos pos_n16x4_r30_max "-gW=16 -gH=4 -gROUTE_100PS=30 $MAXF \
    -gCLK_HIGH_100PS=300 -gCLK_LOW_100PS=200"

  # unit positives: latch-OR sources (A / B / skewed-both), window-safe key
  # change, and the track-mode sysclk-domain contract characterisation
  run_unit latch_or_tb u_latch_or_b_leg  "-gSCEN=0"
  run_unit latch_or_tb u_latch_or_r_leg  "-gSCEN=1"
  run_unit latch_or_tb u_latch_or_skew   "-gSCEN=2 -gSKEW_100PS=70"
  run_unit latch_or_tb u_latch_or_keyok  "-gSCEN=5"
  run_unit track_cdc_tb u_track_contract "-gSCEN=0"

  # ============================================================ negative runs
  # guard below the latch-fall->first-shift cross-domain budget: the fitted
  # 4.86 ns + setup anchor makes g=0/g=4 fail at fit corner
  run_neg neg_guard00_fit  "SNAP-XDOM" "-gW=1 -gH=4 -gGUARD_100PS=0"
  run_neg neg_guard04_fit  "SNAP-XDOM" "-gW=1 -gH=4 -gGUARD_100PS=40"
  # W-enable LOW phase: synthetic stress 2.5x at max corner, 50 % duty -
  # the col-switch W lands ~28 ns after the source rise (> 25 ns high phase);
  # H=2 keeps the latch-vs-clock race out of the way of the W window
  run_neg neg_wlow_s250_max "W-LOWPHASE" \
    "-gW=2 -gH=2 $MAXF -gSCALE_PCT=250 -gMUXCHK_100PS=1000"
  # 16-deep column, guard 25 at max corner: the latch-OR forward chain loses
  # the per-hop race to the TBUF clock chain -> deep tiles see the first
  # shift edge too close to (or before) their local latch fall
  run_neg neg_deepxdom_max "SNAP-XDOM" "-gW=1 -gH=16 $MAXF -gGUARD_100PS=250"
  # sample-lead way too late (samples the next bit)
  run_neg neg_lead45_fit   "STREAM" "-gW=2 -gH=4 -gLEAD_100PS=450"
  # 3 ns synthetic hop at max corner with 25 ns high phase: the col-1 switch
  # W lands at +20 ns and the T_clk release crosses the clock falling edge
  # (the 30 ns high-phase positive above restores containment)
  run_neg neg_release_r30_max "RELEASE-HIGH" \
    "-gW=2 -gH=4 -gROUTE_100PS=30 $MAXF"
  # returned data inside the settle margin at the sample point (max corner,
  # sample lead 25 ns + 20 ns settle requirement: data lands ~11 ns before
  # the sample -> margin 10.6 ns < 20 ns)
  run_neg neg_lead25_settle_max "DATA-SETTLE" \
    "-gW=1 -gH=4 -gLEAD_100PS=250 -gSETTLE_100PS=200 $MAXF"
  # unit negatives
  run_neg_unit latch_or_tb u_latch_or_glitch "LATCH-GLITCH" \
    "-gSCEN=3 -gSKEW_100PS=70"
  run_neg_unit latch_or_tb u_snap_window     "SNAP-WINDOW" "-gSCEN=4"
  run_neg_unit track_cdc_tb u_track_shortlatch "STREAM"    "-gSCEN=1"

  # ============================================================ sweeps
  # min GUARD / sample-LEAD window / min clock-HIGH phase; scale boundary for
  # the W-low-phase hazard. results/sweeps.txt
  SW="$RES/sweeps.txt"
  {
    echo "# sweep tables, 20 MHz (50 ns), synthetic corners (cfg/corners.json)"
    echo "# guard: latch deassert -> first clock (xdom budget); lead: sample lead"
    echo "# high: clock high phase (W-switch containment); scale: stress x100"
    echo "# columns: corner shape | min_guard_ns | min_lead_ns | max_lead_ns | min_high_ns | wlow_scale_min_pct"
  } > "$SW"

  sweep_one() {  # corner-tag corner-flag W H
    local cn="$1" cf="$2" w="$3" h="$4"
    local guard_min="" lead_min="" lead_max="" high_min="" wlow=""
    local g s hi sc rc log
    local XTRA=""   # 16-deep shapes need the swept guard for other dimensions
    if [ "$h" = "16" ]; then XTRA="-gGUARD_100PS=500"; fi
    for g in 0 1 2 3 4 5 6 8 10 15 20 25 30 40 50 60; do
      log="$RES/sw_g${g}_n${w}x${h}_${cn}.log"
      set +e
      # shellcheck disable=SC2086
      ghdl elab-run $GFLAGS chain_sys_tb -gNAME="sw_g${g}_n${w}x${h}_${cn}" \
        -gW="$w" -gH="$h" -gGUARD_100PS="$((10 * g))" $cf $STOP >"$log" 2>&1
      rc=$?
      set -e
      if [ "$rc" = "0" ] && grep -q SYSPASS "$log"; then guard_min=$g; break; fi
    done
    for s in 1 5 10 20 30 40 44 45 48; do
      log="$RES/sw_s${s}_n${w}x${h}_${cn}.log"
      set +e
      # shellcheck disable=SC2086
      ghdl elab-run $GFLAGS chain_sys_tb -gNAME="sw_s${s}_n${w}x${h}_${cn}" \
        -gW="$w" -gH="$h" -gLEAD_100PS="$((10 * s))" $cf $XTRA $STOP >"$log" 2>&1
      rc=$?
      set -e
      if [ "$rc" = "0" ] && grep -q SYSPASS "$log"; then
        [ -z "$lead_min" ] && lead_min=$s
        lead_max=$s
      fi
    done
    for hi in 150 180 200 220 250 280 300; do
      local lo=$((500 - hi))
      log="$RES/sw_hi${hi}_n${w}x${h}_${cn}.log"
      set +e
      # shellcheck disable=SC2086
      ghdl elab-run $GFLAGS chain_sys_tb -gNAME="sw_hi${hi}_n${w}x${h}_${cn}" \
        -gW="$w" -gH="$h" -gCLK_HIGH_100PS="$hi" -gCLK_LOW_100PS="$lo" $cf $XTRA $STOP >"$log" 2>&1
      rc=$?
      set -e
      if [ "$rc" = "0" ] && grep -q SYSPASS "$log"; then
        high_min=$((hi / 10)).$((hi % 10))
        break
      fi
    done
    # W-low-phase scale boundary (50% duty; only meaningful with a second col)
    for sc in 100 150 200 250 300; do
      log="$RES/sw_w${sc}_n${w}x${h}_${cn}.log"
      set +e
      # shellcheck disable=SC2086
      ghdl elab-run $GFLAGS chain_sys_tb -gNAME="sw_w${sc}_n${w}x${h}_${cn}" \
        -gW="$w" -gH="$h" -gSCALE_PCT="$sc" $cf $XTRA $STOP >"$log" 2>&1
      rc=$?
      set -e
      if [ "$rc" = "0" ] && grep -q SYSPASS "$log"; then
        wlow=$sc
      else
        break
      fi
    done
    {
      echo "N=${w} H=${h} corner=${cn} : min_guard_ns=${guard_min:-NONE} min_lead_ns=${lead_min:-NONE} max_lead_ns=${lead_max:-NONE} min_high_ns=${high_min:-NONE} wlow_scale_max_ok_pct=${wlow:-NONE}"
      echo "SWEEP N=${w} H=${h} corner=${cn} guard_min_ns=${guard_min:-NONE} lead_min_ns=${lead_min:-NONE} lead_max_ns=${lead_max:-NONE} high_min_ns=${high_min:-NONE} wlow_scale_max_ok_pct=${wlow:-NONE}"
    } | tee -a "$SW"
  }

  for CN in fit max; do
    CF=""
    [ "$CN" = "max" ] && CF="$MAXF"
    sweep_one "$CN" "$CF" 2 4
    sweep_one "$CN" "$CF" 16 4
    sweep_one "$CN" "$CF" 1 16
  done
  sweep_one fit  ""      1 4
  sweep_one min  "$MINF" 2 4
  sweep_one min  "$MINF" 16 4
fi

{
  echo
  echo "runs passed: $pass, failed: $fail"
} | tee -a "$SUMMARY"

rm -f ./chain_sys_tb ./latch_or_tb ./track_cdc_tb ./e~*.o 2>/dev/null || true

RC=0
if [ "$fail" != "0" ]; then
  echo "FPGA-SYSTEM FAILED:$FAILED" | tee -a "$SUMMARY"
  RC=1
else
  echo "FPGA-SYSTEM PASS" | tee -a "$SUMMARY"
fi

# host-side full runs: generate machine.json + report.md after the sims
if [ "${SYS_INSIDE:-0}" != "1" ] && [ "$MODE" != "quick" ]; then
  python3 results/make_report.py || RC=1
fi
exit $RC
