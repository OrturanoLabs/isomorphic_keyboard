#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Rev C microcontroller tile: build (stage 1) -> GND plane on top (route_planes) ->
# KiCadRoutingTools (first pass + up to 9 repair passes) -> pours and stitching -> DRC.
# Usage (repo root): hardware/kicad/tile/scripts/revc_mcu_route.sh
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"; cd "$ROOT"
OUT=production/revc_mcu
KPY=(flatpak run --filesystem="$ROOT" --command=python3 org.kicad.KiCad)
quiet() { grep -v -E 'memory leak|Warning|Debug' || true; }
KRT=(podman run --rm --memory 2500m --userns=keep-id -e HOME=/tmp -v "$ROOT/$OUT":/work:Z -w /work
     localhost/krt python /opt/krt/py_router/route.py)
RULES=(--clearance 0.15 --layers F.Cu B.Cu --layer-costs ${LAYER_COSTS:-1.0 1.0} --via-size 0.6 --via-drill 0.3 --escalation board
       --same-net-pad-clearance 0.3 --hole-to-hole-clearance 0.25 --board-edge-clearance 0.3
       --grid-step 0.05)
set -f
"${KPY[@]}" hardware/kicad/tile/scripts/revc_mcu_build.py 2>&1 | quiet
cp $OUT/revc_mcu.kicad_pcb $OUT/krt_in.kicad_pcb; cp $OUT/revc_mcu.kicad_pro $OUT/krt_in.kicad_pro
# 2-layer power scheme: the top (switch side, no parts) is a GND plane, reference for every
# signal, reached by one via per GND pad; the bottom carries the parts, the signals, VCC as
# tracks and a GND pour; KRT's plane-first flow: pour, then route everything
podman run --rm --memory 2500m --userns=keep-id -e HOME=/tmp -v "$ROOT/$OUT":/work:Z -w /work localhost/krt \
    python /opt/krt/py_router/route_planes.py krt_in.kicad_pcb --output krt_pl.kicad_pcb --nets GND --grid-step 0.05 --hole-to-hole-clearance 0.25 \
    --layers F.Cu B.Cu --plane-layers F.Cu --clearance 0.15 --via-size 0.6 --via-drill 0.3 --board-edge-clearance 0.3 \
    > $OUT/krt_planes.log 2>&1
cp $OUT/krt_in.kicad_pro $OUT/krt_pl.kicad_pro
"${KRT[@]}" krt_pl.kicad_pcb krt_out.kicad_pcb --nets '*' --power-nets VCC GND \
    --power-nets-widths 0.4 0.4 --track-width 0.15 --ordering inside_out "${RULES[@]}" > $OUT/krt.log 2>&1
cp $OUT/krt_in.kicad_pro $OUT/krt_out.kicad_pro
# further passes: whatever is still open, allowed to rip up other signal nets, with a wider
# search at each pass
cp $OUT/krt_out.kicad_pcb $OUT/pass.kicad_pcb; cp $OUT/krt_in.kicad_pro $OUT/pass.kicad_pro
LOG=$OUT/krt.log
EXTRA=("" "--max-iterations 1000000 --max-ripup 4 --ripup-blocker-select mincut"
       "--max-iterations 2000000 --max-ripup 6 --ripup-blocker-select cost --ordering original")
for k in $(seq 2 10); do
  # open nets of this run plus the nets it ripped up and could not restore (outside its scope)
  OPEN=$(python3 - $LOG <<'PY'
import sys, json
t = open(sys.argv[1]).read()
m = json.loads(t.split("JSON_SUMMARY_MIN: ", 1)[1].splitlines()[0])
full = json.loads(t.split("JSON_SUMMARY: ", 1)[1].splitlines()[0]) if "JSON_SUMMARY: " in t else {}
print(" ".join(sorted(set(m["pad_pairs_open"]["nets"]) | set(full.get("ripped_open", [])))))
PY
)
  [ -z "$OPEN" ] && break
  echo "pass $k for: $OPEN"
  LOG=$OUT/krt$k.log
  "${KRT[@]}" pass.kicad_pcb pass_out.kicad_pcb --nets $OPEN --rip-existing-nets '*' \
      --power-nets VCC GND --power-nets-widths 0.3 0.3 --track-width 0.15 ${EXTRA[$((k % 3))]} "${RULES[@]}" > $LOG 2>&1
  cp $OUT/pass_out.kicad_pcb $OUT/pass.kicad_pcb
done
cp $OUT/pass.kicad_pcb $OUT/revc_mcu.kicad_pcb
set +f
"${KPY[@]}" hardware/kicad/tile/scripts/revc_mcu_build.py --finish 2>&1 | quiet
KICAD_EXTRA_FS="$ROOT" tools/kicad-cli.sh pcb drc --format json -o "$ROOT/$OUT/drc.json" $OUT/revc_mcu.kicad_pcb | tail -1
python3 - "$OUT/drc.json" <<'PY'
import json, sys, collections
d = json.load(open(sys.argv[1]))
err = collections.Counter(v["type"] for v in d["violations"] if v["severity"] == "error")
print("DRC errors:", dict(err) or 0, "| unconnected:", len(d["unconnected_items"]))
PY
"${KPY[@]}" tools/scripts/check_via_in_pad.py $OUT/revc_mcu.kicad_pcb 0.2 2>&1 | quiet
# keep the routed board under version control (production/ is ignored): only a clean result
if python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));sys.exit(any(v["severity"]=="error" for v in d["violations"]) or len(d["unconnected_items"]))' $OUT/drc.json; then
  mkdir -p hardware/kicad/revc-mcu-tile
  cp $OUT/revc_mcu.kicad_pcb $OUT/revc_mcu.kicad_pro $OUT/revc_mcu.kicad_dru hardware/kicad/revc-mcu-tile/
  echo "clean: copied to hardware/kicad/revc-mcu-tile/"
fi
