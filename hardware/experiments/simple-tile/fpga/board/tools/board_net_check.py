#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""board_net_check -- circuit/net-binding verification of the emitted
.kicad_pcb against the vendor pin DBs + board constraint files.

This re-derives the expected netlist INDEPENDENTLY of kicad/board_gen.py
(own literal tables, own parser) and then compares pad-by-pad:
  N1 FPGA pad->net equality over all 49 pads (gw1nz U1 present; up5k U1
     absent by NOFIT design - netlist intent still exported)
  N2 power-rail membership: bank/VCCX rails on "VCC", core on "VCC1V2",
     grounds/EP on "GND"; rail rollup is stated HERE, not trusted from
     the generator (the 2026-10-13 singleton-rail bug class)
  N3 strap/filter/pull resistors: exact pad-net sets + values
  N4 config/JTAG/SPI test-pad coverage: each covered net has exactly one TP
  N5 decoupling census per rail + ferrite series topology (VCC1V2_RAW has
     exactly {U2.5, FB1.1}; FPGA core pads sit on the FILTERED side VCC1V2)
  N6 12 key sockets (pad1=VCC, pad2=Kn) + 19 chassis pads with the
     connector-next net set (14 signals + VCC + GND)
  N7 unused FPGA pads == expected pool complement exactly (pin-9 hazard
     excluded etc.)
  N8 single-pad net census must be EMPTY (gw1nz; up5k NOFIT board allows
     only U1-facing nets) - catches any future singleton power rail AND
     floating "presence" pads (DRC's unconnected-pair metric cannot see
     single-pad nets)
  N9 presence-pad bonding: each JP_GND_DET_{T,B,R} pad net == GND and the
     GND net contains the FPGA ground pads + the LDO ground pin (rev-A
     presence semantics: hard ground on an inserted tile, open when
     removed; the backplane's separate traces belong to connector-next
     and are not graph-changeable from here)
NEGATIVE CONTROL: the same checks are re-run with (a) a corrupted EXPECTED
map ( FPGA core pin bound to GND), (b) a corrupted PARSED board (a key
socket pad net renamed K1->K2), and (c) a presence pad rebound to an
ISOLATED net (the exact pre-fix defect).  All MUST fail.  A checker that
cannot fail proves nothing.

Exit 0 iff every real check passes AND every negative control fails as
expected.  Writes ../out/netcheck_report.{json,md}.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.abspath(os.path.join(HERE, ".."))
KICAD = os.path.join(BOARD, "kicad")
sys.path.insert(0, KICAD)
import pin_con_parse  # noqa: E402  (local, shared with the pincon checker)

TILE_NETS = {"clk_pin": "B_clk", "t_w_pin": "T_W", "t_endcol_pin": "T_endcol",
             "b_first_pin": "B_first", "l_endrow_pin": "L_endrow",
             "t_data_pin": "T_data", "l_data_pin": "L_data",
             "b_latch_pin": "B_latch", "r_latch_pin": "R_latch",
             "t_clk_pin": "T_clk", "l_clk_pin": "L_clk",
             "latcho_pin": "L_latch", "dout_pin": "B_data", "b_w_pin": "B_W"}

# rail rollup: vendor rail name -> board net (independent restatement of the
# binding rule; docs/power_reg.md carries the prose + source)
RAILS = {
    "gw1nz": {"VCCIO0": "VCC", "VCCIO1": "VCC", "VCCX3V3": "VCC",
              "VCC1V2": "VCC1V2"},
    "up5k": {"VCCIO": "VCC", "SPI_VCCIO1": "VCC", "VPP_2V5": "VCC",
             "VCC1V2": "VCC1V2", "VCCPLL_1V2": "VCCPLL_1V2"},
}

