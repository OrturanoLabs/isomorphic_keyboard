#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# run_sims.sh -- self-checking Verilog TB for the ATF1502ASV one-chip tile
# candidate, in the pinned OSS CAD Suite container (no host tool installs).
#
#   src/tile_cpld.v  -> must PASS (exit 0 AND marker AND no FAIL lines)
#   sim/mutants/*.v  -> must FAIL (TB catches the defect; a passing mutant
#                       means the TB is blind -> whole run fails)
#
# Logs: ../results/logs/{env,sim_tile_cpld,...}.log, build vvp under
# ../results/build/. Overall exit: 0 only if candidate passes AND every
# mutant is caught.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CF="$(cd "$HERE/.." && pwd)"                 # .../simple-tile/cpld-fit
REPO="$(git -C "$HERE" rev-parse --show-toplevel)"
OSS="$REPO/tools/oss.sh"
IMG="${OSS_IMAGE:-localhost/oss-cad-suite:2026-09-26}"
cd "$CF"

mkdir -p results/build results/logs

{
  echo "date_utc: $(date -u '+%FT%TZ')"
  echo "workdir: $CF"
  echo "image: $IMG"
  podman image inspect "$IMG" --format 'image_id: {{.Id}}'
  printf 'iverilog: '; "$OSS" iverilog -V 2>/dev/null | head -1 || true
  printf 'vvp: '; ( "$OSS" vvp -V 2>&1 || true ) | head -1
  echo "src_sha256:"
  sha256sum src/tile_cpld.v src/tile_cpld_tb.v sim/mutants/*.v | sed 's/^/  /'
} | tee results/logs/env.log

fail_run=0

run_case () { # <name> <dut-file> <expect: pass|fail>
  local name="$1" dut="$2" expect="$3"
  local blog="results/logs/${name}.log"
  echo "== $name (expect $expect) ==" | tee "$blog"
  if ! "$OSS" iverilog -g2012 -o "results/build/${name}.vvp" "$dut" src/tile_cpld_tb.v >>"$blog" 2>&1; then
    echo "  BUILD-ERROR (see $blog)" | tee -a "$blog"
    [ "$expect" = fail ] && { echo "  (fail expected: build error counts as caught)"; return 1; }
    fail_run=1; return 1
  fi
  set +e
  "$OSS" vvp "results/build/${name}.vvp" >>"$blog" 2>&1
  local rc=$?
  set -e
  local marker=0 nfail=0
  grep -q "CPLD_FIT_TB PASS" "$blog" && marker=1
  grep -q "FAIL" "$blog" && nfail=1
  echo "  exit=$rc pass_marker=$marker fail_lines=$nfail" | tee -a "$blog"
  if [ "$expect" = pass ]; then
    if [ "$rc" -eq 0 ] && [ "$marker" -eq 1 ] && [ "$nfail" -eq 0 ]; then
      echo "  OK: candidate PASS" | tee -a "$blog"; return 0
    else
      echo "  ERROR: candidate did not pass cleanly" | tee -a "$blog"
      fail_run=1; return 1
    fi
  else
    if [ "$marker" -eq 1 ] && [ "$rc" -eq 0 ]; then
      echo "  ERROR: MUTANT $name NOT CAUGHT (tb blind)" | tee -a "$blog"
      fail_run=1; return 1
    else
      echo "  OK: mutant $name caught (exit=$rc)" | tee -a "$blog"; return 0
    fi
  fi
}

run_case sim_tile_cpld            src/tile_cpld.v                    pass
run_case mut_syncload             sim/mutants/tile_cpld_syncload.v   fail
run_case mut_flagswap             sim/mutants/tile_cpld_flagswap.v   fail

echo "== summary =="
if [ "$fail_run" -eq 0 ]; then
  echo "RUNS PASS: candidate passes; all mutants caught"
  exit 0
else
  echo "RUNS FAIL"
  exit 1
fi
