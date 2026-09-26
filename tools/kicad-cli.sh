#!/usr/bin/env bash
# Run kicad-cli from the user-level KiCad flatpak (org.kicad.KiCad).
# Extra host paths the sandbox must see can be passed via KICAD_EXTRA_FS (colon separated).
set -euo pipefail
args=(--command=kicad-cli)
IFS=: read -ra extra <<< "${KICAD_EXTRA_FS:-}"
for p in "${extra[@]}"; do [ -n "$p" ] && args+=("--filesystem=$p"); done
exec flatpak run "${args[@]}" org.kicad.KiCad "$@"