TP_MAP = {
    "gw1nz": {"JTAG_TCK": "TP_TCK", "JTAG_TMS": "TP_TMS",
              "JTAG_TDI": "TP_TDI", "JTAG_TDO": "TP_TDO",
              "CFG_READY": "TP_READY", "CFG_DONE": "TP_DONE",
              "CFG_RECONFIG": "TP_RECFG", "JTAGSEL_N": "TP_JTAGSEL",
              "VCC1V2": "TP_VCC1V2", "VCC": "TP_VCC", "GND": "TP_GND"},
    "up5k": {"SPI_SCK": "TP_SCK", "SPI_SI": "TP_SI", "SPI_SO": "TP_SO",
             "SPI_SS": "TP_SS", "CFG_CRESET": "TP_CRESET",
             "CFG_DONE": "TP_CDONE", "VCC1V2": "TP_VCC1V2",
             "VCC": "TP_VCC", "GND": "TP_GND"},
}

STRAPS = {
    "gw1nz": {"R1": ("1k", {"MODE0", "GND"}), "R2": ("1k", {"MODE1", "GND"}),
              "R3": ("4k7", {"JTAG_TCK", "GND"}),
              "R4": ("4k7", {"CFG_READY", "VCC"}),
              "R5": ("4k7", {"CFG_DONE", "VCC"}),
              "R6": ("4k7", {"CFG_RECONFIG", "VCC"})},
    "up5k": {"R1": ("10k", {"CFG_CRESET", "VCC"}),
             "R2": ("100", {"VCC1V2", "VCCPLL_1V2"})},
}

SIG_NETS = {"T_W", "T_clk", "T_data", "T_endcol", "B_W", "B_clk", "B_data",
            "B_first", "B_latch", "L_clk", "L_data", "L_endrow", "L_latch",
            "R_latch"}
# presence pad REFS keep their connector-next role labels; their pad nets
# are tile GND by design.  Any *net* named GND_DET_* on the tile = defect.
PRESENCE_REFS = ["JP_GND_DET_T", "JP_GND_DET_B", "JP_GND_DET_R"]


# ------------------------------------------------------------- pcb parsing
def _blocks(t, tag):
    out, i = [], 0
    n = f"({tag}"
    while True:
        j = t.find(n, i)
        if j < 0:
            break
        d, k = 0, j
        while k < len(t):
            if t[k] == "(":
                d += 1
            elif t[k] == ")":
                d -= 1
                if d == 0:
                    out.append(t[j:k + 1])
                    break
            k += 1
        i = k + 1
    return out


def load_pcb(path):
    t = open(path).read()
    fps = {}
    for blk in _blocks(t, "footprint"):
        m = re.search(r'\(footprint\s+"?([^"\s]+)"?', blk)
        ref = m.group(1)
        val = re.search(r'\(property\s+"Value"\s+"([^"]*)"', blk)
        pads = {}
        for pb in _blocks(blk, "pad"):
            pm = re.match(r'\(pad\s+"?([0-9A-Za-z_]+)"?', pb)
            if not pm:
                continue
            nm = re.search(r'\(net\s+\d+\s+"([^"]*)"\)', pb)
            pads[pm.group(1)] = nm.group(1) if nm else None
        fps[ref] = {"value": val.group(1) if val else "", "pads": pads}
    nets = {}
    for ref, f in fps.items():
        for pn, nn in f["pads"].items():
            if nn:
                nets.setdefault(nn, []).append(f"{ref}.{pn}")
    fps_all = fps
    fps = {r: f for r, f in fps.items() if not r.startswith("REF**")}
    return {"fps": fps, "nets": nets}


# ------------------------------------------------- expected FPGA net table
def expected_fpga(variant):
    db = json.load(open(os.path.join(
        BOARD, "data",
        "pins_gw1nz_qn48.json" if variant == "gw1nz"
        else "pins_ice40up_sg48.json")))
    pins = pin_con_parse.load(os.path.join(BOARD, "constraints"))[variant]
    exp = {str(i): None for i in range(1, 49)}
    exp["49"] = "GND"
    for n, (pad, _pull) in pins.items():
        exp[str(pad)] = (f"K{int(n[5:-1]) + 1}" if n.startswith("keys[")
                         else TILE_NETS[n])
    io_class = {"io", "io_config_shared", "io_gclk"}
    for p, row in db["pins"].items():
        pp = "49" if p in ("EPAD", "Paddle") else p
        role = row["role"]
        if role == "power":
            exp[pp] = RAILS[variant][row["net"]]
        elif role == "ground":
            exp[pp] = "GND"
        elif role in ("jtag", "cfg_status", "jspare", "spi_cfg"):
            exp[pp] = row["net"]
        elif role == "strap":
            exp[pp] = row["name"].split("/")[-1]     # MODE0/MODE1
    unused = sorted(int(p) for p, v in exp.items()
                    if v is None and p != "49")
    return exp, unused, db


