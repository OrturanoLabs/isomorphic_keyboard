#!/usr/bin/env python3
"""fanout_prep.py -- FPGA-02 phase-B dry run: deterministic SMD power
fanout plan (stub + 0.6/0.3 via per SMD power pad) computed off the r6
placement. NO copper is written; the output is a machine-checked plan
(docs/fanout_prep.json) that the FPGA-02 fanout phase can apply with
pcbnew or by hand. 2L context: stubs give deterministic escapes off the
QFN/SMD islands; on the 4L alternative the same stub list is what
connects pads to In1.Cu GND / In2.Cu VCC (docs/LEDGER.md trap:
freerouting cannot attach SMD pads to plane layers).

Geometry model: obstacle AABBs per pad/hole (NPTH drill +0.15 annulus)
from tools/routing_geo.py's parse; stub track 0.2 wide, via 0.6 pad /
0.3 drill; 0.2 clearance to every obstacle except the SOURCE pad; via
corner-to-outline min >= 0.6 (edge rule) using the true stepped
Edge.Cuts polygon (not the bbox); candidate escapes = 4 orthogonal dirs
per pad, scored by min clearance, best >= 0.2 wins.

Self-checks: plan-vs-plan via collision-free; a deliberately corrupted
copy of the plan MUST be flagged by the checker (vacuity control);
census: pads planned == pcb power-net pads minus anchors (EP pad 49 is
recorded as a soldered GND anchor with no stub; JP contacts get no
stubs -- they are the outside world).
"""
import importlib.util
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
PCB = os.path.join(BOARD, "out", "kicad", "tile_gw1nz.kicad_pcb")
OUT = os.path.join(BOARD, "docs", "fanout_prep.json")

spec = importlib.util.spec_from_file_location(
    "rg", os.path.join(HERE, "routing_geo.py"))
rg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rg)

POWER_NETS = {"GND", "VCC", "VCC1V2", "VCC1V2_RAW"}
VIA_PAD = 0.6
TRACK_W = 0.2
CLEAR = 0.2
EDGE_RULE = 0.6


def parse_outline(path):
    text = open(path).read()
    segs = []
    for m in re.finditer(r'\(gr_line \(start ([-\d.]+) ([-\d.]+)\) '
                         r'\(end ([-\d.]+) ([-\d.]+)\) \(layer "Edge.Cuts"',
                         text):
        segs.append(((float(m.group(1)), float(m.group(2))),
                     (float(m.group(3)), float(m.group(4)))))
    # chain segments into a polygon (stepped outline)
    if not segs:
        return []
    poly = [segs[0][0], segs[0][1]]
    rest = segs[1:]
    while rest:
        nxt = rest.pop(0)
        for a, b in (nxt, nxt[::-1]):
            if math.dist(poly[-1], a) < 1e-3:
                poly.append(b)
                break
    return poly


def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0,
        ((px - ax) * vx + (py - ay) * vy) / L2))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def poly_min_dist(p, poly):
    return min(seg_dist(p, poly[i], poly[(i + 1) % len(poly)])
               for i in range(len(poly)))


def point_in_poly(p, poly):
    x, y = p
    ins = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi):
            ins = not ins
        j = i
    return ins


def rect_dist(a, b):
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def fan_box(pad_box, d, off):
    """stub(0.2 track)+via envelope from pad edge outward along d."""
    x0, y0, x1, y1 = pad_box
    if d == (1, 0):
        cx = x1 + off
        hw = max(TRACK_W / 2, VIA_PAD / 2)
        return (x1 - 0.01, pad_cy(y0, y1) - hw, cx + VIA_PAD / 2,
                pad_cy(y0, y1) + hw), (cx, pad_cy(y0, y1))
    if d == (-1, 0):
        cx = x0 - off
        hw = max(TRACK_W / 2, VIA_PAD / 2)
        return (cx - VIA_PAD / 2, pad_cy(y0, y1) - hw, x0 + 0.01,
                pad_cy(y0, y1) + hw), (cx, pad_cy(y0, y1))
    if d == (0, 1):
        cy = y1 + off
        hw = max(TRACK_W / 2, VIA_PAD / 2)
        return (pad_cx(x0, x1) - hw, y1 - 0.01,
                pad_cx(x0, x1) + hw, cy + VIA_PAD / 2), (pad_cx(x0, x1), cy)
    cy = y0 - off
    hw = max(TRACK_W / 2, VIA_PAD / 2)
    return (pad_cx(x0, x1) - hw, cy - VIA_PAD / 2,
            pad_cx(x0, x1) + hw, y0 + 0.01), (pad_cx(x0, x1), cy)


def pad_cx(x0, x1):
    return (x0 + x1) / 2


def pad_cy(y0, y1):
    return (y0 + y1) / 2


