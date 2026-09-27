#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Tile-to-tile clock hop with the vendor IBIS data (supersedes the generic tile_hop.py).

Driver: TI SN74LVC2G126 output at 3.3 V (U101 -> L_clk), IBIS-lite (ibis_lite.py).
Loads:  6 x TI LVC inputs at 3.3 V (GND clamp only: LVC inputs are 5 V tolerant, no clamp
        to VCC, so overshoot is NOT limited by the receivers).
Track lengths are the routed ones (rev A from the rev-A board, rev B as routed).

Run (hardware/si/): podman run --rm --userns=keep-id -e HOME=/tmp -e MPLCONFIGDIR=/tmp \
    -v "$PWD":/work:Z -w /work localhost/ngspice python3 tile_hop_ibis.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import si_lib as S

CASES = [
    # label, Rs, Z0 track, own track mm (driver->connector), neighbour B_clk tree mm
    ("rev A: 2 layers ~110 ohm, no Rs, 14 + 141 mm", 0, 110, 14, 141),
    ("rev B as routed: 4 layers ~55 ohm, 33 ohm, 20 + 134 mm", 33, 55, 20, 134),
    ("rev B with 22 ohm", 22, 55, 20, 134),
    ("rev B with 47 ohm", 47, 55, 20, 134),
]


def deck(rs, z0, own, tree_mm):
    drv, (tr, tf) = S.lvc_driver_subckt("126")
    lines = [drv, S.lvc_receiver_subckt(), "Vdd vdd 0 3.3",
             f"Vc ctl 0 PWL(0 0 5n 0 {5e-9 + tr} 1 400n 1 {400e-9 + tf} 0)",
             "Xd n0 ctl vdd 0 DRV126", "Lpkg n0 n0a 1n", f"Rs n0a a {max(rs, 1e-3)}",
             f"Town a 0 c 0 Z0={z0} TD={own * S.PS_PER_MM * 1e-12}",
             "Tcon c 0 k 0 Z0=120 TD=0.1n"]
    tl, _ = S.tree("b", "k", z0, tree_mm, 6, pullup="10k")
    return "\n".join(lines + tl)


def main():
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
    print(f"{'case':56s} {'node':5s} {'over%':>6} {'under V':>8} {'VIL x':>6} {'VIH x':>6}")
    for label, rs, z0, own, tree_mm in CASES:
        t, (v1, v6) = S.run(deck(rs, z0, own, tree_mm), ["v(b1)", "v(b6)"], tstop=800e-9, tstep=0.02e-9, timeout=300)
        for node, v in (("near", v1), ("far", v6)):
            m = S.edge_metrics(t, v, t_rise=(4e-9, 395e-9), t_fall=(398e-9, 790e-9))
            print(f"{label:56s} {node:5s} {m['over']:6.0f} {m['under']:8.2f} {m['x_vil']:6d} {m['x_vih']:6d}")
        ax[0].plot(t * 1e9, v6, label=label); ax[1].plot(t * 1e9, v6, label=label)
    ax[0].set_xlim(0, 40); ax[1].set_xlim(395, 435)
    for a, ttl in zip(ax, ("rising edge, far load", "falling edge, far load")):
        a.axhline(2.0, ls=":", c="gray"); a.axhline(0.8, ls=":", c="gray"); a.grid(alpha=.3)
        a.set_title(ttl); a.set_xlabel("ns")
    ax[0].set_ylabel("V"); ax[1].legend(fontsize=7)
    plt.tight_layout(); plt.savefig("measurements/tile_hop_ibis.png", dpi=100)


if __name__ == "__main__":
    main()
