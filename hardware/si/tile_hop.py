#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Tile-to-tile clock hop: U101/U107 ('126/'125 LVC buffer) -> own track -> edge connector
-> the neighbour's B_clk tree (6 CMOS inputs spread along the track).

PRELIMINARY generic model (see docs/LEDGER.md); it includes simple input clamp diodes.
Compares the rev-A layout (2 layers, ~110 ohm tracks, 141 mm tree, no series R) with the
rev-B target (4 layers, ~55 ohm tracks over a solid GND plane, shorter tree) for several
series resistor values.

Run (from hardware/si/):
  podman run --rm --userns=keep-id -e HOME=/tmp -e MPLCONFIGDIR=/tmp -v "$PWD":/work:Z \
      -w /work localhost/ngspice python3 tile_hop.py
"""
import os, subprocess
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

VDD, TR, ROUT = 3.3, 1.2e-9, 25.0      # LVC at 3.3 V: ~25 ohm, ~1-1.5 ns edges
V_PER_MM = 1 / 6.0e-3                  # ~6 ps/mm in FR-4 (microstrip, eff. er ~3.2)
C_IN = 5e-12                           # CMOS input + pad + via

def deck(name, rs, z_trk, own_mm, tree_mm, n_loads=6, z_conn=120, conn_ps=100):
    seg = tree_mm / n_loads
    lines = [f"* {name}",
             f"Vdrv drv 0 PULSE(0 {VDD} 5n {TR} {TR} 400n 800n)",
             f"Rout drv a {ROUT}", f"Rs a b {max(rs, 1e-3)}",
             f"Town b 0 c 0 Z0={z_trk} TD={own_mm*6e-12}",
             f"Tcon c 0 n0 0 Z0={z_conn} TD={conn_ps*1e-12}",
             ".model DCL D(IS=1e-14 N=1 RS=5)"]
    for i in range(n_loads):
        lines += [f"Tseg{i} n{i} 0 n{i+1} 0 Z0={z_trk} TD={seg*6e-12}",
                  f"Cin{i} n{i+1} 0 {C_IN}",
                  f"Dh{i} n{i+1} vdd DCL", f"Dl{i} 0 n{i+1} DCL"]
    lines += [f"Vdd vdd 0 {VDD}", ".control", "tran 0.02n 900n",
              f"wrdata out.txt v(n1) v(n{n_loads})", "quit", ".endc", ".end"]
    open("deck.cir", "w").write("\n".join(lines) + "\n")
    subprocess.run(["ngspice", "-b", "deck.cir"], check=True, capture_output=True)
    d = np.loadtxt("out.txt"); os.remove("out.txt"); os.remove("deck.cir")
    return d[:, 0], d[:, 1], d[:, 3]      # t, first load, last load

def metrics(t, v):
    r, f = (t > 5e-9) & (t < 405e-9), (t > 405e-9) & (t < 800e-9)
    over = (v[r].max() - VDD) / VDD * 100
    under = v[f].min()
    # threshold crossings: a clean edge crosses VIL once (fall) and VIH once (rise)
    x_fall = int(np.sum(np.diff((v[f] > 0.8).astype(int)) != 0))
    x_rise = int(np.sum(np.diff((v[r] > 2.0).astype(int)) != 0))
    return over, under, x_fall, x_rise

cases = [("rev A: 2L ~110 ohm, 141 mm tree, Rs=0", 0, 110, 14, 141),
         ("rev B: 4L ~55 ohm, 100 mm tree, Rs=0", 0, 55, 14, 100),
         ("rev B: Rs=22", 22, 55, 14, 100),
         ("rev B: Rs=33", 33, 55, 14, 100),
         ("rev B: Rs=47", 47, 55, 14, 100),
         ("rev B as routed: 20 mm + 141 mm, Rs=33", 33, 55, 20, 141)]
fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
print(f"{'case':42s} {'node':5s} {'over%':>6} {'under V':>8} {'VIL crossings':>14} {'VIH crossings':>14}")
for name, rs, z, own, tree in cases:
    t, v1, vn = deck(name, rs, z, own, tree)
    for lbl, v in (("near", v1), ("far", vn)):
        o, u, xf, xr = metrics(t, v)
        flag = "  <-- multiple crossings" if (xf > 1 or xr > 1) else ""
        print(f"{name:42s} {lbl:5s} {o:6.0f} {u:8.2f} {xf:14d} {xr:14d}{flag}")
    ax[0].plot(t*1e9, vn, label=name); ax[1].plot(t*1e9, vn, label=name)
for a, (lo, hi), ttl in ((ax[0], (0, 60), "rising edge, far load"), (ax[1], (400, 460), "falling edge, far load")):
    a.set_xlim(lo, hi); a.axhline(2.0, ls=":", c="gray"); a.axhline(0.8, ls=":", c="gray")
    a.set_title(ttl); a.set_xlabel("ns"); a.grid(alpha=.3)
ax[0].set_ylabel("V"); ax[1].legend(fontsize=7)
plt.tight_layout(); plt.savefig("tile_hop.png", dpi=110)
