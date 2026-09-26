#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Assembler-neutral fabrication + assembly outputs for the tile (rev B), all via kicad-cli.
# Usage (repo root): hardware/kicad/tile/scripts/production.sh [OUTDIR]
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"; cd "$ROOT/hardware/kicad/tile"
OUT="$(realpath -m "${1:-$ROOT/production/rev-b}")"
K="$ROOT/tools/kicad-cli.sh"; export KICAD_EXTRA_FS="$OUT"
PCB=isomorphic_tile.kicad_pcb; SCH=isomorphic_tile.kicad_sch
rm -rf "$OUT"; mkdir -p "$OUT"/{gerber,assembly,docs}

"$K" pcb drc --schematic-parity --exit-code-violations --severity-error --format json \
    -o "$OUT/docs/drc.json" "$PCB" >/dev/null           # refuse to export a board with errors
"$K" sch erc --exit-code-violations --severity-error --format json -o "$OUT/docs/erc.json" "$SCH" >/dev/null

"$K" pcb export gerbers --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,F.SilkS,B.SilkS,Edge.Cuts \
    --subtract-soldermask --use-drill-file-origin -o "$OUT/gerber/" "$PCB" >/dev/null
"$K" pcb export drill --format excellon --excellon-separate-th --generate-map --map-format pdf \
    -o "$OUT/gerber/" "$PCB" >/dev/null
"$K" pcb export ipc2581 -o "$OUT/isomorphic_tile_revB.ipc2581.xml" "$PCB" >/dev/null
"$K" pcb export pos --format csv --units mm --side both --smd-only --exclude-dnp -o "$OUT/assembly/pick_and_place.csv" "$PCB" >/dev/null
# The Kailh hot-swap footprint sits on F.Cu (the switch goes in from the top) but the socket
# itself is soldered on the BOTTOM: report those rows as bottom-side parts.
python3 - "$OUT/assembly/pick_and_place.csv" <<'PY'
import csv, sys
rows = list(csv.reader(open(sys.argv[1])))
for r in rows[1:]:
    if r[0].startswith("SW"):
        r[1] = "Kailh hot-swap socket CPG151101S11"
        r[-1] = "bottom"
csv.writer(open(sys.argv[1], "w", newline=""), quoting=csv.QUOTE_MINIMAL).writerows(rows)
PY
"$K" sch export bom --fields 'Reference,Value,Footprint,Manufacturer,MPN,${QUANTITY},${DNP}' \
    --labels 'Refs,Value,Footprint,Manufacturer,MPN,Qty,DNP' --group-by 'Value,Footprint,MPN' \
    --exclude-dnp -o "$OUT/assembly/bom.csv" "$SCH" >/dev/null
"$K" pcb export pdf --layers F.Fab,Edge.Cuts --mode-single -o "$OUT/assembly/assembly_top.pdf" "$PCB" >/dev/null
"$K" pcb export pdf --layers B.Fab,Edge.Cuts --mode-single --mirror -o "$OUT/assembly/assembly_bottom.pdf" "$PCB" >/dev/null
"$K" pcb export step --subst-models --no-dnp -o "$OUT/docs/isomorphic_tile_revB.step" "$PCB" >/dev/null 2>&1 || echo "STEP export failed (see ledger)"
"$K" sch export pdf -o "$OUT/docs/schematic.pdf" "$SCH" >/dev/null
cp "$ROOT/docs/build/fab-notes.md" "$OUT/FAB-NOTES.md"
(cd "$OUT" && python3 -m zipfile -c gerber.zip gerber)
echo "outputs in $OUT:"; (cd "$OUT" && find . -type f | sort)
