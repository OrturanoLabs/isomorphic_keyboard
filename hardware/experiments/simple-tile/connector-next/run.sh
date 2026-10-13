#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# connector-next runner:
#   1. measure the 20-pos mezzanine footprints with pcbnew (flatpak)
#   2. budget.py    - aggregated contact budget + 4x4 backplane graph checks
#   3. step_axis.py - STEP registration against the footprint (feature-based)
#   4. study.py     - 19-pad plan, tiered rails, stagger+tilt, mezzanine fit,
#                     SVGs, report
#   5. make_coupons_next.py (flatpak pcbnew) - 3 draft coupons
#   6. fresh kicad-cli DRC on every coupon: gate = 0 errors AND 0 unconnected
# Every artifact lands in connector-next/out/. Coupons are concepts (no ERC).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
OUT="$HERE/out"
COUT="$OUT/coupons_next"
KCLI="$REPO/tools/kicad-cli.sh"
cd "$REPO"
mkdir -p "$COUT"

{
  echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "host python: $(python3 --version 2>&1)"
  echo -n "kicad-cli: "; "$KCLI" version 2>/dev/null || echo UNAVAILABLE
  echo -n "flatpak pcbnew python: "
  flatpak run --command=python3 org.kicad.KiCad -c \
      'import sys, pcbnew; print(sys.version.split()[0], "| pcbnew", pcbnew.Version())' \
      2>/dev/null || echo UNAVAILABLE
  echo -n "openscad: "; command -v openscad >/dev/null \
      && openscad --version 2>&1 || echo "NOT INSTALLED (missing tool, reported)"
} | tee "$OUT/versions.txt"

flatpak run --filesystem="$REPO" --command=python3 org.kicad.KiCad \
    "$HERE/measure_next.py" "$OUT/mezz_next.json" || exit 1

python3 "$HERE/budget.py" "$OUT"
BUDGET_RC=$?

python3 "$HERE/step_axis.py" "$OUT"
AXIS_RC=$?

python3 "$HERE/df40_step.py" "$OUT"
DF40_RC=$?

python3 "$HERE/study.py" "$OUT"
STUDY_RC=$?

flatpak run --filesystem="$REPO" --command=python3 org.kicad.KiCad \
    "$HERE/make_coupons_next.py"
COUPON_RC=$?

DRC_FAIL=0
for c in coupon_agg19 coupon_mezz20 coupon_backplane; do
  rm -f "$COUT/$c.drc.json"
  if ! KICAD_EXTRA_FS="$COUT" "$KCLI" pcb drc --format json \
      -o "$COUT/$c.drc.json" "$COUT/$c.kicad_pcb" >/dev/null 2>&1; then
    printf 'DRC command failed for %s\n' "$c" >&2
    DRC_FAIL=1
  fi
done
python3 - "$COUT" <<'PY' || DRC_FAIL=1
import json, os, sys
cout = sys.argv[1]
gate = {}
for c in ("coupon_agg19", "coupon_mezz20", "coupon_backplane"):
    d = json.load(open(os.path.join(cout, f"{c}.drc.json")))
    errs = [v for v in d.get("violations", []) if v["severity"] == "error"]
    unc = len(d.get("unconnected_items", []))
    gate[c] = {"errors": len(errs),
               "warnings": sum(1 for v in d["violations"] if v["severity"] != "error"),
               "unconnected_items": unc,
               "gate_fail": bool(errs or unc),
               "note": "coupons have no schematic/ERC: concept, not fab-ready"}
    print(c, "drc errors:", len(errs),
          "warnings:", gate[c]["warnings"], "unconnected:", unc,
          "gate:", "FAIL" if errs or unc else "pass")
json.dump(gate, open(os.path.join(cout, "drc_gate.json"), "w"), indent=1)
sys.exit(1 if any(v["gate_fail"] for v in gate.values()) else 0)
PY

echo "budget rc=$BUDGET_RC, step_axis rc=$AXIS_RC, df40 rc=$DF40_RC, study rc=$STUDY_RC, coupons rc=$COUPON_RC, DRC gate rc=$DRC_FAIL"
[ "$BUDGET_RC" = 0 ] && [ "$AXIS_RC" = 0 ] && [ "$DF40_RC" = 0 ] && [ "$STUDY_RC" = 0 ] && \
  [ "$COUPON_RC" = 0 ] && [ "$DRC_FAIL" = 0 ]
