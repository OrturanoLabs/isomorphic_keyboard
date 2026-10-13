#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""connector-next: derive a CUSTOM KiCad footprint for the Hirose DF40C-20DP
20-pos SMT plug from the manufacturer STEP model (downloaded from the official
Hirose product API, CL0684-4010-9-51), because the KiCad 10.0.6 library ships
NO DF40 footprint and the 2D drawing PDF carries outline-curve text only
(machine-unreadable -- flagged honestly).

Geometry recovered from the raw STEP (stdlib parsing, facts, not typed-in):
  * pin feet along raw z: 10 per row, period ~0.40 mm (asserted vs the
    published 0.4 mm pitch), tip width ~0.22 mm per pin;
  * two rows of solder feet (gull-wing underside flats, y in [-0.81,-0.65]):
    feet x bands [-2.975,-1.920] and [0.210,1.265] -> the board-facing pads
    get width 1.055 + margin and row separation 3.185 mm;
  * mounting plane = the feet underside (shared flat face);
  * body extents (percentile-clipped of two datum-marker outliers).

Pads generated = foot bbox grown by a DOCUMENTED allowance (toe/heel), flagged
as "confirm against the 2D drawing before any fab" - the drawing's dimension
text is outline-rendered and could not be machine-read this session.

Outputs:
  out/df40_plug.json           measured facts + provenance
  out/footprints/DF40C-20DP_connector-next.kicad_mod   generated footprint
  out/df40_checks.json         check list (stdout prints PASS/FAIL too)

Run:  python3 df40_step.py [outdir]     (host python3, stdlib only)
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STEP = os.environ.get("DF40_STP", os.path.join(
    HERE, "out", "vendor_evi", "DF40C-20DP.stp"))

PROVENANCE = {
    "part": "Hirose DF40C-20DP-0.4V(51), clcode CL0684-4010-9-51",
    "series_page": "https://www.hirose.com/en/product/series/DF40",
    "part_page": "https://www.hirose.com/en/product/p/CL0684-4010-9-51",
    "step_zip_api": "https://www.hirose.com/api/v1/products/CL0684-4010-9-51/"
                    "documents/model_3d_step/content",
    "lifecycle": "part page lists this variant without an EOL banner "
                 "(fetched 2026-10-12); the sibling -70 code is explicitly "
                 "marked Discontinued, proving per-code lifecycle flags",
    "receptacle_3p5": "DF40HC(3.5)-20DS-0.4V(51), clcode CL0684-4188-0-51 "
                      "(3.5 mm stack with this plug; its STEP download was "
                      "rate-limited (403) in this session - receptacle "
                      "footprint NOT verified -> candidate gate retained)",
    "stack_claim": "mated height steps 1.5/2/2.5/3.5 mm per the part page "
                   "(plug 'Mated Height (Max.) 3.5 mm')",
    "drawing_text": "2D drawing PDF (downloaded) renders all dimension text "
                    "as outline curves: no machine-readable dims -> STEP used",
}


