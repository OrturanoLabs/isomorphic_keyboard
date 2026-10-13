#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
#
# scan20 functional regression.
#
# Positive grids run the UNCHANGED fall-snapshot tile FPGA cores
# (hardware/experiments/simple-tile/fpga/rtl/tile_fpga.vhdl) and the
# docs-derived expected-stream package (regression/tile_reg_pkg.vhdl)
# against firmware/ice40/scan20/src/scan20_core.vhdl at the two EXACT
# 20 MHz-shift configurations (f60: 3 ticks/bit 2h+1l; f120: 6 ticks/bit
# 4h+2l). Negative configs must hit real VHDL assertions (model floors)
# and DUT mutants must be caught by runtime scoreboard assertions.
#
# Usage:   bash run_sims.sh           (container localhost/oss-cad-suite,
#                                      one podman invocation for everything)
#          OSS_HOST=1 bash run_sims.sh  (host oss-cad-suite fallback)
#
# Logs:    sim/build/logs/<run>.log ; ghdl worklibs under sim/build/.
# Exit 0 <=> every expectation met. Never exits silently.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null || echo /work)"
BUILD="$HERE/build"
LOGS="$BUILD/logs"
mkdir -p "$BUILD" "$LOGS"

# re-exec once inside the container (oss.sh mounts $REPO at /work, cwd kept)
if [ "${OSS_HOST:-0}" != "1" ] && [ "${SCAN20_INBOX:-0}" != "1" ]; then
  cd "$HERE"
  exec "$REPO/tools/oss.sh" bash -c "SCAN20_INBOX=1 bash run_sims.sh"
fi
if [ "${OSS_HOST:-0}" = "1" ]; then
  export PATH="$HOME/.local/share/oss-cad-suite/bin:$PATH"
fi

cd "$HERE"
echo "env: $(ghdl --version | head -1)"
echo "cwd: $(pwd)"

PKGSRC="../../../../hardware/experiments/simple-tile/regression/tile_reg_pkg.vhdl"
TILESRC="../../../../hardware/experiments/simple-tile/fpga/rtl/tile_fpga.vhdl"
CORESRC="../src/scan20_core.vhdl"
TBSRC="scan20_tb.vhdl"
for f in "$PKGSRC" "$TILESRC" "$CORESRC" "$TBSRC"; do
  [ -f "$f" ] || { echo "MISSING SOURCE: $f"; exit 2; }
done

LIB="$BUILD/lib"
rm -rf "$LIB"; mkdir -p "$LIB"

analyze() { # args: workdir files...
  local wd="$1"; shift
  ghdl -a --std=08 -fsynopsys --workdir="$wd" "$@" || exit 2
}

analyze "$LIB" "$PKGSRC" "$TILESRC" "$CORESRC" "$TBSRC"

PASS_N=0; FAIL_N=0

# apply generics; run; expect PASS token -------------------------------------
run_pos() {
  local name="$1"; shift
  local log="$LOGS/$name.log"
  timeout 600 ghdl --elab-run --std=08 --workdir="$LIB" scan20_tb -gNAME="$name" "$@" \
    > "$log" 2>&1
  local rc=$?
  if [ $rc -eq 0 ] && grep -q "SCAN20PASS $name" "$log"; then
    echo "PASS  $name  ($(grep -m1 SCAN20SUMMARY "$log" | tr -s ' '))"
    PASS_N=$((PASS_N+1))
  else
    echo "FAIL  $name  rc=$rc (log: $log)"
    grep -E "assertion|error|failure" "$log" | head -3
    FAIL_N=$((FAIL_N+1))
  fi
}

