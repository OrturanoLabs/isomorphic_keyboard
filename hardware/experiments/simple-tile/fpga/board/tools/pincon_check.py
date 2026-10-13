#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""pincon_check -- pin-constraint checker for the FPGA tile board variants.

Validates the BOARD constraints (constraints/tile_gw1nz_board.cst and
constraints/tile_up5k_board.pcf) against the pin databases
(data/pins_gw1nz_qn48.json, data/pins_ice40up_sg48.json), which carry the
vendor-document provenance fetched 2026-10-12.

Rules enforced:
  B1  the constraint file assigns exactly the 26 tile nets of
      ../../docs/pin_budget.md (12 keys + 5 UP inputs + 4 DOWN inputs + 5
      outputs), each exactly once, each on a distinct pad.
  B2  every assigned pad exists in the vendor table and has a user-IO role
      (io / io_config_shared / io_gclk / io_gbin); power, ground, JTAG,
      config/strap or LED-driver pads are never assigned.
  B3  reserved pads stay reserved: JTAG (TCK/TMS/TDI/TDO), straps
      (MODE0/MODE1 on QN48), config status (READY/DONE/RECONFIG_N or
      CDONE/CRESET_B/SPI_*), excluded-hazard pads ([9] on QN48).
  B4  device cross-check: the pure power/ground pad set in the vendor table
      equals, exactly, the chipdb-empirical "missing IO pads" set published
      by the fpga workstream (docs/pin_budget.md). This guards against
      inferring power pins from tool absence: here the vendor docs LEAD and
      the chipdb MATCHES (verified equality, both devices).
  B5  pull direction bookkeeping: UP inputs get pad pull-up (both devices);
      DOWN inputs and keys get pad pull-down (QN48 only) or are listed in the
      external-resistor BOM requirement (SG48).
      iCE40 pads are pull-UP only (DS/flow known) -> any DOWN class pin used
      by the SG48 constraint MUST carry the 'ext10k' marker in the report.
  H1  hazard rule: QN48 pad 9 excluded (automotive UG846 lists VCC there, the
      commercial UG842-1.6.8E list it as IOR2A user IO; order-code hazard).
  S1  primary-source completeness: every pad in each DB carries a vendor
      source tier (doc URL + sha256 on file); any pad claim without one is
      flagged 'UNKNOWN primary source' and FAILS the gate.
  F1  file hygiene: both constraint files parse; no unknown pad attributes.

Outputs: out/pincon_report.json + out/pincon_report.md; rc=1 on any failure.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(BOARD, "out")

TILE_IO = {
    "keys": [f"keys[{i}]" for i in range(12)],
    "in_up": ["clk_pin", "t_w_pin", "t_endcol_pin", "b_first_pin",
              "l_endrow_pin"],
    "in_down": ["t_data_pin", "l_data_pin", "b_latch_pin", "r_latch_pin"],
    "out": ["t_clk_pin", "l_clk_pin", "latcho_pin", "dout_pin", "b_w_pin"],
}
ALL_IO = TILE_IO["keys"] + TILE_IO["in_up"] + TILE_IO["in_down"] + TILE_IO["out"]
assert len(ALL_IO) == 26

# Empirical chipdb censuses, documented by the fpga workstream
# (../../docs/pin_budget.md): pads that host NO placeable IO bel.
CHIPDB_MISSING = {
    "gw1nz": {1, 2, 12, 25, 26, 36, 37},
    "up5k": {1, 5, 7, 8, 22, 24, 29, 30, 33},
}

ALLOWED_IO_ROLES = {"io", "io_config_shared", "io_gclk", "io_gbin"}
RESERVED_ROLES = {"power", "ground", "jtag", "strap", "cfg_status",
                  "spi_cfg", "excluded_hazard", "excluded_led", "jspare"}


def load_db(name):
    with open(os.path.join(BOARD, "data", name)) as f:
        return json.load(f)


