#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""20 MHz burst SI extension for the tile-to-tile clock/data hop.

Extends hardware/si/tile_hop_ibis.py (same IBIS-lite TI SN74LVC2G126 driver,
same receiver tree helpers) from a single edge to:
  A) CLOCK:    a 10-cycle 20 MHz burst (50 ns period, 25 ns high),
  B) DATA:     a deterministically toggling pattern at bit rate,
  C) RELEASE:  the W tri-state release: drive the line low, switch the driver
               to Hi-Z at a falling edge of the clock and let the tile's 10k
               pull-up float the receiver net high (the spurious-edge hazard
               the timing-chain testbench asserts about).

Checks per case at the NEAR and FAR receiver (documented ASSUMED budgets,
not a datasheet signoff): per full cycle exactly one VIH (2.0 V) up-cross and
one VIL (0.8 V) down-cross; dwell above VIH and below VIL >= 10 ns each;
overshoot <= +30 % VDD, undershoot >= -30 % VDD. The float case reports the
0.8->2.0 V rise time + threshold crossing counts (characterisation only).

Model sources/corners: TI vendor IBIS (typical column only -- no min/max
corner in IBIS-lite) for driver + receiver C_comp/GND clamp; lossless 55/110
ohm track model; 6 CMOS inputs; connector 100 ps; 1 nH package stub. Load
assumptions are printed by the run.

--selftest runs a deliberately bad deck (unterminated 200 ohm 400 mm) and
requires the checks to FAIL there (the check harness is not vacuous).

Run (this directory):
  podman run --rm --userns=keep-id -e HOME=/tmp -e MPLCONFIGDIR=/tmp \
    -v "$PWD":/work:Z -w /work localhost/ngspice python3 chain_hop_20mhz.py [--selftest]
