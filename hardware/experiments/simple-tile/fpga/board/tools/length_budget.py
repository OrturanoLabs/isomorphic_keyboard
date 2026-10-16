#!/usr/bin/env python3
"""length_budget.py -- pre-routing length/loading budget for the 45 nets
(FPGA-01 evidence feeding the FPGA-02 route-length discipline, esp. the
B2 edge-critical class T_clk/L_latch/B_data).

Per net (all from the r6 pcb, nothing routed):
  pad_count, pin coords, bbox span dx/dy, HPWL (half-perimeter wire
  lower bound), Manhattan MST length over pin centres (routing lower
  bound estimate), pin-pair diameter (max |dx|+|dy|), net class from
  docs/netclasses.json, series resistor id when the net is one half of
  an R7..R11 boundary pair.
Cross-checks (fail loudly):
  * DSN pin census (out/route/tile_gw1nz.dsn) nets+pins == pcb nets+pins
    (network fidelity, same parity as the batch-3/4 checks);
  * every net classified (docs/netclasses.json) and all 45 present;
  * vacuity: perturbing one K1 pad by +5 mm MUST change K1's MST.
Output: docs/length_budget.json (+ per-class summary, edge-discipline
  candidates = longest edge_critical chains).
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
DSN = os.path.join(BOARD, "out", "route", "tile_gw1nz.dsn")
TABLE = os.path.join(BOARD, "docs", "netclasses.json")
OUT = os.path.join(BOARD, "docs", "length_budget.json")

spec = importlib.util.spec_from_file_location(
    "rg", os.path.join(HERE, "routing_geo.py"))
rg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rg)


def pads_by_net(path):
    text = open(path).read()
    pads = {}
    for b in rg.blocks(text, "(footprint"):
        ref = re.match(r'\(footprint "([^"]+)"', b).group(1)
        fp = re.search(r"^\s*\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)\n",
                       b, re.M)
        fx, fy = float(fp.group(1)), float(fp.group(2))
        for pb in rg.blocks(b, "(pad"):
            m = re.match(r'\(pad\s+(?:"([^"]*)"|([^\s()]+))', pb)
            num = m.group(1) if m.group(1) is not None else m.group(2)
            net = re.search(r'\(net (?:\d+ )?"([^"]+)"\)', pb)
            atp = re.search(r"\(at ([-\d.]+) ([-\d.]+)", pb)
            if not (net and num and atp):
                continue
            pads.setdefault(net.group(1), []).append(
                {"pin": f"{ref}-{num}",
                 "x": fx + float(atp.group(1)),
                 "y": fy + float(atp.group(2))})
    return pads


def manhattan_mst(pts):
    """Prim MST over |dx|+|dy| distances."""
    n = len(pts)
    used = [False] * n
    dist = [math.inf] * n
    dist[0] = 0.0
    tot = 0.0
    for _ in range(n):
        u = min((d, i) for i, d in enumerate(dist) if not used[i])[1]
        used[u] = True
        tot += dist[u]
        for v in range(n):
            if used[v]:
                continue
            d = abs(pts[u][0] - pts[v][0]) + abs(pts[u][1] - pts[v][1])
            if d < dist[v]:
                dist[v] = d
    return tot


def metrics(pads, second_pin_perturb=None):
    pts = [(p["x"], p["y"]) for p in pads]
    if second_pin_perturb is not None:
        pts[1] = (pts[1][0] + second_pin_perturb, pts[1][1])
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    span = (max(xs) - min(xs), max(ys) - min(ys))
    dia = max(abs(a[0] - b[0]) + abs(a[1] - b[1])
              for i, a in enumerate(pts) for b in pts[i + 1:]) \
        if len(pts) > 1 else 0.0
    mst = manhattan_mst(pts) if len(pts) > 1 else 0.0
    return span[0], span[1], span[0] + span[1], dia, mst


def dsn_nets(path):
    text = open(path).read()
    nets = {}
    for nb in rg.blocks(text, "(network"):
        for m in re.finditer(r'\(net\s+(\S+)\s+\(pins\s+([^)]*)\)\s*\)',
                             nb):
            nets[m.group(1)] = m.group(2).split()
    return nets


def main():
    pads = pads_by_net(PCB)
    dsn = dsn_nets(DSN)
    probs = []
    if set(pads) != set(dsn):
        probs.append("pcb/dsn net census mismatch "
                     f"{sorted(set(pads) ^ set(dsn))[:4]}")
    else:
        for n in pads:
            if len(pads[n]) != len(dsn[n]):
                probs.append(f"{n}: pcb {len(pads[n])} vs dsn {len(dsn[n])}")
    table = json.load(open(TABLE))
    cls_of = {n: k for k, v in table["classes"].items() for n in v["nets"]}
    if set(cls_of) != set(pads) or len(pads) != 45:
        probs.append("class table / pcb net census mismatch")

    # series resistor ref for boundary nets: *-DRV plus plain twin share
    # one R ref (the pad belongs to both nets by construction)
    twin = {}
    for n in pads:
        if n.endswith("_DRV"):
            plain = n[:-4]
            if plain in pads:
                rrefs = ({p["pin"].split("-")[0] for p in pads[n]} &
                         {p["pin"].split("-")[0] for p in pads[plain]})
                rrefs = {r for r in rrefs if re.fullmatch(r"R\d+", r)}
                for rr in rrefs:
                    twin[n] = rr
                    twin[plain] = rr

    budget = []
    for n in sorted(pads):
        ps = pads[n]
        dx, dy, hp, dia, mst = metrics(ps)
        rec = {"net": n, "class": cls_of.get(n),
               "pad_count": len(ps),
               "pins": [f"{p['pin']}({p['x']:.2f},{p['y']:.2f})"
                        for p in ps],
               "bbox_span_xy": [round(dx, 2), round(dy, 2)],
               "hpwl_mm": round(hp, 2),
               "pin_diameter_manhattan_mm": round(dia, 2),
               "mst_manhattan_mm": round(mst, 2)}
        if n in twin:
            rec["series_resistor"] = twin[n]
        budget.append(rec)

    # vacuity control
    ctrl = None
    for n in pads:
        if n == "K1" and len(pads[n]) > 1:
            base_m = metrics(pads[n])[4]
            pert = metrics(pads[n], second_pin_perturb=5.0)[4]
            ctrl = (base_m != pert)
    if ctrl is not True:
        probs.append("vacuity FAIL: K1 MST insensitive to +5mm pad move")

    byclass = {}
    for r in budget:
        c = byclass.setdefault(r["class"], {"nets": 0, "mst_max": 0.0,
                                            "mst_sum": 0.0, "worst": ""})
        c["nets"] += 1
        c["mst_sum"] = round(c["mst_sum"] + r["mst_manhattan_mm"], 2)
        if r["mst_manhattan_mm"] > c["mst_max"]:
            c["mst_max"] = r["mst_manhattan_mm"]
            c["worst"] = r["net"]
    ec = sorted((r for r in budget if r["class"] == "edge_critical"),
                key=lambda r: -r["mst_manhattan_mm"])
    rep = {"_meta": {"model": "pin-centre Manhattan MST (routing lower "
                     "bound) + bbox HP + pin diameter; class from "
                     "netclasses.json; no copper implied",
                     "generated_by": "tools/length_budget.py"},
           "vacuity_control": control_text(ctrl, probs),
           "dsn_cross_check": "PASS" if not probs else probs,
           "per_class": byclass,
           "edge_critical_rank": [{"net": r["net"], "mst": r["mst_manhattan_mm"],
                                   "series": r.get("series_resistor")}
                                  for r in ec],
           "nets": budget}
    with open(OUT, "w") as f:
        json.dump(rep, f, indent=1)
        f.write("\n")
    top = ec[0]
    print(("LENGTH_BUDGET OK: " if not probs else
           f"LENGTH_BUDGET FAIL: {probs}") +
          f"45 nets, per-class mst_max="
          f"{[(k, v['mst_max'], v['worst']) for k, v in byclass.items()]}, "
          f"edge-critical longest={top['net']} {top['mst_manhattan_mm']}mm "
          f"-> {OUT}")
    sys.exit(1 if probs else 0)


def control_text(ctrl, probs):
    if ctrl:
        return "PASS: K1 MST changed under +5mm pad perturbation"
    return "FAIL"


if __name__ == "__main__":
    main()
