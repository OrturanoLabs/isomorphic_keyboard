#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""schematic_check.py -- authoritative-schematic gate for the FPGA tile
(board variant gw1nz). Runs (and asserts on) REAL KiCad output; no
hand-waved equivalence. Sections:

  S1  Fresh KiCad ERC (kicad-cli sch erc --severity-all) -> 0 violations.
      No exclusion files, no severity filters, project libs resolve via
      the generated sym-lib-table/fp-lib-table.
  S2  Netlist export (kicadsexpr) parses; power nets carry real names
      (VCC/GND/VCC1V2 present; no '' or '<NO NET>' nets).
  S3  Net-name census == the canonical 45 board nets (hardcoded here;
      triangularly cross-checked against cst + pins db + pcb; 40 +
      five <net>_DRV driver-side stubs of the r6 series positions).
  S4  Schematic<->PCB parity: every net's (ref,pin) set in the KiCad
      netlist equals the pcb's (ref,pad) set, modulo schematic-only refs
      (#PWR*, FLG1) which by construction have no copper.
  S5  Constraint parity: the 26 tile IO in tile_gw1nz_board.cst map 1:1
      onto schematic nets U1 pins (port->net table from
      rtl/top_gw1nz.vhdl). The db io-pin legality half is NOT repeated
      here -- it is covered by tools/pincon_check.py (B1..B6).
  S6  U1 power coverage == pins_gw1nz_qn48.json (power pins land on the
      right nets, exactly pins 6/9/14/15/29 are NC) plus EXACT strap
      topology: MODE0/MODE1/JTAG_TCK/CFG_*/ nets carry precisely their
      {U1 pin, strap-R pad, optional TP} node sets, and each strap
      resistor's far end sits on the right rail (cross-covered on the
      pcb by board_net_check N3).
  S7  Negative controls: three deliberate corruptions (netlist net
      rename, dropped netlist node, pcb pad remap) MUST be detected by
      the comparisons used in S3/S4. If any control is NOT caught, the
      whole check FAILS (means the comparisons are vacuous).

Exit 0 only if everything passes. Heavy kicad-cli steps go through
tools/resource_guard.py like every other heavy job.

Note: kicad-cli's netlist exporter prints "Warning: schematic has
annotation errors..." because this design uses semantic refs
(JP_B_clk, TP_TCK, ...) instead of annotatable Jn/Tn names -- same refs
as the PCB (parity is deliberate). Documented benign; ERC is clean.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

BOARD = Path(__file__).resolve().parent.parent
KOUT = BOARD / "out" / "kicad"
ROOT = BOARD.parents[4]                      # repo root
KICAD = ROOT / "tools" / "kicad-cli.sh"
GUARD = ROOT / "hardware/experiments/simple-tile/tools/resource_guard.py"

SCH = KOUT / "tile_gw1nz.kicad_sch"
ERC_JSON = KOUT / "tile_gw1nz.erc.json"
NETLIST = KOUT / "tile_gw1nz.net"
PCB = KOUT / "tile_gw1nz.kicad_pcb"
CST = BOARD / "constraints" / "tile_gw1nz_board.cst"
PINS_DB = BOARD / "data" / "pins_gw1nz_qn48.json"

# frame-neutral series-termination mirror (board_gen.SERIES_DRV_GW1NZ;
# base net, series R, U1 pin) -- the driver side lives on <net>_DRV.
SERIES_DRV = (("T_clk", "R7", "35"), ("L_clk", "R8", "19"),
              ("L_latch", "R9", "31"), ("B_data", "R10", "30"),
              ("B_W", "R11", "27"))
SERIES_DRV_NETS = {b for b, _r, _p in SERIES_DRV}

CANONICAL_NETS = (
    {f"K{i}" for i in range(1, 13)} |
    {"T_W", "T_clk", "T_data", "T_endcol", "B_W", "B_clk", "B_data",
     "B_first", "B_latch", "L_clk", "L_data", "L_endrow", "L_latch",
     "R_latch"} |
    {f"{b}_DRV" for b, _r, _p in SERIES_DRV} |      # board r6: 45 nets
    {"JTAG_TCK", "JTAG_TMS", "JTAG_TDI", "JTAG_TDO", "CFG_READY",
     "CFG_DONE", "CFG_RECONFIG", "JTAGSEL_N", "MODE0", "MODE1"} |
    {"VCC", "GND", "VCC1V2", "VCC1V2_RAW"}
)
assert len(CANONICAL_NETS) == 45

