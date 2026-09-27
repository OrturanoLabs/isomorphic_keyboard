#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""How much ringing does the probe itself add? ("the spring question", no hardware needed)

A clean LVC edge (IBIS model of the 74LVC2G126 driving a short track and one LVC input)
is observed through the Analog Discovery 2 input (24 pF || 1 MOhm, 30 MHz) with different
probe ground loops, and then sampled at 100 MS/s as WaveForms does:
  spring tip ~5 nH, short clip ~50 nH, 15 cm ground clip ~200 nH, flywire pair ~1 uH.
The node voltage itself is plotted as the reference.

Run (hardware/si/): podman run --rm --userns=keep-id -e HOME=/tmp -e MPLCONFIGDIR=/tmp \
    -v "$PWD":/work:Z -w /work localhost/ngspice python3 probe_effect.py
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import si_lib as S

LOOPS = [("spring tip (~5 nH)", 5e-9, 0.5), ("short clip (~50 nH)", 50e-9, 1.0),
         ("15 cm ground clip (~200 nH)", 200e-9, 2.0), ("AD2 flywires (~1 uH)", 1e-6, 5.0)]


def deck(lloop, rloop, probe=True):
    drv, (tr, tf) = S.lvc_driver_subckt("126")
    lines = [drv, S.lvc_receiver_subckt(), S.scope_subckt(30e6), "Vdd vdd 0 3.3",
             f"Vc ctl 0 PWL(0 1 50n 1 {50e-9 + tf} 0 250n 0 {250e-9 + tr} 1)",
             "Xd n0 ctl vdd 0 DRV126", "Rs n0 n1 33", "T1 n1 0 n2 0 Z0=55 TD=0.12n",
             "Xr n2 vdd 0 RCV"]
    if probe:
        lines.append(f"Xsc n2 sc 0 SCOPE params: rloop={rloop} lloop={lloop}")
    return "\n".join(lines)


def main():
    t, (vn,) = S.run(deck(0, 0, probe=False), ["v(n2)"], tstop=450e-9, tstep=0.02e-9)
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
    for a in ax:
        a.plot(t * 1e9, vn, "k", lw=2, label="node (truth)")
    print(f"{'probe':30s} {'apparent over%':>15} {'apparent under V':>17} {'ring freq MHz':>14}")
    for label, l, r in LOOPS:
        t2, (vs,) = S.run(deck(l, r), ["v(sc)"], tstop=450e-9, tstep=0.02e-9)
        ts = np.arange(0, 450e-9, 10e-9) + 3e-9                  # 100 MS/s samples
        vsamp = np.interp(ts, t2, vs)
        m = S.edge_metrics(t2, vs, t_rise=(245e-9, 440e-9), t_fall=(45e-9, 240e-9))
        seg = vs[(t2 > 255e-9) & (t2 < 440e-9)] - 3.3
        zc = np.nonzero(np.diff(np.sign(seg)) != 0)[0]
        f = 1 / (2 * np.mean(np.diff(zc)) * 0.02e-9) / 1e6 if len(zc) > 2 else float("nan")
        print(f"{label:30s} {m['over']:15.0f} {m['under']:17.2f} {f:14.0f}")
        for a in ax:
            a.plot(t2 * 1e9, vs, label=label)
        ax[1].plot(ts * 1e9, vsamp, "o", ms=3, alpha=.5)
    ax[0].set_xlim(40, 200); ax[1].set_xlim(240, 400)
    ax[0].set_title("falling edge"); ax[1].set_title("rising edge (dots: 100 MS/s samples)")
    for a in ax:
        a.grid(alpha=.3); a.set_xlabel("ns")
    ax[0].set_ylabel("V"); ax[0].legend(fontsize=7)
    plt.tight_layout(); plt.savefig("measurements/probe_effect.png", dpi=100)


if __name__ == "__main__":
    main()
