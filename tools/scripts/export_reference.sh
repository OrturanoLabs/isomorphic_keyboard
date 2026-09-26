#!/usr/bin/env bash
# Extract the reference design (default: tag rev-a-prototype) and export its netlist, so that
# check_invariants.py can compare the working copy against it.
#   usage: tools/scripts/export_reference.sh [OUTDIR] [GIT_REF]
# Produces OUTDIR/ref.kicad_pcb and OUTDIR/ref.net
set -euo pipefail
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
OUT="$(realpath -m "${1:-$ROOT/production/reference}")"
REF="${2:-rev-a-prototype}"
mkdir -p "$OUT/src"
# the project folder and name changed during the 2026-09 reorganisation
if git -C "$ROOT" cat-file -e "$REF:hardware/kicad/tile/isomorphic_tile.kicad_pcb" 2>/dev/null; then
  DIR=hardware/kicad/tile; NAME=isomorphic_tile
else
  DIR=hardware/kicad/module-tile; NAME=tastiera_isomorfa
fi
git -C "$ROOT" archive "$REF" "$DIR" | tar -x -C "$OUT/src"
cp "$OUT/src/$DIR/$NAME.kicad_pcb" "$OUT/ref.kicad_pcb"
KICAD_EXTRA_FS="$OUT${KICAD_EXTRA_FS:+:$KICAD_EXTRA_FS}" "$ROOT/tools/kicad-cli.sh" \
  sch export netlist --format kicadsexpr -o "$OUT/ref.net" "$OUT/src/$DIR/$NAME.kicad_sch" >/dev/null
echo "reference $REF -> $OUT/ref.kicad_pcb, $OUT/ref.net"
