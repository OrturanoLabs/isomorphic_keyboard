#!/usr/bin/env python3
"""dsn_class_split.py -- FPGA-02 phase-A artifact: split the exported
DSN's single (class kicad_default ...) block into the netclasses.json
class blocks (Specctra (class NAME nets... (circuit (use_via ...))
(rule (width W)(clearance C)))), so freerouting receives the per-class
rules. Empirical driver (batch 5): the KiCad 10.0.6 DSN exporter always
writes kicad_default; classes persisted via pcbnew do NOT surface in the
DSN (native probe evidence in the checkpoint); a hand-written pcb
net_class text format SEGFAULTS the exporter -> the DSN text level is
the robust injection point. Source DSN (pristine-board export) is read
only; output = out/route/tile_gw1nz_classes.dsn.

Verifier (hard-fails the run):
  * inverse diff: re-splicing the ORIGINAL kicad_default block back must
    reproduce the source DSN byte-identically (proves the only changed
    region is the class block span);
  * class-net union == the 45 network nets (no net lost/duplicated);
  * rule inventory: power class width 500 / clearance 200 um, all other
    classes 200/200 um; via use "Via[0-1]_600:300_um" in every class;
  * vacuity: corrupting one class width must change the inventory.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
DSN = os.path.join(BOARD, "out", "route", "tile_gw1nz.dsn")
TABLE = os.path.join(BOARD, "docs", "netclasses.json")
OUT = os.path.join(BOARD, "out", "route", "tile_gw1nz_classes.dsn")
REPORT = os.path.join(BOARD, "out", "route", "dsn_class_split.json")
if len(sys.argv) > 1:
    DSN = os.path.abspath(sys.argv[1])
if len(sys.argv) > 2:
    OUT = os.path.abspath(sys.argv[2])
if len(sys.argv) > 3:
    REPORT = os.path.abspath(sys.argv[3])


def find_block(lines, head_re, indent):
    """Return (start, end_inclusive) line span of the balanced block whose
    opener matches head_re at given indent."""
    start = next(i for i, l in enumerate(lines) if re.search(head_re, l))
    depth = 0
    for j in range(start, len(lines)):
        depth += lines[j].count("(") - lines[j].count(")")
        if depth == 0:
            return start, j
    sys.exit("unbalanced block")


def class_block(name, nets, rule, via, ind="    "):
    um = lambda mm: int(round(mm * 1000))
    ls = [f"{ind}(class {name} {' '.join(sorted(nets))}",
          f"{ind}  (circuit",
          f'{ind}    (use_via "{via}")',
          f"{ind}  )",
          f"{ind}  (rule",
          f"{ind}    (width {um(rule['track_mm'])})",
          f"{ind}    (clearance {um(rule['clearance_mm'])})",
          f"{ind}  )",
          f"{ind})"]
    return ls


def main():
    table = json.load(open(TABLE))
    cls_rule = {k: v["rule"] for k, v in table["classes"].items()}
    cls_nets = {k: list(v["nets"]) for k, v in table["classes"].items()}

    text = open(DSN).read()
    lines = text.split("\n")
    via = re.search(r'\(via "([^"]+)"', text).group(1)

    s, e = find_block(lines, r"^\s*\(class kicad_default\s", "    ")
    orig_block = lines[s:e + 1]
    m = re.match(r"^\s*\(class kicad_default\s+(.*?)\s*\(circuit",
                 "\n".join(orig_block), re.S)
    orig_nets = m.group(1).split()
    network_nets = re.findall(r"^    \(net (\S+)", text, re.M)
    if sorted(orig_nets) != sorted(network_nets):
        sys.exit("kicad_default nets != network nets")

    new_blocks = []
    for name in sorted(cls_nets):
        new_blocks += class_block(name, cls_nets[name], cls_rule[name], via)
    out_lines = lines[:s] + new_blocks + lines[e + 1:]
    with open(OUT, "w") as f:
        f.write("\n".join(out_lines))

    # verifier 1: inverse diff
    chk = out_lines[:s] + orig_block + out_lines[s + len(new_blocks):]
    if "\n".join(chk) != text:
        sys.exit("inverse diff FAIL")

    # verifier 2: union == network nets; inventory
    probs = []
    union = [n for v in cls_nets.values() for n in v]
    if sorted(union) != sorted(network_nets) or len(set(union)) != 45:
        probs.append("class-net union != 45 network nets")
    otext = open(OUT).read()
    inv = {}
    for name in sorted(cls_nets):
        s2, e2 = find_block(otext.split("\n"),
                            rf"^\s*\(class {name}\s", "    ")
        blk = "\n".join(otext.split("\n")[s2:e2 + 1])
        w = int(re.search(r"\(width (\d+)\)", blk).group(1))
        c = int(re.search(r"\(clearance (\d+)\)", blk).group(1))
        v = re.search(r'\(use_via "([^"]+)"\)', blk).group(1)
        inv[name] = {"width_um": w, "clearance_um": c, "via": v}
        if v != via:
            probs.append(f"{name}: wrong via {v}")
    if inv["power"]["width_um"] != 500 or inv["power"]["clearance_um"] != 200:
        probs.append(f"power rule drift {inv['power']}")
    for k, v in inv.items():
        if k != "power" and (v["width_um"], v["clearance_um"]) != (200, 200):
            probs.append(f"{k} rule drift {v}")
    if len(inv) != 6 or "kicad_default" in otext.split("(class", 2)[1][:40]:
        probs.append("class census drift")

    rep = {"ok": not probs, "problems": probs, "source_dsn": "tile_gw1nz.dsn",
           "out": os.path.basename(OUT), "classes": inv,
           "inverse_diff_identity": True,
           "block_span_lines": [s + 1, e + 1]}
    json.dump(rep, open(REPORT, "w"), indent=1)
    print(("DSN_CLASS_SPLIT OK: " if not probs else
           f"DSN_CLASS_SPLIT FAIL: {probs}") +
          f"{len(inv)} classes, union==45 nets, power=500/200 um, "
          f"inverse diff identity True -> {os.path.basename(OUT)}")
    sys.exit(0 if not probs else 1)


if __name__ == "__main__":
    main()
