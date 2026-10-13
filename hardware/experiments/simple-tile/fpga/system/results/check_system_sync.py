#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# Drift guard for fpga/system (host python3, stdlib only).
#
# Verifies, and FAILS (rc=1) on any mismatch:
#   1. every constant triplet in vhdl/system_timing_pkg.vhdl equals the
#      corresponding triplet in cfg/corners.json (single source of truth);
#   2. the fitted anchors in results/interior_delays.json match the values
#      the corners claim (crit 3.93 total, xdom 4.86 + 0.04 setup = 4.9 req,
#      clk2q 0.46, fmax 254.84) -- i.e. the extraction has been run and the
#      source logs are the pinned ones;
#   3. the read-only reference hashes (cfg/sources.json) are unchanged --
#      the system model never silently tracks changed inputs;
#   4. the 26-pin plan: synth/tile_gw1nz.cst holds exactly 26 IO_LOCs.
#
# Run from anywhere:  python3 .../fpga/system/results/check_system_sync.py

import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))      # results/
SYS = os.path.dirname(HERE)                            # fpga/system/
FPGA = os.path.dirname(SYS)
ROOT = os.path.abspath(os.path.join(FPGA, "..", "..", "..", ".."))

fails = []
notes = []


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(msg):
    fails.append(msg)
    print("SYNC-FAIL: " + msg)


# ---- 1: timing package vs corners.json --------------------------------------
corners = json.load(open(os.path.join(SYS, "cfg", "corners.json")))
tri = corners["delays_ns"]
pkgpath = os.path.join(SYS, "vhdl", "system_timing_pkg.vhdl")
pkg = open(pkgpath).read()

# map: json triplet key -> (pkg base name, [suffixes]) where triplet order is
# [syn_min (no suffix), fit (_F), syn_max (_X)]
KEYS = ["t_padin", "t_do_int", "t_bw_int", "t_latcho_int", "t_padout",
        "t_tbuf_en", "t_tbuf_dis", "t_tbuf_pd", "t_xdom_req", "t_snap_su",
        "t_snap_hd", "t_clkhi_req", "route_hop"]
SUF = ["", "_F", "_X"]
for key in KEYS:
    cname = key.upper() + "_NS"
    for i, suf in enumerate(SUF):
        const = cname if suf == "" else cname.replace("_NS", suf + "_NS")
        m = re.search(re.escape(const) + r"\s*:\s*real\s*:=\s*([0-9.]+)", pkg)
        if not m:
            fail(f"constant {const} missing in system_timing_pkg.vhdl")
            continue
        v = float(m.group(1))
        want = float(tri[key][i])
        if abs(v - want) > 1e-9:
            fail(f"{const}: pkg {v} != corners.json {want}")
notes.append(f"pkg-vs-corners: {len(KEYS) * 3} constants checked")

# ---- 2: extraction anchors ---------------------------------------------------
idel = json.load(open(os.path.join(HERE, "interior_delays.json")))
a = idel["anchors"]


def chk(name, got, want):
    if got is None or abs(got - want) > 1e-9:
        fail(f"anchor {name}: interior_delays.json {got} != expected {want}")


chk("fit_crit_total_ns", a["fit_crit_total_ns"], 3.93)
chk("fit_xdom_neglatch_posclk_ns", a["fit_xdom_neglatch_posclk_ns"], 4.86)
chk("fit_clk2q_ns", a["fit_clk2q_ns"], 0.46)
chk("fit_fmax_shift_clk_mhz", a["fit_fmax_shift_clk_mhz"], 254.84)
chk("gw1nz_track_xdom_posysclk_posclk_ns",
    a["gw1nz_track_xdom_posysclk_posclk_ns"], 5.59)
# corners claim xdom req = xdom + setup
if abs(tri["t_xdom_req"][2] - (4.86 + 0.04)) > 1e-9:
    fail("t_xdom_req syn_max != fitted 4.86 + 0.04 setup")
notes.append("interior anchors: crit/xdom/clk2q/fmax/track-xdom checked")

# ---- 3: read-only source hashes ----------------------------------------------
src = json.load(open(os.path.join(SYS, "cfg", "sources.json")))
for rel, want in src["files"].items():
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        fail(f"missing reference {rel}")
        continue
    got = sha256(p)
    if got != want:
        fail(f"hash drift {rel}: {got} != pinned {want}")
notes.append(f"source hashes: {len(src['files'])} checked")

# ---- 4: 26-pin plan -----------------------------------------------------------
cst = os.path.join(ROOT, src["pin_budget_check"]["cst"])
n = len(re.findall(r"IO_LOC", open(cst).read()))
if n != src["pin_budget_check"]["expected_io_loc"]:
    fail(f"pin plan: {n} IO_LOC in tile_gw1nz.cst != 26")
notes.append(f"pin plan: {n} IO_LOC == 26")

if fails:
    print("SYNC-FAIL: %d problem(s)" % len(fails))
    sys.exit(1)
print("SYNC-PASS " + "; ".join(notes))
sys.exit(0)