# rtl/top_gw1nz.vhdl port -> schematic net (entity top_gw1nz, 26 tile IO)
PORT2NET = ({"keys[%d]" % i: "K%d" % (i + 1) for i in range(12)} | {
    "clk_pin": "B_clk", "t_w_pin": "T_W", "t_endcol_pin": "T_endcol",
    "t_data_pin": "T_data", "b_first_pin": "B_first",
    "b_latch_pin": "B_latch", "r_latch_pin": "R_latch",
    "l_endrow_pin": "L_endrow", "l_data_pin": "L_data",
    "t_clk_pin": "T_clk", "l_clk_pin": "L_clk", "latcho_pin": "L_latch",
    "dout_pin": "B_data", "b_w_pin": "B_W"})
# db power net -> schematic rail
DB_PWR = {"VCCIO0": "VCC", "VCCIO1": "VCC", "VCCX3V3": "VCC",
          "VCC1V2": "VCC1V2", "GND": "GND"}


def run_guarded(cmd, timeout):
    full = [sys.executable, str(GUARD), "--timeout", str(timeout), "--",
            "bash", "-c", cmd]
    env = dict(os.environ)
    env.setdefault("RESOURCE_GUARD_DEADLINE", "2026-10-15T10:00:00+02:00")
    r = subprocess.run(full, capture_output=True, text=True, cwd=KOUT,
                       env=env)
    return r
# NOTE: bash -c wrapper keeps quoting simple; commands are constant
# strings authored here, nothing user-controlled.


def parse_netlist(path):
    t = open(path).read()
    i = t.index("\t(nets")
    nets = {}
    while True:
        j = t.find("\n\t\t(net\n", i)
        if j < 0:
            break
        j += 1
        d, k = 0, j
        while k < len(t):
            if t[k] == "(":
                d += 1
            elif t[k] == ")":
                d -= 1
                if d == 0:
                    break
            k += 1
        blk = t[j:k + 1]
        m = re.search(r'\(name "([^"]*)"\)', blk)
        nodes = set(re.findall(r'\(ref "([^"]+)"\)\s*\n?\s*\(pin "([^"]+)"\)',
                               blk))
        nets[m.group(1)] = nodes
        i = k + 1
    return nets


def norm(name):
    return name[1:] if name.startswith("/") else name


def parse_pcb(path):
    t = open(path).read()
    pads = {}                       # net name -> {(ref, pad)}
    i = 0
    while True:
        j = t.find("(footprint ", i)
        if j < 0:
            break
        d, k = 0, j
        while k < len(t):
            if t[k] == "(":
                d += 1
            elif t[k] == ")":
                d -= 1
                if d == 0:
                    break
            k += 1
        blk = t[j:k + 1]
        m = re.search(r'property "Reference" "([^"]+)"', blk)
        ref = m.group(1) if m else re.search(r'\(footprint "([^"]+)"',
                                             blk).group(1)
        # pads reference nets directly by name: (net 12 "B_clk"); pad names
        # may be quoted ("1") or bare (1) and pads without a net must NOT
        # leak the next pad's net -> parse each pad's own span only.
        marks = [m.start() for m in re.finditer(r'\(pad\s', blk)]
        for q, a in enumerate(marks):
            span = blk[a:marks[q + 1] if q + 1 < len(marks) else len(blk)]
            pm = re.match(r'\(pad\s+"?([^"\s\)]+)"?', span)
            nm = re.search(r'\(net \d+ "([^"]+)"\)', span)
            if pm and nm and nm.group(1):
                pads.setdefault(nm.group(1), set()).add((ref, pm.group(1)))
        i = k + 1
    return pads


def compare(name, a, b, problems):
    """two maps net->set(ref,pin); report member-level diffs."""
    only_a = set(a) - set(b)
    only_b = set(b) - set(a)
    if only_a:
        problems.append(f"{name}: nets only in first: {sorted(only_a)}")
    if only_b:
        problems.append(f"{name}: nets only in second: {sorted(only_b)}")
    for net in sorted(set(a) & set(b)):
        if a[net] != b[net]:
            problems.append(f"{name}: net {net} members differ: "
                            f"first-only={sorted(a[net] - b[net])} "
                            f"second-only={sorted(b[net] - a[net])}")


