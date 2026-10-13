#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Parse the two board constraint files into {variant: {net: (pin, pull)}}.
Single parse used by board_gen and kept in lockstep with tools/pincon_check.py
(which re-checks everything the generator consumed)."""
import os
import re


def load(cdir):
    out = {"gw1nz": {}, "up5k": {}}
    cst = os.path.join(cdir, "tile_gw1nz_board.cst")
    for ln in open(cst):
        ln = re.sub(r"//.*$", "", ln)
        for m in re.finditer(r'IO_LOC\s+"([^"]+)"\s+(\d+)\s*;', ln):
            out["gw1nz"][m.group(1)] = (int(m.group(2)), None)
        for m in re.finditer(r'IO_PORT\s+"([^"]+)"\s+PULL_MODE=(UP|DOWN)\s*;', ln):
            n = m.group(1)
            if n in out["gw1nz"]:
                out["gw1nz"][n] = (out["gw1nz"][n][0], m.group(2))
    pcf = os.path.join(cdir, "tile_up5k_board.pcf")
    for ln in open(pcf):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        m = re.match(r"set_io\s+(?:-pullup\s+(yes|no)\s+)?(\S+)\s+(\d+)$", ln)
        if m:
            out["up5k"][m.group(2)] = (
                int(m.group(3)), "UP" if m.group(1) == "yes" else None)
    return out
