#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# Timing-aware rev-A tile chain testbench runner.
#
#   hardware/experiments/simple-tile/timing-chain/run_timing_chain.sh [quick]
#
# Behaviour:
#   * OSS CAD Suite container (tools/oss.sh) when present, else host ghdl.
#   * Analyses the UNMODIFIED golden package (regression/tile_reg_pkg.vhdl)
#     plus this directory's timing pkg / timed leaves / timed tile / TB.
#   * A config passes iff GHDL exits 0 AND "TCREGPASS <name>" is in its log.
#   * Negative configs MUST fail with a TIMING-FAIL token in the log and no
#     TCREGPASS marker; a negative config that passes (or fails by compile/
#     elab error) is an infrastructure failure of the harness itself.
#   * Sweeps record min LATCH_GUARD_NS / SAMPLE_LEAD_NS vs N to results/.
#   * generated files (build/, results/) are git-ignored.
#
# Timing here is datasheet min/max + a SYNTHETIC fixed route delay: this is
# necessary-condition evidence, not 20 MHz hardware sign-off.

set -euo pipefail
cd "$(dirname "$0")"

REG_REL=../regression
ROOT_REL=../../../..
BUILD=build
RES=results
GFLAGS="--std=08 -fsynopsys --workdir=$BUILD"
STOP="--stop-time=60ms"

MODE="${1:-full}"   # quick: only the smallest positive + one negative

# ---------------------------------------------------------------- wrapper
if [ "${TC_INSIDE:-0}" != "1" ]; then
  mkdir -p "$RES"
  # datasheet-constant drift guard vs logic/timing/timing.json (host python3)
  if command -v python3 >/dev/null 2>&1; then
    python3 results/check_timing_sync.py | tee "$RES/sync.log" || exit 1
  else
    echo "WARN: host python3 not found; timing sync check skipped" | tee "$RES/sync.log"
  fi
  IMAGE="${OSS_IMAGE:-localhost/oss-cad-suite:2026-09-26}"
  if command -v podman >/dev/null 2>&1 && podman image exists "$IMAGE"; then
    DIGEST="$(podman image inspect --format='{{.Id}}' "$IMAGE" 2>/dev/null || echo unknown)"
    echo "container $IMAGE id $DIGEST" > "$RES/mode.log"
    exec "$ROOT_REL/tools/oss.sh" env TC_INSIDE=1 OSS_DIGEST="$DIGEST" \
      bash ./run_timing_chain.sh "$@"
  fi
  echo "container image $IMAGE not found, trying host ghdl" | tee "$RES/mode.log"
fi

if ! command -v ghdl >/dev/null 2>&1; then
  echo "ERROR: ghdl not available (no container image, no host ghdl)" >&2
  exit 2
fi

