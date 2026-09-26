#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Rebuild the rev-B PCB from the rev-A board (KiCad 10 format) in one go:
#   netlist -> revb_pcb.py stage 1 -> Freerouting -> stage 2 -> DRC + invariants.
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
rm -f "$OUT/isomorphic_tile.ses"
podman run --rm --userns=keep-id -e HOME=/tmp -v "$ROOT/$OUT":/work:Z -w /work \
    localhost/freerouting:2.4.1 -de isomorphic_tile.dsn -do isomorphic_tile.ses -mp 40 \
    --gui.enabled=false > "$OUT/freerouting.log" 2>&1
"${KPY[@]}" hardware/kicad/tile/scripts/revb_pcb.py --route-in "$ROOT/$OUT/isomorphic_tile.ses" 2>&1 | quiet
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
