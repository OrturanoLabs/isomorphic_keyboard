#!/usr/bin/env python3
"""netclass_prep.py -- FPGA-02 preparation: net-class assignment table for
the r6 gw1nz tile, machine-derived from the actual pcb (no hand census).

Emits docs/netclasses.json: for every one of the 45 r6 nets -- its class,
the candidate routing rule (track/clearance/via from the strict reference
rule set, docs/routing_plan.md), return-path requirements, and bench
relevance (B1/B2 probe points). A later FPGA-02 session converts this into
KiCad net classes; nothing here routes anything or changes the pcb.

Self-checks (exit 1 on failure):
  N1  partition is EXACT: every pcb net classified, exactly once, total 45.
  N2  the five forward outputs + their _DRV stubs match the N10 topology
      read back off the pcb (U1 pin -> Rn.1 on <net>_DRV, Rn.2 -> JP net).
  N3  power net set == exactly {VCC, VCC1V2, VCC1V2_RAW, GND}.
  N4  every interface net (edge/level/channel) has its JP pad present on
      the pcb, and the three GND_DET presence pads sit on GND.
  N5  negative control: with T_clk removed from the class lists the
      partition check MUST fail (guards vacuity).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
PCB = os.path.join(BOARD, "out", "kicad", "tile_gw1nz.kicad_pcb")
OUT = os.path.join(BOARD, "docs", "netclasses.json")

RULE = {"track_mm": 0.2, "clearance_mm": 0.2, "via_d_mm": 0.6,
        "via_drill_mm": 0.3}  # strict reference set (docs/routing_plan.md)

CLASSES = {
    "edge_critical": {
        "nets": ["T_clk", "T_clk_DRV", "L_clk", "L_clk_DRV",
                 "L_latch", "L_latch_DRV"],
        "rule": {**RULE, "note": "clock/strobe class: any threshold "
                 "re-crossing is a spurious shift/latch (termination.md); "
                 "route with adjacent continuous GND return, no plane "
                 "splits under the run, B2-scoped at the far contact"},
        "bench": "B2"},
    "level_out": {
        "nets": ["B_data", "B_data_DRV", "B_W", "B_W_DRV"],
        "rule": {**RULE, "note": "level nets (star or p2p): settle before "
                 "the capture edge; continuous return still required; "
                 "B_data is B2-scoped as the star-class representative"},
        "bench": "B2"},
    "channel_in": {
        "nets": ["B_clk", "T_W", "T_endcol", "B_first", "L_endrow",
                 "T_data", "L_data", "B_latch", "R_latch"],
        "rule": {**RULE, "note": "downstream/return channel inputs; "
                 "pad pull per cst (PULL_MODE); keep out of the switch "
                 "contact bounce shadow is NOT a routing feature"},
        "bench": None},
    "keys": {
        "nets": [f"K{i}" for i in range(1, 13)],
        "rule": {**RULE, "note": "key matrix inputs, pad pull-DOWN "
                 "(external-10k bench fallback), slow human signals"},
        "bench": None},
    "power": {
        "nets": ["VCC", "VCC1V2", "VCC1V2_RAW", "GND"],
        "rule": {"track_mm": 0.5, "clearance_mm": 0.2, "via_d_mm": 0.6,
                 "via_drill_mm": 0.3,
                 "note": "GND = pour/plane first-class net; VCC1V2_RAW is "
                 "the ~31 mm LDO->bead run: wide trace, ~1.5 mV IR at "
                 "30 mA (power_reg.md); VCC1V2 = bead-filtered core rail"},
        "bench": "B1"},
    "config": {
        "nets": ["JTAG_TCK", "JTAG_TMS", "JTAG_TDI", "JTAG_TDO",
                 "JTAGSEL_N", "MODE0", "MODE1", "CFG_READY", "CFG_DONE",
                 "CFG_RECONFIG"],
        "rule": {**RULE, "note": "one-time programming/strap class; every "
                 "net has exactly one TP (checker N4) which must stay "
                 "probed-able; JTAG cable reference = 3.3 V"},
        "bench": "B3"},
}


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


def parse_pcb(path):
    text = open(path).read()
    fps, pads = {}, {}
    for b in blocks(text, "(footprint"):
        ref = re.match(r'\(footprint "([^"]+)"', b).group(1)
        for pb in blocks(b, "(pad"):
            m = re.match(r'\(pad\s+(?:"([^"]*)"|([^\s()]+))', pb)
            num = m.group(1) if m.group(1) is not None else m.group(2)
            net = re.search(r'\(net \d+ "([^"]+)"\)', pb)
            if net:
                pads.setdefault(net.group(1), set()).add((ref, num))
    return pads


def main():
    pads = parse_pcb(PCB)
    nets = set(pads)

    # N2: series topology read off the pcb
    expect_drv = {"T_clk": ("35", "R7"), "L_clk": ("19", "R8"),
                  "B_W": ("27", "R11"), "B_data": ("30", "R10"),
                  "L_latch": ("31", "R9")}
    for net, (pin, r) in expect_drv.items():
        drv = pads.get(net + "_DRV", set())
        base = pads.get(net, set())
        if ("U1", pin) not in drv or (r, "1") not in drv or \
                (r, "2") not in base or ("JP_" + net, "1") not in base:
            sys.exit(f"N2 FAIL: {net} topology drift: drv={sorted(drv)} "
                     f"base={sorted(base)}")

    def partition_ok(cls_map):
        flat = {n for v in cls_map.values() for n in v["nets"]}
        return (flat == nets
                and len(flat) == sum(len(v["nets"]) for v in cls_map.values()))

    # N5 vacuity control: with T_clk dropped the partition MUST fail
    corrupt = {c: {**v, "nets": [n for n in v["nets"] if n != "T_clk"]}
               for c, v in CLASSES.items()}
    if partition_ok(corrupt):
        sys.exit("N5 FAIL: control accepted an incomplete partition "
                 "(vacuous check)")
    if not partition_ok(CLASSES):
        flat = {n for v in CLASSES.values() for n in v["nets"]}
        sys.exit(f"N1 FAIL: unclassified={sorted(nets - flat)} "
                 f"phantom={sorted(flat - nets)} (pcb nets={len(nets)})")
    if set(CLASSES["power"]["nets"]) != nets & {"VCC", "VCC1V2",
                                                "VCC1V2_RAW", "GND"}:
        sys.exit("N3 FAIL: power net drift")
    jp_nets = {n for n, nd in pads.items()
               if any(r.startswith("JP_") for r, _ in nd)}
    iface = (set(CLASSES["edge_critical"]["nets"]) |
             set(CLASSES["level_out"]["nets"]) |
             set(CLASSES["channel_in"]["nets"]))
    if not iface <= (jp_nets | {n + "_DRV" for n in jp_nets}):
        sys.exit("N4 FAIL: interface net without JP presence: "
                 f"{sorted(iface - jp_nets - {n + '_DRV' for n in jp_nets})}")
    for det in ("JP_GND_DET_T", "JP_GND_DET_B", "JP_GND_DET_R"):
        if (det, "1") not in pads.get("GND", set()):
            sys.exit(f"N4 FAIL: {det} not bonded to GND")

    out = {
        "_meta": {
            "source_pcb": os.path.relpath(PCB, BOARD),
            "generated_by": "tools/netclass_prep.py (FPGA-02 preparation; "
                            "nothing routed, nothing activated)",
            "board_rev": "r6 placement prototype, 45 nets, 0 tracks",
            "checks": "N1 partition exact; N2 series topology off pcb; "
                      "N3 power set; N4 JP/presence coverage; N5 vacuity "
                      "control",
        },
        "rule_reference": {**RULE, "source": "docs/routing_plan.md"},
        "classes": CLASSES,
        "net_to_class": {n: cname
                         for cname, c in CLASSES.items()
                         for n in sorted(c["nets"])},
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    census = {c: len(v["nets"]) for c, v in CLASSES.items()}
    print(f"NETCLASS_PREP OK: {len(nets)} pcb nets, "
          f"{sum(census.values())} classified ({census}) -> {OUT}")


if __name__ == "__main__":
    main()
