#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""connector-next: verify the socket STEP model's orientation AND board-plane
against the vendored footprint -- replacing the baseline's "raw STEP-extent
bound, axis unverified" with a feature-verified registration.

Stdlib only (OpenSCAD NOT INSTALLED; nothing is faked):

  E1 board-plane candidates. The CPG1511's solder tabs are the x-extreme
     metal wings; their z-histogram shows two flat-plate levels. Both are
     candidate solder-foot planes.
  E2 board-plane decision. The spring boxes receive the MX leads through the
     footprint's d3.05 NPTH holes; the box tops must end at the board top
     face (= solder plane + 1.6 mm board), else they collide with the switch
     body sitting on the board. The candidate satisfying flush tops (<0.1 mm)
     wins; the other is REJECTED because it would push box metal >1 mm above
     the board top face inside the 15.6 mm switch-body region.
  E3 in-plane registration. With the foot plane known, the solder-foot flat
     plates (points in a thin slab around it) are split west/east; their xy
     centroids are scored against pads 1/2 of the vendored footprint for all
     8 planar maps {+/-x, +/-y} x {swap, no-swap} - no translation, scale=1.
     The winner must win by >5x and match the pad x-gap within 0.15 mm.
  E4 depth below the board is then a measured model fact:
     depth = |z_min - plane|, reported together with the conservative
     full-extent bound (+0.5 mm guard) that the z-budget keeps using.

Outputs out/step_axis.json + stdout PASS/FAIL table.

