#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
# simple-tile 20 MHz timing constraint calculator (rev 2, post-review).
#
# Reads timing.json:  devices = datasheet-extracted values (source+table+conditions,
#   null where the datasheet is silent); assumptions = system/interconnect parameters
#   that are NOT datasheet data and start null.
#
# Verdicts:
#   NECESSARY-ONLY : component-level sum of datasheet numbers. A necessary constraint
#                    the design cannot beat, NOT a 20 MHz system sign-off.
#   UNKNOWN        : at least one assumption/input is null (unmeasured) or a datasheet
#                    cell is missing. Never invent numbers.
#   PROVISIONAL    : CPLD-composed estimate; needs the (closed) ATF1502 fitter STA.
#   FAIL / PASS    : full system bound including measured assumptions (only reachable
#                    via CLI overrides today).
#
# CLI: --set assumptions.route_delays_ns.clock_fwd_hop.value=1.23   (repeatable)
#      --selftest   synthetic zero / nonzero / negative cases
# All times ns; T = 50 ns (20 MHz), half period 25 ns.

import json, os, sys, copy

HERE = os.path.dirname(os.path.abspath(__file__))
DB0 = json.load(open(os.path.join(HERE, "timing.json")))


def set_by_dotted(d, dotted, value):
    keys = dotted.split(".")
    node = d
    for k in keys[:-1]:
        if k not in node:
            raise KeyError(f"unknown key path: {dotted}")
        node = node[k]
    if keys[-1] not in node:
        raise KeyError(f"unknown key path: {dotted}")
    node[keys[-1]] = value


def get_assn(db, name):
    return db["assumptions"]["route_delays_ns"][name]["value"]


def get_ctrl(db, name):
    return db["assumptions"]["controller_ns"][name]["value"]


def fsum(terms):
    """Sum of [name, value]; None if any value null."""
    for _, v in terms:
        if v is None:
            return None
    return sum(v for _, v in terms)


def row(name, terms, budget, kind, note=""):
    """kind: necessary | system | provisional. Budget None => no slack to compute."""
    if kind == "info":
        return (name, None, None, None, "INFO", note)
    comp = fsum(terms) if terms else None
    if budget is None:
        verdict = {"necessary": "NECESSARY-ONLY", "provisional": "PROVISIONAL"}.get(kind, "UNKNOWN")
        if comp is None and kind != "necessary":
            verdict = "UNKNOWN"
        return (name, comp, None, None, verdict, note)
    if comp is None:
        return (name, None, budget, None, "UNKNOWN", note)
    slack = budget - comp
    if kind == "system":
        verdict = "PASS" if slack >= 0 else "FAIL"
    elif kind == "provisional":
        verdict = "PROVISIONAL"
    else:
        verdict = "NECESSARY-ONLY"
    return (name, comp, budget, slack, verdict, note)


def hold_row(name, change_terms, hold_req, note=""):
    h = fsum(change_terms)
    if h is None:
        return (name, None, hold_req, None, "UNKNOWN", note)
    slack = h - hold_req
    return (name, h, hold_req, slack, "PASS" if slack >= 0 else "FAIL", note)


def report(rows):
    w = max(len(r[0]) for r in rows)
    print(f"{'PATH':<{w}} {'ARRIVAL_NS':>10} {'BUDGET_NS':>9} {'SLACK_NS':>8}  VERDICT")
    for name, arr, budget, slack, verdict, note in rows:
        a = f"{arr:10.1f}" if arr is not None else "    UNKNOWN"
        b = f"{budget:9.1f}" if budget is not None else "    -----"
        s = f"{slack:8.1f}" if slack is not None else "  UNKNOWN"
        n = f"  ({note})" if note else ""
        print(f"{name:<{w}} {a} {b} {s}  {verdict}{n}")


