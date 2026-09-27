#!/usr/bin/env bash
# Download the vendor IBIS models used by the SI scripts (not redistributed in this repo).
# Source: Texas Instruments product pages ("IBIS model"), https://www.ti.com/lit/zip/<id>
set -euo pipefail
cd "$(dirname "$0")"
tmp=$(mktemp -d)
for id in SCEM288 SCEM283 SCEM216; do       # SN74LVC2G125, SN74LVC2G126, SN74LVC1G04
  curl -fsSL -A "Mozilla/5.0" -o "$tmp/$id.zip" "https://www.ti.com/lit/zip/$id"
  python3 -m zipfile -e "$tmp/$id.zip" "$tmp/$id"
  find "$tmp/$id" -iname '*.ibs' -exec sh -c 'cp "$1" "$(basename "$1" | tr A-Z a-z)"' _ {} \;
done
rm -rf "$tmp"; ls -1 *.ibs