# expect a real assertion failure whose text matches a token ------------------
run_neg() {
  local name="$1" token="$2"; shift 2
  local log="$LOGS/$name.log"
  timeout 600 ghdl --elab-run --std=08 --workdir="$LIB" scan20_tb -gNAME="$name" "$@" \
    > "$log" 2>&1
  local rc=$?
  if grep -q "SCAN20PASS" "$log"; then
    echo "FAIL  $name  passed but MUST NOT (log: $log)"
    FAIL_N=$((FAIL_N+1))
  elif grep -qi "$token" "$log"; then
    echo "PASS  $name  caught: $(grep -i -m 1 "$token" "$log" | tr -s ' ' | cut -c1-100)"
    PASS_N=$((PASS_N+1))
  else
    echo "FAIL  $name  failed rc=$rc but without expected token '$token' (log: $log)"
    grep -E "assertion|error|failure" "$log" | head -3
    FAIL_N=$((FAIL_N+1))
  fi
}

# generic sets -------------------------------------------------------------
# f60: 60.000 MHz exact (icepll DIVF=79 DIVQ=4); 3 ticks/bit = 33.33ns high +
#      16.67ns low; guard 4*16.667 = 66.7 ns (>= 50 ns deep-col max bound)
F60="-gTSYS_PS=16667 -gTPB=3 -gTHI=2 -gLEAD=1 -gGUARD_TICKS=4 -gFGAP_TICKS=3 -gLATCH_TICKS=60 -gREC_TICKS=120 -gIDLE_TICKS=400"
# f120: 120.000 MHz exact (DIVF=79 DIVQ=3); 6 ticks/bit = 33.33ns high +
#      16.67ns low; guard 7*8.333 = 58.3 ns (>= 50 ns; 6 ticks=50.0 exact
#      physically but 49.998 ns on the sim 1 ps grid -> use 7)
F120="-gTSYS_PS=8333 -gTPB=6 -gTHI=4 -gLEAD=1 -gGUARD_TICKS=7 -gFGAP_TICKS=6 -gLATCH_TICKS=120 -gREC_TICKS=240 -gIDLE_TICKS=800"

P16="1111111111111111"   # 16 ones
MIX="111110100100"       # 3x4 bottom-up rows: c1 h4, c2 h2, c3 h1 -> 7 frames

for C in F60 F120; do
  CFG="$(eval echo \$$C)"
  lc="$(echo "$C" | tr 'A-Z' 'a-z')"
  run_pos ${lc}_n1x1  $CFG -gW=1  -gH=1  -gPRESENT="1"      -gCLEAN_SCANS=2
  run_pos ${lc}_col2  $CFG -gW=1  -gH=2  -gPRESENT="11"     -gCLEAN_SCANS=2
  run_pos ${lc}_col16 $CFG -gW=1  -gH=16 -gPRESENT="$P16"   -gCLEAN_SCANS=2 -gMODEL_MIN_GUARD_PS=50000
  run_pos ${lc}_g4x4  $CFG -gW=4  -gH=4  -gPRESENT="$P16"   -gCLEAN_SCANS=2
  run_pos ${lc}_mix34 $CFG -gW=3  -gH=4  -gPRESENT="$MIX"   -gCLEAN_SCANS=2
  # marker-error injection + recovery (test-engine behaviour, not MIDI path)
  run_pos ${lc}_injcol2 $CFG -gW=1 -gH=2 -gPRESENT="11"    -gCLEAN_SCANS=2 -gINJ_FRAME=1 -gINJ_EP=1
  run_pos ${lc}_inj4x4  $CFG -gW=4 -gH=4 -gPRESENT="$P16"  -gCLEAN_SCANS=2 -gINJ_FRAME=5 -gINJ_EP=1
done
# watchdog recovery (physics of the episode longer than the given watchdog)
run_pos f60_tmo  $F60  -gW=1 -gH=2 -gPRESENT="11" -gTIMEOUT_TICKS=120 -gEXPECT_TIMEOUTS=2
run_pos f120_tmo $F120 -gW=1 -gH=2 -gPRESENT="11" -gTIMEOUT_TICKS=240 -gEXPECT_TIMEOUTS=2

