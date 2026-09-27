#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Rev C routability test (stage 1 / stage 2 like revb_pcb.py, on production/revc).

Single board: the stacking connectors J105/J106 <-> J107/J108 disappear, so their nets are
merged 1:1 (BTNs_L<k> becomes BTNs<k>, VCC_T/GND_T become VCC/GND). The edge connectors are
not on this board (they need a new edge-contact design), so their nets end at no pin.
  stage 1: merge nets, inner planes, power fan-out, DSN export
  stage 2 (--route-in SES): import, ground pours, fill, save
"""
import importlib.util, os, sys
import pcbnew
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
OUT = os.path.join(ROOT, "production", "revc")
spec = importlib.util.spec_from_file_location("revb", os.path.join(HERE, "revb_pcb.py"))
revb = importlib.util.module_from_spec(spec); spec.loader.exec_module(revb)
BRD = os.path.join(OUT, "revc_route.kicad_pcb")


def stage1():
    ref = pcbnew.LoadBoard(os.path.join(ROOT, "hardware", "kicad", "tile", "isomorphic_tile.kicad_pcb"))
    canon = {"VCC_T": "VCC", "GND_T": "GND"}
    for a, b in (("J105", "J107"), ("J106", "J108")):
        fa, fb = ref.FindFootprintByReference(a), ref.FindFootprintByReference(b)
        for p in fa.Pads():
            key_net = fb.FindPadByNumber(p.GetNumber()).GetNetname()
            c = canon.get(key_net, key_net)                 # key-board name wins, _T rails -> main
            canon[p.GetNetname()] = c
            canon[key_net] = c
    b = pcbnew.LoadBoard(os.path.join(OUT, "revc_placed.kicad_pcb"))
    n = 0
    for fp in b.GetFootprints():
        for p in fp.Pads():
            c = canon.get(p.GetNetname())
            if c and c != p.GetNetname():
                p.SetNet(revb.net(b, c)); n += 1
    print("pads re-netted:", n)
    b.SetCopperLayerCount(4)
    b.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER); b.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)
    outline = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(outline, False)
    revb.add_zone(b, outline, pcbnew.In1_Cu, "GND"); revb.add_zone(b, outline, pcbnew.In2_Cu, "VCC")
    revb.POWER = ("VCC", "GND")
    revb.fanout_power(b)
    pcbnew.SaveBoard(BRD, b)
    b = pcbnew.LoadBoard(BRD)
    pcbnew.ExportSpecctraDSN(b, os.path.join(OUT, "revc_route.dsn"))


def stage2(ses):
    b = pcbnew.LoadBoard(BRD)
    if not pcbnew.ImportSpecctraSES(b, ses):
        sys.exit("SES import failed: " + ses)
    outline = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(outline, False)
    revb.add_zone(b, outline, pcbnew.F_Cu, "GND"); revb.add_zone(b, outline, pcbnew.B_Cu, "GND")
    b.BuildConnectivity(); pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(BRD, b)


if __name__ == "__main__":
    stage2(sys.argv[2]) if "--route-in" in sys.argv else stage1()
