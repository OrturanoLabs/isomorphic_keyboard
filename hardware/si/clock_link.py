#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""First-order signal-integrity model of the board clock (pico-ice -> first tile).

PRELIMINARY: generic parameters, not yet IBIS models or field-solved impedances. The model
must first reproduce the rev-A scope capture (docs/media/rev-a-scope-clock-ringing.jpg)
before it is trusted for rev-B decisions (see docs/LEDGER.md).

Topology:
  driver (ideal edge + Rout) -> Rs (series termination under test)
  -> dupont wire (lossless T-line, Z_wire, 20 cm) + wire/return inductance
  -> tile track (T-line, Z_trace, ~70 mm to the load cluster)
  -> lumped load C_load (6 CMOS inputs + connector + pull-up)
Run inside the ngspice container (from hardware/si/):
  podman run --rm --userns=keep-id -e HOME=/tmp -e MPLCONFIGDIR=/tmp -v "$PWD":/work:Z -w /work localhost/ngspice python3 clock_link.py
"""
import subprocess, numpy as np, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

P = dict(vdd=3.3, tr=1.5e-9, rout=20, z_wire=200, td_wire=0.8e-9,
         l_ret=150e-9, z_trace=100, td_trace=0.45e-9, c_load=30e-12)

def deck(rs, p=P):
    return f"""* clock link rs={rs}
Vdrv drv 0 PULSE(0 {p['vdd']} 5n {p['tr']} {p['tr']} 400n 800n)
Rout drv n1 {p['rout']}
Rs n1 n2 {max(rs,1e-3)}
Twire n2 0 n3 0 Z0={p['z_wire']} TD={p['td_wire']}
Lret n3 n4 {p['l_ret']}
Ttrk n4 0 rx 0 Z0={p['z_trace']} TD={p['td_trace']}
Cld rx 0 {p['c_load']}
Rpu rx vcc 10k
Vcc vcc 0 {p['vdd']}
.control
tran 0.05n 900n
wrdata out_{rs}.txt v(rx)
quit
.endc
.end
"""

def run(rs):
    open(f"deck_{rs}.cir", "w").write(deck(rs))
    subprocess.run(["ngspice", "-b", f"deck_{rs}.cir"], check=True, capture_output=True)
    d = np.loadtxt(f"out_{rs}.txt")
    os.remove(f"deck_{rs}.cir"); os.remove(f"out_{rs}.txt")
    return d[:, 0], d[:, 1]

rows = []
plt.figure(figsize=(9, 5))
for rs in (0, 33, 68, 150):
    t, v = run(rs)
    rise = (t > 5e-9) & (t < 405e-9)
    fall = t > 405e-9
    over = (v[rise].max() - P['vdd']) / P['vdd'] * 100
    under = v[fall].min()
    # 10-90 % rise time
    t10 = t[rise][np.argmax(v[rise] > 0.33)]; t90 = t[rise][np.argmax(v[rise] > 2.97)]
    # non-monotonic re-crossings of the input thresholds (VIH 2.0 V / VIL 0.8 V) = double-clock risk
    ring_lo = np.sum(np.diff((v[fall] > 0.8).astype(int)) != 0)
    rows.append((rs, over, under, (t90 - t10) * 1e9, ring_lo))
    plt.plot(t * 1e9, v, label=f"Rs = {rs} Ω")
plt.axhline(2.0, ls=":", c="gray"); plt.axhline(0.8, ls=":", c="gray")
plt.xlim(0, 80); plt.xlabel("ns"); plt.ylabel("V at tile inputs"); plt.legend(); plt.grid(alpha=.3)
plt.title("Board clock at the first tile — preliminary model")
plt.savefig("clock_link_rising.png", dpi=110)
plt.xlim(400, 480); plt.title("Falling edge"); plt.savefig("clock_link_falling.png", dpi=110)
print(f"{'Rs':>4} {'overshoot %':>12} {'undershoot V':>13} {'rise ns':>8} {'VIL re-crossings':>17}")
for r in rows: print(f"{r[0]:>4} {r[1]:>12.0f} {r[2]:>13.2f} {r[3]:>8.1f} {r[4]:>17}")
