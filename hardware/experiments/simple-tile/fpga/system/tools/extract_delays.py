#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# Extract applicable FITTED (post-route) interior delays from the existing
# fpga/synth nextpnr logs / fitted netlist JSON into a machine-readable table.
#
# Scope + honesty rules:
#   * Only "as-reported" numbers are extracted; each entry records source
#     file + line pattern + sha256. No interpolation, no invention.
#   * nextpnr-himbaechel / icetime report MAX-analysis only: there is NO
#     min-delay analysis, NO pad/input external delay, NO board interconnect
#     here. Everything not present is emitted as "unknown": true so the
#     downstream corners must declare SYNTHETIC values for it.
#   * The pre-route estimates (nextpnr prints them before routing) are
#     recorded separately and are NOT used as fitted anchors.
#
# Run from the repository root or anywhere:
#   python3 hardware/experiments/simple-tile/fpga/system/tools/extract_delays.py
# Output: results/interior_delays.json next to this script's ../results.

import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SYS = os.path.dirname(HERE)                       # fpga/system
FPGA = os.path.dirname(SYS)                       # fpga/
LOGS = os.path.join(FPGA, "synth", "results", "logs")
BUILD = os.path.join(FPGA, "synth", "results", "build")
OUT = os.path.join(SYS, "results", "interior_delays.json")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_nextpnr(path):
    """Return dict with pre/post route Fmax per clock, max-delay cross paths,
    and the post-route critical-path stage breakdown."""
    txt = open(path).read().splitlines()
    clocks = {}
    cur_clock = None
    clk2q = None
    for i, ln in enumerate(txt):
        m = re.search(r"clk-to-q\s+([0-9.]+)\s+([0-9.]+)", ln)
        if m and cur_clock and clk2q is None:
            clk2q = float(m.group(1))
        m = re.search(r"Max frequency for clock '([^']+)': ([0-9.]+) MHz", ln)
        if m:
            clk = m.group(1)
            clocks.setdefault(clk, []).append(float(m.group(2)))
        m = re.search(r"Max delay (.*?): ([0-9.]+) ns", ln)
        if m:
            clocks.setdefault("__paths__", []).append(
                {"path": m.group(1).strip(), "max_delay_ns": float(m.group(2))})
        m = re.search(r"Critical path report for clock '([^']+)'", ln)
        if m:
            cur_clock = m.group(1)
        if cur_clock and ln.startswith("Info: ") and "ns logic" in ln and "routing" in ln:
            m2 = re.search(r"([0-9.]+) ns logic, ([0-9.]+) ns routing", ln)
            if m2:
                clocks.setdefault("__crit__", {})[cur_clock] = {
                    "logic_ns": float(m2.group(1)),
                    "routing_ns": float(m2.group(2)),
                }
            cur_clock = None
    out = {"clocks": {}}
    for clk, vals in clocks.items() if isinstance(clocks, dict) else []:
        pass
    for clk, vals in ((k, v) for k, v in clocks.items() if k not in ("__paths__", "__crit__")):
        out["clocks"][clk] = {
            "fmax_preroute_mhz": vals[0] if vals else None,
            "fmax_postroute_mhz": vals[-1] if vals else None,
        }
    paths = clocks.get("__paths__", [])
    # post-route = last occurrence of each path class, pre-route = first
    by_path = {}
    for p in paths:
        by_path.setdefault(p["path"], []).append(p["max_delay_ns"])
    out["cross_paths"] = {
        k: {"preroute_ns": v[0], "postroute_ns": v[-1]} for k, v in by_path.items()
    }
    out["crit"] = clocks.get("__crit__", {})
    out["crit_clk2q_ns"] = clk2q
    return out


def parse_icetime(path):
    txt = open(path).read().splitlines() if os.path.exists(path) else []
    for ln in txt:
        m = re.search(r"Timing estimate: ([0-9.]+) ns \(([0-9.]+) MHz\)", ln)
        if m:
            return {"period_ns": float(m.group(1)), "fmax_mhz": float(m.group(2))}
    return None


