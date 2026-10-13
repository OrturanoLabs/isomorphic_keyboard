#!/usr/bin/env python3
"""Probe: which B.Cu GND fill islands have no GND via/pad contact (= pour
islands disconnected from the net), and nearest GND copper around each.
Run: flatpak run --command=python3 org.kicad.KiCad layout/tools/probe_gnd_islands.py
"""
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, '..', 'tile_variant_a_routed.kicad_pcb')


def mm(x):
    return round(pcbnew.ToMM(x), 3)


def main():
    b = pcbnew.LoadBoard(BOARD)
    b.BuildConnectivity()
    gnd_vias = [t for t in b.GetTracks()
                if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == 'GND']
    gnd_pads = [p for f in b.GetFootprints() for p in f.Pads()
                if p.GetNetname() == 'GND' and p.HasHole()]
    for z in b.Zones():
        if z.GetNetname() != 'GND' or z.GetLayer() != pcbnew.B_Cu:
            continue
        fl = z.GetFilledPolysList(pcbnew.B_Cu)
        print('islands:', fl.OutlineCount(),
              '| gnd vias:', len(gnd_vias), '| gnd tht pads:', len(gnd_pads))
        for oi in range(fl.OutlineCount()):
            ps = pcbnew.SHAPE_POLY_SET()
            ps.AddOutline(fl.Outline(oi))
            bb = fl.Outline(oi).BBox()
            hits = []
            for t in gnd_vias + gnd_pads:
                shp = t.GetEffectiveShape(pcbnew.B_Cu)
                if ps.Collide(shp, 0) if hasattr(ps, 'Collide') else False:
                    hits.append('x')
                    break
                # fallback center-in-poly
                if ps.Contains(t.GetPosition()):
                    hits.append('c')
                    break
            tag = 'anchored' if hits else 'FLOATING'
            print(f'  {tag}: bbox x {mm(bb.GetX())}..{mm(bb.GetRight())} '
                  f'y {mm(bb.GetY())}..{mm(bb.GetBottom())}')


if __name__ == '__main__':
    main()
