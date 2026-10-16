#!/usr/bin/env python3
"""netclass_apply_pcbnew.py -- FPGA-02 phase-A dry run, NATIVE path: let
pcbnew itself build the net classes (the hand-written text format segfaults
the 10.0.6 DSN exporter -- batch-5 bisection evidence), save a KiCad-written
classed board copy, then export its DSN in the same process. The design
artifact out/kicad/tile_gw1nz.kicad_pcb is NEVER touched.

Run INSIDE the KiCad flatpak:
  flatpak run --filesystem=<repo> --command=python3 org.kicad.KiCad \
      fpga/board/tools/netclass_apply_pcbnew.py
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
TABLE = os.path.join(BOARD, "docs", "netclasses.json")
COPY = os.path.join(BOARD, "out", "route", "tile_gw1nz_rules.kicad_pcb")
DSN = os.path.join(BOARD, "out", "route", "tile_gw1nz_rules.dsn")


def nm(mm):
    return int(round(mm * 1_000_000))


def make(rule):
    def f(x):
        return "%g" % x
    return dict(clearance=nm(rule["clearance_mm"]),
                track=nm(rule["track_mm"]),
                via_d=nm(rule["via_d_mm"]),
                via_drill=nm(rule["via_drill_mm"]))


def main():
    table = json.load(open(TABLE))
    classes = {k: v["rule"] for k, v in table["classes"].items()}
    classes["Default"] = table["rule_reference"]
    net2cls = {n: k for k, v in table["classes"].items() for n in v["nets"]}

    b = pcbnew.LoadBoard(SRC)
    ncs = b.GetNetClasses()
    for name, rule in classes.items():
        c = pcbnew.NETCLASS(name)
        r = make(rule)
        c.SetClearance(r["clearance"])
        c.SetTrackWidth(r["track"])
        c.SetViaDiameter(r["via_d"])
        c.SetViaDrill(r["via_drill"])
        c.SetDescription("FPGA-02 prep, docs/netclasses.json")
        ncs[name] = c
    byname = b.GetNetInfo().NetsByName()
    assigned, missing = 0, []
    for netname, cls in net2cls.items():
        try:
            item = byname[netname]
        except Exception:
            missing.append(netname)
            continue
        item.SetNetClass(ncs[cls])
        assigned += 1
    if missing:
        sys.exit(f"assignment FAIL: nets not on board: {missing[:5]}")
    b.SynchronizeNetsAndNetClasses(False)

    pcbnew.SaveBoard(COPY, b)
    pcbnew.ExportSpecctraDSN(b, DSN)
    got = {}
    for name, c in ncs.items():
        got[name] = {"clearance_mm": c.GetClearance() / 1e6,
                     "track_mm": c.GetTrackWidth() / 1e6,
                     "via_d_mm": c.GetViaDiameter() / 1e6,
                     "via_drill_mm": c.GetViaDrill() / 1e6}
    print("NETCLASS_APPLY_PCBNEW_OK assigned=%d classes=%s" %
          (assigned, got))
    print("saved=%s dsn=%s" % (COPY, DSN))


if __name__ == "__main__":
    main()