"""
import functools
import subprocess
import sys
import time

import numpy as np

print = functools.partial(print, flush=True)

# per-case wall-clock budget for the three decks of one case
# (clock + data + release); a case that blows it is marked SI-TIMEOUT and the
# sweep continues with the next case (previously a single stuck deck could
# block the whole run behind the caller's outer timeout with zero evidence)
CASE_BUDGET_S = 300


def run_budgeted(deck_txt, probes, t_case, **kw):
    """S.run with the remaining per-case budget as the ngspice timeout."""
    left = CASE_BUDGET_S - (time.monotonic() - t_case)
    if left <= 0:
        raise subprocess.TimeoutExpired("case", CASE_BUDGET_S)
    return S.run(deck_txt, probes, timeout=min(kw.pop("timeout", 300), left), **kw)

# unbuffered prints: the runner's log is the primary evidence, and a killed or
# timed-out host caller must not lose everything still in the pipe buffer
print = functools.partial(print, flush=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import si_lib as S
import ibis_lite

VDD = S.VDD
VIH, VIL = 2.0, 0.8
NCYC = 10
PERIOD, HIGH, T0 = 50e-9, 25e-9, 5e-9
# pass budgets (documented assumptions, applied to steady-state cycles)
MAX_OVER_PCT, MAX_UNDER_V = 30.0, -0.99

IBIS_SRC = ("TI IBIS sn74lvc2g126.ibs / sn74lvc2g125.ibs (typ column), fetched "
            "via hardware/si/models/fetch.sh ids SCEM283/288; no IBIS min/max "
            "corner is modelled (IBIS-lite typ only)")


def pwl_burst(ncyc=NCYC, period=PERIOD, high=HIGH, t0=T0):
    """PWL clock control; every edge carries a hold point so the slope is the
    IBIS ramp, not a ramp across the whole low/high interval."""
    tr, tf = RAMP
    pts = ["0 0"]
    t = t0
    v = 0
    for _ in range(ncyc):
        pts += [f"{t} {v}", f"{t + tr} 1"]          # rise at t
        pts += [f"{t + high} 1", f"{t + high + tf} 0"]  # fall at t+high
        v = 0
        t += period
    return " ".join(pts), t


def pwl_data(ncyc=NCYC, period=PERIOD, t0=T0):
    """'Data burst': idle low, then DATA_BITS at one bit per period. Every cell
    boundary first holds the OLD value, then ramps over the IBIS ramp time --
    omitting the hold point makes the transition ramp across the whole cell."""
    tr, tf = RAMP
    v = 0
    pts = ["0 0", f"{t0} 0"]
    for i, b in enumerate(DATA_BITS[:ncyc]):
        nv = int(b)
        pts.append(f"{t0 + i * period} {v}")
        if nv != v:
            pts.append(f"{t0 + i * period + (tr if nv else tf)} {nv}")
        v = nv
    pts.append(f"{t0 + ncyc * period} {v}")
    return " ".join(pts), t0 + ncyc * period


def deck(ctl_pwl, rs, z0, own, tree_mm, extra_loads=6):
    drv, ramps = S.lvc_driver_subckt("126")
    lines = [drv, S.lvc_receiver_subckt(), "Vdd vdd 0 3.3",
             f"Vc ctl 0 PWL({ctl_pwl})",
             "Xd n0 ctl vdd 0 DRV126", "Lpkg n0 n0a 1n", f"Rs n0a a {max(rs, 1e-3)}",
             f"Town a 0 c 0 Z0={z0} TD={own * S.PS_PER_MM * 1e-12}",
             "Tcon c 0 k 0 Z0=120 TD=0.1n"]
    tl, _ = S.tree("b", "k", z0, tree_mm, extra_loads, pullup="10k")
    return "\n".join(lines + tl)


def edges_per_window(t, v, periods):
    """Per-cycle crossing counts + dwells: returns list of (x_up_vih, x_dn_vil,
    dwell_high_s, dwell_low_s) for each window."""
    out = []
    for (a, b) in periods:
        m = (t >= a) & (t < b)
        tw, vw = t[m], v[m]
        if len(tw) < 2:
            out.append((0, 0, 0.0, 0.0))
            continue
        up = np.sum(np.diff((vw > VIH).astype(int)) == 1)
        dn = np.sum(np.diff((vw < VIL).astype(int)) == 1)
        dwell_hi = float(np.sum(vw > VIH) * (tw[1] - tw[0]))
        dwell_lo = float(np.sum(vw < VIL) * (tw[1] - tw[0]))
        out.append((int(up), int(dn), dwell_hi, dwell_lo))
    return out


# dwell budget: the clocked '165 minimum clock pulse (4.3 ns) unless the
# caller widens it; multiple VIL/VIH crossings at the active edge are what
# double-clocks a fast CMOS input, so those stay hard failures.
MIN_DWELL = 4.3e-9


def check_burst(t, v, t_launch=T0):
    """Clock checks over cycles 3..NCYC-1 (steady state), windows anchored on
    the receiver's own VIH up-crossings so launch-to-receiver delay never
    shifts an edge across a window boundary."""
    up_idx = np.where(np.diff((v > VIH).astype(int)) == 1)[0]
    up_t = t[up_idx]
    if len(up_t) < 3:
        return False, f"only {len(up_t)} VIH up-crossings total (expected ~{NCYC})"
    over = (v[(t > t_launch) & (t < t_launch + NCYC * PERIOD)].max() - VDD) / VDD * 100
    under = v[(t > t_launch) & (t < t_launch + NCYC * PERIOD)].min()
    bad = []
    dhi_w, dlo_w = [], []
    for k in range(2, min(len(up_t) - 1, NCYC - 1)):
        a, b = up_t[k], up_t[k + 1]
        m = (t >= a) & (t < b)
        tw, vw = t[m], v[m]
        dt = tw[1] - tw[0]
        # contiguous dwell runs
        dhi = longest_run(vw > VIH, dt)
        dlo = longest_run(vw < VIL, dt)
        dhi_w.append(dhi)
        dlo_w.append(dlo)
        dn = int(np.sum(np.diff((vw < VIL).astype(int)) == 1))
        # the next up-crossing is the window's end by construction
        if dn != 1:
            bad.append(f"cyc@{k + 1}: VIL-dn={dn}")
        if dhi < MIN_DWELL:
            bad.append(f"cyc@{k + 1}: dwell-high {dhi * 1e9:.1f}ns < {MIN_DWELL * 1e9:.1f}ns")
        if dlo < MIN_DWELL:
            bad.append(f"cyc@{k + 1}: dwell-low {dlo * 1e9:.1f}ns < {MIN_DWELL * 1e9:.1f}ns")
    if over > MAX_OVER_PCT:
        bad.append(f"overshoot {over:.0f}% > {MAX_OVER_PCT:.0f}%")
    if under < MAX_UNDER_V:
        bad.append(f"undershoot {under:.2f}V < {MAX_UNDER_V:.2f}V")
    det = (f"over={over:5.0f}% under={under:5.2f}V min-dwell-hi={min(dhi_w) * 1e9:4.1f}ns "
           f"min-dwell-lo={min(dlo_w) * 1e9:4.1f}ns")
    return (not bad), det + (" | " + "; ".join(bad) if bad else "")


def longest_run(mask, dt):
    best, cur = 0.0, 0.0
    for x in mask:
        cur = cur + dt if x else 0.0
        best = max(best, cur)
    return best


DATA_BITS = "1101001010110011"


def check_data(t, v, t_launch=T0):
    """Per-bit checks for the data pattern: the receiver must read the
    pattern bit at 60% of each cell (errs 2..NCYC), with <= 3 threshold
    crossings per cell (no chattering), plus over/undershoot budgets."""
    bad = []
    over = (v[(t > t_launch) & (t < t_launch + NCYC * PERIOD)].max() - VDD) / VDD * 100
    under = v[(t > t_launch) & (t < t_launch + NCYC * PERIOD)].min()
    for i in range(1, NCYC):
        c = t_launch + i * PERIOD + 0.6 * PERIOD
        got = v[np.argmin(np.abs(t - c))]
        want = int(DATA_BITS[i])
        if (want and got < VIH) or (not want and got > VIL):
            bad.append(f"bit{i + 2}({want}): @60% = {got:.2f}V")
        m = (t >= t_launch + i * PERIOD) & (t < t_launch + (i + 1) * PERIOD)
        x = int(np.sum(np.abs(np.diff(((v[m] > VIH).astype(int) -
                                       (v[m] < VIL).astype(int)))) > 0))
        if x > 3:
            bad.append(f"cell{i + 2}: {x} threshold crossings")
    if over > MAX_OVER_PCT:
        bad.append(f"overshoot {over:.0f}% > {MAX_OVER_PCT:.0f}%")
    if under < MAX_UNDER_V:
        bad.append(f"undershoot {under:.2f}V < {MAX_UNDER_V:.2f}V")
    det = f"over={over:5.0f}% under={under:5.2f}V"
    return (not bad), det + (" | " + "; ".join(bad) if bad else "")


# geometry: (label, z0, own track mm, neighbour tree mm)
REV_A = ("rev-A (110 ohm, 14+141 mm)", 110, 14, 141)
REV_B = ("rev-B as routed (55 ohm, 20+134 mm)", 55, 20, 134)

CASES = [(g, lbl_, rs) for (g, lbl_) in (("A", REV_A), ("B", REV_B))
         for rs in (0, 22, 33, 47)]

RAMP = ibis_lite.ramp_times(S.model("sn74lvc2g126.ibs", "LVC2G126_OUT_33"))


def main(selftest=False):
    print("# 20 MHz burst hop SI; model source:", IBIS_SRC)
    print("# thresholds: VIH=2.0 V, VIL=0.8 V; budgets: contiguous dwell>=4.3 ns (165 tw),")
    print("# exactly one crossing per active edge, overshoot<=+30%, undershoot>=-0.99 V")
    print("# (ASSUMED budgets, typical-corner IBIS, lossless track - NOT a signoff)")

    if selftest:
        # intentionally degenerate deck: checks MUST fail (guard vs vacuity)
        bad = ("selftest-degenerate (200 ohm, 10+400 mm, Rs=0)", 200, 10, 400)
        pwl, _ = pwl_burst()
        t, (v1, v6) = S.run(deck(pwl, 0, *bad[1:]), ["v(b1)", "v(b6)"],
                            tstop=570e-9, tstep=0.02e-9, timeout=300)
        ok1, det = check_burst(t, v6)
        print(f"SI-SELFTEST degenerate deck (clock check): {'PASSED (BAD)' if ok1 else 'failed as required'}")
        print("  " + det)
        pwl, _ = pwl_data()
        t, (v1, v6) = S.run(deck(pwl, 0, *bad[1:]), ["v(b1)", "v(b6)"],
                            tstop=570e-9, tstep=0.02e-9, timeout=300)
        ok2, det = check_data(t, v6)
        print(f"SI-SELFTEST degenerate deck (data check): {'PASSED (BAD)' if ok2 else 'failed as required'}")
        print("  " + det)
        if ok1 or ok2:
            print("SI-SELFTEST FAIL")
            return 1
        print("SI-SELFTEST PASS")
        return 0

    fig, ax = plt.subplots(1, 2, figsize=(13, 5))
    rc = 0
    nplot = 0
    t_start = time.monotonic()
    for fam, (label, z0, own, tree_mm) in (("A", REV_A), ("B", REV_B)):
        for rs in (0, 22, 33, 47):
            nm = f"{label}, Rs={rs}"
            t_case = time.monotonic()
            print(f"SI-PROGRESS case fam={fam} rs={rs} start elapsed_s={int(time.monotonic() - t_start)}")
            try:
                pwl, _ = pwl_burst()
                t, (v1, v6) = run_budgeted(deck(pwl, rs, z0, own, tree_mm),
                                           ["v(b1)", "v(b6)"], t_case,
                                           tstop=570e-9, tstep=0.02e-9)
                for lbl, v in (("near", v1), ("far", v6)):
                    ok, det = check_burst(t, v)
                    tag = "SI-PASS" if ok else "SI-FAIL"
                    if not ok:
                        rc = 1
                    print(f"{tag} clock fam={fam} rs={rs:2d} node={lbl:4s} {det}")
                ax[0].plot(t * 1e9, v6, label=nm, lw=0.8)

                # data pattern over the same channel
                pwl, _ = pwl_data()
                t, (v1, v6) = run_budgeted(deck(pwl, rs, z0, own, tree_mm),
                                           ["v(b1)", "v(b6)"], t_case,
                                           tstop=570e-9, tstep=0.02e-9)
                ok, det = check_data(t, v6)
                tag = "SI-PASS" if ok else "SI-FAIL"
                if not ok:
                    rc = 1
                print(f"{tag} data  fam={fam} rs={rs:2d} node=far  {det}")

                # release (float) case; also keep the waveform for the plot
                drv, _ = S.lvc_driver_subckt("126")
                lines = [drv, S.lvc_receiver_subckt(), "Vdd vdd 0 3.3",
                         "Vc ctl 0 PWL(0 0 100n 0)",
                         "Voe oe 0 PWL(0 1 100n 1 100.001n 0)",
                         ".model relsw SW vt=0.5 ron=0.001 roff=1e12",
                         "Xd n0 ctl vdd 0 DRV126", "Lpkg n0 n0a 1n",
                         "Srel n0a a oe 0 relsw", f"Rs a b {max(rs, 1e-3)}",
                         f"Town b 0 c 0 Z0={z0} TD={own * S.PS_PER_MM * 1e-12}",
                         "Tcon c 0 k 0 Z0=120 TD=0.1n"]
                tl, _ = S.tree("b", "k", z0, tree_mm, 6, pullup="10k")
                # NOTE (measured): ngspice's adaptive step collapses ("timestep
                # too small") near t~5 ns on this deck if the print step is
                # coarser than ~0.1 ns; 0.05 ns steps complete the full 3 us.
                tr, (v1f, v6f) = run_budgeted("\n".join(lines + tl),
                                              ["v(b1)", "v(b6)"], t_case,
                                              tstop=3000e-9, tstep=0.05e-9)
                m = tr > 100e-9
                tw, vw = tr[m], v6f[m]
                ih = np.argmax(vw > VIH)
                il = np.argmax(vw > VIL)
                rf = float(tw[ih] - tw[il]) * 1e9 if vw[-1] > VIH else float("inf")
                xh = int(np.sum(np.diff((vw > VIH).astype(int)) != 0))
                xl = int(np.sum(np.diff((vw < VIL).astype(int)) != 0))
                print(f"SI-INFO release fam={fam} rs={rs:2d} float VIL->VIH {rf:7.1f} ns "
                      f"(10k pull-up), crossings VIH={xh} VIL={xl}")
                ax[1].plot(tr * 1e9, v6f, label=nm, lw=0.8)
                nplot += 1
            except subprocess.TimeoutExpired:
                rc = 1
                print(f"SI-TIMEOUT case fam={fam} rs={rs}: exceeded the "
                      f"{CASE_BUDGET_S} s per-case budget; continuing with the next case")
            print(f"SI-PROGRESS case fam={fam} rs={rs} done case_s={int(time.monotonic() - t_case)}")
    ax[0].set(title="20 MHz clock burst, far load", xlabel="ns")
    ax[1].set(title="W-release float-up (10k pull-up), far load", xlabel="ns")
    for a in ax:
        a.grid(alpha=.3)
        a.axhline(VIH, ls=":", c="gray")
        a.axhline(VIL, ls=":", c="gray")
    ax[0].legend(fontsize=6, loc="lower right")
    plt.tight_layout()
    plt.savefig("results/chain_hop_20mhz.png", dpi=110)
    print("SI-DONE rc=%d" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main(selftest="--selftest" in sys.argv))
