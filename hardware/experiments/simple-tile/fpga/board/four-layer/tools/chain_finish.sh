#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# chain_finish.sh -- one guard admission for the finish chain:
#   pcbnew finish (SES import + stitch + pours + fill) -> variant_check
#   (host) -> kicad-cli drc (final) -> drc digest (host)
set -euo pipefail
FL="flatpak run --filesystem=/home/marco/Documents/OrturanoLabs/isomorphic_keyboard --command=python3 org.kicad.KiCad"
D=hardware/experiments/simple-tile/fpga/board
O=$D/four-layer/out
KC=/home/marco/Documents/OrturanoLabs/isomorphic_keyboard/tools/kicad-cli.sh
SES="${1:-$O/tile_gw1nz_4l_widened.ses}"
cd /home/marco/Documents/OrturanoLabs/isomorphic_keyboard
echo "== 1/4 finish_4l_variant (pcbnew import/fill) =="
$FL $D/four-layer/tools/finish_4l_variant.py "$SES" "$O/tile_gw1nz_4l_routed.kicad_pcb" "$O/finish_report.json"
echo "== 2/4 variant_check variant+final (host) =="
python3 $D/four-layer/tools/variant_check.py "$O/variant_check.json" "$O/tile_gw1nz_4l_routed.kicad_pcb"
echo "== 3/4 kicad-cli drc (final) =="
$KC pcb drc --format json -o "$O/tile_gw1nz_4l_routed.drc.json" "$O/tile_gw1nz_4l_routed.kicad_pcb"
echo "== 4/4 drc digest (host) =="
python3 - "$O/tile_gw1nz_4l_routed.drc.json" <<'EOF'
import json,sys
d=json.load(open(sys.argv[1]))
v=d.get('violations',[])
errs=[x for x in v if x.get('severity')=='error']
warn=[x for x in v if x.get('severity')!='error']
un=d.get('unconnected_items',[])
print('DRC_DIGEST errors=%d warnings=%d unconnected=%d' % (len(errs),len(warn),len(un)))
import collections
c=collections.Counter(x.get('type') for x in v)
print('violation types:', dict(c))
if errs[:5]:
    print('first errors:', [ (x.get('type'), x.get('description','')[:110]) for x in errs[:5]])
EOF
echo "CHAIN_FINISH_DONE"
