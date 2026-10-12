#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# Self-checking rev-A tile scan regression.
#
#   hardware/experiments/simple-tile/regression/run_regression.sh
#
# Behaviour:
#   * uses the OSS CAD Suite container (tools/oss.sh) when the image is present,
#     otherwise falls back to host ghdl; the choice is logged and pinned
#     (ghdl version + container image id/digest) into logs/env.log
#   * analyses the UNMODIFIED DUT (hardware/simulation/74hc165.vhdl, tile.vhdl)
#     plus the reference model + testbench from this directory
#   * runs the topology matrix below; a config passes only if GHDL exits 0 AND
#     the "REGPASS <name>" marker is in its log (logs/<name>.log)
#   * then runs mutation configs: tile.vhdl is copied to build/mutants/, sed-edited
#     (bit mapping / fixed flag / W select), and the regression MUST FAIL;
#     a mutation that still passes is itself a regression failure
#   * generated files (build/, logs/) are git-ignored; no VCD is produced
#
# Zero-delay behavioural sims at a 20 MHz shift clock: functionality ONLY,
# not hardware timing closure.

set -euo pipefail
cd "$(dirname "$0")"

SIM_REL=hardware/simulation
ROOT_REL=../../../..
BUILD=build
LOGS=logs
GFLAGS="--std=08 -fsynopsys --workdir=$BUILD"
STOP="--stop-time=60us"

# ---------------------------------------------------------------- wrapper mode
if [ "${REG_INSIDE:-0}" != "1" ]; then
  mkdir -p "$LOGS"
  IMAGE="${OSS_IMAGE:-localhost/oss-cad-suite:2026-09-26}"
  if command -v podman >/dev/null 2>&1 && podman image exists "$IMAGE"; then
    DIGEST="$(podman image inspect --format='{{.Id}}' "$IMAGE" 2>/dev/null || echo unknown)"
    mkdir -p "$LOGS"
    echo "container $IMAGE id $DIGEST" > "$LOGS/mode.log"
    exec "$ROOT_REL/tools/oss.sh" env REG_INSIDE=1 OSS_DIGEST="$DIGEST" \
      bash ./run_regression.sh "$@"
  fi
  echo "container image $IMAGE not found, trying host ghdl" | tee "$LOGS/mode.log"
fi

if ! command -v ghdl >/dev/null 2>&1; then
  echo "ERROR: ghdl not available (no container image, no host ghdl)" >&2
  exit 2
fi

