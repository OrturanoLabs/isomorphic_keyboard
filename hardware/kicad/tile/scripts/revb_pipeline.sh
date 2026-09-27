#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Rebuild the rev-B PCB from the rev-A board (KiCad 10 format) in one go:
#   netlist -> revb_pcb.py stage 1 -> router -> stage 2 -> DRC + invariants.
# Router: ROUTER=freerouting (default) or ROUTER=krt (KiCadRoutingTools; faster, fab-aware,
# but on this placement it leaves 1-2 connections around U101/U107/U103 open).
# Usage (repo root): hardware/kicad/tile/scripts/revb_pipeline.sh [REV_A_COMMIT]
# REV_A_COMMIT defaults to the KiCad-10 migration commit of the rev-A board.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"; cd "$ROOT"
BASE="${1:-$(git log --format=%H -1 --grep='Migrate the tile project to KiCad 10')}"
PCB=hardware/kicad/tile/isomorphic_tile.kicad_pcb
OUT=production; mkdir -p "$OUT"
KPY=(flatpak run --filesystem="$ROOT" --command=python3 org.kicad.KiCad)
quiet() { grep -v -E 'memory leak|Warning|Debug' || true; }

git show "$BASE:$PCB" > "$PCB"
(cd hardware/kicad/tile && KICAD_EXTRA_FS="$ROOT" ../../../tools/kicad-cli.sh sch export netlist \
    --format kicadsexpr -o "$ROOT/$OUT/new.net" isomorphic_tile.kicad_sch >/dev/null)
"${KPY[@]}" hardware/kicad/tile/scripts/revb_pcb.py "$OUT/new.net" 2>&1 | quiet
if [ "${ROUTER:-freerouting}" = krt ]; then
  # KiCadRoutingTools: inter-board nets at 0.3 mm first, then the rest at 0.2 mm,
  # outer layers only (the inner layers are planes). It routes the .kicad_pcb in place.
  KRT=(podman run --rm --userns=keep-id -e HOME=/tmp -v "$ROOT":/work:Z -w /work localhost/krt
       python /opt/krt/py_router/route.py)
  # shrink only down to the board's own design-rule minimums (never to fab tiers the board
  # does not allow), no via in or touching a pad; the project file carries the rules
  # (hole clearance 0.25 mm, net classes) and must sit next to the board KRT reads
  KRT_STRICT=(--escalation board --same-net-pad-clearance 0.3 --hole-to-hole-clearance 0.25
              --board-edge-clearance 0.3)
  cp "$PCB" "$OUT/krt_in.kicad_pcb"
  cp hardware/kicad/tile/isomorphic_tile.kicad_pro "$OUT/krt_in.kicad_pro"
  "${KRT[@]}" "$OUT/krt_in.kicad_pcb" "$OUT/krt_a.kicad_pcb" --nets "/tile/L_*" "/tile/T_*" "/tile/B_*" \
      "/tile/R_*" "/tile/*_drv" --track-width 0.3 --clearance 0.2 --layers F.Cu B.Cu \
      --via-size 0.6 --via-drill 0.3 "${KRT_STRICT[@]}" > "$OUT/krt_a.log" 2>&1
  cp "$OUT/krt_in.kicad_pro" "$OUT/krt_a.kicad_pro"
  "${KRT[@]}" "$OUT/krt_a.kicad_pcb" "$OUT/krt_b.kicad_pcb" --nets "*" "!GND*" "!VCC*" \
      --grid-step 0.05 --ordering inside_out \
      --track-width 0.2 --clearance 0.2 --layers F.Cu B.Cu --via-size 0.6 --via-drill 0.3 "${KRT_STRICT[@]}" \
      > "$OUT/krt_b.log" 2>&1
  grep -h -E "JSON_SUMMARY_MIN|FAB NOTE" "$OUT/krt_a.log" "$OUT/krt_b.log" | cut -c1-240
  cp "$OUT/krt_b.kicad_pcb" "$PCB"
  if grep -h JSON_SUMMARY_MIN "$OUT/krt_b.log" | grep -q '"pad_pairs_open": {"count": 0'; then
    "${KPY[@]}" hardware/kicad/tile/scripts/revb_pcb.py --finish 2>&1 | quiet
  else
    # completion pass: Freerouting keeps the KRT wiring fixed and routes what is left
    echo "KRT left open connections -> Freerouting completion pass"
    "${KPY[@]}" hardware/kicad/tile/scripts/revb_pcb.py --export-dsn "$ROOT/$OUT/complete.dsn" 2>&1 | quiet
    rm -f "$OUT/complete.ses"
    podman run --rm --userns=keep-id -e HOME=/tmp -v "$ROOT/$OUT":/work:Z -w /work \
        localhost/freerouting:2.4.1 -de complete.dsn -do complete.ses -mp 20 \
        --gui.enabled=false --router.optimizer.enabled=false > "$OUT/freerouting_complete.log" 2>&1
    "${KPY[@]}" hardware/kicad/tile/scripts/revb_pcb.py --route-in "$ROOT/$OUT/complete.ses" 2>&1 | quiet
  fi
else
  rm -f "$OUT/isomorphic_tile.ses"
  podman run --rm --userns=keep-id -e HOME=/tmp -v "$ROOT/$OUT":/work:Z -w /work \
      localhost/freerouting:2.4.1 -de isomorphic_tile.dsn -do isomorphic_tile.ses -mp 40 \
      --gui.enabled=false > "$OUT/freerouting.log" 2>&1
  "${KPY[@]}" hardware/kicad/tile/scripts/revb_pcb.py --route-in "$ROOT/$OUT/isomorphic_tile.ses" 2>&1 | quiet
fi
(cd hardware/kicad/tile && KICAD_EXTRA_FS="$ROOT" ../../../tools/kicad-cli.sh pcb drc --schematic-parity \
    --format json -o "$ROOT/$OUT/drc.json" isomorphic_tile.kicad_pcb | tail -3)
python3 - "$OUT/drc.json" <<'PY'
import json, sys, collections
d = json.load(open(sys.argv[1]))
err = [v["type"] for v in d["violations"] if v["severity"] == "error"]
print("DRC errors:", collections.Counter(err) or 0, "| unconnected:", len(d["unconnected_items"]),
      "| parity:", len(d["schematic_parity"]))
PY
[ -f "$OUT/reference/ref.kicad_pcb" ] || tools/scripts/export_reference.sh >/dev/null
tools/scripts/check_invariants.py pcb "$OUT/reference/ref.kicad_pcb" "$PCB" | tail -1
"${KPY[@]}" tools/scripts/check_via_in_pad.py "$PCB" 0.2 2>&1 | quiet