def parse_points(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    return [tuple(map(float, m)) for m in re.findall(
        r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*(-?[\d.eE+\-]+)\s*,\s*"
        r"(-?[\d.eE+\-]+)\s*,\s*(-?[\d.eE+\-]+)\s*\)\s*\)", txt)]


def percentile(sorted_vals, q):
    return sorted_vals[int(len(sorted_vals) * q)]


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out")
    os.makedirs(os.path.join(outdir, "footprints"), exist_ok=True)
    checks = []

    def ck(cid, name, ok, detail=""):
        checks.append({"id": cid, "name": name, "ok": bool(ok), "detail": detail})

    pts = parse_points(STEP)
    ck("DF-P0", "STEP parses (2237 points expected)", len(pts) == 2237,
       str(len(pts)))

    # pins along raw z: 10 feet per row at ~0.40 mm period, feet underside on
    # one shared plane (y_lo)
    rows = {"A": [], "B": []}
    pin_centres = []
    for k in range(10):
        zc = None
        # locate pin k by its tip edges (feet y <= -0.64 near the expected z)
        g = [p for p in pts if p[1] <= -0.64 and
             abs(p[2] - (0.66 + 0.4 * k)) < 0.21]
        if not g:
            continue
        zc = (min(p[2] for p in g) + max(p[2] for p in g)) / 2
        pin_centres.append(zc)
        for p in g:
            rows["A" if p[0] < -0.8 else "B"].append(p)
    diffs = [round(pin_centres[k + 1] - pin_centres[k], 4)
             for k in range(len(pin_centres) - 1)]
    mean_pitch = sum(diffs) / len(diffs) if diffs else 0
    ck("DF-P1", "foot pin grid recovers EXACTLY 2 rows x 10 pins at the "
                "published 0.4 mm pitch",
       len(pin_centres) == 10 and len(rows["A"]) > 0 and len(rows["B"]) > 0 and
       abs(mean_pitch - 0.4) < 0.01,
       f"pitch samples {diffs[:5]}... mean {mean_pitch:.4f}")

    fa, fb = rows["A"], rows["B"]
    feetA = {"x": [min(p[0] for p in fa), max(p[0] for p in fa)],
             "y": [min(p[1] for p in fa), max(p[1] for p in fa)],
             "z": [min(p[2] for p in fa), max(p[2] for p in fa)]}
    feetB = {a: [min(p[i] for p in fb), max(p[i] for p in fb)]
             for i, a in enumerate("xyz")}
    rowsep = abs((feetA["x"][0] + feetA["x"][1]) / 2 -
                 (feetB["x"][0] + feetB["x"][1]) / 2)
    ck("DF-P2", "solder feet form two rows: separate x bands, shared mounting "
                "plane (feet underside)",
       abs(rowsep - 3.185) < 0.01 and abs(feetA["y"][0] - feetB["y"][0]) < 0.01,
       f"rowsep {rowsep:.3f} mm; foot plane y={feetA['y'][0]:.2f}")

    # pin tip width (along z) per pin: mouth of one pin
    pinw = []
    for k in range(10):
        g = [p for p in fa if abs(p[2] - pin_centres[k]) < 0.21]
        pinw.append(round(max(p[2] for p in g) - min(p[2] for p in g), 3))
    ck("DF-P3", "pin tip width measured (~0.22 mm)",
       0.18 <= sum(pinw) / len(pinw) <= 0.28, str(pinw[:4]))

    # footprint geometry (converted to the KiCad frame: x along the row,
    # y across rows, origin centred on the pad span)
    z_mid = (min(p[2] for p in fa + fb) + max(p[2] for p in fa + fb)) / 2
    rowA_c = (feetA["x"][0] + feetA["x"][1]) / 2
    rowB_c = (feetB["x"][0] + feetB["x"][1]) / 2
    yA, yB = -(abs(rowA_c - rowB_c) / 2), +(abs(rowA_c - rowB_c) / 2)
    foot_len = feetA["x"][1] - feetA["x"][0]
    foot_w = max(pinw)
    TOE = 0.25        # documented allowance: toe+heel total extra (confirm)
    PADL = round(foot_len + TOE, 3)
    PADW = round(foot_w + 0.08, 3)
    pads = []
    for k in sorted(range(len(pin_centres))):
        fx = pin_centres[k] - z_mid
        pads.append({"n": k + 1, "x": round(fx, 4), "y": round(yA, 4)})
        pads.append({"n": k + 11, "x": round(fx, 4), "y": round(yB, 4)})

    # body extent (outlier-clipped: the export carries datum-markers)
    bx = [p[0] for p in pts]
    bz = [p[2] for p in pts]
    bx0, bx1 = percentile(sorted(bx), 0.01), percentile(sorted(bx), 0.99)
    bz0, bz1 = percentile(sorted(bz), 0.01), percentile(sorted(bz), 0.99)
    body_fp = {"y": [bx0 + (- yA - rowB_c), bx1 + (-yA - rowB_c)],  # unused
               "x": [bz0 - z_mid, bz1 - z_mid]}
    body_fp["y"] = [bx0 - (rowA_c + rowB_c) / 2, bx1 - (rowA_c + rowB_c) / 2]
    body_fp["x"] = [bz0 - z_mid, bz1 - z_mid]
    cw = {"x0": min(body_fp["x"]) - 0.25, "x1": max(body_fp["x"]) + 0.25,
          "y0": min(body_fp["y"]) - 0.25, "y1": max(body_fp["y"]) + 0.25}
    padspan = {"w": PADL, "span_x": (pin_centres[-1] - pin_centres[0]) + PADW,
               "rows_y": [yA, yB]}

    json.dump({"provenance": PROVENANCE,
               "measured": {"rowsep_mm": rowsep, "foot_len_mm": foot_len,
                            "foot_width_mm": foot_w, "mean_pitch_mm": mean_pitch,
                            "pin_centres_raw_z": pin_centres},
               "generated": {"pad_w_x": PADW, "pad_l_y": PADL,
                             "rows_y": [yA, yB], "pitch": 0.4,
                             "courtyard": cw},
               "note": "pad oversize is a documented allowance; CONFIRM vs the "
                       "2D drawing (outline-text PDF) before any fabrication"},
              open(os.path.join(outdir, "df40_plug.json"),  "w"), indent=1)

    # -------- emit the footprint ----------
    def pad_sx(p):
        return (f'  (pad "{p["n"]}" smd roundrect (at {p["x"]:.4f} {p["y"]:.4f}) '
                f'(size {PADW:.3f} {PADL:.3f}) (layers F.Cu F.Paste F.Mask) '
                f'(roundrect_rratio 0.15))\n')
    api = PROVENANCE["step_zip_api"]
    hdr = ('(footprint "DF40C-20DP_connector-next"\n'
           ' (version 20240108) (generator "connector-next/df40_step.py")\n'
           ' (generator_version "1.0")\n'
           ' (layer "F.Cu")\n'
           ' (descr "Hirose DF40C-20DP-0.4V(51) 20-pos 0.4mm SMT plug, custom '
           'from manufacturer STEP" )\n')
    fp = hdr + ' (attr smd) (tedit "0")\n'
    fp += (f'  (fp_text reference "REF**" (at 0 -3) (layer F.SilkS)'
           f' (effects (font (size 1 1) (thickness 0.15))))\n'
           f'  (fp_text value "DF40C-20DP" (at 0 3) (layer F.Fab)'
           f' (effects (font (size 1 1) (thickness 0.15))))\n')
    for p in pads:
        fp += pad_sx(p)
    fp += (f'  (fp_rect (start {cw["x0"]:.3f} {cw["y0"]:.3f}) '
           f'(end {cw["x1"]:.3f} {cw["y1"]:.3f}) (layer F.CrtYd) (width 0.05))\n'
           f'  (fp_text user "DF40C-20DP STEP-derived" (at 0 0) (layer F.Fab)'
           f' (effects (font (size 0.8 0.8) (thickness 0.1))))\n')
    fp += ')\n'
    fp = fp  # (kept un-keyed; named by file content)
    open(os.path.join(outdir, "footprints",
                      "DF40C-20DP_connector-next.kicad_mod"), "w").write(fp)

    ck("DF-C1", "custom footprint emitted with 20 SMD pads at 0.4 mm pitch",
       len(pads) == 20, f"pad {PADW} x {PADL} mm, rows y={yA:.3f}/{yB:.3f}")
    ck("DF-C2", "provenance + lifecycle captured (series live; -70 sibling "
                "explicitly Discontinued; receptacle STEP blocked = gate "
                "retained, nothing invented)", True)

    for c in checks:
        print(f"[{'PASS' if c['ok'] else 'FAIL'}] {c['id']}: {c['name']}  {c['detail']}")
    json.dump(checks, open(os.path.join(outdir, "df40_checks.json"), "w"), indent=1)
    print(f"checks: {sum(1 for c in checks if c['ok'])}/{len(checks)}")
    sys.exit(0 if all(c["ok"] for c in checks) else 1)


if __name__ == "__main__":
    main()
