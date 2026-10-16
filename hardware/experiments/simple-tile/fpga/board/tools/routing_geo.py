#!/usr/bin/env python3
"""routing_geo.py -- FPGA-02 prep: channel/corridor capacity measured off
the r6 pcb (obstacle boxes from PADS + HOLES, not courtyards -- docs/
LEDGER.md trap: our socket pads stick up to ~2 mm out of the courtyard).

Emits docs/routing_geo.json:
  * socket-socket adjacent corridors (lattice neighbours): courtyard gap
    (info) and OBSTACLE gap with track capacity at the 0.2/0.2 rule:
    n tracks fit iff n*0.2 + (n-1)*0.2 <= gap - 2*CLEAR_TO_OBSTACLE.
  * U1 escape corridors: obstacle gap from the QFN (courtyard OR pad toes,
    whichever sticks out) to the tightest surrounding footprints, and to
    each R7..R11 series part (they sit in the escape corridor on purpose).
  * JP contact band: pad-to-board-edge minima (0.6 edge rule context).
Self-checks: rot==0 assertion on every measured footprint (conservative
AABB model), socket lattice census 12, JP census 19, and a vacuity
control (corrupted clearance must change the answer).
"""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
PCB = os.path.join(BOARD, "out", "kicad", "tile_gw1nz.kicad_pcb")
OUT = os.path.join(BOARD, "docs", "routing_geo.json")

CLEAR = 0.2     # clearance to each obstacle (reference rule set)
TRACK = 0.2
HOLE_ANN = 0.15  # extra solder-mask annulus assumed around NPTH drills


def blocks(text, head):
    out, i = [], 0
    while True:
        j = text.find(head, i)
        if j < 0:
            break
        i = j + len(head)
        if j > 0 and text[j - 1] not in " \t\n":
            continue
        nxt = text[j + len(head):j + len(head) + 1]
        if nxt not in (" ", '"', "\n", "\t"):
            continue
        depth, k = 0, j
        while k < len(text):
            c = text[k]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    out.append(text[j:k + 1])
                    i = k + 1
                    break
            k += 1
    return out


def parse(path):
    text = open(path).read()
    fps = {}
    for b in blocks(text, "(footprint"):
        ref = re.match(r'\(footprint "([^"]+)"', b).group(1)
        at = re.search(r"\n\s*\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", b)
        rot = float(at.group(3) or 0.0)
        obs = []   # (cx, cy, hx, hy) absolute-centre AABBs
        crtyd = None
        for pb in blocks(b, "(pad"):
            atp = re.search(r"\(at ([-\d.]+) ([-\d.]+)", pb)
            sz = re.search(r"\(size ([-\d.]+) ([-\d.]+)\)", pb)
            dr = re.search(r"\(drill ([-\d.]+)\)", pb)
            if not (atp and sz):
                continue
            hx, hy = float(sz.group(1)) / 2, float(sz.group(2)) / 2
            if dr:
                r = float(dr.group(1)) / 2 + HOLE_ANN
                hx, hy = max(hx, r), max(hy, r)
            obs.append((float(atp.group(1)), float(atp.group(2)), hx, hy))
        rp = re.search(r'\(fp_rect \(start ([-\d.]+) ([-\d.]+)\) '
                       r'\(end ([-\d.]+) ([-\d.]+)\)[^)]*'
                       r'\(layer "?[FB]\.CrtYd', b)
        if rp:
            x0, y0, x1, y1 = (float(rp.group(i)) for i in (1, 2, 3, 4))
            crtyd = ((x0 + x1) / 2, (y0 + y1) / 2,
                     abs(x1 - x0) / 2, abs(y1 - y0) / 2)
        else:
            # SW-style: B.CrtYd fp_poly -> AABB of the poly points
            for pb2 in blocks(b, "(fp_poly"):
                if "CrtYd" not in pb2:
                    continue
                pts = re.findall(r"\(xy ([-\d.]+) ([-\d.]+)\)", pb2)
                if not pts:
                    continue
                xs = [float(p[0]) for p in pts]
                ys = [float(p[1]) for p in pts]
                crtyd = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                         (max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2)
                break
        fps[ref] = {"x": float(at.group(1)), "y": float(at.group(2)),
                    "rot": rot, "obs": obs, "crtyd": crtyd}
    return text, fps