def cell_census(path):
    d = json.load(open(path))
    types = {}
    for mod in d.get("modules", {}).values():
        for cell in mod.get("cells", {}).values():
            t = cell.get("type", "?")
            types[t] = types.get(t, 0) + 1
    return types


def main():
    res = {
        "schema": "fpga-system/interior_delays/v1",
        "provenance_note": (
            "Extracted verbatim from existing fpga/synth artifacts by "
            "tools/extract_delays.py; every value carries its source file + "
            "sha256. These are FPGA-INTERIOR fitted numbers from nextpnr "
            "max-analysis / icetime only. Absent quantities (min delays, pad "
            "delays, interconnect, external recovery/metastability windows) "
            "are emitted as unknown=true and must come from SYNTHETIC corner "
            "config - never from here."),
        "sources": {},
        "gw1nz_fall": {},
        "gw1nz_track": {},
        "up5k_fall": {},
        "lp8k_fall": {},
        "cell_census": {},
    }

    for tag in ("gw1nz_fall", "gw1nz_track"):
        log = os.path.join(LOGS, f"{tag}_nextpnr.log")
        res["sources"][f"{tag}_nextpnr.log"] = sha256(log)
        res[tag]["nextpnr"] = parse_nextpnr(log)

    for tag in ("up5k_fall", "lp8k_fall"):
        log = os.path.join(LOGS, f"{tag}_nextpnr.log")
        ice = os.path.join(LOGS, f"{tag}_icetime.log")
        res["sources"][f"{tag}_nextpnr.log"] = sha256(log)
        res[tag]["nextpnr"] = parse_nextpnr(log)
        if os.path.exists(ice):
            res["sources"][f"{tag}_icetime.log"] = sha256(ice)
            res[tag]["icetime"] = parse_icetime(ice)

    pnr = os.path.join(BUILD, "gw1nz_fall_pnr.json")
    res["sources"]["gw1nz_fall_pnr.json"] = sha256(pnr)
    res["cell_census"]["gw1nz_fall"] = cell_census(pnr)

    # Distilled anchors used by the timing package (max-analysis, fitted):
    g = res["gw1nz_fall"]["nextpnr"]
    clk = None
    for name in g["clocks"]:
        if "b_clk" in name:
            clk = name
    xdom = None
    for pth, v in g["cross_paths"].items():
        if pth.startswith("negedge") and "posedge" in pth:
            xdom = v["postroute_ns"]
    crit = g["crit"].get(clk, {})
    res["anchors"] = {
        "fit_clk2q_ns": g.get("crit_clk2q_ns"),
        "fit_crit_logic_ns": crit.get("logic_ns"),
        "fit_crit_routing_ns": crit.get("routing_ns"),
        "fit_crit_total_ns": (
            round(crit["logic_ns"] + crit["routing_ns"], 2) if crit else None),
        "fit_xdom_neglatch_posclk_ns": xdom,
        "fit_fmax_shift_clk_mhz": g["clocks"].get(clk, {}).get("fmax_postroute_mhz"),
        "gw1nz_track_xdom_posysclk_posclk_ns": (
            res["gw1nz_track"]["nextpnr"]["cross_paths"]
            .get("posedge sysclk -> posedge u_tile.b_clk", {})
            .get("postroute_ns")),
        "min_delay_analysis": {"unknown": True},
        "pad_input_delay_ns": {"unknown": True},
        "pad_output_delay_ns": {"unknown": True},
        "tbuf_enable_disable_ns": {"unknown": True},
        "board_interconnect_ns": {"unknown": True},
        "ff_recovery_window_ns": {"unknown": True},
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, sort_keys=True)
        f.write("\n")

    a = res["anchors"]
    print("EXTRACT-OK gw1nz_fall: fmax_postroute=%s MHz xdom=%s ns "
          "crit=%s ns  -> %s"
          % (a["fit_fmax_shift_clk_mhz"], a["fit_xdom_neglatch_posclk_ns"],
             a["fit_crit_total_ns"], os.path.relpath(OUT)))
    missing = [k for k, v in a.items()
               if not isinstance(v, dict) and v is None]
    if missing:
        print("EXTRACT-WARN missing anchors: %s" % ",".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
