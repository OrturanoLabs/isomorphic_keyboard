#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Assembly panel: 2 tiles side by side, 5 mm rails top/bottom, 3 tooling holes, 3 panel
# fiducials, mouse-bite tabs, zones refilled. KiKit in a rootless container.
# Usage (repo root): hardware/kicad/tile/scripts/panel.sh [OUTDIR]
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
OUT="$(realpath -m "${1:-$ROOT/production/panel}")"
rm -rf "$OUT"; mkdir -p "$OUT"
cp -r "$ROOT/hardware/kicad/tile" "$ROOT/hardware/kicad/lib" "$OUT/"
podman run --rm --userns=keep-id -e HOME=/tmp -v "$OUT":/work:Z -w /work \
  docker.io/yaqwsx/kikit:v1.8.1-v10 panelize \
  --layout 'grid; rows: 1; cols: 2; space: 3mm' \
  --tabs 'fixed; width: 5mm; vcount: 2; hcount: 0' \
  --cuts 'mousebites; drill: 0.5mm; spacing: 0.8mm; offset: 0.2mm' \
  --framing 'railstb; width: 5mm; space: 3mm' \
  --tooling '3hole; hoffset: 2.5mm; voffset: 2.5mm; size: 1.5mm' \
  --fiducials '3fid; hoffset: 5mm; voffset: 2.5mm; coppersize: 1mm; opening: 2mm' \
  --text 'simple; text: isomorphic tile rev B panel; anchor: mt; voffset: 2.5mm; hjustify: center; vjustify: center' \
  --post 'millradius: 1mm; refillzones: true' \
  tile/isomorphic_tile.kicad_pcb isomorphic_tile_panel.kicad_pcb 2>&1 | grep -v -E 'Debug|assert' || true
KICAD_EXTRA_FS="$OUT" "$ROOT/tools/kicad-cli.sh" pcb drc --exit-code-violations --severity-error \
  --format json -o "$OUT/drc.json" "$OUT/isomorphic_tile_panel.kicad_pcb" | tail -1
echo "panel: $OUT/isomorphic_tile_panel.kicad_pcb"