def build_rows(db):
    T = db["meta"]["period_ns"]; HP = db["meta"]["half_period_ns"]
    D = db["devices"]
    sr = D["ti_74lvc165a"]["params"]; lv161 = D["ti_74lv161a"]["params"]
    hc161 = D["ti_74hc161"]["params"]
    g08 = D["ti_74lvc2g08"]["params"]; g32 = D["ti_74lvc2g32"]["params"]
    g125 = D["ti_74lvc2g125"]["params"]; g126 = D["ti_74lvc2g126"]["params"]
    g74 = D["ti_74lvc2g74"]["params"]
    gal15 = D["atf22lv10c"]["params"]["g15"]; gal10 = D["atf22lv10c"]["params"]["g10"]
    cpld = D["atf1502asv"]["params"]; fpga = D["lattice_ice40up5k"]["params"]

    cf = get_assn(db, "clock_fwd_hop"); dh = get_assn(db, "data_hop")
    lh = get_assn(db, "latch_hop")
    co = get_assn(db, "ctrl_cable_out"); ci = get_assn(db, "ctrl_cable_in")
    frt = get_assn(db, "fpga_sample_route")
    lpw = get_ctrl(db, "latch_pulse_width"); ldf = get_ctrl(db, "latch_deassert_to_first_clk")

    cq = sr["tpd_cq_max_ns"]; su = sr["tsu_ser_ns"]
    rowsA, rowsB, rowsC, rowsX = [], [], [], []

    # ----- Candidate A -----
    fwdA = g125["tpd_max_ns"]; muxA = max(g125["tpd_max_ns"], g126["tpd_max_ns"])
    baseA = [("fwd", fwdA), ("cq", cq), ("mux", muxA), ("su", su)]
    rowsA.append(row("hop setup, component bound", baseA, T, "necessary",
                     "no interconnect terms"))
    rowsA.append(row("hop setup, SYSTEM", baseA + [("clk_fwd_hop", cf), ("data_hop", dh)],
                     T, "system", "needs measured clock/data hop interconnect"))
    rowsA.append(hold_row("hop hold, component bound",
                          [("f", g125["tpd_min_ns"]), ("c", sr["tpd_cq_min_ns"]),
                           ("m", g125["tpd_min_ns"])], sr["th_ser_ns"],
                          "min corners; FAIL if negative"))
    rowsA.append(hold_row("hop hold, SYSTEM",
                          [("f", g125["tpd_min_ns"]), ("c", sr["tpd_cq_min_ns"]),
                           ("m", g125["tpd_min_ns"]),
                           ("clk_fwd_hop(min est)", cf), ("data_hop(min est)", dh)],
                          sr["th_ser_ns"], "route mins reused from the same assumption"))
    rowsA.append(row("flag: LV161A RCO(cnt) + 2G08 AND + 2G32 OR + 2G74 t_su",
                     [("rco", lv161["tpd_rco_max_ns"]), ("and", g08["tpd_max_ns"]),
                      ("or", g32["tpd_max_ns"]), ("su", g74["tsu_data_ns"])], T,
                     "necessary", "on-tile path, no interconnect in series"))
    rowsA.append(row("flag: HC161 RCO + 2G08 + 2G32 + 2G74 t_su",
                     [("rco", hc161["tpd_rco_max_ns_3v3"]), ("and", g08["tpd_max_ns"]),
                      ("or", g32["tpd_max_ns"]), ("su", g74["tsu_data_ns"])], T,
                     "system", "HC161 has NO 3.3 V column -> unprovable"))
    rowsA.append(row("flag: 165 tpdCQ + 2G08 + 2G32 + 2G74 t_su",
                     [("cq", cq), ("and", g08["tpd_max_ns"]), ("or", g32["tpd_max_ns"]),
                      ("su", g74["tsu_data_ns"])], T, "necessary",
                     "B_data freshness sub-path"))

    # ----- Candidate B -----
    for gname, g in (("LV10C-15", gal15), ("LV10C-10", gal10)):
        baseB = [("fwd", g["tpd_max_ns"]), ("cq", cq), ("ds", g["tpd_max_ns"]), ("su", su)]
        rowsB.append(row(f"hop setup, component bound [{gname}]", baseB, T, "necessary",
                         f"GAL tPD max {g['tpd_max_ns']} @ CL=35pF"))
        rowsB.append(row(f"hop setup, SYSTEM [{gname}]",
                         baseB + [("clk_fwd_hop", cf), ("data_hop", dh)], T, "system"))
        rowsB.append(hold_row(f"hop hold, component bound [{gname}]",
                              [("f", g["tpd_min_ns"]), ("c", sr["tpd_cq_min_ns"]),
                               ("m", g["tpd_min_ns"])], sr["th_ser_ns"]))
        rowsB.append(row(f"BW D: 165 tpdCQ + GAL tS [{gname}]",
                         [("cq", cq), ("ts", g["ts_min_ns"])], T, "necessary",
                         "BDATA pin into the array; tS = input setup"))

    # ----- Candidate C -----
    cqCc = cpld["tcop_max_ns"] + cpld["tod1_max_ns"]
    fwdC = cpld["tpd1_max_ns"]
    for lbl, cq_ in (("tCOP", cpld["tcop_max_ns"]), ("tCOP+tOD1", cqCc)):
        baseC = [("fwd", fwdC), ("cq", cq_), ("ds", cpld["tin_max_ns"]),
                 ("su", cpld["tfsu_min_ns"])]
        rowsC.append(row(f"hop setup, DS-mux composed [{lbl}]", baseC, T, "provisional",
                         "tIN+tFSU model a full DS mux only approximately; needs closed-fitter STA"))
        rowsC.append(row(f"hop setup, SYSTEM [{lbl}]",
                         baseC + [("clk_fwd_hop", cf), ("data_hop", dh)], T, "provisional"))
    rowsC.append(row("BW D: tCOP + tIN + tLAD + tSU(global)",
                     [("co", cpld["tcop_max_ns"]), ("in", cpld["tin_max_ns"]),
                      ("lad", cpld["tlad_max_ns"]), ("su", cpld["tsu_min_ns"])], T,
                     "provisional", "internal composition unverified"))

    # ----- controller return (all candidates) -----
    for lbl, cq_ in (("A/B (165 CQ)", cq), ("C (tCOP)", cpld["tcop_max_ns"]),
                     ("C (tCOP+tOD1)", cqCc)):
        for per, bgt in (("full period", T), ("half period", HP)):
            baseR = [("fpga_tco", fpga["tco_pio_max_ns"]), ("cq", cq_),
                     ("fpga_tsu", fpga["tsu_pio_ns"])]
            rowsX.append(row(f"return setup {per}, component bound {lbl}", baseR, bgt,
                             "necessary", "FPGA launch + tile CQ + FPGA setup only"))
            rowsX.append(row(f"return setup {per}, SYSTEM {lbl}",
                             baseR + [("cable_out", co), ("cable_in", ci),
                                      ("sample_route", frt)], bgt, "system",
                             "needs cable out/in flight and FPGA sampling route"))
    rowsX.append(hold_row("return hold at FPGA, SYSTEM",
                          [("fpga_tco_min", fpga["tco_pio_min_ns"]), ("cq_min", sr["tpd_cq_min_ns"]),
                           ("cable_out(min est)", co), ("cable_in(min est)", ci)],
                          fpga["th_pio_ns"],
                          "FPGA tCO min not published; cables unmeasured -> UNKNOWN"))

    # ----- latch discipline -----
    # (i) local pulse width requirement vs actual controller pulse (unimplemented)
    latch_req = max(sr["tw_shld_low_ns"], gal15["taw_ns"], lv161["tw_ns"])
    rowsX.append(row("latch pulse width, component requirement", [], latch_req, "necessary",
                     f"need pulse >= {latch_req} ns (max of 165 tW {sr['tw_shld_low_ns']}, "
                     f"LV10C tAW {gal15['taw_ns']}, LV161 tW {lv161['tw_ns']})"))
    rowsX.append(("latch pulse width, SYSTEM", lpw, latch_req,
                  (lpw - latch_req) if lpw is not None else None,
                  ("PASS" if lpw >= latch_req else "FAIL") if lpw is not None else "UNKNOWN",
                  "controller at 16 tiles / 20 MHz not implemented; the existing ~1.42 us "
                  "tick belongs to the 350 kHz FSM and does NOT qualify"))

    # (ii) deassert->first-clock recovery at the LAST tile: chains through 16 tiles
    rec_req = max(gal15["tar_ns"], sr["tsu_shld_high_ns"], g74["tsu_clr_inactive_ns"])
    for lbl, per_hop in (("A discrete latch fwd=2G32", g32["tpd_max_ns"]),
                         ("B GAL latch fwd=tPD", gal15["tpd_max_ns"]),
                         ("C CPLD latch fwd=tPD1 (provisional)", cpld["tpd1_max_ns"])):
        agg = 16 * per_hop
        rowsX.append(row(f"latch deassert fwd-chain aggregate {lbl}",
                         [("16x_fwd", agg)], None, "necessary",
                         f"16 x {per_hop} = {agg} ns device-only; interconnect extra"))
        rowsX.append(row(f"latch deassert->1st clock at last tile, SYSTEM {lbl}",
                         [("16x_fwd", agg),
                          ("16x_latch_hop", 16 * lh if lh is not None else None),
                          ("recovery", rec_req)],
                         ldf, "system",
                         f"recovery need >= {rec_req} ns incl.; budget = controller gap"))
    # (iii) first bit at the controller
    rowsX.append(row("first bit at controller, component bound",
                     [("load_out", sr["tpd_load_out_max_ns"])], None, "necessary",
                     f"165 SH/LD->QH max {sr['tpd_load_out_max_ns']} ns from latch assertion "
                     "reaching the first tile; aggregate latch path + capacitive recovery "
                     "NOT included"))
    rowsX.append(row("first bit at controller, SYSTEM",
                     [("load_out", sr["tpd_load_out_max_ns"]), ("cable_in", ci),
                      ("sample_route", frt)], None, "system",
                     "conditional: full latch path / line capacitance recovery unmeasured"))

    # ----- 16-tile clock/latch chain: OPEN, not absorbed -----
    for lbl, per_hop in (("A", fwdA), ("B LV10C-15", gal15["tpd_max_ns"]),
                         ("C", cpld["tpd1_max_ns"])):
        agg = fsum([("x", per_hop)]) * 16
        rowsX.append(row(f"clock fwd-chain aggregate {lbl}", [("16x", agg)], None,
                         "necessary",
                         f"16 x {per_hop} = {agg} ns. PER-HOP slack analysis did NOT prove "
                         "system behavior for chained phase; sample-before-clock absorption "
                         "claim REMOVED - open: inter-tile phase/clock-chain checks"))
    return {"A": rowsA, "B": rowsB, "C": rowsC, "X": rowsX}


