#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""connector-next: fresh pcbnew measurement of the 20-position mezzanine
candidates (runs INSIDE the KiCad flatpak):

    flatpak run --filesystem="$REPO" --command=python3 org.kicad.KiCad \
        hardware/experiments/simple-tile/connector-next/measure_next.py OUT.json

Candidates (all geometry MEASURED from the installed KiCad 10.0.6 library,
never typed in):
  - Hirose DF12E3.0-20DP plug + DF12C3.0-20DS receptacle (0.5 mm SMT, series
    "Planned End of Life" per hirose.com - kept as the rejected reference)
  - Harwin Gecko MVX2005L0X / FVX2005L0X vertical pair (1.25 mm; these stock
    footprints carry 0.55 mm drills => THROUGH-BOARD tails, measured here)
  - Harwin Gecko MS12005M2P (the stocked SMT male; a full-SMT Gecko pair is
    not buildable from the stock library, so this stays informational)
  - Hirose BM24-40DP/DS pair (40 pos; series "Not recommended for new design"
    per hirose.com - measured for completeness of the comparison)
The KiCad 10.0.6 library ships NO DF40 footprints (checked): the DF40 row of
the comparison is sourced from the series page only and flagged as
"custom footprint required".
"""
import json
import os
import sys

import pcbnew

FP_ROOT = os.environ.get("STUDY_FP_ROOT",
                         "/app/extensions/Library/Footprints/footprints")

CANDIDATES = [
    ("df12_plug20", "Connector_Hirose.pretty",
     "Hirose_DF12_DF12E3.0-20DP-0.5V_2x10_P0.50mm_Vertical",
     "tile side (plug), SMT, 0.5 mm"),
    ("df12_receptacle20", "Connector_Hirose.pretty",
     "Hirose_DF12_DF12C3.0-20DS-0.5V_2x10_P0.50mm_Vertical",
     "chassis side (receptacle), SMT, 0.5 mm"),
    ("gecko_mv20", "Connector_Harwin.pretty",
     "Harwin_Gecko-G125-MVX2005L0X_2x10_P1.25mm_Vertical",
     "tile side (male, 20 pos, through-board tails)"),
    ("gecko_fv20", "Connector_Harwin.pretty",
     "Harwin_Gecko-G125-FVX2005L0X_2x10_P1.25mm_Vertical",
     "chassis side (female, 20 pos, through-board tails)"),
    ("gecko_ms1_20", "Connector_Harwin.pretty",
     "Harwin_Gecko_G125-MS12005M2P_2x10_P1.25mm_Vertical",
     "SMT male (informational; no stocked SMT female)"),
    ("bm24_plug40", "Connector_Hirose.pretty",
     "Hirose_BM24_BM24-40DP-2-0.35V_2x20_P0.35mm_PowerPin2_Vertical",
     "plug, 40 pos (NRND family)"),
    ("bm24_receptacle40", "Connector_Hirose.pretty",
     "Hirose_BM24_BM24-40DS-2-0.35V_2x20_P0.35mm_PowerPin2_Vertical",
     "receptacle, 40 pos (NRND family)"),
]


def mm(v):
    return pcbnew.ToMM(v)


def measure(lib, name):
    path = os.path.join(FP_ROOT, lib, name + ".kicad_mod")
    if not os.path.isfile(path):
        return None
    fp = pcbnew.FootprintLoad(os.path.join(FP_ROOT, lib), name)
    pads = []
    for p in fp.Pads():
        c = p.GetPosition()
        s = p.GetSize()
        pads.append({"n": p.GetNumber(), "x": round(mm(c.x), 4),
                     "y": round(mm(c.y), 4), "w": round(mm(s.x), 4),
                     "h": round(mm(s.y), 4), "drill_x": round(mm(p.GetDrillSizeX()), 3),
                     "shape": str(p.GetShape())})
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    drills = sorted({p["drill_x"] for p in pads if p["drill_x"] > 0})
    return {"file": path, "descr": fp.GetLibDescription(), "pads": pads,
            "style": ("through-board (drills)" if drills else "SMT"),
            "drills_mm": drills,
            "courtyard_bbox_fpside": {"x0": round(mm(bb.GetX()), 3),
                                     "y0": round(mm(bb.GetY()), 3),
                                     "x1": round(mm(bb.GetRight()), 3),
                                     "y1": round(mm(bb.GetBottom()), 3)},
            "pads_bbox": {
                "x0": round(min(p["x"] - p["w"] / 2 for p in pads), 3),
                "y0": round(min(p["y"] - p["h"] / 2 for p in pads), 3),
                "x1": round(max(p["x"] + p["w"] / 2 for p in pads), 3),
                "y1": round(max(p["y"] + p["h"] / 2 for p in pads), 3)}}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "mezz_next.json"
    res = {}
    for logical, lib, name, role in CANDIDATES:
        m = measure(lib, name)
        if m is None:
            res[logical] = {"error": "footprint not found", "lib": lib, "name": name}
        else:
            m.update({"lib": lib, "name": name, "role": role})
            res[logical] = m
    res["_meta"] = {"tool": "pcbnew " + pcbnew.Version(), "fp_root": FP_ROOT,
                    "note": "measured from the installed KiCad stock footprint "
                            "files; DFS40-family footprints are NOT shipped"}
    json.dump(res, open(out, "w"), indent=1, sort_keys=True)
    for logical, lib, name, role in CANDIDATES:
        m = res[logical]
        if "error" in m:
            print(f"{logical}: NOT FOUND ({lib}/{name})")
        else:
            b = m["courtyard_bbox_fpside"]
            print(f"{logical}: pads={len(m['pads'])} drills={m['drills_mm']} "
                  f"courtyard {b['x1']-b['x0']:.2f} x {b['y1']-b['y0']:.2f} mm "
                  f"({m['style']})")
    print("wrote", out)


main()
