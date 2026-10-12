#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Simple-tile connector study: one-command runner.
#   1. measure candidate mezzanine footprints with KiCad's pcbnew (flatpak)
#   2. run the parametric placement study (host python3, stdlib only)
#   3. build the three concept coupons with pcbnew
#   4. KiCad DRC on the coupons (kicad-cli via tools/kicad-cli.sh)
# Every artifact lands in connectors/out/.  Exit status: study checks AND
# coupon DRC gate (0 DRC errors and 0 unconnected items; silk warnings are
# reported). Coupons have no schematic/ERC and remain concepts.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
OUT="$HERE/out"
KCLI="$REPO/tools/kicad-cli.sh"
cd "$REPO"
mkdir -p "$OUT/coupons"

{
  echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "host python: $(python3 --version 2>&1)"
  echo -n "kicad-cli: "; "$KCLI" version 2>/dev/null || echo UNAVAILABLE
  echo -n "flatpak pcbnew python: "
  flatpak run --command=python3 org.kicad.KiCad -c \
      'import sys, pcbnew; print(sys.version.split()[0], "| pcbnew", pcbnew.Version())' \
      2>/dev/null || echo UNAVAILABLE
} | tee "$OUT/versions.txt"

flatpak run --filesystem="$REPO" --command=python3 org.kicad.KiCad \
    "$HERE/measure_footprints.py" "$OUT/mezzanine_measures.json" || exit 1

python3 "$HERE/study.py" "$OUT"
STUDY_RC=$?

flatpak run --filesystem="$REPO" --command=python3 org.kicad.KiCad \
    "$HERE/make_coupons.py"
COUPON_RC=$?

DRC_FAIL=0
for c in coupon_spring coupon_mezz coupon_direct; do
  rm -f "$OUT/coupons/$c.drc.json"
  if ! KICAD_EXTRA_FS="$OUT/coupons" "$KCLI" pcb drc --format json \
      -o "$OUT/coupons/$c.drc.json" "$OUT/coupons/$c.kicad_pcb" >/dev/null 2>&1; then
    printf 'DRC command failed for %s\n' "$c" >&2
    DRC_FAIL=1
  fi
done
python3 - "$OUT" <<'PY' || DRC_FAIL=1
import json, os, sys
out = sys.argv[1]
gate = {}
for c in ("coupon_spring", "coupon_mezz", "coupon_direct"):
    d = json.load(open(os.path.join(out, "coupons", f"{c}.drc.json")))
    errs = [v for v in d.get("violations", []) if v["severity"] == "error"]
    unc = len(d.get("unconnected_items", []))
    # REVIEW RULE: the gate never passes with errors OR unconnected items.
    gate[c] = {"errors": len(errs),
               "warnings": sum(1 for v in d["violations"] if v["severity"] != "error"),
               "unconnected_items": unc,
               "gate_fail": bool(errs or unc),
               "note": "coupons have no schematic/ERC: concept, not fab-ready"}
    print(c, "drc errors:", len(errs),
          "warnings:", gate[c]["warnings"], "unconnected:", unc,
          "gate:", "FAIL" if errs or unc else "pass")
json.dump(gate, open(os.path.join(out, "coupons", "drc_gate.json"), "w"), indent=1)
sys.exit(1 if any(v["gate_fail"] for v in gate.values()) else 0)
PY

echo "study checks rc=$STUDY_RC, coupons rc=$COUPON_RC, DRC gate rc=$DRC_FAIL"
[ "$STUDY_RC" = 0 ] && [ "$COUPON_RC" = 0 ] && [ "$DRC_FAIL" = 0 ]