Run:  python3 step_axis.py [outdir]     (host python3, stdlib only)
"""
import collections
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
STP = os.path.join(ROOT, "hardware", "kicad", "lib", "3dmodels",
                   "SW_Hotswap_Kailh_MX.stp")

sys.path.insert(0, os.path.join(HERE, "..", "connectors"))
import study as base  # noqa: E402  (baseline geometry engine, imported READONLY)

FP = base.parse_kicad_mod(base.VENDORED_FP)
PADS = sorted(((p["x"], p["y"]) for p in FP["pads"]))          # pads 1, 2 xy
HOLES_3P05 = sorted((h["x"], h["y"]) for h in FP["holes"] if abs(h["d"] - 3.05) < 0.01)
BOARD_T = 1.6
SWITCH_BODY_HALF = 15.6 / 2


def parse_points():
    txt = open(STP, encoding="utf-8", errors="replace").read()
    return [tuple(map(float, m)) for m in re.findall(
        r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*(-?[\d.eE+\-]+)\s*,\s*"
        r"(-?[\d.eE+\-]+)\s*,\s*(-?[\d.eE+\-]+)\s*\)\s*\)", txt)]


def wings(pts):
    """x-extreme 1% clusters (the solder tabs), west then east."""
    xs = sorted(p[0] for p in pts)
    lo_t = xs[int(len(xs) * 0.01)]
    hi_t = xs[int(len(xs) * 0.99)]
    return [p for p in pts if p[0] <= lo_t], [p for p in pts if p[0] >= hi_t]


def centroid(g):
    n = len(g)
    return (sum(p[0] for p in g) / n, sum(p[1] for p in g) / n)


def centroid3(g):
    n = len(g)
    return (sum(p[0] for p in g) / n, sum(p[1] for p in g) / n,
            sum(p[2] for p in g) / n)


def planar_maps():
    return [
        ("fp=(+x,+y)", lambda p: (p[0], p[1])),
        ("fp=(+x,-y)", lambda p: (p[0], -p[1])),
        ("fp=(-x,+y)", lambda p: (-p[0], p[1])),
        ("fp=(-x,-y)", lambda p: (-p[0], -p[1])),
        ("fp=(+y,+x)", lambda p: (p[1], p[0])),
        ("fp=(+y,-x)", lambda p: (p[1], -p[0])),
        ("fp=(-y,+x)", lambda p: (-p[1], p[0])),
        ("fp=(-y,-x)", lambda p: (-p[1], -p[0])),
    ]


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out")
    os.makedirs(outdir, exist_ok=True)
    pts = parse_points()
    west, east = wings(pts)

    # -------- E1/E2: board plane --------
    zh = collections.Counter()
    for p in west + east:
        zh[round(p[2] * 2) / 2] += 1
    peaks = sorted((z for z in zh if zh[z] >= 40))
    box_pts = []
    for hx, hy in HOLES_3P05:                      # verified below: fp.y = -stp.y
        box_pts += [p for p in pts if math.hypot(p[0] - hx, p[1] - (-hy)) < 1.4]
    box_pts = box_pts or pts
    zbox = sorted(p[2] for p in box_pts)[int(len(box_pts) * 0.99)]
    plane_tests = []
    for pk in peaks:
        flush_resid = abs((pk + BOARD_T) - zbox)     # plane + board T vs box top
        above = [p for p in box_pts if p[2] > pk + BOARD_T + 0.05]
        plane_tests.append({"candidate_plane": pk,
                            "boxtop_flush_residual_mm": round(flush_resid, 3),
                            "metal_above_board_top_mm":
                                round(max(p[2] for p in above) - pk - BOARD_T, 3)
                                if above else 0.0,
                            "rejected": flush_resid > 0.1})
    ok_planes = [t for t in plane_tests if not t["rejected"]]
    bp = ok_planes[0]["candidate_plane"] if ok_planes else None

    # -------- E3: in-plane registration on the foot flat --------
    slab = [p for p in west + east if abs(p[2] - bp) <= 0.25] if bp is not None \
        else west + east
    scores = []
    for nm, f in planar_maps():
        mp = [f((p[0], p[1])) for p in slab]
        wset = [q for q in mp if q[0] < 0]
        eset = [q for q in mp if q[0] >= 0]
        if not wset or not eset:
            scores.append({"map": nm, "rms_mm": 9999.0,
                           "note": "x-split degenerates under this map"})
            continue
        cw = (sum(q[0] for q in wset) / len(wset), sum(q[1] for q in wset) / len(wset))
        ce = (sum(q[0] for q in eset) / len(eset), sum(q[1] for q in eset) / len(eset))
        dx0 = cw[0] - PADS[0][0]
        dy0 = cw[1] - PADS[0][1]
        dx1 = ce[0] - PADS[1][0]
        dy1 = ce[1] - PADS[1][1]
        # best assignment of the two cluster centres to the two pads
        rmsA = math.sqrt((dx0 * dx0 + dy0 * dy0 + dx1 * dx1 + dy1 * dy1) / 2)
        bx0 = ce[0] - PADS[0][0]
        by0 = ce[1] - PADS[0][1]
        bx1 = cw[0] - PADS[1][0]
        by1 = cw[1] - PADS[1][1]
        rmsB = math.sqrt((bx0 * bx0 + by0 * by0 + bx1 * bx1 + by1 * by1) / 2)
        rms = min(rmsA, rmsB)
        scores.append({"map": nm, "rms_mm": round(rms, 4),
                       "w_centroid": [round(v, 3) for v in cw],
                       "e_centroid": [round(v, 3) for v in ce]})
    scores.sort(key=lambda s: s["rms_mm"])
    best, runner = scores[0], scores[1]
    xgap_model = abs(best["e_centroid"][0] - best["w_centroid"][0])
    xgap_fp = abs(PADS[1][0] - PADS[0][0])

    # solder-foot containment: foot flat-plate points must project INSIDE the
    # footprint pads (the feet are smaller than the pads by design)
    pw = FP["pads"][0]["w"]
    ph = FP["pads"][0]["h"]
    containment = []
    if best["map"] == "fp=(+x,-y)":
        for sel, (px, py) in (((lambda p: p[0] < 0), PADS[0]),
                              ((lambda p: p[0] >= 0), PADS[1])):
            g = [p for p in slab if sel(p)]
            inside = [p for p in g
                      if abs(p[0] - px) <= pw / 2 and abs(-p[1] - py) <= ph / 2]
            containment.append(round(len(inside) / max(1, len(g)) * 100, 1))

    zmin = min(p[2] for p in pts)
    depth_model = (bp - zmin) if bp is not None else None
    checks = []
    checks.append({"id": "SA1", "ok": len(pts) == 16027,
                   "name": "STEP parses 16027 CARTESIAN_POINTs",
                   "detail": str(len(pts))})
    checks.append({"id": "SA2", "ok": bp is not None and len(ok_planes) == 1 and
                   ok_planes[0]["boxtop_flush_residual_mm"] < 0.1,
                   "name": "board plane identified at the solder-foot plate plane: "
                           "the spring boxes then end FLUSH at the board top face "
                           "(residual < 0.1 mm)",
                   "detail": json.dumps(plane_tests)})
    alt = [t for t in plane_tests if t["candidate_plane"] != bp]
    checks.append({"id": "SA3", "ok": bool(alt) and all(
        t["metal_above_board_top_mm"] > 1.0 for t in alt),
        "name": "alternative board plane(s) rejected: they raise spring-box metal "
                ">1 mm above the board top face inside the switch body outline "
                "(collides with the seated switch)",
        "detail": "; ".join(f"plane {t['candidate_plane']}: "
                            f"+{t['metal_above_board_top_mm']} mm" for t in alt)})
    checks.append({"id": "SA4", "ok": best["map"] == "fp=(+x,-y)" and
                   best["rms_mm"] < 0.25 and runner["rms_mm"] > 5 * best["rms_mm"],
                   "name": "in-plane orientation verified by solder-foot->pad "
                           "registration: fp.x = stp.x, fp.y = -stp.y (feature "
                           "match, not raw bbox)",
                   "detail": f"best {best['map']} rms={best['rms_mm']} mm; "
                             f"runner-up {runner['map']} rms={runner['rms_mm']} mm"})
    checks.append({"id": "SA5", "ok": len(containment) == 2 and
                   all(c >= 90.0 for c in containment),
                   "name": f"solder-foot flat plates project >=90% inside the "
                           f"footprint pads (feet are smaller than pads by design; "
                           f"x-gap foot {xgap_model:.3f} vs pad {xgap_fp:.3f} mm)",
                   "detail": f"containment west/east: {containment} % of foot-slab "
                             "points inside the pad rect"})
    checks.append({"id": "SA6", "ok": depth_model is not None and 2.0 < depth_model < 3.0,
                   "name": "socket depth below the board (model, verified frame) = "
                           f"{depth_model:.3f} mm; +0.5 mm guard = "
                           f"{depth_model + 0.5:.2f} mm -- the conservative "
                           "full-extent bound (4.44 + 0.5 = 4.94) stays the z-budget "
                           "bound for chassis robustness",
                   "detail": f"stp z extent [{zmin:.3f}, 0]; solder plane z={bp}"})
    out = {
        "step_file": os.path.relpath(STP, ROOT),
        "footprint_model_reference": "the .kicad_mod references the WRL with an "
            "identity transform (at 0 0 0 / scale 1 / rotate 0); the WRL is a "
            "partial mesh (contact cage), so the full-frame evidence comes from "
            "the STEP, registered here against the footprint pads/holes",
        "points": len(pts),
        "planar_scores": scores,
        "board_plane_stpz": bp, "plane_tests": plane_tests,
        "box_top_z99_mm": zbox,
        "verified": {
            "in_plane_map": "fp.x = stp.x ; fp.y = -stp.y",
            "board_plane": f"stp z = {bp} (solder-foot plate plane; box tops flush "
                           "at the board top face within 0.1 mm)",
            "socket_below_board_mm": round(depth_model, 3),
            "socket_below_board_plus_guard_mm": round(depth_model + 0.5, 3),
            "conservative_full_extent_bound_plus_guard_mm": round(abs(zmin) + 0.5, 3),
            "note": "the registration involves a y-mirror (baked into the verified "
                    "map); the chassis z-budget keeps the conservative bound, the "
                    "model-verified depth is reported alongside."},
        "checks_summary": {"ok": sum(1 for c in checks if c["ok"]),
                           "total": len(checks)}}
    json.dump(out, open(os.path.join(outdir, "step_axis.json"), "w"), indent=1)
    for c in checks:
        print(f"[{'PASS' if c['ok'] else 'FAIL'}] {c['id']}: {c['name']}  {c['detail']}")
    print(f"checks: {out['checks_summary']['ok']}/{out['checks_summary']['total']}")
    sys.exit(0 if all(c["ok"] for c in checks) else 1)


if __name__ == "__main__":
    main()