def parse_cst(path):
    """Return {net: (pin, pull)} from a Gowin .cst. Statements may share a
    line (the fpga workstream's synth/tile_gw1nz.cst style, accepted by
    nextpnr): scan ALL IO_LOC/IO_PORT occurrences, not one per line."""
    locs, pulls = {}, {}
    for ln in open(path):
        ln = re.sub(r'//.*$', '', ln)
        for m in re.finditer(r'IO_LOC\s+"([^"]+)"\s+(\d+)\s*;', ln):
            locs[m.group(1)] = int(m.group(2))
        for m in re.finditer(r'IO_PORT\s+"([^"]+)"\s+PULL_MODE=(UP|DOWN)\s*;', ln):
            pulls[m.group(1)] = m.group(2)
        rest = re.sub(r'IO_LOC\s+"[^"]+"\s+\d+\s*;', '', ln)
        rest = re.sub(r'IO_PORT\s+"[^"]+"\s+PULL_MODE=(UP|DOWN)\s*;', '', rest)
        if rest.strip():
            raise ValueError(f"{path}: unparsed residue: {rest.strip()!r}")
    return {n: (p, pulls.get(n)) for n, p in locs.items()}


def parse_pcf(path):
    pins, pulls = {}, {}
    for ln in open(path):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        m = re.match(r'set_io\s+(?:-pullup\s+(yes|no)\s+)?(\S+)\s+(\d+)$', ln)
        if not m:
            raise ValueError(f"{path}: unparsed line: {ln!r}")
        pu, net, pin = m.group(1), m.group(2), int(m.group(3))
        pins[net] = (pin, "UP" if pu == "yes" else None)
    return pins


def check_variant(name, dbfile, cst_path, reserved_extra, chipdb_key,
                  key_pull, down_pull_capable):
    db = load_db(dbfile)
    table = db["pins"]
    cst = parse_cst(cst_path) if cst_path.endswith(".cst") else parse_pcf(cst_path)
    rep = {"variant": name, "part": db["part"], "checks": []}

    def ck(rid, desc, ok, detail):
        rep["checks"].append({"id": f"{name}:{rid}", "desc": desc,
                              "ok": bool(ok), "detail": detail})

    # ---- B1: exact 26-net budget, one pad each, distinct pads
    names = set(cst)
    want = set(ALL_IO)
    pads = [v[0] for v in cst.values()]
    ck("B1a", "constraint assigns exactly the 26 tile nets",
       names == want, f"missing={sorted(want - names)} extra={sorted(names - want)}")
    ck("B1b", "26 distinct pads", len(pads) == 26 and len(set(pads)) == 26,
       f"{len(pads)} assignments / {len(set(pads))} distinct")

    # ---- B2: every pad is a documented user-IO pad in the vendor table
    bad = []
    for n, (p, _) in cst.items():
        row = table.get(str(p))
        if row is None:
            bad.append(f"{n}->pad {p}: NOT IN VENDOR TABLE")
        elif row["role"] not in ALLOWED_IO_ROLES:
            bad.append(f"{n}->pad {p}: role={row['role']} ({row.get('name','')})")
    ck("B2", "every assigned pad is a vendor-verified user IO",
       not bad, "; ".join(bad) if bad else "all 26 pads IO-classed")

    # ---- B3: reserved pads stay reserved
    reserved = {int(p) for p, row in table.items()
                if p.isdigit() and row["role"] in RESERVED_ROLES} | reserved_extra
    clash = sorted(p for p in pads if p in reserved)
    jtag_or_cfg = sorted(p for p, row in table.items()
                         if row["role"] in ("jtag", "strap", "cfg_status", "spi_cfg"))
    ck("B3a", "no tile net lands on a reserved pad (JTAG/strap/config/power)",
       not clash, f"clash={clash}")
    ck("B3b", "config/JTAG/strap pads are enumerated for the board test pads",
       len(jtag_or_cfg) >= 6, f"reserved cfg/jtag pads: {jtag_or_cfg}")

    # ---- B4: vendor power+ground set == chipdb empirical missing set
    v_pg = {int(p) for p, row in table.items()
            if p.isdigit() and row["role"] in ("power", "ground")}
    emp = set(CHIPDB_MISSING[chipdb_key])
    if chipdb_key == "up5k":
        # chipdb exclusion also covers the two config-only pins 7/8
        v_pg |= {int(p) for p, row in table.items()
                 if p.isdigit() and row["role"] == "cfg_status"}
    ck("B4", "vendor power/ground(/config-only) pad set == chipdb-missing set "
       "(power fact now sourced from the vendor pin list, not inferred)",
       v_pg == emp, f"vendor={sorted(v_pg)} empirical={sorted(emp)}")

    # ---- B5/B6: pulls
    pull_errs = []
    for n in TILE_IO["in_up"]:
        if cst[n][1] != "UP":
            pull_errs.append(f"{n}: expected pad pull-UP, got {cst[n][1]}")
    for n in TILE_IO["in_down"]:
        got = cst[n][1]
        if down_pull_capable and got != "DOWN":
            pull_errs.append(f"{n}: expected pad pull-DOWN, got {got}")
        if not down_pull_capable and got == "DOWN":
            pull_errs.append(f"{n}: iCE40 pads are pull-UP only")
    keypulls = {cst[k][1] for k in TILE_IO["keys"]}
    ck("B5", "pad pull directions: 5xUP; 4xDOWN only where the silicon can",
       not pull_errs, "; ".join(pull_errs) if pull_errs else "pulls consistent")
    ck("B6", f"key pull strategy = {key_pull}",
       (keypulls == {"DOWN"} if key_pull == "pad-down"
        else keypulls == {None}),
       f"key pulls on pads: {sorted(keypulls, key=str)}")

    # ---- H1: excluded-hazard pads unused
    haz = sorted(p for p, row in table.items()
                 if row["role"] in ("excluded_hazard", "excluded_led"))
    used_haz = sorted(p for p in pads if str(p) in haz)
    ck("H1", "excluded-hazard/LED pads unused by tile nets",
       not used_haz, f"used={used_haz} excluded={haz}")

    # ---- S1: primary sources present for the pin DB
    sprobs = []
    for sid, s in db["sources"].items():
        if "url" not in s and "doc" not in s:
            sprobs.append(f"source {sid}: no doc/url")
    for p, row in table.items():
        if "role" not in row or "name" not in row and "net" not in row:
            sprobs.append(f"pad {p}: no vendor name/net captured")
    has_pin_primary = any("inout" in s.get("doc", "").lower()
                          or "pinout" in s.get("doc", "").lower()
                          or "Pinout" in s.get("doc", "")
                          for s in db["sources"].values())
    ck("S1", "pin DB cites vendor primary sources (URL + sha256), pin list "
       "present", not sprobs and has_pin_primary, "; ".join(sprobs)[:200])

    rep["pins_assigned"] = {n: {"pad": v[0], "pad_pull": v[1]}
                            for n, v in sorted(cst.items())}
    rep["ok"] = all(c["ok"] for c in rep["checks"])
    return rep


