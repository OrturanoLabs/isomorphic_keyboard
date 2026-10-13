#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# check_pins.py -- pin-constraint checker for the ATF1502ASV TQFP-44 tile
# candidate. Stdlib only (host python3). Validates
# constraints/tile_cpld_tqfp44.csv against the device capability database
# transcribed from DS20006485A Table 1-6 (dedicated pinouts) and Table 1-7
# (I/O pinouts), plus the design rules of the candidate (JTAG reserved,
# bclk on a global clock pin, tri-state outputs on I/O macrocells, PD pins
# reserved spare, full 44-pin accounting). Exits nonzero on any violation.
#
# Usage: check_pins.py [path/to/constraints.csv]  (default: sibling csv)

import csv, os, sys

# --- Device database, DS20006485A Tables 1-6/1-7 (44-lead TQFP) -------------
# pin -> (kind, block, mc, flags)   kind: io | in | vcc | gnd
MC = {}
def _mcpins(block, pairs):
    for mcno, pin in pairs:
        MC[pin] = ("io", block, mcno)

_mcpins("A", [(1,42),(2,43),(3,44),(4,1),(5,2),(6,3),(7,5),(8,6),
              (9,7),(10,8),(11,10),(12,11),(13,12),(14,13),(15,14),(16,15)])
_mcpins("B", [(17,35),(18,34),(19,33),(20,32),(21,31),(22,30),(23,28),(24,27),
              (25,26),(26,25),(27,23),(28,22),(29,21),(30,20),(31,19),(32,18)])
JTAG = {1:"TDI", 7:"TMS", 26:"TCK", 32:"TDO"}      # dual-user-I/O, Table 1-6
PD   = {5:"PD1", 19:"PD2"}                          # dual-user-I/O, Table 1-6
DEDICATED_IN = {37:"GCLK1", 38:"OE1", 39:"GCLR", 40:"GCLK2/OE2"}
VCC = [9, 17, 29, 41]
GND = [4, 16, 24, 36]
GCLK_PINS = {37:"GCLK1", 40:"GCLK2", 35:"GCLK3"}

def pin_kind(pin):
    if pin in VCC: return "vcc"
    if pin in GND: return "gnd"
    if pin in DEDICATED_IN: return "in"
    if pin in MC: return "io"
    return None

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "tile_cpld_tqfp44.csv")
    rows = []
    with open(path) as f:
        for r in csv.reader(f):
            if not r or r[0].strip().startswith("#"):
                continue
            rows.append([c.strip() for c in r])
    errs, warns = [], []

    seen = {}
    used_io, spare_io, used_ded = set(), set(), set()
    signals = set()
    for r in rows:
        if len(r) < 6:
            errs.append("malformed row: %r" % (r,)); continue
        sig, dr, pin_s, _blk, role, _note = r
        signals.add(sig)
        if sig in seen:
            errs.append("signal %s assigned twice" % sig)
        seen[sig] = pin_s
        if pin_s in ("-", ""):
            if role != "internal":
                errs.append("%s: unpinned signal must have role internal" % sig)
            continue
        try:
            pin = int(pin_s)
        except ValueError:
            errs.append("%s: pin %r not a number" % (sig, pin_s)); continue
        if not (1 <= pin <= 44):
            errs.append("%s: pin %d out of range 1..44" % (sig, pin)); continue
        kind = pin_kind(pin)
        if kind is None:
            errs.append("%s: pin %d does not exist on TQFP-44 per Table 1-6/1-7"
                        % (sig, pin)); continue
        if kind in ("vcc", "gnd"):
            errs.append("%s: pin %d is %s" % (sig, pin, kind.upper())); continue
        if kind == "in":
            if dr != "in":
                errs.append("%s: pin %d (%s) is input-only, cannot be '%s'"
                            % (sig, pin, DEDICATED_IN[pin], dr))
            used_ded.add(pin)
        if kind == "io":
            used_io.add(pin)
            if pin in JTAG:
                errs.append("%s: pin %d (MC%d) is dual-role JTAG %s: reserved "
                            "for ISP, must not carry a logic signal"
                            % (sig, pin, MC[pin][2], JTAG[pin]))
            if pin in PD:
                errs.append("%s: pin %d (MC%d) is power-down pin %s: kept spare "
                            "to preserve the power-down option"
                            % (sig, pin, MC[pin][2], PD[pin]))
            if dr == "out" and sig in ("tclk", "lclk") and kind != "io":
                errs.append("%s: tri-state output must sit on an I/O macrocell" % sig)
        if sig == "bclk" and pin not in GCLK_PINS:
            errs.append("bclk: must use a global clock pin (%s), got pin %d"
                        % (sorted(GCLK_PINS), pin))
        if sig.startswith("buttons["):
            idx = int(sig[8:-1])
            if idx < 0 or idx > 11:
                errs.append("button index out of range: %s" % sig)
            if kind == "io" and MC[pin][1] != "A":
                errs.append("%s: keys are grouped on block A by design; pin %d is block %s"
                            % (sig, pin, MC[pin][1]))

    # --- required signal set (module ports) ---
    need = {"bclk", "endrow", "endcol", "blatch", "rlatch", "tw", "bfirst",
            "tdata", "ldata", "dout", "bw", "latcho", "tclk", "lclk",
            "npl", "ds"} | {"buttons[%d]" % i for i in range(12)}
    missing = sorted(need - signals)
    extra = sorted(signals - need)
    if missing: errs.append("unassigned ports: %s" % missing)
    if extra:   errs.append("unknown signals in csv: %s" % extra)

    # --- full-device accounting ---
    all_io = set(MC)
    jtag = set(JTAG) & all_io
    pd = set(PD) & all_io
    spare_io = sorted(all_io - used_io - jtag - pd)
    free_ded = sorted(set(DEDICATED_IN) - used_ded)
    total = (len(used_io) + len(jtag) + len(pd) + len(spare_io)
             + len(DEDICATED_IN) + len(VCC) + len(GND))

    print("pin accounting (TQFP-44):")
    print("  user I/O macrocells : %2d used, %d reserved JTAG, %d reserved PD, %d spare %s"
          % (len(used_io), len(jtag), len(pd), len(spare_io), spare_io))
    print("  dedicated inputs    : %d used %s, %d unused %s"
          % (len(used_ded), sorted(used_ded), len(free_ded), free_ded))
    print("  power               : VCC %s GND %s" % (VCC, GND))
    print("  reconciled total    : %d (must equal 44)" % total)
    if total != 44:
        errs.append("pin accounting does not reconcile to 44: %d" % total)
    for w in warns:
        print("WARN: %s" % w)
    if errs:
        for e in errs:
            print("ERROR: %s" % e)
        print("PINMAP FAIL (%d errors) -- %s" % (len(errs), path))
        sys.exit(1)
    print("PINMAP PASS: %d constraints (%d pins + %d internal), 0 errors -- %s"
          % (len(rows), len([r for r in rows if r[2] not in ('-', '')]),
             len([r for r in rows if r[2] in ('-', '')]), path))

if __name__ == "__main__":
    main()