# negative configs: model floors must fire a REAL assertion ------------------
# duty: 1 tick high @ f60 = 16.7 ns. The DUT armed-fall assert (TICKS_HIGH>=2)
# or the tb chain floor (28 ns) may fire first; both are real assertions.
run_neg neg_f60_duty  "high" $F60 -gTHI=1 -gW=1 -gH=1 -gPRESENT="1"
# deep-col guard: 2 ticks @ f60 = 33.3 ns < 50 ns floor for a 16-deep column
# (DUT lead-fits assert may also fire first for too-small guards)
run_neg neg_f60_col16_guard "guard" $F60 -gGUARD_TICKS=2 -gW=1 -gH=16 -gPRESENT="$P16" -gMODEL_MIN_GUARD_PS=50000
# sample lead: 4 ticks @ f120 = 33.3 ns > 28 ns window
run_neg neg_f120_lead "sample lead outside modeled window" $F120 -gLEAD=4 -gW=1 -gH=1 -gPRESENT="1"
# latch width: 1 tick @ f120 = 8.3 ns (DUT armed-exit assert needs LATCH>=2
# too) -- either real assertion counts
run_neg neg_f120_latch "latch" $F120 -gLATCH_TICKS=1 -gW=1 -gH=1 -gPRESENT="1"

# DUT mutants: the scoreboard must catch real runtime assertions -------------
mut_build() { # name sedscript
  local name="$1" sedscript="$2"
  local mdir="$BUILD/mut_$name"
  rm -rf "$mdir"; mkdir -p "$mdir/lib"
  sed -e "$sedscript" "$CORESRC" > "$mdir/scan20_core.vhdl"
  if cmp -s "$CORESRC" "$mdir/scan20_core.vhdl"; then
    echo "FAIL  mut_$name: sed script did not change the source (vacuous)"
    FAIL_N=$((FAIL_N+1)); return 1
  fi
  analyze "$mdir/lib" "$PKGSRC" "$TILESRC" "$mdir/scan20_core.vhdl" "$TBSRC"
  return 0
}

run_mut() { # name sedscript token cfgset
  local name="$1" sedscript="$2" token="$3" cfgset="$4"
  local log="$LOGS/mut_$name.log"
  if mut_build "$name" "$sedscript"; then
    timeout 600 ghdl --elab-run --std=08 --workdir="$BUILD/mut_$name/lib" scan20_tb \
      -gNAME="mut_$name" $cfgset -gW=1 -gH=2 -gPRESENT="11" -gCLEAN_SCANS=2 \
      > "$log" 2>&1
    if grep -q "SCAN20PASS" "$log"; then
      echo "FAIL  mut_$name  MUTANT NOT CAUGHT (log: $log)"; FAIL_N=$((FAIL_N+1))
    elif grep -qi "$token" "$log"; then
      echo "PASS  mut_$name  caught: $(grep -i -m 1 "$token" "$log" | tr -s ' ' | cut -c1-100)"
      PASS_N=$((PASS_N+1))
    else
      echo "FAIL  mut_$name  died differently ($(grep -E 'assertion|error' "$log" | head -1 | cut -c1-100)); wanted '$token'"
      FAIL_N=$((FAIL_N+1))
    fi
  fi
}

# sample moved to the launch tick: sample->launch lead collapses to 0
run_mut leadpair 's/ph = TICKS_PER_BIT - 2 - SAMPLE_LEAD_TICKS/ph = TICKS_PER_BIT - 1 - SAMPLE_LEAD_TICKS/' \
  "sample->launch lead" "$F60"
# 16th-pulse condition broken: engine tries a 17th launch
run_mut x17launch 's/if bit_cnt = 16 then/if bit_cnt = 17 then/' \
  "preceding sample\|more than 16 launches\|bound check" "$F60"
# clock falls one tick late (f120: fall arm at THI-3): exact-duty assertion
run_mut duty     's/ph = TICKS_HIGH - 2 then/ph = TICKS_HIGH - 3 then/' \
  "high phase" "$F120"
# row walk broken: coords of frame 2 of a column are wrong
run_mut coord    's/row *<= row + 1;/row     <= row + 2;/' \
  "expected (1,2)\|, expected" "$F60"

echo "----------------------------------------------------------------"
echo "SCAN20 SIMS: $PASS_N passed, $FAIL_N failed of $((PASS_N+FAIL_N)) expectations"
[ "$FAIL_N" -eq 0 ]
