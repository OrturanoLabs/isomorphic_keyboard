#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Calibrate the controller-link model on the rev-A scope capture, then answer
"how much of what we saw is the probe?" without waiting for new hardware.

Model (see si_lib.py): iCE40 pin (ideal ramp + R_drv) -> dupont wire (T-line Z_dup, TD_dup)
-> first tile B_clk tree (rev A: 141 mm, ~110 ohm, 6 LVC inputs from IBIS, 10k pull-up)
-> AD2 probe loop (R_loop + L_loop) -> 24 pF || 1 MOhm -> 30 MHz Butterworth.
The probe is assumed on the tile entry (J103 pin 2).

Fitted: R_drv, t_edge, Z_dup, TD_dup, L_loop, R_loop (Nelder-Mead on the RMS error of the
second falling and second rising edge of channel 2, measurements/scope_2026-06-15.csv).
Then the fitted circuit is re-simulated with (a) the node voltage itself, (b) the same long
probe loop, (c) a spring-tip ground (~5 nH), (d) the AD2 flywires (~1 uH loop).

Run (hardware/si/):  podman run --rm --userns=keep-id -e HOME=/tmp -e MPLCONFIGDIR=/tmp \
    -v "$PWD":/work:Z -w /work localhost/ngspice python3 fit_measurement.py
