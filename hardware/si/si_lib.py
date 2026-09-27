#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Building blocks for the tile signal-integrity decks (ngspice, run in the container).

Topology pieces:
  * IBIS-lite drivers/receivers of the real TI parts (models/*.ibs, see ibis_lite.py);
  * a generic driver (ideal ramp + R_out) for the iCE40 on the pico-ice, whose IBIS model is
    not freely downloadable; its R_out and edge time are fitted to the measurement;
  * lossless T-lines for tracks, the 2.54 mm edge connector and dupont wires;
  * the Analog Discovery 2 measurement chain: probe loop (series R + L of the flywire /
    ground lead), 1 MOhm || 24 pF input, 30 MHz 2nd-order Butterworth front end.
"""
import os
import subprocess
import tempfile

import numpy as np

import ibis_lite

HERE = os.path.dirname(os.path.abspath(__file__))
VDD = 3.3
PS_PER_MM = 6.0          # microstrip in FR-4, eff. er ~3.2

_M = {}


def model(fname, name):
    key = (fname, name)
    if key not in _M:
        _M[key] = ibis_lite.parse_model(os.path.join(HERE, "models", fname), name)
    return _M[key]


def lvc_driver_subckt(part="126"):
    m = model(f"sn74lvc2g{part}.ibs", f"LVC2G{part}_OUT_33")
    return ibis_lite.subckt(m, f"DRV{part}"), ibis_lite.ramp_times(m)


def lvc_receiver_subckt():
    return ibis_lite.subckt(model("sn74lvc2g125.ibs", "LVC2G125_IN_33"), "RCV")


def scope_subckt(bw_hz=30e6):
    """AD2 front end: 1 MOhm || 24 pF after the probe loop, then a 2nd-order Butterworth."""
    # series R-L, shunt C, output across C: H = 1 / (LC s^2 + RC s + 1),
    # w0 = 1/sqrt(LC), Q = sqrt(L/C)/R  ->  L = R Q / w0, C = 1 / (R Q w0)  (Q = 0.707)
    w0 = 2 * np.pi * bw_hz
    r, q = 100.0, 1 / np.sqrt(2)
    l, c = r * q / w0, 1 / (r * q * w0)
    return (f".subckt SCOPE probe out gnd params: rloop=2 lloop=150n\n"
            f"Rl probe a {{rloop}}\nLl a m {{lloop}}\nCin m gnd 24p\nRin m gnd 1Meg\n"
            f"E1 b gnd m gnd 1\nRf b c {r}\nLf c out {l:.4g}\nCf out gnd {c:.4g}\n.ends\n")


def tree(prefix, start, z0, length_mm, n_loads, rcv="RCV", pullup=None, gnd="0", vdd="vdd"):
    """A track of length_mm with n_loads receivers spread evenly; returns deck lines.
    gnd/vdd are the local (tile) reference nodes."""
    seg = length_mm / n_loads
    lines, node = [], start
    for i in range(n_loads):
        nxt = f"{prefix}{i + 1}"
        lines.append(f"T{prefix}{i} {node} {gnd} {nxt} {gnd} Z0={z0} TD={seg * PS_PER_MM * 1e-12:.4g}")
        lines.append(f"X{prefix}r{i} {nxt} {vdd} {gnd} {rcv}")
        node = nxt
    if pullup:
        lines.append(f"R{prefix}pu {start} {vdd} {pullup}")
    return lines, node


def run(deck, probes, tstop=900e-9, tstep=0.02e-9, timeout=10):
    """Run ngspice on a deck body; return t and one array per probe expression."""
    with tempfile.TemporaryDirectory() as d:
        cir, out = os.path.join(d, "deck.cir"), os.path.join(d, "out.txt")
        body = deck + (f"\n.control\ntran {tstep} {tstop}\nwrdata {out} " + " ".join(probes) +
                       "\nquit\n.endc\n.end\n")
        open(cir, "w").write("* si deck\n" + body)
        # some parameter corners make ngspice crawl ("timestep too small"): give up on them
        r = subprocess.run(["ngspice", "-b", cir], capture_output=True, text=True, timeout=timeout)
        if not os.path.exists(out):
            raise RuntimeError(r.stdout[-2000:] + r.stderr[-2000:])
        d_ = np.loadtxt(out)
    t = d_[:, 0]
    return t, [d_[:, 2 * k + 1] for k in range(len(probes))]


def edge_metrics(t, v, t_rise=(5e-9, 405e-9), t_fall=(405e-9, 800e-9)):
    r = (t > t_rise[0]) & (t < t_rise[1])
    f = (t > t_fall[0]) & (t < t_fall[1])
    return dict(over=(v[r].max() - VDD) / VDD * 100, under=v[f].min(),
                x_vil=int(np.sum(np.diff((v[f] > 0.8).astype(int)) != 0)),
                x_vih=int(np.sum(np.diff((v[r] > 2.0).astype(int)) != 0)))
