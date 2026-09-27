#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fail if a via's copper comes closer than MIN_GAP to an SMD pad of the SAME net (without a
solder-mask dam the paste wicks into the via barrel during reflow), or overlaps an SMD pad of
any net. Spacing to other nets is the DRC clearance rule's job.
Run with KiCad's Python:  check_via_in_pad.py board.kicad_pcb [min_gap_mm=0.2]"""
import sys
import pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
gap = pcbnew.FromMM(float(sys.argv[2]) if len(sys.argv) > 2 else 0.2)
pads = [p for f in b.GetFootprints() for p in f.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
bad = []
for v in b.GetTracks():
    if v.Type() != pcbnew.PCB_VIA_T:
        continue
    for p in pads:
        lay = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
        g = gap if p.GetNetCode() == v.GetNetCode() else 0
        if v.GetEffectiveShape(lay).Collide(p.GetEffectiveShape(lay), g):
            bad.append(f"via {v.GetNetname()} @({pcbnew.ToMM(v.GetPosition().x):.2f},"
                       f"{pcbnew.ToMM(v.GetPosition().y):.2f}) -> {p.GetParentFootprint().GetReference()}.{p.GetNumber()}")
print(f"vias within {pcbnew.ToMM(gap)} mm of a same-net SMD pad (or touching any SMD pad): {len(bad)}")
for x in bad[:20]:
    print("  " + x)
sys.exit(1 if bad else 0)