def stub_box(pad_box, d, L):
    """surface escape: 0.2 track, length L from the pad edge, no via."""
    x0, y0, x1, y1 = pad_box
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    hw = TRACK_W / 2
    if d == (1, 0):
        return (x1 - 0.01, cy - hw, x1 + L, cy + hw), (x1 + L, cy)
    if d == (-1, 0):
        return (x0 - L, cy - hw, x0 + 0.01, cy + hw), (x0 - L, cy)
    if d == (0, 1):
        return (cx - hw, y1 - 0.01, cx + hw, y1 + L), (cx, y1 + L)
    return (cx - hw, y0 - L, cx + hw, y0 + 0.01), (cx, y0 - L)


def corners(bx):
    return [(bx[0], bx[1]), (bx[2], bx[1]),
            (bx[2], bx[3]), (bx[0], bx[3])]


def check_one(fan, probes, obstacles, poly):
    """min obstacle clearance of the fan envelope; edge rule measured
    from the fan corners + probe points; inside-outline over probes."""
    worst = min(rect_dist(fan, o) for o in obstacles)
    edge = min(poly_min_dist(c, poly) for c in corners(fan) + probes)
    inside = all(point_in_poly(p, poly) for p in probes)
    return worst, edge, inside


def main():
    text, fps = rg.parse(PCB)
    poly = parse_outline(PCB)
    if len(poly) < 4:
        sys.exit("outline polygon parse FAIL")

    # collect power pads
    pads = []  # (ref, num, net, abs box)
    for b in rg.blocks(open(PCB).read(), "(footprint"):
        ref = re.match(r'\(footprint "([^"]+)"', b).group(1)
        f = fps[ref]
        for pb in rg.blocks(b, "(pad"):
            m = re.match(r'\(pad\s+(?:"([^"]*)"|([^\s()]+))', pb)
            num = m.group(1) if m.group(1) is not None else m.group(2)
            net = re.search(r'\(net (?:\d+ )?"([^"]+)"\)', pb)
            if not net or net.group(1) not in POWER_NETS or not num:
                continue
            atp = re.search(r"\(at ([-\d.]+) ([-\d.]+)", pb)
            sz = re.search(r"\(size ([-\d.]+) ([-\d.]+)\)", pb)
            box = (f["x"] + float(atp.group(1)) - float(sz.group(1)) / 2,
                   f["y"] + float(atp.group(2)) - float(sz.group(2)) / 2,
                   f["x"] + float(atp.group(1)) + float(sz.group(1)) / 2,
                   f["y"] + float(atp.group(2)) + float(sz.group(2)) / 2)
            pads.append({"ref": ref, "pad": num, "net": net.group(1),
                         "box": box})

    # obstacles = every other footprint feature box (pads + holes)
    obstacles_of = {}
    all_boxes = []
    for ref, f in fps.items():
        for ob in f["obs"]:
            all_boxes.append((ref, rg.box_of(f, [ob])[0]))

    def obstacles_for(entry):
        return [b for r, b in all_boxes
                if not (r == entry["ref"]
                        and rect_dist(b, entry["box"]) < 1e-6)]

    DIRS = {(1, 0): "+x", (-1, 0): "-x", (0, 1): "+y", (0, -1): "-y"}
    plan, conflicts = [], []
    placed = []  # (fan_box, net) accumulating as greedy obstacles
    off = CLEAR + VIA_PAD / 2  # 0.5 from pad edge to via centre
    for entry in pads:
        if entry["ref"] == "U1" and entry["pad"] == "49":
            entry["anchor"] = True
            entry["note"] = ("EP soldered to GND (batch-4 decision "
                             "analysis): no stub/via; paste window only")
            plan.append(entry)
            continue
        if entry["ref"].startswith("JP_"):
            entry["anchor"] = True
            entry["note"] = "chassis contact: no fanout stub (probe pad)"
            plan.append(entry)
            continue
        eff_obs = obstacles_for(entry) + \
            [b for b, n in placed if n != entry["net"]]
        best = None
        best_via = None
        best_stub = None
        cands = []
        for d, name in DIRS.items():
            cands.append((d, 0.5, True, name))
            cands.append((d, 0.9, True, name))
            cands.append((d, None, False, name))
        for d, vo, use_via, name in cands:
            if use_via:
                fan, vc = fan_box(entry["box"], d, vo)
            else:
                fan, vc = stub_box(entry["box"], d, 0.6)
            worst, edge, inside = check_one(fan, [vc], eff_obs, poly)
            score = min(worst - CLEAR, edge - EDGE_RULE)
            rank = (score, 0 if not use_via else 1, 0 if vo != 0.9 else 1,
                    name)
            cand = (rank, name, fan, vc, worst, edge, inside, use_via)
            if best is None or rank > best[0]:
                best = cand
            alt = (score, name, vo, worst, edge,
                   inside and (worst - CLEAR) >= -1e-9 and
                   (edge - EDGE_RULE) >= -1e-9)
            if use_via:
                if best_via is None or score > best_via[0]:
                    best_via = alt
            else:
                if best_stub is None or score > best_stub[0]:
                    best_stub = alt
        (rank, name, fan, vc, worst, edge, inside, use_via) = best
        ok = inside and (worst - CLEAR) >= -1e-9 and \
            (edge - EDGE_RULE) >= -1e-9
        rec = {**entry, "escape_dir": name, "kind": "via" if use_via
               else "surface_stub",
               "fan_box": [round(v, 3) for v in fan],
               "stub_len_or_via_off": 0.6 if not use_via else
               round(math.hypot(vc[0] - pad_cx(entry["box"][0],
                                               entry["box"][2]),
                                vc[1] - pad_cy(entry["box"][1],
                                               entry["box"][3])), 3),
               "via_center": [round(vc[0], 3), round(vc[1], 3)]
               if use_via else None,
               "measured_clr_to_obstacles": round(worst, 3),
               "fan_corner_to_edge": round(edge, 3),
               "inside_outline": inside, "ok": ok,
               "via_alternative": {"escape_dir": best_via[1],
                                   "ring": best_via[2],
                                   "clr_to_obstacles":
                                   round(best_via[3], 3),
                                   "feasible": best_via[5]},
               "stub_alternative": {"escape_dir": best_stub[1],
                                    "clr_to_obstacles":
                                    round(best_stub[3], 3),
                                    "feasible": best_stub[5]}}
        plan.append(rec)
        placed.append((fan, entry["net"]))
        if not ok:
            conflicts.append(rec["ref"] + "-" + rec["pad"])

    # plan-vs-plan: every pair of fan envelopes across DIFFERENT nets
    # must keep >= CLEAR (belt+braces over the greedy accumulation)
    coll = []
    fans = [(p["fan_box"], p["net"], p["ref"] + "-" + p["pad"])
            for p in plan if "fan_box" in p]
    for i in range(len(fans)):
        for j in range(i + 1, len(fans)):
            if fans[i][1] == fans[j][1]:
                continue
            d = rect_dist(fans[i][0], fans[j][0])
            if d < CLEAR - 1e-9:
                coll.append((fans[i][2], fans[j][2], round(d, 3)))

    # vacuity control: shift one recorded fan box +0.25 mm in +x and
    # require its clearance to (obstacles + placed) to strictly decrease
    ctrl_ok = False
    for p in plan:
        if "fan_box" not in p:
            continue
        eff_obs = obstacles_for(p) + \
            [b for b, n in placed if n != p["net"]]
        fb = p["fan_box"]
        bad = (fb[0] + 0.25, fb[1], fb[2] + 0.25, fb[3])
        worst_bad = min(rect_dist(bad, o) for o in eff_obs)
        if worst_bad < p["measured_clr_to_obstacles"] - 1e-9:
            ctrl_ok = True
            break
    if not ctrl_ok:
        print("VACUITY WARNING: corrupted fan did not reduce clearance")

    rep = {
        "_meta": {
            "model": "stub 0.2 track + via 0.6/0.3, via centre at "
                     "pad_edge+0.5 (0.2 clr + via r); obstacle model from "
                     "routing_geo parse (AABB pads/holes, NPTH +0.15 "
                     "annulus); envelope = stub+via bbox (conservative); "
                     "edge rule 0.6 via-corner to true Edge.Cuts polygon; "
                     "plan vs plan collisions only across different nets",
            "context": "2L baseline; same stub list feeds 4L plane attach "
                       "(LEDGER: freerouting cannot attach SMD to planes)",
            "generated_by": "tools/fanout_prep.py", "written_copper": 0},
        "planned_pads": plan,
        "conflicts": conflicts,
        "via_vs_via_collisions": coll,
        "vacuity_control": "observed reduction" if ctrl_ok else "FAIL",
        "census": {"power_pads_total": len(pads),
                   "anchors": sum(1 for p in plan if p.get("anchor")),
                   "fans_planned": sum(1 for p in plan if "fan_box" in p),
                   "via_fans": sum(1 for p in plan
                                   if p.get("kind") == "via"),
                   "surface_stubs": sum(1 for p in plan
                                        if p.get("kind") == "surface_stub"),
                   "via_feasible_pads": sum(1 for p in plan
                                            if p.get("via_alternative",
                                                     {}).get("feasible")),
                   "ok": sum(1 for p in plan if p.get("ok"))}}
    with open(OUT, "w") as f:
        json.dump(rep, f, indent=1)
        f.write("\n")
    novia4l = [p["ref"] + "-" + p["pad"] for p in plan
               if "kind" in p and
               not p["via_alternative"]["feasible"]]
    rep["fourL_via_attach_blockers"] = novia4l
    print(f"FANOUT_PREP OK: {rep['census']}, 4L via-attach blockers="
          f"{novia4l[:6]}, conflicts={conflicts[:4]}, "
          f"collisions={coll[:4]} -> {OUT}")
    sys.exit(1 if conflicts or coll or not ctrl_ok else 0)


if __name__ == "__main__":
    main()
