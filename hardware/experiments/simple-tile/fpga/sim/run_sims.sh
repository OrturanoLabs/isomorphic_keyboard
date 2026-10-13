#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# Self-checking equivalence + unit sims for the simple-tile FPGA candidate.
#
#   hardware/experiments/simple-tile/fpga/sim/run_sims.sh
#
# Behaviour (mirrors ../../regression/run_regression.sh conventions):
#   * uses the OSS CAD Suite container (tools/oss.sh) when the image is
#     present, otherwise host ghdl; the choice + ghdl version + image id are
#     pinned into logs/env.log
#   * analyses READ-ONLY references by path (hardware/simulation/74hc165.vhdl,
#     tile.vhdl; ../../regression/tile_reg_pkg.vhdl) plus the DUT
#     (../rtl/tile_fpga.vhdl) and the two testbenches here
#   * unit scenarios: first-bit-before-clock, keys changing DURING latch,
#     keys changing after the latch (frozen), mid-scan latch reset,
#     W mux / true tri-state, B_W counter flag, idle tail
#   * pair-grid configs: REF grid (rev-A model) and DUT grid, identical
#     stimulus; per-sample stream equality vs the docs-derived reference AND
#     per-edge B_W / T_clk|L_clk / per-tile B_data equality between grids
#   * mutation stage on ../rtl/tile_fpga.vhdl copies: each mutation MUST fail
#     in simulation; a mutation that passes makes the suite fail
#   * generated files (build/, logs/) are git-ignored; no VCD
#
# Zero-delay 20 MHz behavioural sims: FUNCTIONALITY ONLY.

set -euo pipefail
cd "$(dirname "$0")"

SIM_REL=hardware/simulation
ROOT_REL=../../../../..
BUILD=build
LOGS=logs
GFLAGS="--std=08 -fsynopsys --workdir=$BUILD"
STOP="--stop-time=200us"

# ---------------------------------------------------------------- wrapper mode
if [ "${FPGA_INSIDE:-0}" != "1" ]; then
  mkdir -p "$LOGS"
  IMAGE="${OSS_IMAGE:-localhost/oss-cad-suite:2026-09-26}"
  if command -v podman >/dev/null 2>&1 && podman image exists "$IMAGE"; then
    DIGEST="$(podman image inspect --format='{{.Id}}' "$IMAGE" 2>/dev/null || echo unknown)"
    echo "container $IMAGE id $DIGEST" > "$LOGS/mode.log"
    exec "$ROOT_REL/tools/oss.sh" env FPGA_INSIDE=1 OSS_DIGEST="$DIGEST" \
      bash ./run_sims.sh "$@"
  fi
  echo "container image $IMAGE not found, trying host ghdl" | tee "$LOGS/mode.log"
fi

if ! command -v ghdl >/dev/null 2>&1; then
  echo "ERROR: ghdl not available (no container image, no host ghdl)" >&2
  exit 2
fi