mkdir -p "$BUILD" "$RES"
rm -rf "$BUILD"/*.o "$BUILD"/*.cf "$BUILD"/chain_tb ./chain_tb ./e~* 2>/dev/null || true

{
  echo "date_utc:     $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ "${TC_INSIDE:-0}" = "1" ]; then
    echo "mode:         container ${OSS_IMAGE:-localhost/oss-cad-suite:2026-09-26}"
    echo "image_id:     ${OSS_DIGEST:-unknown}"
  else
    echo "mode:         host (no container image)"
  fi
  echo "ghdl_version: $(ghdl --version | head -1)"
  ghdl --version | sed -n '2,3p' | sed 's/^/              /'
  echo "kernel:       $(uname -srmo)"
} | tee "$RES/env.log"

# ---------------------------------------------------------------- analysis
SRC="vhdl/chain_timing_pkg.vhdl vhdl/logic74_timed.vhdl vhdl/tile_timed.vhdl $REG_REL/tile_reg_pkg.vhdl vhdl/chain_tb.vhdl"
# shellcheck disable=SC2086
ghdl -a $GFLAGS $SRC

SUMMARY="$RES/summary.txt"
{
  echo "== timing-aware chain runs =="
  echo "ghdl: $(ghdl --version | head -1)"
} > "$SUMMARY"

pass=0
fail=0
FAILED=""

run_pos() {  # name gens -> pass iff exit 0 AND TCREGPASS marker
  local name="$1" gens="$2" log="$RES/$1.log"
  set +e
  # shellcheck disable=SC2086
  ghdl elab-run $GFLAGS chain_tb -gNAME="$name" $gens $STOP >"$log" 2>&1
  local rc=$?
  set -e
  if [ "$rc" = "0" ] && grep -q "TCREGPASS $name " "$log"; then
    grep "TCREGSUMMARY" "$log" | sed 's/^/    /' >> "$SUMMARY" || true
    echo "PASS  $name" | tee -a "$SUMMARY"
    pass=$((pass + 1))
  else
    echo "FAIL  $name   (see $RES/$name.log, rc=$rc)" | tee -a "$SUMMARY"
    tail -6 "$log" | sed 's/^/        /' || true
    fail=$((fail + 1)); FAILED="$FAILED $name"
  fi
}

run_neg() {  # name gens -> pass iff exit != 0 AND a TIMING-FAIL token AND no TCREGPASS,
             # and NOT a compilation/elaboration failure (must reach simulation)
  local name="$1" gens="$2" log="$RES/$1.log"
  set +e
  # shellcheck disable=SC2086
  ghdl elab-run $GFLAGS chain_tb -gNAME="$name" $gens $STOP >"$log" 2>&1
  local rc=$?
  set -e
  if grep -q "error: compilation error" "$log" || grep -q "obsoleted" "$log"; then
    echo "ERROR $name: negative run did not reach simulation (see $log)" | tee -a "$SUMMARY"
    fail=$((fail + 1)); FAILED="$FAILED $name(norun)"
  elif grep -q "TCREGPASS" "$log"; then
    echo "FAIL  $name: injected-timing run PASSED - hazard not caught" | tee -a "$SUMMARY"
    fail=$((fail + 1)); FAILED="$FAILED $name(notcaught)"
  elif [ "$rc" != "0" ] && grep -q "TIMING-FAIL:" "$log"; then
    local tok
    tok=$(grep -o "TIMING-FAIL:[A-Z-]*" "$log" | head -1)
    echo "PASS  $name (fails as designed: rc=$rc token=$tok)" | tee -a "$SUMMARY"
    pass=$((pass + 1))
  else
    echo "FAIL  $name: unexpected outcome rc=$rc (see $RES/$name.log)" | tee -a "$SUMMARY"
    tail -6 "$log" | sed 's/^/        /' || true
    fail=$((fail + 1)); FAILED="$FAILED $name"
  fi
}

# ============================================================ positive runs
# All at 20 MHz (50 ns), TAIL=32. Max-corner runs with the synthetic 1.5 ns
# route use CLK_HIGH 30 ns: at 25 ns high phase the W-switch lands ~2-3 ns
# past the local falling edge there (measured; see results/notes) -- that is
# a real finding, exercised below as a documented expected-fail run.
if [ "$MODE" = "quick" ]; then
  run_pos pos_n1_route15_max "-gW=1 -gH=4 -gCLK_HIGH_100PS=300 -gCLK_LOW_100PS=200"
  run_neg neg_recovery_g12  "-gW=1 -gH=4 -gGUARD_100PS=120"
else
  D60="-gCLK_HIGH_100PS=300 -gCLK_LOW_100PS=200"
  # max corner, synthetic 1.5 ns route, N = 1 / 2 / 16 columns x 4 rows
  # + a 16-high single column (the other reading of '16 tiles').
  run_pos pos_n1_route15_max    "-gW=1  -gH=4  $D60"
  run_pos pos_n2_route15_max    "-gW=2  -gH=4  $D60"
  run_pos pos_n16_route15_max   "-gW=16 -gH=4  $D60"
  run_pos pos_col16_route15_max "-gW=1  -gH=16 $D60"
  # min corner (fast silicon: hold / pulse / float checks), 50 % duty
  run_pos pos_n1_route15_min   "-gW=1  -gH=4  -gCORNER_CLK=0 -gCORNER_LATCH=0 -gCORNER_DATA=0"
  run_pos pos_n16_route15_min  "-gW=16 -gH=4  -gCORNER_CLK=0 -gCORNER_LATCH=0 -gCORNER_DATA=0"
  run_pos pos_col16_route15_min "-gW=1 -gH=16 -gCORNER_CLK=0 -gCORNER_LATCH=0 -gCORNER_DATA=0"
  # component-only (no route) reference points, max corner, 50 % duty OK
  run_pos pos_n16_route0_max   "-gW=16 -gH=4  -gROUTE_100PS=0"
  run_pos pos_col16_route0_max "-gW=1  -gH=16 -gROUTE_100PS=0"
  # cross corners: fast latch chain vs slow clock and vice versa
  # (anti-tracking stress of the recovery/window relationships)
  run_pos pos_n16_lmin_cmax    "-gW=16 -gH=4 -gCORNER_LATCH=0 -gCORNER_CLK=1 -gCORNER_DATA=1 $D60"
  run_pos pos_n16_lmax_cmin    "-gW=16 -gH=4 -gCORNER_LATCH=1 -gCORNER_CLK=0 -gCORNER_DATA=0"

  # ============================================================ negative runs
  # Each injects (or, for neg_maxcorner_50duty, does not compensate) a timing
  # defect; the harness above REQUIRES a caught in-simulation failure.
  run_neg neg_recovery_g12     "-gW=1 -gH=4 -gGUARD_100PS=120"
  run_neg neg_release_clk2     "-gW=1 -gH=2 -gSCALE_CLK_PCT=200"
  run_neg neg_setup_data35     "-gW=1 -gH=2 -gSCALE_DATA_PCT=350"
  run_neg neg_sample_lead45    "-gW=2 -gH=4 -gLEAD_100PS=450"
  # documented finding: uncompensated 50 % duty at max corner + 1.5 ns route
  # lets the column-switch W transition land past the source falling edge
  run_neg neg_maxcorner_50duty "-gW=2 -gH=4"

  # ============================================================ sweeps
  # min LATCH_GUARD vs N, sample-lead window vs N, min clock-high phase vs N
  # (max corner, synthetic route 1.5 ns except where noted); results/sweeps.txt
  SW="$RES/sweeps.txt"
  {
    echo "# sweep tables, 1.5 ns/hop synthetic route, 50 ns period (20 MHz)"
    echo "# guard sweep: latch deassert -> first clock; lead sweep: sample lead"
    echo "# window; high sweep: min clock high phase (W-switch containment)"
    echo "# columns: corner N H | min_guard_ns | min_lead_ns | max_lead_ns | min_high_ns"
  } > "$SW"
  pass_guard=1
  for CORNER in max min; do
    CFLAGS=""
    [ "$CORNER" = "min" ] && CFLAGS="-gCORNER_CLK=0 -gCORNER_LATCH=0 -gCORNER_DATA=0"
    for NN in "1 4" "2 4" "16 4" "1 16"; do
      set -- $NN; w=$1; h=$2
      guard_min=""
      for g in 0 1 2 3 4 5 6 8 10 12 15 20 25 30 40; do
        set +e
        ghdl elab-run $GFLAGS chain_tb -gNAME="sw_g${g}_n${w}x${h}_${CORNER}" \
          -gW="$w" -gH="$h" -gGUARD_100PS="$((10 * g))" -gCLK_HIGH_100PS=300 -gCLK_LOW_100PS=200 $CFLAGS $STOP \
          >"$RES/sw_g${g}_n${w}x${h}_${CORNER}.log" 2>&1
        rc=$?
        set -e
        if [ "$rc" = "0" ] && grep -q "TCREGPASS" "$RES/sw_g${g}_n${w}x${h}_${CORNER}.log"; then
          guard_min=$g
          break
        fi
      done
      lead_min=""; lead_max=""
      for s in 5 10 20 30 40 50 60 80 100 120 160 200 240 280 320 360 400 450 490; do
        set +e
        ghdl elab-run $GFLAGS chain_tb -gNAME="sw_s${s}_n${w}x${h}_${CORNER}" \
          -gW="$w" -gH="$h" -gLEAD_100PS="$s" -gCLK_HIGH_100PS=300 -gCLK_LOW_100PS=200 $CFLAGS $STOP \
          >"$RES/sw_s${s}_n${w}x${h}_${CORNER}.log" 2>&1
        rc=$?
        set -e
        if [ "$rc" = "0" ] && grep -q "TCREGPASS" "$RES/sw_s${s}_n${w}x${h}_${CORNER}.log"; then
          [ -z "$lead_min" ] && lead_min=$((s / 10)).$((s % 10))
          lead_max=$((s / 10)).$((s % 10))
        fi
      done
      high_min=""
      for hi in 250 260 270 280 290 300 310 320 340 360; do
        lo=$((500 - hi))
        set +e
        ghdl elab-run $GFLAGS chain_tb -gNAME="sw_hi${hi}_n${w}x${h}_${CORNER}" \
          -gW="$w" -gH="$h" -gCLK_HIGH_100PS="$hi" -gCLK_LOW_100PS="$lo" $CFLAGS $STOP \
          >"$RES/sw_hi${hi}_n${w}x${h}_${CORNER}.log" 2>&1
        rc=$?
        set -e
        if [ "$rc" = "0" ] && grep -q "TCREGPASS" "$RES/sw_hi${hi}_n${w}x${h}_${CORNER}.log"; then
          high_min=$((hi / 10)).$((hi % 10))
          break
        fi
      done
      {
        echo "N=${w} H=${h} corner=${CORNER} : min_guard_ns=${guard_min:-NONE} min_lead_ns=${lead_min:-NONE} max_lead_ns=${lead_max:-NONE} min_high_ns=${high_min:-NONE}"
        echo "SWEEP N=${w} H=${h} corner=${CORNER} guard_min_ns=${guard_min:-NONE} lead_min_ns=${lead_min:-NONE} lead_max_ns=${lead_max:-NONE} high_min_ns=${high_min:-NONE}"
      } | tee -a "$SW"
      [ -z "$guard_min" ] && { pass_guard=0; FAILED="$FAILED sweep_guard_n${w}x${h}_${CORNER}"; }
    done
    # shellcheck disable=SC2086
    :
  done
  if [ "$pass_guard" != "1" ]; then
    echo "FAIL  sweep: some guard minima could not be found" | tee -a "$SUMMARY"
    fail=$((fail + 1))
  fi
fi

{
  echo
  echo "runs passed: $pass, failed: $fail"
} | tee -a "$SUMMARY"

if [ "$fail" != "0" ]; then
  echo "TIMING-CHAIN FAILED:$FAILED" | tee -a "$SUMMARY"
  exit 1
fi
echo "TIMING-CHAIN PASS" | tee -a "$SUMMARY"