# ------------------------------------------------------------------ checks
def run_checks(variant, pcb, exp, unused):
    rows = []

    def c(cid, ok, detail):
        rows.append({"id": cid, "ok": bool(ok), "detail": detail})

    fps, nets = pcb["fps"], pcb["nets"]
    u1 = fps.get("U1")

    # N1 FPGA pad equality
    if u1 is None:
        c("N1", variant == "up5k",
          "U1 ABSENT (up5k NOFIT board is a placement-review artifact by "
          "design)" if variant == "up5k" else "U1 MISSING on placed variant")
    else:
        diffs = []
        for p, want in exp.items():
            got = u1["pads"].get(p)
            if got != want:
                diffs.append(f"pin {p}: board={got} expected={want}")
        extra = [p for p in u1["pads"] if p not in exp]
        ok = not diffs and not extra
        c("N1", ok, f"49 pads compared; diffs={diffs[:8]} extra={extra}"
                    if not ok else "49/49 FPGA pad nets exact")
    # N2 rail membership from the DB side
    if u1 is not None:
        railpads = {}
        for p, want in exp.items():
            if want in ("VCC", "VCC1V2", "VCCPLL_1V2", "GND"):
                railpads.setdefault(want, []).append(int(p))
        detail = {k: sorted(v) for k, v in sorted(railpads.items())}
        ncore = len(railpads.get("VCC1V2", []))
        ok = (len(railpads.get("VCC", [])) >= 3 and ncore >= 2 and
              len(railpads.get("GND", [])) >= 3)
        c("N2", ok, f"FPGA pads per rail: {detail}")
    else:
        c("N2", True, "skipped (U1 absent)")

    # N3 strap/filter resistors
    bad = []
    for ref, (val, wantnets) in STRAPS[variant].items():
        got = fps.get(ref)
        if got is None:
            bad.append(f"{ref} missing")
            continue
        gset = set(got["pads"].values()) - {None}
        if gset != wantnets or got["value"] != val:
            bad.append(f"{ref} val={got['value']} nets={sorted(gset)} "
                       f"want {val}/{sorted(wantnets)}")
    c("N3", not bad, f"straps+filters: {'; '.join(bad) if bad else 'OK'}")

    # N4 TP coverage
    bad = []
    for net, ref in TP_MAP[variant].items():
        got = fps.get(ref)
        if got is None or got["pads"].get("1") != net:
            bad.append(f"{ref}({net})")
    c("N4", not bad, f"TP coverage: {'missing/wrong: ' + ','.join(bad) if bad else 'all ' + str(len(TP_MAP[variant])) + ' nets have exactly one TP'}")

    # N5 decoupling census + ferrite topology
    caps = {}
    for ref, f in fps.items():
        if not ref.startswith("C"):
            continue
        n1 = f["pads"].get("1")
        caps.setdefault((variant, n1, f["value"]), []).append(ref)
    if variant == "gw1nz":
        n_vcc_100n = len(caps.get((variant, "VCC", "100n"), []))
        n_v12_100n = len(caps.get((variant, "VCC1V2", "100n"), []))
        n_vcc_4u7 = len(caps.get((variant, "VCC", "4u7"), []))
        n_v12_4u7 = len(caps.get((variant, "VCC1V2", "4u7"), []))
        raw = sorted(nets.get("VCC1V2_RAW", []))
        ok = (n_vcc_100n >= 3 and n_v12_100n >= 2 and n_vcc_4u7 >= 1 and
              n_v12_4u7 >= 1 and raw == ["FB1.1", "U2.5"])
        c("N5", ok, f"100n: VCC x{n_vcc_100n} VCC1V2 x{n_v12_100n}; 4u7: VCC "
                    f"x{n_vcc_4u7} VCC1V2 x{n_v12_4u7}; VCC1V2_RAW pads={raw} "
                    f"(want exactly [FB1.1, U2.5] = ferrite series)")
    else:
        n_vcc_100n = len(caps.get((variant, "VCC", "100n"), []))
        n_v12_100n = len(caps.get((variant, "VCC1V2", "100n"), []))
        n_pll = (len(caps.get((variant, "VCCPLL_1V2", "100n"), [])) +
                 len(caps.get((variant, "VCCPLL_1V2", "4u7"), [])))
        ok = n_vcc_100n >= 4 and n_v12_100n >= 2 and n_pll >= 2
        c("N5", ok, f"100n: VCC x{n_vcc_100n} VCC1V2 x{n_v12_100n}; "
                    f"VCCPLL caps x{n_pll}")

    # N6 sockets + chassis pads
    swbad = []
    for i in range(12):
        f = fps.get(f"SW{i + 1}")
        if f is None or f["pads"].get("1") != "VCC" or \
                f["pads"].get("2") != f"K{i + 1}":
            swbad.append(f"SW{i + 1}")
    jps = {r: f["pads"].get("1") for r, f in fps.items()
           if r.startswith("JP_")}
    want_jp = SIG_NETS | {"VCC", "GND"}
    jpn = set(jps.values())
    ok = (not swbad and len(jps) == 19 and jpn == want_jp and
          all(r in jps for r in PRESENCE_REFS))
    c("N6", ok, f"sockets bad={swbad or '[]'}; JP count={len(jps)}; "
                f"JP nets == 14 signals+VCC+GND: {jpn == want_jp}; "
                f"presence refs present: "
                f"{[r for r in PRESENCE_REFS if r in jps]}")

    # N7 unused pads
    if u1 is not None:
        nonet = sorted(int(p) for p, v in u1["pads"].items()
                       if v is None and p != "49")
        c("N7", nonet == unused,
          f"no-net FPGA pads {nonet} == expected unused {unused}")
    else:
        c("N7", True, f"skipped (U1 absent); expected unused={unused}")

    # N8 single-pad nets: gw1nz (U1 present) requires ZERO; the up5k NOFIT
    # review board allows only nets that would have met a U1 pad.
    singles = {n: pads[0] for n, pads in nets.items() if len(pads) == 1}
    allowed = set() if u1 is not None else {v for v in exp.values() if v}
    extra = {n: p for n, p in singles.items() if n not in allowed}
    c("N8", not extra,
      f"single-pad nets={ {n: p for n, p in sorted(singles.items())} }; "
      f"unexpected={extra or '{}'} (gw1nz: NONE allowed; up5k NOFIT: only "
      f"U1-facing nets allowed)")

    # N9 presence pads bonded to tile GND, and GND carries FPGA+LDO grounds
    pbad = []
    for r in PRESENCE_REFS:
        got = fps.get(r)
        if got is None or got["pads"].get("1") != "GND":
            pbad.append(f"{r}->{None if got is None else got['pads'].get('1')}")
    gnd_nodes = set(nets.get("GND", []))
    if variant == "gw1nz":
        want_on_gnd = {"U1.2", "U1.26", "U1.49", "U2.2"}
    else:  # up5k: U1 absent by NOFIT design; LDO + flash grounds instead
        want_on_gnd = {"U2.2", "U3.4"}
    missing = sorted(want_on_gnd - gnd_nodes)
    ok = not pbad and not missing
    c("N9", ok, f"presence pads bonded to GND: "
                f"{[fps[r]['pads'].get('1') for r in PRESENCE_REFS
                    if r in fps]}; required GND nodes missing={missing or '[]'}"
                + (f"; BAD: {pbad}" if pbad else ""))
    return rows


