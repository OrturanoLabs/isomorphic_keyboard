#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Minimal IBIS -> ngspice converter ("IBIS-lite").

Reads one [Model] of an IBIS file (typ column) and emits an ngspice .subckt built from
behavioural current sources:
  * input  model  : C_comp + [GND Clamp] + [POWER Clamp]             pins: pad vcc gnd
  * output/3-state: the above + [Pulldown] * Kd(t) + [Pullup] * Ku(t) pins: pad ctl vcc gnd
    where V(ctl) goes 0 -> 1 for a rising output (Ku = V(ctl), Kd = 1 - V(ctl)).
The switching coefficients follow a linear ramp; its 0-100 % time is derived from the
IBIS [Ramp] dV/dt (20-80 % of the swing into R_load, so t_full ~ t_20_80 / 0.6).
This ignores [Rising/Falling Waveform] tables and package parasitics (added by the caller),
which is adequate for the edge rates of these parts (~1 ns) on sub-10 cm interconnects.

IBIS conventions used: pulldown and GND-clamp tables are I(Vpin); pullup and POWER-clamp
tables are I(Vcc - Vpin); positive current flows into the pin.
"""
import re

SECTIONS = ("GND Clamp", "POWER Clamp", "Pulldown", "Pullup")


def _num(s):
    s = s.strip()
    m = re.match(r"^([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)([a-zA-Z]*)", s)
    if not m:
        return None
    v, suf = float(m.group(1)), m.group(2).lower()
    scale = {"": 1, "v": 1, "a": 1, "s": 1, "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6,
             "m": 1e-3, "k": 1e3, "ma": 1e-3, "ua": 1e-6, "na": 1e-9, "pf": 1e-12,
             "nf": 1e-9, "ns": 1e-9, "ps": 1e-12, "mv": 1e-3}
    for k in sorted(scale, key=len, reverse=True):
        if suf.startswith(k):
            return v * scale[k]
    return v


def parse_model(path, name):
    text = open(path, encoding="latin-1").read()
    m = re.search(r"^\[Model\]\s+" + re.escape(name) + r"\s*$(.*?)(?=^\[Model\]|^\[End\]|\Z)",
                  text, re.S | re.M | re.I)
    if not m:
        raise KeyError(f"model {name} not found in {path}")
    body = m.group(1)
    model = {"name": name}
    cc = re.search(r"^C_comp\s+(\S+)", body, re.M)
    model["C_comp"] = _num(cc.group(1)) if cc else 0.0
    mt = re.search(r"^Model_type\s+(\S+)", body, re.M)
    model["type"] = mt.group(1) if mt else "?"
    # split into bracketed sections
    parts = re.split(r"^\[([^\]]+)\]", body, flags=re.M)
    for i in range(1, len(parts), 2):
        key, content = parts[i].strip(), parts[i + 1]
        if key in SECTIONS:
            pts = []
            for line in content.splitlines():
                line = line.split("|")[0].strip()
                f = line.split()
                if len(f) >= 2:
                    v, i_typ = _num(f[0]), _num(f[1])
                    if v is not None and i_typ is not None:
                        pts.append((v, i_typ))
            if pts:
                model[key] = sorted(dict(pts).items())   # unique, sorted by voltage
        elif key == "Ramp":
            for kind in ("r", "f"):
                r = re.search(r"dV/dt_" + kind + r"\s+(\S+)/(\S+)", content)
                if r:
                    model["ramp_" + kind] = (_num(r.group(1)), _num(r.group(2)))
    return model


def _pwl(var, table, scale=1.0):
    pts = ", ".join(f"{v:.4g},{i * scale:.5g}" for v, i in table)
    return f"pwl({var}, {pts})"


def subckt(model, sname=None):
    """Return ngspice .subckt text for an IBIS model."""
    sname = sname or model["name"]
    out = model.get("Pulldown") is not None
    pins = "pad ctl vcc gnd" if out else "pad vcc gnd"
    lines = [f"* IBIS-lite {model['name']} ({model['type']})", f".subckt {sname} {pins}",
             f"Ccomp pad gnd {model['C_comp']:.4g}"]
    terms = []
    if "GND Clamp" in model:
        terms.append(_pwl("v(pad,gnd)", model["GND Clamp"]))
    if "POWER Clamp" in model:
        terms.append(_pwl("v(vcc,pad)", model["POWER Clamp"]))
    if out:
        terms.append("(1-v(ctl,gnd))*" + _pwl("v(pad,gnd)", model["Pulldown"]))
        terms.append("v(ctl,gnd)*" + _pwl("v(vcc,pad)", model["Pullup"]))
    lines.append("Bio pad gnd I = " + " + ".join(terms))
    lines.append(".ends")
    return "\n".join(lines) + "\n"


def ramp_times(model):
    """0-100 % ramp times (s) for the switching coefficients."""
    tr = model["ramp_r"][1] / 0.6 if "ramp_r" in model else 1e-9
    tf = model["ramp_f"][1] / 0.6 if "ramp_f" in model else 1e-9
    return tr, tf


if __name__ == "__main__":
    import sys
    m = parse_model(sys.argv[1], sys.argv[2])
    print({k: (v if not isinstance(v, list) else f"{len(v)} pts") for k, v in m.items()})
    print(subckt(m)[:600])