def print_all(res):
    print("== Candidate A: optimized discrete ==");    report(res["A"]); print()
    print("== Candidate B: ATF22LV10C + 2x LVC165A =="); report(res["B"]); print()
    print("== Candidate C: ATF1502ASV full tile ==");    report(res["C"]); print()
    print("== Cross-cutting (controller, latch, chain) =="); report(res["X"]); print()
    print("NECESSARY-ONLY = component-level datasheet bound, not a system sign-off.")
    print("UNKNOWN = a null assumption/datasheet cell blocks the number (fill via --set).")
    print("PROVISIONAL = CPLD composed estimate pending closed-fitter STA.")


def flatten_system_rows(res):
    out = {}
    for cand, rows in res.items():
        for name, arr, b, s, v, n in rows:
            out[(cand, name)] = (arr, s, v)
    return out


def selftest():
    ok = True
    def check(cond, msg):
        nonlocal ok
        print(("SELFTEST-PASS " if cond else "SELFTEST-FAIL ") + msg)
        ok = ok and cond

    base = build_rows(copy.deepcopy(DB0))
    flat = flatten_system_rows(base)
    check(flat[("A", "hop setup, SYSTEM")][2] == "UNKNOWN",
          "default: system hop setup is UNKNOWN (null assumptions)")
    check(flat[("A", "hop setup, component bound")][2] == "NECESSARY-ONLY",
          "default: component bound labeled NECESSARY-ONLY")
    check(any(v[2] == "PROVISIONAL" for v in flat.values()),
          "default: CPLD composed rows are PROVISIONAL (never PASS)")

    # zero fills: system == component bound everywhere both exist
    dbz = copy.deepcopy(DB0)
    for grp in ("route_delays_ns", "controller_ns"):
        for k in dbz["assumptions"][grp]:
            dbz["assumptions"][grp][k]["value"] = 0.0
    fz = flatten_system_rows(build_rows(dbz))
    compA = flat[("A", "hop setup, component bound")][0]
    sysA0 = fz[("A", "hop setup, SYSTEM")][0]
    check(abs(sysA0 - compA) < 1e-9,
          f"zero fills: system hop ({sysA0}) == component bound ({compA}), verdict {fz[('A','hop setup, SYSTEM')][2]}")

    # nonzero fills: system = component + 2.0 (two route terms in the hop path)
    dbn = copy.deepcopy(DB0)
    for k in dbn["assumptions"]["route_delays_ns"]:
        dbn["assumptions"]["route_delays_ns"][k]["value"] = 1.0
    fn = flatten_system_rows(build_rows(dbn))
    sysA1 = fn[("A", "hop setup, SYSTEM")][0]
    check(abs(sysA1 - (compA + 2.0)) < 1e-9,
          f"nonzero fills: system hop {sysA1} == component {compA} + 2.0")

    # negative case: huge route delays -> FAIL
    dbf = copy.deepcopy(DB0)
    for k in dbf["assumptions"]["route_delays_ns"]:
        dbf["assumptions"]["route_delays_ns"][k]["value"] = 100.0
    ff = flatten_system_rows(build_rows(dbf))
    check(ff[("A", "hop setup, SYSTEM")][2] == "FAIL",
          f"negative case: 100 ns route terms -> system hop verdict {ff[('A','hop setup, SYSTEM')][2]} slack {ff[('A','hop setup, SYSTEM')][1]}")
    # hold negative: force a hold violation synthetically by overriding th? hold uses
    # component mins; emulate via --set-free check on the comparator instead:
    r = hold_row("synthetic hold", [("a", 0.1)], 0.5)
    check(r[4] == "FAIL", f"hold helper: 0.1 ns change vs 0.5 ns hold -> {r[4]} (was UNKNOWN bug)")
    return ok


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(0 if selftest() else 1)
    db = copy.deepcopy(DB0)
    i = 0
    while i < len(args):
        if args[i] == "--set" and i + 1 < len(args):
            k, v = args[i + 1].split("=", 1)
            set_by_dotted(db, k, float(v)); i += 2
        elif args[i].startswith("--set="):
            k, v = args[i][6:].split("=", 1)
            set_by_dotted(db, k, float(v)); i += 1
        else:
            i += 1
    print_all(build_rows(db))


if __name__ == "__main__":
    main()