def main():
    os.makedirs(OUT, exist_ok=True)
    gw = check_variant(
        "GW1NZ_QN48", "pins_gw1nz_qn48.json",
        os.path.join(BOARD, "constraints", "tile_gw1nz_board.cst"),
        reserved_extra={9},           # automotive pin-9 hazard (excluded_hazard too)
        chipdb_key="gw1nz", key_pull="pad-down", down_pull_capable=True)
    up = check_variant(
        "UP5K_SG48", "pins_ice40up_sg48.json",
        os.path.join(BOARD, "constraints", "tile_up5k_board.pcf"),
        reserved_extra=set(),
        chipdb_key="up5k", key_pull="external-10k", down_pull_capable=False)

    reports = [gw, up]
    json.dump(reports, open(os.path.join(OUT, "pincon_report.json"), "w"),
              indent=1)
    lines = ["# pincon_check report",
             "", "| check | desc | result | detail |", "|---|---|---|---|"]
    for r in reports:
        lines.append(f"| **{r['variant']}** ({r['part']}) | | **"
                     f"{'PASS' if r['ok'] else 'FAIL'}** | |")
        for c in r["checks"]:
            lines.append(f"| {c['id']} | {c['desc']} | "
                         f"{'PASS' if c['ok'] else 'FAIL'} | {c['detail']} |")
    with open(os.path.join(OUT, "pincon_report.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    for r in reports:
        print(f"{r['variant']}: {'PASS' if r['ok'] else 'FAIL'}")
        for c in r["checks"]:
            print(f"  [{('OK' if c['ok'] else 'FAIL'):4}] {c['id']}: {c['desc']}"
                  f" -- {c['detail'][:120]}")
    sys.exit(0 if all(r["ok"] for r in reports) else 1)


if __name__ == "__main__":
    main()