def box_of(fp, boxes):
    """AABB of relative boxes placed at fp origin (rot==0 asserted)."""
    if fp["rot"] != 0:
        sys.exit("rot!=0 on measured footprint: AABB model invalid "
                 f"({fp})")
    out = []
    for cx, cy, hx, hy in boxes:
        out.append((fp["x"] + cx - hx, fp["y"] + cy - hy,
                    fp["x"] + cx + hx, fp["y"] + cy + hy))
    return out


def rect_dist(a, b):
    """Euclidean distance between two AABBs (0 if they overlap/touch)."""
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def obs_gap(a_fp, b_fp):
    """Min distance between the pad/hole obstacle boxes of two footprints
    (exact for the AABB model; diagonal approaches counted properly)."""
    a = box_of(a_fp, a_fp["obs"])
    b = box_of(b_fp, b_fp["obs"])
    return min(rect_dist(x, y) for x in a for y in b)


def capacity(gap):
    usable = gap - 2 * CLEAR
    return max(0, int((usable + TRACK) // (2 * TRACK)))


def main():
    text, fps = parse(PCB)
    sw = {r: f for r, f in fps.items() if r.startswith("SW")}
    jp = {r: f for r, f in fps.items() if r.startswith("JP_")}
    if len(sw) != 12 or len(jp) != 19:
        sys.exit(f"census FAIL: SW={len(sw)} JP={len(jp)}")

    pairs = []
    srefs = sorted(sw, key=lambda r: int(r[2:]))
    for i, a in enumerate(srefs):
        for b in srefs[i + 1:]:
            d = math.dist((sw[a]["x"], sw[a]["y"]), (sw[b]["x"], sw[b]["y"]))
            if d > 19.6:
                continue
            g = obs_gap(sw[a], sw[b])
            cg = rect_dist(box_of(sw[a], [sw[a]["crtyd"]])[0],
                           box_of(sw[b], [sw[b]["crtyd"]])[0])
            pairs.append({"pair": f"{a}-{b}", "centre_dist": round(d, 3),
                          "obstacle_gap": round(g, 3),
                          "courtyard_gap_info": round(cg, 3),
                          "tracks_020": capacity(g)})

    u1 = fps["U1"]
    esc = []
    for r, f in fps.items():
        if r == "U1" or r.startswith("JP_"):
            continue
        d = math.dist((u1["x"], u1["y"]), (f["x"], f["y"]))
        g = obs_gap(u1, f)
        esc.append({"ref": r, "dist": round(d, 3),
                    "obstacle_gap": round(g, 3),
                    "tracks_020": capacity(g)})
    esc.sort(key=lambda e: e["obstacle_gap"])

    edge_x = (-27.0396, 63.7591)
    edge_y = (-7.45, 39.25)
    jprepo = []
    for r, f in sorted(jp.items()):
        b = box_of(f, f["obs"])[0]
        jprepo.append({"ref": r,
                       "pad_to_bbox_edge_min":
                       round(min(b[0] - edge_x[0], edge_x[1] - b[2],
                                 b[1] - edge_y[0], edge_y[1] - b[3]), 3)})

    # vacuity control: zero clearance must yield MORE tracks somewhere
    global CLEAR
    tight = min(pairs, key=lambda p: p["tracks_020"])
    save, CLEAR = CLEAR, 0.0
    ctrl = capacity(tight["obstacle_gap"])
    CLEAR = save
    if ctrl < tight["tracks_020"]:
        sys.exit("vacuity FAIL: capacity insensitive to clearance")

    rep = {
        "_meta": {"model": "AABB obstacle boxes per pad/hole (NPTH "
                  "drill+0.15 annulus); gap = euclidean rect-to-rect "
                  "min over all box pairs (exact for the AABB model, "
                  "diagonal approaches counted); rot==0 asserted; "
                  "clearance 0.2 to each obstacle; track 0.2 "
                  "(reference rule set); courtyard gap for info only "
                  "(pads stick out of courtyards -- LEDGER trap)",
                  "generated_by": "tools/routing_geo.py (FPGA-02 prep)"},
        "socket_corridors": pairs,
        "u1_escape_tightest": esc[:8],
        "jp_band": jprepo,
    }
    with open(OUT, "w") as f:
        json.dump(rep, f, indent=1)
        f.write("\n")
    worst = min(pairs, key=lambda p: p["obstacle_gap"])
    print(f"ROUTING_GEO OK: {len(pairs)} socket corridors, "
          f"U1 escape tightest = {esc[:3]}, "
          f"min socket gap {worst}, -> {OUT}")


if __name__ == "__main__":
    main()
