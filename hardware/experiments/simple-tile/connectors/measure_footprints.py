#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure candidate mezzanine connector footprints (tile<->chassis study).

Runs inside the KiCad flatpak (pcbnew):

    flatpak run --filesystem="$PWD" --command=python3 org.kicad.KiCad \
        hardware/experiments/simple-tile/connectors/measure_footprints.py OUT.json

Loads each candidate .kicad_mod from the KiCad 10 stock footprint library that ships
with the org.kicad.KiCad flatpak, then records, per footprint:

  - pad rectangles (centre, size) and their overall bounding box
  - the courtyard polygon (F.CrtYd segments/arcs, exact published outline)
  - the manufacturer drawing URL carried in the footprint's descr field
  - the absolute library file path (provenance)

Units: mm. The values are *measured from the installed library files*, never typed in.
"""
import json
import os
import sys

import pcbnew

FP_ROOT = os.environ.get(
    "STUDY_FP_ROOT",
    "/app/extensions/Library/Footprints/footprints")

# (logical name, library dir, footprint file without extension, role)
CANDIDATES = [
    ("df12_receptacle", "Connector_Hirose.pretty",
     "Hirose_DF12_DF12C3.0-20DS-0.5V_2x10_P0.50mm_Vertical", "chassis side (receptacle)"),
    ("df12_plug", "Connector_Hirose.pretty",
     "Hirose_DF12_DF12E3.0-20DP-0.5V_2x10_P0.50mm_Vertical", "tile side (plug)"),
    ("df12_receptacle30", "Connector_Hirose.pretty",
     "Hirose_DF12_DF12C3.0-30DS-0.5V_2x15_P0.50mm_Vertical",
     "chassis side (receptacle, 30 pos)"),
    ("df12_plug30", "Connector_Hirose.pretty",
     "Hirose_DF12_DF12E3.0-30DP-0.5V_2x15_P0.50mm_Vertical",
     "tile side (plug, 30 pos)"),
    ("gecko_male", "Connector_Harwin.pretty",
     "Harwin_Gecko-G125-MVX1205L0X_2x06_P1.25mm_Vertical", "tile side (male, 12 pos)"),
    ("gecko_female", "Connector_Harwin.pretty",
     "Harwin_Gecko-G125-FVX1205L0X_2x06_P1.25mm_Vertical", "chassis side (female, 12 pos)"),
    ("gecko_male20", "Connector_Harwin.pretty",
     "Harwin_Gecko-G125-MVX2005L0X_2x10_P1.25mm_Vertical", "tile side (male, 20 pos)"),
    ("gecko_female20", "Connector_Harwin.pretty",
     "Harwin_Gecko-G125-FVX2005L0X_2x10_P1.25mm_Vertical",
     "chassis side (female, 20 pos)"),
]


def mm(v):
    return pcbnew.ToMM(v)


def measure(lib, name):
    path = os.path.join(FP_ROOT, lib, name + ".kicad_mod")
    if not os.path.isfile(path):
        return None
    fp = pcbnew.FootprintLoad(os.path.join(FP_ROOT, lib), name)
    descr = fp.GetLibDescription()
    pads = []
    for p in fp.Pads():
        c = p.GetPosition()
        s = p.GetSize()
        pads.append({"n": p.GetNumber(), "x": mm(c.x), "y": mm(c.y),
                     "w": mm(s.x), "h": mm(s.y),
                     "shape": str(p.GetShape()), "drill_x": mm(p.GetDrillSizeX())})
    # exact courtyard on F.CrtYd (segments + arcs)
    crty = []
    for d in fp.GraphicalItems():
        if d.GetLayer() != pcbnew.F_CrtYd:
            continue
        shp = d.GetShape()
        if shp == pcbnew.SHAPE_T_SEGMENT:
            st, en = d.GetStart(), d.GetEnd()
            crty.append({"type": "seg", "x0": mm(st.x), "y0": mm(st.y),
                         "x1": mm(en.x), "y1": mm(en.y)})
        elif shp == pcbnew.SHAPE_T_ARC:
            c = d.GetCenter(); st = d.GetStart(); en = d.GetEnd()
            crty.append({"type": "arc", "cx": mm(c.x), "cy": mm(c.y),
                         "x0": mm(st.x), "y0": mm(st.y),
                         "x1": mm(en.x), "y1": mm(en.y)})
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    body = {"x0": mm(bb.GetX()), "y0": mm(bb.GetY()),
            "x1": mm(bb.GetRight()), "y1": mm(bb.GetBottom())}
    return {"file": path, "descr": descr, "pads": pads, "courtyard_fpside": crty,
            "courtyard_bbox_fpside": body,
            "pads_bbox": {
                "x0": min(p["x"] - p["w"] / 2 for p in pads),
                "y0": min(p["y"] - p["h"] / 2 for p in pads),
                "x1": max(p["x"] + p["w"] / 2 for p in pads),
                "y1": max(p["y"] + p["h"] / 2 for p in pads)}}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "mezzanine_measures.json"
    res = {}
    for logical, lib, name, role in CANDIDATES:
        m = measure(lib, name)
        if m is None:
            res[logical] = {"error": "not found", "lib": lib, "name": name}
        else:
            m["lib"] = lib
            m["name"] = name
            m["role"] = role
            res[logical] = m
    res["_meta"] = {"tool": "pcbnew " + pcbnew.Version(),
                    "fp_root": FP_ROOT,
                    "note": "measured from the installed KiCad stock footprint files"}
    with open(out, "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    for logical, lib, name, role in CANDIDATES:
        m = res[logical]
        if "error" in m:
            print(f"{logical}: NOT FOUND ({lib}/{name})")
        else:
            b = m["courtyard_bbox_fpside"]
            print(f"{logical}: {lib}/{name}  pads={len(m['pads'])}  "
                  f"courtyard bbox {b['x1']-b['x0']:.2f} x {b['y1']-b['y0']:.2f} mm  role: {role}")
    print("wrote", out)


main()