def main():
    problems = []
    # ---------------- S1: fresh true ERC, zero violations
    r = run_guarded(
        f"{KICAD} sch erc --format json --severity-all "
        f"-o {ERC_JSON} {SCH}", 300)
    if r.returncode != 0:
        problems.append(f"S1: kicad-cli erc failed: {r.stdout[-400:]} "
                        f"{r.stderr[-400:]}")
        violations = None
    else:
        reps = json.load(open(ERC_JSON))
        violations = [x for x in reps["sheets"][0]["violations"]]
        if violations:
            problems.append("S1: ERC violations: " +
                            "; ".join(f"{x['severity']}:{x['type']} "
                                      f"{x['description'][:70]}"
                                      for x in violations[:10]))
    print(f"S1 ERC: {'0 violations' if violations == [] else 'FAIL'}"
          f" (severity-all, no exclusions)")
    # ---------------- S2: netlist export
    r = run_guarded(
        f"{KICAD} sch export netlist --format kicadsexpr "
        f"-o {NETLIST} {SCH}", 300)
    if r.returncode != 0:
        problems.append(f"S2: netlist export failed: {r.stdout[-300:]}")
        nets = {}
    else:
        nets = parse_netlist(NETLIST)
        bad = [n for n in nets if not n or "<NO NET>" in n]
        if bad:
            problems.append(f"S2: bad/empty net names: {bad}")
    print(f"S2 netlist: {len(nets)} nets, bad names: "
          f"{[n for n in nets if not n or '<NO NET>' in n]}")
    # ---------------- S3: census
    have = {norm(n) for n in nets if not n.startswith("unconnected-")}
    if have != CANONICAL_NETS:
        problems.append(f"S3: census mismatch: only-in-kicad="
                        f"{sorted(have - CANONICAL_NETS)} missing="
                        f"{sorted(CANONICAL_NETS - have)}")
    print(f"S3 census: {len(have)}/{len(CANONICAL_NETS)} nets")
    # ---------------- S4: pcb parity
    pcb = parse_pcb(PCB)
    norm_k = {norm(n): nodes for n, nodes in nets.items()
              if not n.startswith("unconnected-")}
    norm_k = {n: {(r, p) for (r, p) in nodes
                  if not r.startswith("#") and r != "FLG1"}
              for n, nodes in norm_k.items()}
    s4 = []
    compare("S4", pcb, norm_k, s4)
    problems += s4
    print(f"S4 pcb parity: pcb {sum(len(v) for v in pcb.values())} pads, "
          f"sch {sum(len(v) for v in norm_k.values())} pins; "
          f"{'MATCH' if not s4 else 'FAIL ' + str(s4[:2])}")
    # ---------------- S5: cst parity
    cst = CST.read_text()
    locs = dict(re.findall(r'IO_LOC "([^"]+)"\s+(\d+);', cst))
    if set(locs) != set(PORT2NET):
        problems.append("S5: cst ports != rtl-derived 26: "
                        f"{sorted(set(locs) ^ set(PORT2NET))}")
    u1 = {}
    for n, nodes in nets.items():
        for (ref, pin) in nodes:
            if ref == "U1":
                u1.setdefault(pin, set()).add(norm(n))
    s5 = []
    for port, net in PORT2NET.items():
        want = net + "_DRV" if net in SERIES_DRV_NETS else net
        got = u1.get(locs.get(port, ""), set())
        if got != {want}:
            s5.append(f"{port}@{locs.get(port)}: U1 net {got} != {want}")
    if s5:
        problems.append("S5: " + "; ".join(s5))
    print(f"S5 cst parity: {len(locs)}/26 ports == U1 pins "
          f"{'MATCH' if not s5 else 'FAIL ' + str(s5[:3])}")
    # ---------------- S6: power/strap coverage vs pins db
    s6 = []
    db = json.load(open(PINS_DB))["pins"]
    # NC set from the netlist: U1 pins that sit on no real net
    nc = {p for p in map(str, range(1, 50))
          if not u1.get(p)
          or next(iter(u1[p])).startswith("unconnected-")}
    if nc != {"6", "9", "14", "15", "29"}:
        s6.append(f"U1 NC set {sorted(nc)} != 6/9/14/15/29")
    for p, rec in db.items():
        want = DB_PWR.get(rec.get("net", ""), rec.get("net"))
        if rec.get("role") in ("power", "ground"):
            sch_pin = "49" if p == "EPAD" else p      # 49 = exposed pad
            got = u1.get(sch_pin, set())
            if got != {want}:
                s6.append(f"U1.{p}: net {got} != {want}")
    # strap RC topology, hardcoded from the verified r5 circuit -- the
    # SAME table board_net_check N3 enforces on the pcb. NOT a formality:
    # the node sets are exact, so a dropped strap pad or a wrong rail
    # lands here even if every net name still parses.
    STRAPS = [  # net, exact {(ref,pin)} nodes, strap R, far-end rail
        ("MODE0",       {("U1", "43"), ("R1", "1")},                         "R1", "GND"),
        ("MODE1",       {("U1", "42"), ("R2", "1")},                         "R2", "GND"),
        ("JTAG_TCK",    {("U1", "3"), ("R3", "1"), ("TP_TCK", "1")},          "R3", "GND"),
        ("CFG_READY",   {("U1", "45"), ("R4", "1"), ("TP_READY", "1")},       "R4", "VCC"),
        ("CFG_DONE",    {("U1", "46"), ("R5", "1"), ("TP_DONE", "1")},        "R5", "VCC"),
        ("CFG_RECONFIG",{("U1", "48"), ("R6", "1"), ("TP_RECFG", "1")},       "R6", "VCC"),
    ]
    normed = {}
    for n, nodes in nets.items():
        normed.setdefault(norm(n), set()).update(nodes)
    for net, want_nodes, rref, rail in STRAPS:
        got = normed.get(net, set())
        if got != want_nodes:
            s6.append(f"strap net {net}: nodes {sorted(got)} != "
                      f"{sorted(want_nodes)}")
        elif (rref, "2") not in normed.get(rail, set()):
            s6.append(f"strap resistor {rref}.2 not on rail {rail}")
    # series-termination split (mirror of board net checker N10): each
    # output is exactly U1.pin--Rn.1 on <net>_DRV and Rn.2--JP_<net>.1 on
    # <net>; the interface net name stays at the chassis contact.
    for base, rref, pin in SERIES_DRV:
        drv = base + "_DRV"
        if normed.get(drv, set()) != {("U1", pin), (rref, "1")}:
            s6.append(f"series net {drv}: nodes "
                      f"{sorted(normed.get(drv, set()))} != "
                      f"[('U1',{pin!r}), ({rref!r},'1')]")
        if normed.get(base, set()) != {("JP_" + base, "1"), (rref, "2")}:
            s6.append(f"series net {base}: nodes "
                      f"{sorted(normed.get(base, set()))} != "
                      f"[('JP_{base}','1'), ({rref!r},'2')]")
    if s6:
        problems.append("S6: " + "; ".join(s6))
    print(f"S6 power/strap coverage: {'MATCH' if not s6 else 'FAIL'} "
          f"(NC {sorted(nc)})")
    # ---------------- S7: negative controls
    det = []
    tmp1 = dict(nets)
    victim = next(n for n in tmp1 if norm(n) == "T_data")
    tmp1[victim.replace("T_data", "CFG_")] = tmp1.pop(victim)
    ctrl = []
    compare("ctl", pcb, {norm(n): {(r, p) for (r, p) in s
                                   if not r.startswith("#") and r != "FLG1"}
                         for n, s in tmp1.items()}, ctrl)
    det.append(bool(ctrl))
    tmp2 = {n: set(s) for n, s in norm_k.items()}
    tmp2["B_clk"].discard(("U1", "47"))
    ctrl = []
    compare("ctl", pcb, tmp2, ctrl)
    det.append(bool(ctrl))
    tmp3 = {n: set(s) for n, s in pcb.items()}
    tmp3["B_clk"].discard(("JP_B_clk", "1"))
    ctrl = []
    compare("ctl", tmp3, norm_k, ctrl)
    det.append(bool(ctrl))
    if not all(det):
        problems.append(f"S7: negative controls failed to fire: {det}")
    print(f"S7 negative controls: 3/3 fired == {all(det)}")
    # ---------------- verdict
    print("-" * 60)
    if problems:
        print("SCHEMATIC_CHECK: FAIL")
        for p in problems:
            print("  !", p)
        sys.exit(1)
    print("SCHEMATIC_CHECK: PASS (S1-S7)")


if __name__ == "__main__":
    main()
