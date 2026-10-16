#!/usr/bin/env python3
"""widen_check.py -- FPGA-02 preparation audit: for every recorded SES

arm, emit the fix_routed-style WIDEN LIST a SES-adopting import would
need, plus a per-net routed-length vs length_budget.json comparison.

Width basis: docs/netclasses.json (net_to_class -> class rule track_mm;
absolute floor 0.2 mm for every class, 0.5 mm for power). SES units are
0.1-um integers for both path widths and coordinates (established in
batch 8 on the in-tree fixture; batches 9-11 reconfirmed on our arms).

LEDGER precedent: freerouting emits below-rule widths and 0 violations
(discrete fix_routed.py existed exactly for widening them); this audit
quantifies the same trait on OUR three arms, per net and per path, so
an adopting pass knows exactly what to widen (or re-route) instead of
trusting the router's own violation count.

Writes docs/widen_report.json. Pure text audit; exits nonzero only on
parse/schema breakage. Run under resource_guard per session policy.
"""
import hashlib
import importlib.util
import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
_spec = importlib.util.spec_from_file_location(
    "sc", os.path.join(HERE, "ses_import_check.py"))
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

OUT = os.path.join(BOARD, "docs", "widen_report.json")
UNIT_TO_MM = 1.0 / 10000          # SES 0.1-um units -> mm
UNIT_TO_UM = 1.0 / 10             # SES 0.1-um units -> um
FLOOR_UM = 200.0                  # strict 0.2 mm class floor

ARMS = [
    ("bare", "out/route/tile_gw1nz.ses"),
    ("dead_end_stubs", "out/route/tile_gw1nz_fanout.ses"),
    ("four_l_planes", "out/route/tile_gw1nz_4l.ses"),
    ("four_l_attach_vias", "out/route/tile_gw1nz_4l_attach.ses"),
]


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def parse_ses_paths(path):
    """Per net: wire paths [{layer,width_units,pts[(x,y),..]}], vias."""
    text = open(path).read()
    nets = {}
    for nb in sc.blocks(text, "(network_out"):
        for nseg in sc.blocks(nb, "(net"):
            m = re.match(r'\(net\s+(\S+)', nseg)
            if not m:
                continue
            name = m.group(1).strip('"')
            entry = nets.setdefault(name, {"paths": [], "vias": 0})
            for wb in sc.blocks(nseg, "(wire"):
                for pm in re.finditer(
                        r"\(path\s+(\S+)\s+(\d+)((?:\s+-?[\d.]+\s+-?[\d.]+)+)\s*\)",
                        wb):
                    pts = [(float(a), float(b)) for a, b in re.findall(
                        r"(-?[\d.]+)\s+(-?[\d.]+)", pm.group(3))]
                    entry["paths"].append({
                        "layer": pm.group(1),
                        "width_units": int(pm.group(2)),
                        "pts": pts,
                    })
            entry["vias"] += len(re.findall(r'\(via\s+"[^"]+"', nseg))
    return nets


def path_len_mm(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1])
               for a, b in zip(pts, pts[1:])) * UNIT_TO_MM


def main():
    nc = json.load(open(os.path.join(BOARD, "docs", "netclasses.json")))
    n2c = {sc.norm(k): v for k, v in nc["net_to_class"].items()}
    min_um = {c: float(v["rule"]["track_mm"]) * 1000.0
              for c, v in nc["classes"].items()}
    lb = json.load(open(os.path.join(BOARD, "docs", "length_budget.json")))
    budget = {e["net"]: e for e in lb["nets"]}

    arms = []
    for arm_id, rel in ARMS:
        p = os.path.join(BOARD, rel)
        nets = parse_ses_paths(p)
        widen, subrule, lengths = [], [], {}
        n_paths = 0
        for name, e in sorted(nets.items()):
            c = n2c.get(sc.norm(name))
            req = max(min_um.get(c, FLOOR_UM), FLOOR_UM)
            total = 0.0
            for path in e["paths"]:
                n_paths += 1
                w_um = path["width_units"] * UNIT_TO_UM
                L = path_len_mm(path["pts"])
                total += L
                rec = {
                    "net": name, "class": c,
                    "layer": path["layer"],
                    "width_um": round(w_um, 1),
                    "required_um": round(req, 1),
                    "start": [round(path["pts"][0][0] * UNIT_TO_MM, 4),
                              round(path["pts"][0][1] * UNIT_TO_MM, 4)],
                    "n_points": len(path["pts"]),
                    "length_mm": round(L, 3),
                }
                if w_um < req - 1e-9:
                    widen.append(rec)
                if w_um < FLOOR_UM - 1e-9:
                    subrule.append(rec)
            if total > 0:
                b = budget.get(name)
                lengths[name] = {
                    "routed_mm_partial": round(total, 3),
                    "mst_budget_mm": b["mst_manhattan_mm"] if b else None,
                    "class": n2c.get(sc.norm(name)),
                    "note": "SES paths are per-part routed so far; net "
                            "incomplete per ses_import_check --full",
                }
        ratios = [(v["mst_budget_mm"] and v["routed_mm_partial"]
                   / v["mst_budget_mm"]) for v in lengths.values()
                  if v["mst_budget_mm"]]
        arms.append({
            "id": arm_id,
            "ses": rel,
            "ses_sha256_12": sha256(p)[:12],
            "nets_with_wire": sum(1 for e in nets.values() if e["paths"]),
            "wire_paths": n_paths,
            "widen_paths": len(widen),
            "sub_rule_paths": len(subrule),
            "widen_list": widen,
            "sub_rule_list": subrule,
            "routed_lengths_by_net": lengths,
            "routed_over_budget_partial_max":
                round(max(ratios), 3) if ratios else None,
        })
    doc = {
        "tool": "widen_check.py",
        "width_basis": "docs/netclasses.json class rules; floor "
                       "0.2 mm all classes, 0.5 mm power",
        "ledger_precedent": "discrete fix_routed.py: freerouting emits "
                            "below-rule widths with 0 violations scored",
        "arms": arms,
    }
    json.dump(doc, open(OUT, "w"), indent=1)
    print(f"WIDEN_CHECK OK -> {OUT}")
    for a in arms:
        print(f"  {a['id']}: paths={a['wire_paths']} "
              f"widen={a['widen_paths']} sub_rule={a['sub_rule_paths']} "
              f"nets_wired={a['nets_with_wire']} "
              f"len/budget_max={a['routed_over_budget_partial_max']}")


if __name__ == "__main__":
    main()