mkdir -p "$BUILD" "$LOGS"
rm -rf "$BUILD"/mutants "$BUILD"/*.o "$BUILD"/*.cf "$BUILD"/tile_*_tb "$BUILD"/e~* 2>/dev/null || true
rm -f ./tile_unit_tb ./tile_grid_pair_tb ./e~*.o 2>/dev/null || true

# ---------------------------------------------------------------- pinned env log
{
  echo "date_utc:     $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ "${FPGA_INSIDE:-0}" = "1" ]; then
    echo "mode:         container ${OSS_IMAGE:-localhost/oss-cad-suite:2026-09-26}"
    echo "image_id:     ${OSS_DIGEST:-unknown}"
  else
    echo "mode:         host (no container image)"
  fi
  echo "ghdl_version: $(ghdl --version | head -1)"
  ghdl --version | sed -n '2,3p' | sed 's/^/              /'
  echo "kernel:       $(uname -srmo)"
} | tee "$LOGS/env.log"

# ---------------------------------------------------------------- analysis
REFS="$ROOT_REL/$SIM_REL/74hc165.vhdl $ROOT_REL/$SIM_REL/tile.vhdl \
       ../../regression/tile_reg_pkg.vhdl"
DUT="../rtl/tile_fpga.vhdl"
TBS="tile_unit_tb.vhdl tile_grid_pair_tb.vhdl"
# shellcheck disable=SC2086
ghdl -a $GFLAGS $REFS $DUT $TBS

pass=0
fail=0
FAILED=""
SUMMARY="$LOGS/summary.txt"
{
  echo "== simple-tile FPGA candidate self-checks =="
  echo "ghdl: $(ghdl --version | head -1)"
  echo "flags: $GFLAGS"
  echo
} > "$SUMMARY"

run_tb() {  # tb|name|gens -> 0 iff pass (exit 0 + REGPASS marker)
  local tb="$1" name="$2" gens="$3" log="$LOGS/$2.log"
  set +e
  # shellcheck disable=SC2086
  ghdl elab-run $GFLAGS "$tb" -gNAME="$name" $gens $STOP >"$log" 2>&1
  local rc=$?
  set -e
  if [ "$rc" = "0" ] && grep -q "REGPASS $name" "$log"; then
    return 0
  fi
  return 1
}

record() {  # tb name gens
  if run_tb "$@"; then
    echo "PASS  $2" | tee -a "$SUMMARY"
    pass=$((pass + 1))
  else
    echo "FAIL  $2   (see $LOGS/$2.log)" | tee -a "$SUMMARY"
    tail -5 "$LOGS/$2.log" | sed 's/^/        /' || true
    fail=$((fail + 1))
    FAILED="$FAILED $2"
  fi
}

# ---------------------------------------------------------------- unit scenarios
# track = sysclk approximate snapshot; fall = exact latch-edge snapshot
record tile_unit_tb unit_track "-gSNAP=track"
record tile_unit_tb unit_fall  "-gSNAP=fall"

# ---------------------------------------------------------------- pair-grid matrix
# identical topology coverage to the regression harness + ragged equality,
# once per snapshot mode
CONFIGS="
single_rel|-gPRESENT=1 -gBMODE=2
single_press|-gPRESENT=1 -gBMODE=1
single_dist|-gPRESENT=1
column2_dist|-gW=1 -gH=2 -gPRESENT=11
column16_dist|-gW=1 -gH=16 -gPRESENT=1111111111111111
column16_press|-gW=1 -gH=16 -gPRESENT=1111111111111111 -gBMODE=1
row4_dist|-gW=4 -gH=1 -gPRESENT=1111
row16_dist|-gW=16 -gH=1 -gPRESENT=1111111111111111
grid2x3_dist|-gW=2 -gH=3 -gPRESENT=111111
grid_mixed_dist|-gW=3 -gH=3 -gPRESENT=111101001
grid4x4_dist|-gW=4 -gH=4 -gPRESENT=1111111111111111
grid4x4_press|-gW=4 -gH=4 -gPRESENT=1111111111111111 -gBMODE=1
ragged_gap_detect|-gW=3 -gH=3 -gPRESENT=111100010 -gRAGGED=1
ragged_hole_detect|-gW=3 -gH=2 -gPRESENT=101111 -gRAGGED=1
"

for mode in track fall; do
  while IFS='|' read -r name gens; do
    [ -z "${name// }" ] && continue
    record tile_grid_pair_tb "grid_${mode}_$name" "-gSNAP=$mode $gens"
  done <<< "$CONFIGS"
done

# ---------------------------------------------------------------- mutations
# name|grid-gens|match fragment (grep -F)|replacement
# each mutation is run against BOTH testbenches (unit + 1x1 grid); the
# shadow-freeze mutation is only observable in the unit bench (grid keys are
# static), the rest bite in both.
MUT="$BUILD/mutants"
mkdir -p "$MUT"
MUTATIONS="
mut_markers|-gPRESENT=1|pd(3)           <= '1';|pd(3)           <= '0';
mut_nosnap|-gPRESENT=1|shreg  <= shadow(14 downto 0) & dsin;   -- first shift special load|shreg  <= shreg(14 downto 0) & dsin;
mut_shadowfreeze|-gPRESENT=1|        if latch = '1' then|        if true then
mut_bwcount|-gPRESENT=1|cnt = \"1111\"|cnt = \"1110\"
"

echo >> "$SUMMARY"
while IFS='|' read -r mname gens match repl; do
  [ -z "${mname// }" ] && continue
  src="$MUT/$mname.vhdl"
  cp "$DUT" "$src"
  if ! grep -qF "$match" "$src"; then
    echo "ERROR  $mname: mutation pattern not found in tile_fpga copy" | tee -a "$SUMMARY"
    fail=$((fail + 1))
    FAILED="$FAILED $mname(noapply)"
    continue
  fi
  repl_sed="${repl//&/\\&}"
  sed -i "s|${match}|${repl_sed}|" "$src"
  if ! grep -qF "$repl" "$src"; then
    echo "ERROR  $mname: sed did not change the copy" | tee -a "$SUMMARY"
    fail=$((fail + 1))
    FAILED="$FAILED $mname(nochange)"
    continue
  fi
  ghdl -a $GFLAGS "$src" || { echo "ERROR  $mname: mutant does not analyse" | tee -a "$SUMMARY"; fail=$((fail + 1)); FAILED="$FAILED $mname(noanalyze)"; continue; }
  ghdl -a $GFLAGS $TBS
  caught=0
  for tb in tile_unit_tb tile_grid_pair_tb; do
    log="$LOGS/${mname}_${tb}.log"
    if [ "$tb" = "tile_unit_tb" ]; then mgens="-gSNAP=track"; else mgens="-gSNAP=track $gens"; fi
    set +e
    # shellcheck disable=SC2086
    ghdl elab-run $GFLAGS "$tb" -gNAME="$mname:$tb" $mgens $STOP >"$log" 2>&1
    rc=$?
    set -e
    if grep -q "error: compilation error" "$log" || grep -q "obsoleted" "$log" \
       || grep -q "error during elaboration" "$log"; then
      echo "ERROR  $mname: mutation run did not reach simulation (see $log)" | tee -a "$SUMMARY"
      fail=$((fail + 1))
      FAILED="$FAILED ${mname}(norun)"
      caught=-1
      break
    elif [ "$rc" != "0" ] && grep -q "assertion failure" "$log"; then
      caught=$((caught + 1))
    fi
  done
  if [ "$caught" = "-1" ]; then
    :
  elif [ "$caught" -ge 1 ]; then
    echo "PASS  $mname (mutation caught in $caught/2 benches)" | tee -a "$SUMMARY"
    pass=$((pass + 1))
  else
    echo "FAIL  $mname: mutation was NOT caught by either bench" | tee -a "$SUMMARY"
    fail=$((fail + 1))
    FAILED="$FAILED $mname(notcaught)"
  fi
  # restore the pristine DUT into the work library
  # shellcheck disable=SC2086
  ghdl -a $GFLAGS $DUT
  ghdl -a $GFLAGS $TBS
done <<< "$MUTATIONS"

# final sanity: pristine DUT still passes after the mutation stage
if run_tb tile_grid_pair_tb sanity_after_mutations "-gPRESENT=1"; then
  echo "PASS  sanity_after_mutations" | tee -a "$SUMMARY"
  pass=$((pass + 1))
else
  echo "FAIL  sanity_after_mutations" | tee -a "$SUMMARY"
  fail=$((fail + 1))
  FAILED="$FAILED sanity_after_mutations"
fi

# ---------------------------------------------------------------- verdict
{
  echo
  echo "configs+mutations passed: $pass, failed: $fail"
} | tee -a "$SUMMARY"

if [ "$fail" != "0" ]; then
  echo "SIMS FAILED:$FAILED" | tee -a "$SUMMARY"
  exit 1
fi
echo "SIMS PASS" | tee -a "$SUMMARY"