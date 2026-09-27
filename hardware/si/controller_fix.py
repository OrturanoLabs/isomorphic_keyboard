#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Use the calibrated controller-link model (measurements/fit_2026-06-15.json) to size a
series resistor at the pico-ice outputs (adapter board). Prints the node (logic) view."""
import json
import numpy as np
import fit_measurement as F
import si_lib as S

fit = json.load(open("measurements/fit_2026-06-15.json"))
p = np.array([fit[k] for k in F.NAMES])
print(f"{'extra series R at the pico-ice':32s} {'over%':>6} {'under V':>8} {'VIL x':>6} {'VIH x':>6}")
for rs in (0, 33, 68, 100, 150, 220):
    q = p.copy(); q[0] = p[0] + rs
    t, vj, _ = F.sim_edges(q, timeout=120, probe=False)
    m = S.edge_metrics(t, vj, t_rise=(F.T_RISE - 5e-9, 690e-9), t_fall=(F.T_FALL - 5e-9, F.T_RISE - 10e-9))
    r = (t > F.T_RISE) & (t < 690e-9)
    t10 = t[r][np.argmax(vj[r] > 0.33)]; t90 = t[r][np.argmax(vj[r] > 2.97)]
    print(f"{rs:>28d} ohm {m['over']:6.0f} {m['under']:8.2f} {m['x_vil']:6d} {m['x_vih']:6d}   rise {1e9 * (t90 - t10):.1f} ns")