"""
import json
import sys
import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import si_lib as S

T_FALL, T_RISE = 50e-9, 450e-9
NAMES = ["r_drv", "t_edge", "z_dup", "td_dup", "l_loop", "r_loop", "l_gnd", "gain", "offset"]
LO = np.array([8, 0.3e-9, 60, 0.3e-9, 5e-9, 0.2, 5e-9, 0.85, -0.3])
HI = np.array([120, 6e-9, 450, 2.5e-9, 8000e-9, 80, 3000e-9, 1.1, 0.3])
X0 = np.array([35, 1.5e-9, 200, 1.0e-9, 1000e-9, 10, 300e-9, 0.95, -0.1])


def deck(p, scope_bw=30e6, probe=True, lloop=None, rloop=None):
    """Ground node 0 = controller/AD2 ground; tg = tile ground, joined by the dupont GND wire
    (l_gnd). The tile logic sees v(j)-v(tg); the scope sees v(j)-v(0) through its loop."""
    r_drv, t_e, z_dup, td_dup, l_loop, r_loop, l_gnd = p[:7]
    l_loop = l_loop if lloop is None else lloop
    r_loop = r_loop if rloop is None else rloop
    lines = [S.lvc_receiver_subckt(), S.scope_subckt(scope_bw), "Vdd vdd tg 3.3",
             f"Vs s 0 PWL(0 3.3 {T_FALL} 3.3 {T_FALL + t_e} 0 {T_RISE} 0 {T_RISE + t_e} 3.3)",
             f"Rdrv s p {r_drv}", f"Tdup p 0 j tg Z0={z_dup} TD={td_dup}",
             f"Lgnd tg g1 {l_gnd}", "Rgnd g1 0 0.3"]
    tl, _ = S.tree("b", "j", 110, 141, 6, pullup="10k", gnd="tg")
    lines += tl
    if probe:
        lines.append(f"Xsc j sc 0 SCOPE params: rloop={r_loop} lloop={l_loop}")
    return "\n".join(lines)


def measured():
    a = np.genfromtxt("measurements/scope_2026-06-15.csv", delimiter=",", skip_header=1)
    a = a[~np.isnan(a[:, 2])]
    t, v = a[:, 0] * 1e-9, a[:, 2]
    # second falling edge (~435 ns) and second rising edge (~775 ns) of the capture
    def cross(lo, hi, rising):
        m = (t > lo) & (t < hi)
        tt, vv = t[m], v[m]
        s = (vv > 1.5) if rising else (vv < 1.5)
        return tt[np.argmax(s)]
    tf = cross(380e-9, 500e-9, False)
    tr = cross(700e-9, 850e-9, True)
    wf = (t > tf - 30e-9) & (t < tf + 180e-9)
    wr = (t > tr - 30e-9) & (t < tr + 120e-9)
    return (t[wf] - tf, v[wf]), (t[wr] - tr, v[wr])


def sim_edges(p, timeout=10, **kw):
    """Returns t, logic view v(j,tg), scope view (gain/offset of the measurement applied)."""
    gain, offset = p[7], p[8]
    if kw.get("probe", True) is False:
        t, (vj,) = S.run(deck(p, **kw), ["v(j,tg)"], tstop=700e-9, tstep=0.05e-9, timeout=timeout)
        return t, vj, vj
    t, (vj, vs) = S.run(deck(p, **kw), ["v(j,tg)", "v(sc)"], tstop=700e-9, tstep=0.05e-9, timeout=timeout)
    return t, vj, gain * vs + offset


def align(t, v, t0, rising):
    m = t > t0
    s = (v[m] > 1.5) if rising else (v[m] < 1.5)
    return t - t[m][np.argmax(s)]


def cost(x, meas):
    p = LO + (HI - LO) / (1 + np.exp(-x))                  # bounded parameters
    try:
        t, _, vs = sim_edges(p)
        (tfm, vfm), (trm, vrm) = meas
        tf = align(t, vs, T_FALL - 5e-9, False)
        tr = align(t, vs, T_RISE - 5e-9, True)
    except Exception:                                       # timeout / edge never crosses 1.5 V
        return 1e3
    mf = (t > T_FALL - 40e-9) & (t < T_RISE - 60e-9)
    mr = t > T_RISE - 40e-9
    ef = vfm - np.interp(tfm, tf[mf], vs[mf])
    er = vrm - np.interp(trm, tr[mr], vs[mr])
    return float(np.sqrt(np.mean(np.concatenate([ef, er]) ** 2)))


def nelder_mead(f, x0, step=0.6, iters=160, tol=1e-4):
    n = len(x0)
    pts = [x0] + [x0 + step * np.eye(n)[i] for i in range(n)]
    vals = [f(p) for p in pts]
    for it in range(iters):
        o = np.argsort(vals)
        pts, vals = [pts[i] for i in o], [vals[i] for i in o]
        if vals[-1] - vals[0] < tol:
            break
        c = np.mean(pts[:-1], axis=0)
        xr = c + (c - pts[-1]); fr = f(xr)
        if fr < vals[0]:
            xe = c + 2 * (c - pts[-1]); fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = c + 0.5 * (pts[-1] - c); fc = f(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                for i in range(1, n + 1):
                    pts[i] = pts[0] + 0.5 * (pts[i] - pts[0]); vals[i] = f(pts[i])
    i = int(np.argmin(vals))
    return pts[i], vals[i]


def main():
    meas = measured()
    if "--from-json" in sys.argv:
        fit = json.load(open("measurements/fit_2026-06-15.json"))
        p = np.array([fit[k] for k in NAMES])
        return views(p, meas)
    x0 = -np.log((HI - LO) / (X0 - LO) - 1)
    # coarse multi-start, then Nelder-Mead from the best start
    starts = [x0] + [x0 + np.random.default_rng(k).normal(0, 1.2, len(x0)) for k in range(12)]
    t0 = time.time()
    scored = sorted(((cost(s, meas), i) for i, s in enumerate(starts)))
    print("multi-start costs:", [round(c, 3) for c, _ in scored[:5]], f"({time.time() - t0:.0f} s)", flush=True)
    best_x, best = nelder_mead(lambda x: cost(x, meas), starts[scored[0][1]])
    p = LO + (HI - LO) / (1 + np.exp(-best_x))
    fit = dict(zip(NAMES, p.tolist()), rms_V=best)
    print("fit:", {k: (f"{v:.3g}") for k, v in fit.items()})
    json.dump(fit, open("measurements/fit_2026-06-15.json", "w"), indent=1)
    views(p, meas)


def views(p, meas):
    # what is real and what is the probe?
    views = {"node (what the logic sees)": dict(probe=False),
             "AD2, long probe loop (fitted)": dict(),
             "AD2, spring tip (5 nH)": dict(lloop=5e-9, rloop=0.5),
             "AD2 flywires (1 uH loop)": dict(lloop=1e-6, rloop=5)}
    # (a 200 MHz front end made ngspice stall; the node view is the ideal-instrument reference)
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
    (tfm, vfm), (trm, vrm) = meas
    rows = []
    for label, kw in views.items():
        t, vj, v = sim_edges(p, timeout=300, **kw)
        m = S.edge_metrics(t, v, t_rise=(T_RISE - 5e-9, 690e-9), t_fall=(T_FALL - 5e-9, T_RISE - 10e-9))
        tf = align(t, v, T_FALL - 5e-9, False); tr = align(t, v, T_RISE - 5e-9, True)
        mf, mr = (t > T_FALL - 40e-9) & (t < T_RISE - 60e-9), t > T_RISE - 40e-9
        e = np.concatenate([vfm - np.interp(tfm, tf[mf], v[mf]), vrm - np.interp(trm, tr[mr], v[mr])])
        m["rms"] = float(np.sqrt(np.mean(e ** 2)))
        rows.append((label, m))
        ax[0].plot(tf * 1e9, v, label=label); ax[1].plot(tr * 1e9, v, label=label)
    ax[0].plot(tfm * 1e9, vfm, "k.", ms=3, label="measured (digitised photo)")
    ax[1].plot(trm * 1e9, vrm, "k.", ms=3, label="measured (digitised photo)")
    for a, ttl in ((ax[0], "falling edge"), (ax[1], "rising edge")):
        a.set_xlim(-30, 180); a.axhline(0.8, ls=":", c="gray"); a.axhline(2.0, ls=":", c="gray")
        a.set_title(ttl); a.set_xlabel("ns from 1.5 V crossing"); a.grid(alpha=.3)
    ax[0].set_ylabel("V"); ax[1].legend(fontsize=7)
    plt.tight_layout(); plt.savefig("measurements/fit_2026-06-15.png", dpi=100)
    print(f"{'view':34s} {'over%':>6} {'under V':>8} {'VIL x':>6} {'VIH x':>6} {'RMS vs meas':>12}")
    for label, m in rows:
        print(f"{label:34s} {m['over']:6.0f} {m['under']:8.2f} {m['x_vil']:6d} {m['x_vih']:6d} {m['rms']:12.3f}")


if __name__ == "__main__":
    main()
