#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# drive_attr_ab.sh -- exhaustively close the "can the OSS flow set pad
# drive/slew on GW1NZ?" question (fpga-01 review P3a/P3b).
#
#   VARIANT A: RTL ports with NO DRIVE attribute.
#   VARIANT B: VHDL attribute DRIVE="24" on the 5 merged-output ports
#              (attribute inserted into a COPY of the rtl -- fpga/rtl is
#              read-only for this workstream).
#   Both variants use an attr-free copy of the production cst (the cst
#   DRIVE/SLEW_RATE path is already proven dead: out/pnr/tmp/ab_{A,B}.fs).
#   Forensics: where does the attribute die? (synth json -> pnr json ->
#   gowin_pack grep) plus apicula/gowin_pack source probe (P3b).
#
# Run (inside the oss container):  tools/oss.sh bash fpga/board/tools/drive_attr_ab.sh
set -euo pipefail
cd "$(dirname "$0")/.."                       # .../fpga/board
TMP=out/pnr/tmp/rtl_ab
mkdir -p "$TMP"

GW_CHIPDB=/opt/oss-cad-suite/share/nextpnr/himbaechel/gowin/chipdb-GW1NZ-1.bin
GW_DEVICE=GW1NZ-LV1QN48C6/I5
RTL=../rtl

# ---- attr-free cst copy (IO_LOC + IO_TYPE kept -- bank config is real
# functionality; only the DRIVE/SLEW_RATE attributes are stripped)
sed -E 's/ DRIVE=[^ ;]+//g; s/ SLEW_RATE=[^ ;]+//g' \
    constraints/tile_gw1nz_board.cst > "$TMP/clean.cst"
grep -c 'IO_LOC' "$TMP/clean.cst" >/dev/null

# ---- variant copies of the two rtl files
cp "$RTL/tile_fpga.vhdl" "$RTL/top_gw1nz.vhdl" "$TMP/"

# variant B: DRIVE="24" attributes on the 5 output ports. VHDL rule
# (ghdl-enforced): attribute specs for PORTS live in the ENTITY
# declarative region, before "end top_gw1nz;".
awk '/^end top_gw1nz;$/ {
  print "  -- A/B variant B (drive_attr_ab.sh): RTL DRIVE attribute probe.";
  print "  attribute DRIVE : string;";
  print "  attribute DRIVE of t_clk_pin  : signal is \"24\";";
  print "  attribute DRIVE of l_clk_pin  : signal is \"24\";";
  print "  attribute DRIVE of latcho_pin : signal is \"24\";";
  print "  attribute DRIVE of dout_pin   : signal is \"24\";";
  print "  attribute DRIVE of b_w_pin    : signal is \"24\";";
} 1' "$TMP/top_gw1nz.vhdl" > "$TMP/top_gw1nz_drv.vhdl"
grep -c "attribute DRIVE" "$TMP/top_gw1nz_drv.vhdl"

echo "== P3b: does the OSS packer know pad DRIVE/SLEW at all? =="
PYBIN=$(sed -n 's/^#!//p' "$(command -v gowin_pack)" 2>/dev/null | head -1)
echo "gowin_pack interpreter: ${PYBIN:-unknown}"
AP=""
if [ -n "${PYBIN:-}" ] && [ -x "${PYBIN%% *}" ]; then
  AP=$(${PYBIN%% *} -c "import apicula, os; print(os.path.dirname(apicula.__file__))" 2>/dev/null || true)
fi
if [ -z "$AP" ]; then
  AP=$(find /opt/oss-cad-suite -type d -name apicula 2>/dev/null | head -1)
fi
echo "apicula pkg: ${AP:-NOT FOUND}"
if [ -n "${AP:-}" ]; then
  echo "-- grep DRIVE|SLEW in apicula python sources:"
  grep -rn "DRIVE\|SLEW" "$AP" --include="*.py" 2>/dev/null | grep -v "^Binary" | head -20 || echo "  (none found)"
fi
echo "-- chipdb binary probe:"
strings -a "$GW_CHIPDB" 2>/dev/null | grep -i "slew\|drive" | sort -u | head -10 || echo "  (no SLEW/DRIVE strings in chipdb)"

echo "== P3a: synth + pnr + pack, variants A (no attr) / B (DRIVE=24 rtl) =="
for v in A B; do
  if [ "$v" = B ]; then top_src="$TMP/top_gw1nz_drv.vhdl"; else top_src="$TMP/top_gw1nz.vhdl"; fi
  yosys -m ghdl -p "ghdl --std=08 $TMP/tile_fpga.vhdl $top_src -e top_gw1nz; \
      synth_gowin -top top_gw1nz -json $TMP/syn_$v.json" > "$TMP/syn_$v.log" 2>&1
  nextpnr-himbaechel --chipdb "$GW_CHIPDB" --device "$GW_DEVICE" \
      --json "$TMP/syn_$v.json" --vopt cst="$TMP/clean.cst" \
      --write "$TMP/pnr_$v.json" --freq 20 > "$TMP/pnr_$v.log" 2>&1
  gowin_pack -d "$GW_DEVICE" -o "$TMP/fs_$v.fs" "$TMP/pnr_$v.json" \
      > "$TMP/pack_$v.log" 2>&1
done

echo "-- where does DRIVE die?"
echo "   syn json A: $(grep -c 'DRIVE' $TMP/syn_A.json || true) hits"
echo "   syn json B: $(grep -c 'DRIVE' $TMP/syn_B.json || true) hits"
echo "   pnr json A: $(grep -c 'DRIVE' $TMP/pnr_A.json || true) hits"
echo "   pnr json B: $(grep -c 'DRIVE' $TMP/pnr_B.json || true) hits"
if grep -q 'DRIVE' "$TMP/syn_B.json"; then
  echo "   context in syn_B.json:"; grep -o '.\{0,60\}DRIVE.\{0,60\}' "$TMP/syn_B.json" | head -4
fi

echo "-- bitstream compare:"
sha256sum "$TMP/fs_A.fs" "$TMP/fs_B.fs"
if cmp -s "$TMP/fs_A.fs" "$TMP/fs_B.fs"; then
  echo "AB_RESULT: IDENTICAL -- RTL DRIVE attribute does NOT reach the bitstream"
  echo '(identical either because synth_gowin drops the attribute, or because'
  echo ' nextpnr/gowin_pack ignore it; forensics above say which.)'
else
  echo "AB_RESULT: DIFFER -- RTL DRIVE attribute WIRES THROUGH to the bitstream"
fi
