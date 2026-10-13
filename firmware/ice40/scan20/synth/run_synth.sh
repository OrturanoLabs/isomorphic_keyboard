#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
#
# scan20 UP5K (sg48) standalone synth/PnR at the ACTUAL PLL clock, explicit
# --freq per config. Interior static timing only: this build closes the FABRIC
# (sysclk domain + 12 MHz reference is unconstrained-ish); the external scan
# chain (pads, cables, '165s, connectors) is NOT part of this STA -- see
# README.md/RESULTS.md. No hardware sign-off is claimed or implied.
#
# Configs:  f60    60.000 MHz exact  (3 ticks/bit 2h+1l)  shift 20.000 MHz
#           f120   120.000 MHz exact (6 ticks/bit 4h+2l)  shift 20.000 MHz
#           f100p5 100.500 MHz (100.0 infeasible per icepll; +0.5% shift)
# The PLL parameters written into the bitstream JSON are re-verified against
# icepll output before PnR (fail hard on mismatch -- no fake divisions).
#
# Usage:   bash run_synth.sh            (container)
#          OSS_HOST=1 bash run_synth.sh (host fallback)
# Per-config artifacts: synth/build/<cfg>/{yosys.log,top.json,nextpnr.log,
#                                          top.asc,top.bin,icetime.log,sta.txt}

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null || echo /work)"
BUILD="$HERE/build"

if [ "${OSS_HOST:-0}" != "1" ] && [ "${SCAN20_INBOX:-0}" != "1" ]; then
  cd "$HERE"
  exec "$REPO/tools/oss.sh" bash -c "SCAN20_INBOX=1 bash run_synth.sh"
fi
if [ "${OSS_HOST:-0}" = "1" ]; then
  export PATH="$HOME/.local/share/oss-cad-suite/bin:$PATH"
fi
cd "$HERE"

echo "env: $(yosys -V | head -1) / $(nextpnr-ice40 --version 2>&1 | head -1)"

PYBIN="${PYTHON3:-$(command -v python3 || echo /opt/oss-cad-suite/py3bin/python3.11)}"
[ -x "$PYBIN" ] || command -v "$PYBIN" >/dev/null || { echo "no python3"; exit 2; }
echo "python: $PYBIN ($($PYBIN --version 2>&1))"

CORE="../src/scan20_core.vhdl"
TOP="../src/scan20_top.vhdl"
PCF="scan20_up5k.pcf"
[ -f "$CORE" ] && [ -f "$TOP" ] && [ -f "$PCF" ] || { echo "MISSING inputs"; exit 2; }

# cfg|wrapper|freq_mhz|pll_divf|pll_divq|must_close?
# f60 is the target config (EXACT 20.000 MHz shift); f120/f100p5 are attempts
# whose failure is a reported datapoint, not a suite failure (per workstream
# brief: attempt 100.5/120 at explicit freq, choose 60 if it closes).
CFGS="f60 cfg_f60.vhdl 60 79 4 must
f120 cfg_f120.vhdl 120 79 3 report
f100p5 cfg_f100p5.vhdl 100.5 66 3 report"

FAILED=0
RESULTS=""

# verify the PLL dividers yosys put into the JSON against the cfg expectation
pll_check() { # json_file freq divf divq
  "$PYBIN" - "$1" "$2" "$3" "$4" <<'EOF'
import json, sys
jf, freq, divf, divq = sys.argv[1], float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
d = json.load(open(jf))
top = d["modules"][d["top"]] if "top" in d else list(d["modules"].values())[0]
found = []
for mod in d["modules"].values():
    for c in mod.get("cells", {}).values():
        if c.get("type", "").startswith("SB_PLL40"):
            found.append(c["parameters"])
if not found:
    print("PLL-CHECK FAIL: no SB_PLL40 cell in json"); sys.exit(1)
for p in found:
    def b2i(v): return int(v, 2) if isinstance(v, str) else int(v)
    r, f, q = b2i(p["DIVR"]), b2i(p["DIVF"]), b2i(p["DIVQ"])
    fout = 12.0 * (f + 1) / ((r + 1) * (2 ** q))
    print(f"PLL-CHECK: DIVR={r} DIVF={f} DIVQ={q} -> fout={fout:.4f} MHz "
          f"(want {freq})")
    if (r, f, q) != (0, divf, divq) or abs(fout - freq) > 1e-6:
        print("PLL-CHECK FAIL: bitstream PLL dividers != config expectation")
        sys.exit(1)
print("PLL-CHECK OK")
EOF
}

