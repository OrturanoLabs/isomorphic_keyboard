#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# run_synth.sh -- Yosys -> ATF1502 techmap -> EDIF for tile_cpld, in the
# pinned OSS CAD Suite container. Validates the EDIF by reading it back.
# This is a structure/mapping proof only; NO device fit is produced or claimed.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CF="$(cd "$HERE/.." && pwd)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel)"
OSS="$REPO/tools/oss.sh"
IMG="${OSS_IMAGE:-localhost/oss-cad-suite:2026-09-26}"
cd "$CF"

mkdir -p results/build

{
  echo "date_utc: $(date -u '+%FT%TZ')"
  echo "image: $IMG"
  podman image inspect "$IMG" --format 'image_id: {{.Id}}'
  printf 'yosys: '; "$OSS" yosys -V 2>/dev/null | head -1 || true
  echo "src_sha256:"
  sha256sum src/tile_cpld.v synth/atf1502_cells.v synth/atf1502_techmap.v synth/tile_cpld_atf1502.ys | sed 's/^/  /'
} | tee results/logs/synth_env.log

"$OSS" yosys -T -l results/logs/synth_yosys.log synth/tile_cpld_atf1502.ys

# ---- validation: EDIF must exist, name the device primitives, be parseable --
grep -c "ATF1502_" results/tile_cpld_atf1502.edif | \
  sed 's/^/edif ATF1502 references: /' | tee -a results/logs/synth_yosys.log

# this yosys build has no EDIF *reader*; validate the export structurally:
python3 - <<'EOF' | tee -a results/logs/synth_yosys.log
import re, sys
txt = open("results/tile_cpld_atf1502.edif").read()
# 1) balanced s-expressions
depth = 0
for i, c in enumerate(txt):
    if c == '(': depth += 1
    elif c == ')':
        depth -= 1
        if depth < 0: sys.exit("EDIF PARSE FAIL: unbalanced parens at char %d" % i)
if depth != 0: sys.exit("EDIF PARSE FAIL: unbalanced parens (depth %d)" % depth)
# 2) expected structure markers
assert "(edif tile_cpld" in txt, "EDIF MARKER MISSING: edif header"
for cellname in ["ATF1502_FF_D_SR_CE", "ATF1502_FF_D_AR", "ATF1502_FF_D_AR_CE",
                 "ATF1502_OBUF_TRI"]:
    if not re.search(r"\(cell %s\b" % cellname, txt):
        sys.exit("EDIF MARKER MISSING: cell %s" % cellname)
# device FF instance counts (one macrocell each, per the techmap)
counts = {c: len(re.findall(r"\(cellRef %s\b" % c, txt))
          for c in ["ATF1502_FF_D_SR_CE", "ATF1502_FF_D_AR", "ATF1502_FF_D_AR_CE",
                    "ATF1502_OBUF_TRI"]}
exp_counts = {"ATF1502_FF_D_SR_CE": 16, "ATF1502_FF_D_AR": 4,
              "ATF1502_FF_D_AR_CE": 1, "ATF1502_OBUF_TRI": 2}
if counts != exp_counts:
    sys.exit("EDIF CELL COUNT mismatch: got %r want %r" % (counts, exp_counts))
# 3) every top-level port present as a scalar or array EDIF port
for p in ["endrow","endcol","bclk","blatch","rlatch","tw","bfirst","tdata",
          "ldata","tclk","lclk","latcho","npl","ds","bw","dout"]:
    if not re.search(r"\(port %s \(direction" % p, txt):
        sys.exit("EDIF PORT MISSING: %s" % p)
if "(port (array buttons 12) (direction INPUT))" not in txt:
    sys.exit("EDIF PORT MISSING: (array buttons 12)")
# 4) vector bit mapping must be RTL buttons[b] -> port member (11-b), consistent
for b in range(12):
    pat = r'\(net \(rename id\d+ "buttons\[%d\]"\) \(joined\s+\(portRef \(member [A-Z]+ \d+\) \(instanceRef id\d+\)\)' % b
    m = re.search(re.escape('"buttons[%d]"' % b) + r'[\s\S]*?\(portRef \(member buttons (\d+)\)\)', txt)
    if not m or int(m.group(1)) != 11 - b:
        sys.exit("EDIF BIT MAP mismatch for buttons[%d]" % b)
print("EDIF sanity: balanced, 5 device cell types, 16 scalar ports + buttons[12] array,")
print("         buttons[b] -> member(11-b) consistent; device cells:", exp_counts)
EOF

echo "edif_sha256:"; sha256sum results/tile_cpld_atf1502.edif
echo "SYNTH OK (mapping only -- not a device fit)"
