#!/usr/bin/env python3
"""fanout_apply_probe.py -- FPGA-02 phase-B preparation probe: apply the
batch-6 fanout plan (docs/fanout_prep.json: power stubs/vias, geometrically
pre-verified) onto a pcbnew COPY of the r6 pcb. NEVER touches the design
artifact; writes out/route/tile_gw1nz_fanout_probe.kicad_pcb. The copy then
feeds export_dsn -> dsn_class_split -> a second guarded freerouting dry run
so the delta (routed connection items with deterministic fanout vs the
batch-9 router-only baseline 46/99) can be measured.

Run INSIDE the KiCad flatpak:
  flatpak run --filesystem=<repo> --command=python3 org.kicad.KiCad \
      fpga/board/tools/fanout_apply_probe.py
"""
import faulthandler
import json
import os
import sys

import pcbnew

faulthandler.enable()

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
SRC = os.path.join(BOARD, "out", "kicad", "tile_gw1nz.kicad_pcb")
PLAN = os.path.join(BOARD, "docs", "fanout_prep.json")
COPY = os.path.join(BOARD, "out", "route",
                    "tile_gw1nz_fanout_probe.kicad_pcb")
TRACK_W_NM = 200_000          # power class 0.5 would be nicer but stubs are
                            # escapes; class rules still govern the router
VIA_D_NM = 600_000
VIA_DRILL_NM = 300_000


def nm(mm):
    return int(round(mm * 1_000_000))


def stub_end(box, d):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return {"+x": (x1 + 0.6, cy), "-x": (x0 - 0.6, cy),
            "+y": (cx, y1 + 0.6), "-y": (cx, y0 - 0.6)}[d]


def main():
    plan = json.load(open(PLAN))["planned_pads"]
    fans = [p for p in plan if "kind" in p]
    b = pcbnew.LoadBoard(SRC)
    byname = b.GetNetInfo().NetsByName()
    fps = {fp.GetReference(): fp for fp in b.GetFootprints()}
    added_t, added_v, skipped = 0, 0, []
    for e in fans:
        net = byname[e["net"]]
        if net.GetNetCode() <= 0:
            skipped.append((e["ref"], e["pad"], "netcode"))
            continue
        fp = fps.get(e["ref"])
        pad = None
        for p in fp.Pads():
            if p.GetNumber() == e["pad"]:
                pad = p
                break
        if pad is None:
            skipped.append((e["ref"], e["pad"], "pad"))
            continue
        pos = pad.GetPosition()
        layer = pad.GetLayer()     # SMD single-copper layer enum
        x0, y0, x1, y1 = e["box"]
        pc = ((x0 + x1) / 2, (y0 + y1) / 2)
        end = (tuple(e["via_center"]) if e["kind"] == "via"
               else stub_end(e["box"], e["escape_dir"]))
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(nm(pc[0]), nm(pc[1])))
        t.SetEnd(pcbnew.VECTOR2I(nm(end[0]), nm(end[1])))
        t.SetLayer(layer)
        t.SetWidth(TRACK_W_NM)
        t.SetNet(net)
        b.Add(t)
        added_t += 1
        if e["kind"] == "via":
            v = pcbnew.PCB_VIA(b)
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetPosition(pcbnew.VECTOR2I(nm(end[0]), nm(end[1])))
            v.SetWidth(VIA_D_NM)
            v.SetDrill(VIA_DRILL_NM)
            v.SetNet(net)
            b.Add(v)
            added_v += 1
    if skipped:
        sys.exit(f"apply FAIL: {skipped[:6]}")
    b.BuildConnectivity()
    pcbnew.SaveBoard(COPY, b)
    print(f"FANOUT_APPLY OK: tracks={added_t} vias={added_v} -> {COPY}")


if __name__ == "__main__":
    main()