# clean work library and binaries so every run is reproducible from scratch
# (ghdl elab-run links the executable into the CWD: git-ignored, removed here)
mkdir -p "$BUILD" "$LOGS"
rm -rf "$BUILD"/mutants "$BUILD"/*.o "$BUILD"/*.cf "$BUILD"/tile_grid_tb "$BUILD"/e~* 2>/dev/null || true
rm -f ./tile_grid_tb ./probe_tb ./e~*.o 2>/dev/null || true

# ---------------------------------------------------------------- pinned env log
{
  echo "date_utc:     $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ "${REG_INSIDE:-0}" = "1" ]; then
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
DUT="$ROOT_REL/$SIM_REL/74hc165.vhdl $ROOT_REL/$SIM_REL/tile.vhdl"
HARNESS="tile_reg_pkg.vhdl tile_grid_tb.vhdl"
# shellcheck disable=SC2086
ghdl -a $GFLAGS $DUT $HARNESS

# ---------------------------------------------------------------- config matrix
# name|extra generics
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

pass=0
fail=0
FAILED=""
SUMMARY="$LOGS/summary.txt"
{
  echo "== rev-A tile scan regression =="
  echo "ghdl: $(ghdl --version | head -1)"
  echo "flags: $GFLAGS elab-run <unit> -gNAME=<cfg> ... $STOP"
  echo
} > "$SUMMARY"

run_cfg() {  # name gens -> 0 iff pass (exit 0 + REGPASS marker)
  local name="$1" gens="$2" log="$LOGS/$1.log"
  set +e
  # shellcheck disable=SC2086
  ghdl elab-run $GFLAGS tile_grid_tb -gNAME="$name" $gens $STOP >"$log" 2>&1
  local rc=$?
  set -e
  if [ "$rc" = "0" ] && grep -q "REGPASS $name " "$log"; then
    return 0
  fi
  return 1
}

while IFS='|' read -r name gens; do
  [ -z "${name// }" ] && continue
  if run_cfg "$name" "$gens"; then
    echo "PASS  $name" | tee -a "$SUMMARY"
    pass=$((pass + 1))
  else
    echo "FAIL  $name   (see $LOGS/$name.log)" | tee -a "$SUMMARY"
    tail -5 "$LOGS/$name.log" | sed 's/^/        /' || true
    fail=$((fail + 1))
    FAILED="$FAILED $name"
  fi
done <<< "$CONFIGS"

# ---------------------------------------------------------------- mutations
# name|config-name-for-run|gens|match fragment (grep -F, must exist)|replacement
MUT="$BUILD/mutants"
mkdir -p "$MUT"
MUTATIONS="
mut_markers|single_dist|-gPRESENT=1|& \"11\" &|& \"10\" &
mut_flagbits|grid4x4_dist|-gW=4 -gH=4 -gPRESENT=1111111111111111|to_x01(L_endrow_p) & to_x01(T_endcol_p)|to_x01(T_endcol_p) & to_x01(L_endrow_p)
mut_wsel|grid4x4_dist|-gW=4 -gH=4 -gPRESENT=1111111111111111|ds_input <= T_data_p when to_x01(w_state) = '0' else L_data_p;|ds_input <= L_data_p when to_x01(w_state) = '0' else T_data_p;
mut_bwcount|grid4x4_dist|-gW=4 -gH=4 -gPRESENT=1111111111111111|ffinput <= count(3) and count(2) and count(1) and count(0) and data;|ffinput <= count(3) and count(2) and count(1) and not count(0) and data;
"

echo >> "$SUMMARY"
while IFS='|' read -r mname cfg gens match repl; do
  [ -z "${mname// }" ] && continue
  src="$MUT/$mname.vhdl"
  cp "$ROOT_REL/$SIM_REL/tile.vhdl" "$src"
  if ! grep -qF "$match" "$src"; then
    echo "ERROR  $mname: mutation pattern not found in tile.vhdl copy" | tee -a "$SUMMARY"
    fail=$((fail + 1))
    FAILED="$FAILED $mname(noapply)"
    continue
  fi
  # escape & in the replacement for sed
  repl_sed="${repl//&/\\&}"
  sed -i "s|${match}|${repl_sed}|" "$src"
  if ! grep -qF "$repl" "$src"; then
    echo "ERROR  $mname: sed did not change the copy" | tee -a "$SUMMARY"
    fail=$((fail + 1))
    FAILED="$FAILED $mname(nochange)"
    continue
  fi
  ghdl -a $GFLAGS "$src" || { echo "ERROR  $mname: mutant does not analyse"; fail=$((fail + 1)); FAILED="$FAILED $mname(noanalyze)"; continue; }
  # re-analyse the testbench so GHDL does not flag it obsoleted by the mutant
  ghdl -a $GFLAGS tile_grid_tb.vhdl
  log="$LOGS/$mname.log"
  set +e
  # shellcheck disable=SC2086
  ghdl elab-run $GFLAGS tile_grid_tb -gNAME="$cfg-mut:$mname" $gens $STOP >"$log" 2>&1
  rc=$?
  set -e
  # "caught" = the simulation itself raised an assertion; an elaboration or
  # compile failure is an infrastructure error, NOT a caught mutation
  if grep -q "error: compilation error" "$log" || grep -q "obsoleted" "$log"; then
    echo "ERROR  $mname: mutation run did not reach simulation (see $log)" | tee -a "$SUMMARY"
    fail=$((fail + 1))
    FAILED="$FAILED $mname(norun)"
  elif [ "$rc" != "0" ] && grep -q "assertion failure" "$log"; then
    echo "PASS  $mname (mutation caught in simulation: rc=$rc)" | tee -a "$SUMMARY"
    pass=$((pass + 1))
  else
    echo "FAIL  $mname: mutation was NOT caught by the harness (rc=$rc)" | tee -a "$SUMMARY"
    fail=$((fail + 1))
    FAILED="$FAILED $mname(notcaught)"
  fi
  # restore the pristine DUT into the work library before the next run
  # shellcheck disable=SC2086
  ghdl -a $GFLAGS $DUT
  ghdl -a $GFLAGS tile_grid_tb.vhdl
done <<< "$MUTATIONS"

# final sanity: pristine DUT still passes after the mutation stage
if run_cfg "sanity_after_mutations" "-gPRESENT=1"; then
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
  echo "REGRESSION FAILED:$FAILED" | tee -a "$SUMMARY"
  exit 1
fi
echo "REGRESSION PASS" | tee -a "$SUMMARY"
