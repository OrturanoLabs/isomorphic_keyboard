#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# Report generator for fpga/system (host python3, stdlib only).
#
# Reads results/summary.txt, results/sweeps.txt, the SYSSUMMARY/TMARK lines
# of the run logs, plus cfg/corners.json, cfg/sources.json and
# results/interior_delays.json, and emits:
#   results/machine.json - machine-readable results/assumptions/constraints
#   results/report.md    - human-readable report with source links + commands
#
# Run from fpga/system:  python3 results/make_report.py

import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))      # results/
SYS = os.path.dirname(HERE)                            # fpga/system/


def read(path):
    with open(path) as f:
        return f.read()


def main():
    summary = read(os.path.join(HERE, "summary.txt"))
    corners = json.load(open(os.path.join(SYS, "cfg", "corners.json")))
    sources = json.load(open(os.path.join(SYS, "cfg", "sources.json")))
    idel = json.load(open(os.path.join(HERE, "interior_delays.json")))
    env = {}
    try:
        for ln in read(os.path.join(HERE, "env.log")).splitlines():
            if ":" in ln:
                k, v = ln.split(":", 1)
                env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass

    verdict = "FPGA-SYSTEM PASS" if "FPGA-SYSTEM PASS" in summary else \
        "FPGA-SYSTEM FAILED"
    m = re.search(r"runs passed: (\d+), failed: (\d+)", summary)
    npass, nfail = (int(m.group(1)), int(m.group(2))) if m else (0, 0)

    runs = []
    for ln in summary.splitlines():
        mp = re.match(r"PASS  (\S+) \(fails as designed: rc=\d+ token=(\S+)\)", ln)
        if mp:
            runs.append({"name": mp.group(1), "class": "negative",
                         "result": "pass", "failed_token": mp.group(2)})
            continue
        mp = re.match(r"PASS  (\S+)", ln)
        if mp:
            runs.append({"name": mp.group(1),
                         "class": "unit" if mp.group(1).startswith("u_") else "positive",
                         "result": "pass"})
            continue
        mp = re.match(r"(FAIL|ERROR)  (\S+)", ln)
        if mp:
            runs.append({"name": mp.group(2), "class": "unknown",
                         "result": "fail"})

    # arrival min/max per passing chain run (from SYSSUMMARY lines in logs)
    arrivals = {}
    for r in runs:
        lg = os.path.join(HERE, r["name"] + ".log")
        if not os.path.exists(lg):
            continue
        for mm in re.finditer(
                r"SYSSUMMARY (\S+) arrival_min_ns=(\d+) arrival_max_ns=(\d+)",
                read(lg)):
            arrivals[mm.group(1)] = {"min_ns": int(mm.group(2)),
                                     "max_ns": int(mm.group(3))}

    # W-phase exposure sample: last WPHASE per column of the fit/max runs
    wphase = {}
    for name in ("pos_n2x4_fit", "pos_n2x4_max", "pos_n16x4_fit",
                 "pos_n16x4_max", "pos_n1x16_fit", "pos_g4x4_fit"):
        lg = os.path.join(HERE, name + ".log")
        if not os.path.exists(lg):
            continue
        for mm in re.finditer(
                r"TMARK WPHASE col(\d+) .*since_src_rise_ns=(\d+) phase='(\d)'",
                read(lg)):
            wphase.setdefault(name, {})[mm.group(1)] = {
                "since_src_rise_ns": int(mm.group(2)),
                "local_phase": "high" if mm.group(3) == "1" else "low"}

    # sweep table
    sweeps = []
    swpath = os.path.join(HERE, "sweeps.txt")
    if os.path.exists(swpath):
        for ln in read(swpath).splitlines():
            mm = re.match(
                r"SWEEP N=(\d+) H=(\d+) corner=(\S+) guard_min_ns=(\S+) "
                r"lead_min_ns=(\S+) lead_max_ns=(\S+) high_min_ns=(\S+) "
                r"wlow_scale_max_ok_pct=(\S+)", ln)
            if mm:
                sweeps.append({
                    "N": int(mm.group(1)), "H": int(mm.group(2)),
                    "corner": mm.group(3),
                    "guard_min_ns": mm.group(4), "lead_min_ns": mm.group(5),
                    "lead_max_ns": mm.group(6), "high_min_ns": mm.group(7),
                    "wlow_scale_max_ok_pct": mm.group(8)})

    # track contract tally
    track = {}
    for lg in glob.glob(os.path.join(HERE, "u_track_*.log")):
        txt = read(lg)
        mm = re.search(r"TRACK-SUMMARY \S+ stale_in_window=(\d+) captured=(\d+)"
                       r" steps=(\d+)", txt)
        if mm:
            track[os.path.basename(lg)] = {
                "stale_in_window": int(mm.group(1)),
                "captured": int(mm.group(2)), "steps": int(mm.group(3))}

    # ---- derived "actual constraints needed at 20 MHz" block -----------------
    def swval(shape_w, shape_h, corner, key):
        for s in sweeps:
            if (s["N"], s["H"], s["corner"]) == (shape_w, shape_h, corner):
                return s[key]
        return None

    constraints = {
        "applies_to": ("controller driving the chain at 20 MHz, 50 ns period; "
                       "values from the sweep table (synthetic corners) plus "
                       "the fitted xdom anchor; exploration, not sign-off"),
        "guard_latch_deassert_to_first_clock_ns": {
            "4-deep column (any N cols) fit": swval(2, 4, "fit", "guard_min_ns"),
            "4-deep column (any N cols) max": swval(2, 4, "max", "guard_min_ns"),
            "16-deep column fit": swval(1, 16, "fit", "guard_min_ns"),
            "16-deep column max": swval(1, 16, "max", "guard_min_ns"),
            "bound_explanation":
                ("guard - d_hop*(depth-1) >= xdom_req 4.9 ns(fitted 4.86+0.04), "
                 "d_hop = (latcho+hop+padin) - (tbuf_pd+hop+padin) per level; "
                 "the latch-OR forward chain must not lose the race to the "
                 "TBUF clock chain"),
        },
        "sample_lead_window_ns": {
            "fit": [swval(2, 4, "fit", "lead_min_ns"),
                    swval(2, 4, "fit", "lead_max_ns")],
            "max": [swval(2, 4, "max", "lead_min_ns"),
                    swval(2, 4, "max", "lead_max_ns")],
            "min": [swval(2, 4, "min", "lead_min_ns"),
                    swval(2, 4, "min", "lead_max_ns")],
        },
        "clock_high_min_ns_50_duty_class": {
            "fit": swval(2, 4, "fit", "high_min_ns"),
            "max": swval(2, 4, "max", "high_min_ns"),
            "why": ("W-switch containment: the L_clk enable / T_clk release "
                    "must land while the source clock is still high"),
        },
        "w_enable_low_phase_exposure_scale_pct": {
            "fit_safe_through": swval(2, 4, "fit", "wlow_scale_max_ok_pct"),
            "max_safe_through": swval(2, 4, "max", "wlow_scale_max_ok_pct"),
        },
        "fixed": {
            "latch_pulse_width_ns": 200.0,
            "shift_clock": "20 MHz actual at the controller",
            "cross_domain_req_ns": 4.9,
        },
    }

    anchors = idel["anchors"]
    machine = {
        "schema": "fpga-system/results/v3",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict": verdict, "runs_passed": npass, "runs_failed": nfail,
        "environment": env,
        "non_signoff": ("Synthetic corners exploration at 20 MHz; interior "
                        "anchors from nextpnr/icetime post-route max-analysis; "
                        "pad / TBUF / interconnect / recovery windows "
                        "synthetic or unknown; NOT hardware sign-off."),
        "design": {
            "device_lead": corners["device_lead"],
            "snap_mode": corners["snap_mode"],
            "pins_user_io": 26,
            "pin_plan_source": "fpga/docs/pin_budget.md + synth/tile_gw1nz.cst",
            "pin_plan_io_loc_count": sources["pin_budget_check"]["expected_io_loc"],
        },
        "fitted_anchors_gw1nz_fall": {
            k: v for k, v in anchors.items() if not isinstance(v, dict)},
        "unknown_by_default": [k for k, v in anchors.items()
                               if isinstance(v, dict) and v.get("unknown")],
        "corners": {k: v for k, v in corners["delays_ns"].items()
                    if not k.startswith("_")},
        "controller_fixed": corners["controller_fixed"],
        "runs": runs,
        "arrival_ns": arrivals,
        "wphase": wphase,
        "sweeps": sweeps,
        "constraints_at_20mhz": constraints,
        "track_characterisation": track,
        "sources_sha256": sources["files"],
        "reproduce": {
            "extract": "python3 tools/extract_delays.py",
            "guard": "python3 results/check_system_sync.py",
            "sims": "bash run_system.sh   (or: bash run_system.sh quick)",
            "report": "python3 results/make_report.py",
        },
    }
    with open(os.path.join(HERE, "machine.json"), "w") as f:
        json.dump(machine, f, indent=1, sort_keys=False)
        f.write("\n")

    # ---------------------------------------------------------------- report.md
    def swrow(s):
        return ("| {N} | {H} | {corner} | {guard_min_ns} | {lead_min_ns}.."
                "{lead_max_ns} | {high_min_ns} | {wlow_scale_max_ok_pct} |"
                .format(**s))

    lines = []
    lines.append("# fpga/system: timing-aware FPGA-chain validation — report")
    lines.append("")
    lines.append(f"Verdict: **{verdict}** ({npass} passed, {nfail} failed).  ")
    lines.append("Scope: one-FPGA tile (GW1NZ-LV1QN48 lead, `SNAP_MODE=\"fall\"`) "
                 "in the 20 MHz shift-clock chain (up to 16 tiles). **This is "
                 "synthetic-corner exploration, not hardware sign-off.**")
    lines.append("")
    lines.append("## Ground rules that this run enforces")
    lines.append("")
    lines.append("- Golden behaviour: bit-exact vs "
                 "[`tile_reg_pkg`](../../regression/tile_reg_pkg.vhdl) frames "
                 "(2 passes) on N=1/2/16x4, 1x16, 4x4 grids.")
    lines.append("- Tile leaf = UNMODIFIED golden RTL "
                 "[`tile_fpga.vhdl`](../rtl/tile_fpga.vhdl) wrapped by "
                 "[`tile_sys.vhdl`](../vhdl/tile_sys.vhdl) (pad delays, latch-OR "
                 "on separate pads, TBUF Z timings, leaf assertions).")
    lines.append("- Interior delay anchors are FITTED (post-route nextpnr/"
                 "icetime max-analysis), extracted verbatim by "
                 "[`tools/extract_delays.py`](../tools/extract_delays.py) into "
                 "[`interior_delays.json`](interior_delays.json); "
                 "pads/TBUF/interconnect are SYNTHETIC "
                 "([`cfg/corners.json`](../cfg/corners.json)).")
    lines.append("- Drift guard [`results/check_system_sync.py`](check_system_sync.py): "
                 "package==corners, anchors==extraction, reference hashes pinned, "
                 "26 IO_LOC pin plan.")
    lines.append("")
    lines.append("## Fitted interior anchors used (GW1NZ fall, post-route)")
    lines.append("")
    lines.append("| quantity | value | source |")
    lines.append("|---|---|---|")
    lines.append(f"| shift-clk interior Fmax | {anchors['fit_fmax_shift_clk_mhz']} MHz | "
                 "../synth/results/logs/gw1nz_fall_nextpnr.log |")
    lines.append(f"| FF clk-to-q (critical path elem) | {anchors['fit_clk2q_ns']} ns | same |")
    lines.append(f"| critical path total (logic+route) | {anchors['fit_crit_total_ns']} ns | same |")
    lines.append(f"| cross-domain negedge latch -> posedge clk | "
                 f"{anchors['fit_xdom_neglatch_posclk_ns']} ns | same |")
    lines.append(f"| track-mode posedge sysclk -> posedge clk | "
                 f"{anchors['gw1nz_track_xdom_posysclk_posclk_ns']} ns | "
                 "../synth/results/logs/gw1nz_track_nextpnr.log |")
    lines.append("")
    lines.append("Unknown by default (synthetic corners only): "
                 + ", ".join(machine["unknown_by_default"]) + ".")
    lines.append("")
    lines.append("## Measured sweep table (synthetic corners, 20 MHz)")
    lines.append("")
    lines.append("| N cols | H rows | corner | min guard ns | sample lead window ns | "
                 "min clock high ns | W-low max OK scale % |")
    lines.append("|---|---|---|---|---|---|---|")
    for s in sweeps:
        lines.append(swrow(s))
    lines.append("")
    lines.append("## Actual constraints the 20 MHz run needs (synthetic corners)")
    lines.append("")
    g = constraints["guard_latch_deassert_to_first_clock_ns"]
    lw = constraints["sample_lead_window_ns"]
    hm = constraints["clock_high_min_ns_50_duty_class"]
    lines.append(f"- latch deassert -> first shift clock (guard): "
                 f"**>= {g['4-deep column (any N cols) fit']} ns fit / "
                 f"{g['4-deep column (any N cols) max']} ns max** for 4-deep columns "
                 f"(any column count); **>= {g['16-deep column fit']} ns fit / "
                 f"{g['16-deep column max']} ns max** for a 16-high column.")
    lines.append(f"  Bound rule: `guard - d_hop*(depth-1) >= 4.9 ns` (fitted "
                 f"xdom anchor 4.86+0.04); d_hop = latch-forward chain minus "
                 "TBUF clock chain per level (~1.3 fit / 3.0 max ns).")
    lines.append(f"- sample lead window (before each rising edge): "
                 f"**{lw['fit'][0]}..{lw['fit'][1]} ns fit / "
                 f"{lw['max'][0]}..{lw['max'][1]} ns max** "
                 f"(min corner {lw['min'][0]}..{lw['min'][1]}).")
    arr_f = arrivals.get("pos_n1x4_fit", {})
    arr_m = arrivals.get("pos_n1x4_max", {})
    lines.append(f"- clock high phase (W-switch containment): "
                 f"**>= {hm['fit']} ns fit / {hm['max']} ns max** at the 50 ns "
                 f"period; at 3 ns synthetic hop the max corner needs 30 ns.")
    lines.append(f"- returned-data arrival at the controller: measured "
                 f"{arr_f.get('max_ns')}..{arr_m.get('max_ns')} ns (fit..max) "
                 f"after the launch edge at the receiving tile's pin.")
    lines.append("")
    lines.append("## Runs")
    lines.append("")
    lines.append("```")
    for r in runs:
        tok = f" (negative, caught {r['failed_token']})" if r.get("failed_token") else ""
        lines.append(f"{r['result'].upper():6} {r['name']}{tok}")
    lines.append("```")
    lines.append("")
    lines.append("## Reproduce (actual commands)")
    lines.append("")
    lines.append("```sh")
    lines.append("cd hardware/experiments/simple-tile/fpga/system")
    lines.append("python3 tools/extract_delays.py        # -> results/interior_delays.json")
    lines.append("python3 results/check_system_sync.py   # SYNC-PASS drift guard")
    lines.append("bash run_system.sh                     # full matrix (container)")
    lines.append("python3 results/make_report.py         # this report + machine.json")
    lines.append("```")
    lines.append("")
    with open(os.path.join(HERE, "report.md"), "w") as f:
        f.write("\n".join(lines))

    print(f"REPORT-OK {verdict} runs={npass}/{nfail} -> results/machine.json, results/report.md")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
