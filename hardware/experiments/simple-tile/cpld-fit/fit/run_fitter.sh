#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# run_fitter.sh -- hand the techmapped EDIF (results/tile_cpld_atf1502.edif)
# to a USER-PROVIDED, LICENSED ATF1500 fitter. Microchip's ATF1502 fitter
# (ProChip Designer / WinCUPL, POF2JED) is proprietary; per project policy and
# the cpld-fit checkpoint:
#
#   * NOTHING is installed by this script -- no package manager, no Wine, no
#     binary download, no license-agreement acceptance;
#   * the fitter path MUST be given explicitly (argument or CPLDFIT_FITTER);
#   * if no fitter is available, this script FAILS LOUDLY (exit 2) and the
#     device fit remains BLOCKED -- generic cell counts are never presented
#     as a device fit anywhere in this workstream.
#
# usage:
#   fit/run_fitter.sh /abs/path/to/fitter [fitter-args...]
#   CPLDFIT_FITTER=/abs/path/to/fitter fit/run_fitter.sh [fitter-args...]
#   CPLDFIT_WINE=/abs/path/to/wine \
#     fit/run_fitter.sh /abs/path/to/fit1502.exe [args...]
#
# The exact command executed and the fitter's own output go to
# results/logs/fitter.log. Fitter exit codes propagate.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CF="$(cd "$HERE/.." && pwd)"
cd "$CF"

FITTER="${1:-${CPLDFIT_FITTER:-}}"
if [ -n "${1:-}" ]; then shift; fi   # remaining "$@" = fitter arguments
EDIF="results/tile_cpld_atf1502.edif"

fail() { echo "FIT-BLOCKED: $*" >&2; exit 2; }

[ -f "$EDIF" ] || fail "techmapped EDIF missing: $EDIF (run synth/run_synth.sh first)"

if [ -z "$FITTER" ]; then
  cat >&2 <<'EOM'
FIT-BLOCKED: no fitter path given.
  The ATF1502ASV fitter (Microchip ProChip Designer / WinCUPL POF2JED stage)
  is proprietary and is NOT present on this system (checked: no fit1502,
  no WinCUPL, no wine -- see checkpoints/cpld-fit.md).
  To run the fit, pass an explicit path to a licensed executable:
    fit/run_fitter.sh /abs/path/to/fit1502 [args...]
  This script never installs software and never accepts license agreements
  on the user's behalf.
EOM
  exit 2
fi

[ -e "$FITTER" ] || fail "fitter path does not exist: $FITTER"

RUNNER=()
if [[ "$FITTER" == *.exe || "$FITTER" == *.EXE ]]; then
  WINE="${CPLDFIT_WINE:-}"
  [ -n "$WINE" ] || fail "fitter is a .exe; set CPLDFIT_WINE=/abs/path/to/wine explicitly (wine is NOT present here and is never auto-installed)"
  [ -x "$WINE" ] || fail "CPLDFIT_WINE not executable: $WINE"
  RUNNER=("$WINE")
fi

[ -x "$FITTER" ] || fail "fitter path is not executable: $FITTER"

mkdir -p results/logs
{
  echo "date_utc: $(date -u '+%FT%TZ')"
  sha256sum "$EDIF"
  echo "fitter: $FITTER"
  [ "${#RUNNER[@]}" -gt 0 ] && echo "runner: ${RUNNER[*]}"
  printf 'invocation:'; printf ' %q' "${RUNNER[@]}" "$FITTER" "$EDIF" "$@"; printf '\n'
} | tee results/logs/fitter.log

set +e
"${RUNNER[@]}" "$FITTER" "$EDIF" "$@" 2>&1 | tee -a results/logs/fitter.log
rc=${PIPESTATUS[0]}
set -e
echo "fitter exit code: $rc" | tee -a results/logs/fitter.log
exit "$rc"
