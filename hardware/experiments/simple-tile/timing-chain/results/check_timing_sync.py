#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Drift guard: every datasheet constant used by the timed models must equal
the single source of truth, logic/timing/timing.json (read-only).

Exits 0 and prints SYNC-PASS only if all mapped cells match; exits 1 on any
mismatch or missing JSON cell (except cells documented as unsolicited:
the 0.0 min bounds for ten/tdis are expressed in the package, not the JSON).

Run: python3 hardware/experiments/simple-tile/timing-chain/results/check_timing_sync.py
"""
import json
import re
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.normpath(os.path.join(HERE, "..", "..", "logic", "timing", "timing.json"))
PKG_PATH = os.path.normpath(os.path.join(HERE, "..", "vhdl", "chain_timing_pkg.vhdl"))

# vhdl constant -> (device, json param)
MAP = {
    "LVC165A_TPD_CQ_MIN_NS":   ("ti_74lvc165a", "tpd_cq_min_ns"),
    "LVC165A_TPD_CQ_MAX_NS":   ("ti_74lvc165a", "tpd_cq_max_ns"),
    "LVC165A_TPD_LOAD_MAX_NS": ("ti_74lvc165a", "tpd_load_out_max_ns"),
    "LVC165A_TSU_SER_NS":      ("ti_74lvc165a", "tsu_ser_ns"),
    "LVC165A_TH_SER_NS":       ("ti_74lvc165a", "th_ser_ns"),
    "LVC165A_TSU_SHLD_NS":     ("ti_74lvc165a", "tsu_shld_high_ns"),
    "LVC165A_TW_SHLD_NS":      ("ti_74lvc165a", "tw_shld_low_ns"),
    "LVC165A_TW_CLK_NS":       ("ti_74lvc165a", "tw_clk_ns"),
    "LV161A_TPD_CQ_MIN_NS":    ("ti_74lv161a", "tpd_cq_min_ns"),
    "LV161A_TPD_CQ_MAX_NS":    ("ti_74lv161a", "tpd_cq_max_ns"),
    "LV161A_TPD_RCO_MIN_NS":   ("ti_74lv161a", "tpd_rco_min_ns"),
    "LV161A_TPD_RCO_MAX_NS":   ("ti_74lv161a", "tpd_rco_max_ns"),
    "LV161A_TPHL_CLR_NS":      ("ti_74lv161a", "tphl_clr_max_ns"),
    "LV161A_TW_NS":            ("ti_74lv161a", "tw_ns"),
    "LVC2G08_TPD_MIN_NS":      ("ti_74lvc2g08", "tpd_min_ns"),
    "LVC2G08_TPD_MAX_NS":      ("ti_74lvc2g08", "tpd_max_ns"),
    "LVC2G32_TPD_MIN_NS":      ("ti_74lvc2g32", "tpd_min_ns"),
    "LVC2G32_TPD_MAX_NS":      ("ti_74lvc2g32", "tpd_max_ns"),
    "LVC2G125_TPD_MIN_NS":     ("ti_74lvc2g125", "tpd_min_ns"),
    "LVC2G125_TPD_MAX_NS":     ("ti_74lvc2g125", "tpd_max_ns"),
    "LVC2G125_TEN_MAX_NS":     ("ti_74lvc2g125", "ten_max_ns"),
    "LVC2G125_TDIS_MAX_NS":    ("ti_74lvc2g125", "tdis_max_ns"),
    "LVC2G126_TPD_MIN_NS":     ("ti_74lvc2g126", "tpd_min_ns"),
    "LVC2G126_TPD_MAX_NS":     ("ti_74lvc2g126", "tpd_max_ns"),
    "LVC2G126_TEN_MAX_NS":     ("ti_74lvc2g126", "ten_max_ns"),
    "LVC2G126_TDIS_MAX_NS":    ("ti_74lvc2g126", "tdis_max_ns"),
    "LVC1G04_TPD_MIN_NS":      ("ti_74lvc1g04", "tpd_min_ns"),
    "LVC1G04_TPD_MAX_NS":      ("ti_74lvc1g04", "tpd_max_ns_cl30_50"),
    "LVC2G74_TPD_CQ_MIN_NS":   ("ti_74lvc2g74", "tpd_cq_min_ns"),
    "LVC2G74_TPD_CQ_MAX_NS":   ("ti_74lvc2g74", "tpd_cq_max_ns"),
    "LVC2G74_TSU_NS":          ("ti_74lvc2g74", "tsu_data_ns"),
    "LVC2G74_TH_NS":           ("ti_74lvc2g74", "th_data_ns"),
    "LVC2G74_TSU_CLR_NS":      ("ti_74lvc2g74", "tsu_clr_inactive_ns"),
    "LVC2G74_TW_CLK_NS":       ("ti_74lvc2g74", "tw_clk_ns"),
}

pkg = {}
for m in re.finditer(r"constant\s+(\w+)\s*:\s*real\s*:=\s*([\d.]+)\s*;",
                     open(PKG_PATH).read()):
    pkg[m.group(1)] = float(m.group(2))

db = json.load(open(JSON_PATH))["devices"]
bad = []
for name, (dev, param) in MAP.items():
    if name not in pkg:
        bad.append(f"{name}: missing from vhdl package")
        continue
    try:
        jval = db[dev]["params"][param]
    except KeyError:
        bad.append(f"{name}: JSON cell {dev}.{param} missing")
        continue
    if jval is None:
        bad.append(f"{name}: JSON {dev}.{param} is null but package has {pkg[name]}")
    elif abs(pkg[name] - float(jval)) > 1e-12:
        bad.append(f"{name}: package {pkg[name]} != JSON {dev}.{param} = {jval}")

if bad:
    print("SYNC-FAIL")
    for b in bad:
        print(" ", b)
    sys.exit(1)
print(f"SYNC-PASS {len(MAP)} constants match {JSON_PATH}")