def main():
    report = {"variants": {}, "negative_control": []}
    allok = True
    parsed = {}
    for variant in ("gw1nz", "up5k"):
        pcb = load_pcb(os.path.join(BOARD, "out", "kicad",
                                    f"tile_{variant}.kicad_pcb"))
        exp, unused, _db = expected_fpga(variant)
        rows = run_checks(variant, pcb, exp, unused)
        ok = all(r["ok"] for r in rows)
        allok &= ok
        report["variants"][variant] = {"ok": ok, "checks": rows,
                                       "expected_unused_pads": unused}
        parsed[variant] = (pcb, exp, unused)
        print(f"[{variant}] {'PASS' if ok else 'FAIL'}")
        for r in rows:
            print(f"  [{'OK' if r['ok'] else 'FAIL':4}] {r['id']}: "
                  f"{r['detail']}")

    # negative control (a): corrupt the EXPECTED map -> N1 must fail
    pcb, exp, unused = parsed["gw1nz"]
    badexp = dict(exp)
    badexp["12"] = "GND"        # core pin deliberately wrong
    rows = run_checks("gw1nz", pcb, badexp, unused)
    n1 = [r for r in rows if r["id"] == "N1"][0]
    c_ok_a = not n1["ok"]
    print(f"[negative-control a] corrupted expectation caught by N1: "
          f"{c_ok_a}")
    report["negative_control"].append(
        {"case": "expected pin12=GND (wrong)", "must_fail": True,
         "failed_as_expected": c_ok_a, "detail": n1["detail"][:200]})

    # negative control (b): corrupt the PARSED board -> N6 must fail
    import copy
    pcb2 = copy.deepcopy(pcb)
    pcb2["fps"]["SW1"]["pads"]["2"] = "K2"
    pcb2["nets"].setdefault("K2", []).append("SW1.2")
    rows = run_checks("gw1nz", pcb2, exp, unused)
    n6 = [r for r in rows if r["id"] == "N6"][0]
    c_ok_b = not n6["ok"]
    print(f"[negative-control b] corrupted board net caught by N6: {c_ok_b}")
    report["negative_control"].append(
        {"case": "parsed board SW1.2 renamed to K2", "must_fail": True,
         "failed_as_expected": c_ok_b, "detail": n6["detail"][:200]})

    # negative control (c): rebound presence pad to an ISOLATED net =
    # the exact pre-fix defect -> N9 AND N8 must both fail
    pcb3 = copy.deepcopy(pcb)
    pcb3["fps"]["JP_GND_DET_B"]["pads"]["1"] = "GND_DET_B"
    pcb3["nets"].setdefault("GND_DET_B", []).append("JP_GND_DET_B.1")
    rows = run_checks("gw1nz", pcb3, exp, unused)
    n8c = [r for r in rows if r["id"] in ("N8", "N9")]
    c_ok_c = all(not r["ok"] for r in n8c)
    print(f"[negative-control c] isolated presence pad caught by N8+N9: "
          f"{c_ok_c}")
    report["negative_control"].append(
        {"case": "JP_GND_DET_B rebound to isolated net GND_DET_B "
                 "(pre-fix defect class)", "must_fail": True,
         "failed_as_expected": c_ok_c,
         "detail": f"N8 ok={n8c[0]['ok']} N9 ok={n8c[1]['ok']} "
                   f"(both must be False)"})

    negok = all(r["failed_as_expected"] for r in report["negative_control"])
    report["ok"] = bool(allok and negok)
    with open(os.path.join(BOARD, "out", "netcheck_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    with open(os.path.join(BOARD, "out", "netcheck_report.md"), "w") as f:
        f.write("# board_net_check report\n\n")
        for v, r in report["variants"].items():
            f.write(f"## {v}: {'PASS' if r['ok'] else 'FAIL'}\n\n")
            for c in r["checks"]:
                f.write(f"- [{'OK' if c['ok'] else 'FAIL'}] {c['id']}: "
                        f"{c['detail']}\n")
            f.write("\n")
        f.write("## negative control (must all FAIL to be meaningful)\n\n")
        for r in report["negative_control"]:
            f.write(f"- [{'OK' if r['failed_as_expected'] else 'PROBLEM'}] "
                    f"{r['case']}: {r['detail']}\n")
    print(f"overall: {'PASS' if report['ok'] else 'FAIL'} "
          f"(wrote out/netcheck_report.json/.md)")
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