for cfg in $CFGS; do :; done  # noop for readability
while read -r name wrap freq divf divq mustclose; do
  [ -n "$name" ] || continue
  d="build/$name"
  rm -rf "$d"; mkdir -p "$d"
  echo "=== $name: sysclk $freq MHz ($mustclose) wrapper $wrap"

  if ! timeout 600 yosys -m ghdl -p \
      "ghdl --std=08 $CORE $TOP $wrap -e scan20_cfg; synth_ice40 -top scan20_cfg -json $d/top.json" \
      > "$d/yosys.log" 2>&1; then
    echo "    YOSYS FAIL (see $d/yosys.log)"
    [ "$mustclose" = must ] && FAILED=1
    continue
  fi
  grep -E "SB_PLL40|Number of cells" "$d/yosys.log" | head -2 | sed 's/^/    /'

  if ! pll_check "$d/top.json" "$freq" "$divf" "$divq" > "$d/pll_check.log" 2>&1; then
    sed 's/^/    /' "$d/pll_check.log"
    echo "    FAIL: pll check"
    [ "$mustclose" = must ] && FAILED=1
    continue
  fi
  sed 's/^/    /' "$d/pll_check.log"

  if ! timeout 900 nextpnr-ice40 --up5k --package sg48 --json "$d/top.json" \
      --pcf "$PCF" --asc "$d/top.asc" --freq "$freq" --log "$d/nextpnr.log" \
      > "$d/nextpnr.out" 2>&1; then
    echo "    nextpnr does NOT close at --freq $freq:"
    grep -oE "Max frequency for clock[^:]*: *[0-9.]+ MHz" "$d/nextpnr.log" | sort -u | sed 's/^/      /'
    [ "$mustclose" = must ] && FAILED=1
    [ -f "$BUILD/sta.txt" ] || touch "$BUILD/sta.txt"
    echo "$name sysclk=$freq CLOSED=no (max: $(grep -oE 'Max frequency for clock[^:]*: *[0-9.]+ MHz' "$d/nextpnr.log" | sort -u | tail -1))" >> "$BUILD/sta.txt"
    continue
  fi
  FMAX_PNR="$(grep -oE "Max frequency for clock[^:]*: *[0-9.]+ MHz \((PASS|FAIL)[^)]*\)" "$d/nextpnr.log" | \
              sort -u | tr '\n' '; ' | sed 's/; $//')"
  echo "    nextpnr @$freq: $FMAX_PNR"

  icepack "$d/top.asc" "$d/top.bin" > "$d/icepack.log" 2>&1
  timeout 300 icetime -t -d up5k -P sg48 -p "$PCF" -c "$freq" "$d/top.asc" \
      > "$d/icetime.log" 2>&1
  FMAX_ICE="$(grep -E 'Total path delay|Max frequency|clock constraint' "$d/icetime.log" | \
              tr '\n' '; ' | sed 's/; $//')"
  echo "    icetime: $FMAX_ICE"
  {
    echo "$name sysclk=$freq CLOSED=yes ($mustclose)"
    echo "  nextpnr: $FMAX_PNR"
    echo "  icetime: $FMAX_ICE"
  } >> "$BUILD/sta.txt"
done <<< "$CFGS"

echo "----------------------------------------------------------------"
if [ "$FAILED" -eq 0 ]; then
  echo "SCAN20 SYNTH: f60 closes at 60.000 MHz (exact 20 MHz shift); others reported"
else
  echo "SCAN20 SYNTH: f60 FAILED TO CLOSE (see above)"
fi
exit $FAILED
