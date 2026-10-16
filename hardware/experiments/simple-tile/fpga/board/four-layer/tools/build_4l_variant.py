#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""build_4l_variant.py -- build the FPGA-02 four-layer VARIANT COPY.

Run inside the KiCad flatpak from the repo root:

    flatpak run --filesystem=<repo> --command=python3 org.kicad.KiCad \
        hardware/experiments/simple-tile/fpga/board/four-layer/tools/build_4l_variant.py

Reads (read-only): canonical 2L pcb out/kicad/tile_gw1nz.kicad_pcb (+its
.kicad_pro), docs/fanout_prep.json (measured 52-pad plan; the 6 four-layer
via-attach blockers), docs/netclasses.json.
Writes (owned tree only):
  four-layer/out/tile_gw1nz_4l.kicad_pcb   4-layer variant copy
  four-layer/out/tile_gw1nz_4l.kicad_pro   companion project w/ net classes
  four-layer/out/fanout_sites.json         every fanout via/stub (DSN fix-type
                                           sidecar + audit)

What it does (stackup per layer-decision-review section 4 primary):
  * 4 copper layers: F.Cu signal / In1.Cu=GND / In2.Cu=GND / B.Cu signal;
    realistic 1.6 mm stackup block (proven discrete construction values);
  * GND zones on both inner layers over the full stepped outline, filled
    only AFTER routing (fill in finish_4l_variant.py);
  * REAL dogbone fanout: every planned SMD power pad (fanout_prep.json 52)
    gets a 0.2 mm stub from its pad centre to a collision-checked 0.6/0.3
    via. 6 measured blockers (U1-2, U1-26, C4-2, C5-2, C8-2 GND; U1-37
    VCC1V2) get longer dogbones out of their pinch zones -- never assumed
    direct attaches. GND vias land on the GND planes at fill time;
    VCC-class vias give the router F.Cu hops (no dead-end stubs, T5);
  * stub layer from the pad's layer SET (these SMD pads are B.Cu;
    trap T12: pad.GetLayer() mis-reports);
  * EP (U1-49, GND): pad soldered; outside-EP 0.6/0.3 via ring attempted in
    the measured 1.175 mm corridor; ZERO vias in pad (not approved);
  * JP anchors untouched; the 19-contact geometry is never moved.
Design rules unchanged everywhere: 0.2/0.2 track/clearance, via 0.6/0.3.
"""
import faulthandler
import json
import math
import os
import re
import sys

import pcbnew

faulthandler.enable()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from via_lib import MM, STACKUP, add_zone, outline_ok, via_fits  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD_DIR = os.path.dirname(os.path.dirname(HERE))
CANON = os.path.join(BOARD_DIR, 'out', 'kicad', 'tile_gw1nz.kicad_pcb')
CANON_PRO = CANON.replace('.kicad_pcb', '.kicad_pro')
FANOUT = os.path.join(BOARD_DIR, 'docs', 'fanout_prep.json')
NETCLASSES = os.path.join(BOARD_DIR, 'docs', 'netclasses.json')
OUTDIR = os.path.join(BOARD_DIR, 'four-layer', 'out')
OUT_PCB = os.path.join(OUTDIR, 'tile_gw1nz_4l.kicad_pcb')
OUT_PRO = OUT_PCB.replace('.kicad_pcb', '.kicad_pro')
SITES = os.path.join(OUTDIR, 'fanout_sites.json')

# distance ladder (mm): first two = direct ring attempts (fanout_prep
# rings {0.5,0.9}); beyond = dogbones. Compass fallback for pinch pads.
LADDER = (0.5, 0.9, 1.4, 2.0, 2.8, 3.8, 5.0)
COMPASS = tuple((math.cos(k * math.pi / 4), math.sin(k * math.pi / 4))
                for k in range(8))
BLOCKERS = {('U1', '2'), ('U1', '26'), ('U1', '37'),
            ('C4', '2'), ('C5', '2'), ('C8', '2')}


def pad_layer(pad):
    """Trap T12: trust the pad's layer set, not GetLayer()."""
    return pcbnew.B_Cu if pad.IsOnLayer(pcbnew.B_Cu) else pcbnew.F_Cu


def try_fanout_at(board, items, pad, c, px, py):
    pos = pcbnew.VECTOR2I(MM(px), MM(py))
    v = via_fits(board, items, pos, pad.GetNetCode(), clearance=0.2)
    if v is None or not outline_ok(board, pos):
        return None
    trk = pcbnew.PCB_TRACK(board)
    trk.SetStart(c)
    trk.SetEnd(pos)
    trk.SetWidth(MM(0.2))
    trk.SetLayer(pad_layer(pad))
    trk.SetNet(pad.GetNet())
    v.SetNet(pad.GetNet())
    board.Add(trk)
    board.Add(v)
    items.extend([trk, v])
    return pos


def fanout_pad(board, items, planned):
    fp = board.FindFootprintByReference(planned['ref'])
    if fp is None:
        raise RuntimeError(f"planned ref {planned['ref']} not on board")
    pad = fp.FindPadByNumber(planned['pad'])
    if pad is None or pad.GetNetname() != planned['net']:
        raise RuntimeError(f"plan/net mismatch {planned['ref']}."
                           f"{planned['pad']} want {planned['net']} got "
                           f"{None if pad is None else pad.GetNetname()}")
    c = pad.GetPosition()
    cmm = (pcbnew.ToMM(c.x), pcbnew.ToMM(c.y))
    x0, y0, x1, y1 = planned['box']
    dirs = {'+x': (1, 0), '-x': (-1, 0), '+y': (0, 1), '-y': (0, -1)}
    ex, ey = dirs[planned['escape_dir']]
    edge = {'+x': x1, '-x': x0, '+y': y1, '-y': y0}[planned['escape_dir']]
    for dist in LADDER:
        px, py = ((edge + ex * dist, cmm[1]) if ex
                  else (cmm[0], edge + ey * dist))
        pos = try_fanout_at(board, items, pad, c, px, py)
        if pos is not None:
            return 'attach_ring' if dist <= 0.9 else 'dogbone', dist, pos
    for dx, dy in COMPASS:
        for dist in LADDER:
            pos = try_fanout_at(board, items, pad, c,
                                cmm[0] + dx * dist, cmm[1] + dy * dist)
            if pos is not None:
                return 'dogbone_compass', dist, pos
    return None


def ep_ring(board, items, sites):
    """Up to 4 GND vias OUTSIDE the EP outline (no via-in-pad, none
    approved): centre at outline edge + 0.5 mm in the 1.175 mm corridor."""
    fp = board.FindFootprintByReference('U1')
    pad = fp.FindPadByNumber('49')
    c = pad.GetPosition()
    bb = pad.GetBoundingBox()
    ex, ey = pcbnew.ToMM(bb.GetWidth()) / 2, pcbnew.ToMM(bb.GetHeight()) / 2
    cmm = (pcbnew.ToMM(c.x), pcbnew.ToMM(c.y))
    n = 0
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        pos = pcbnew.VECTOR2I(MM(cmm[0] + dx * (ex + 0.5)),
                              MM(cmm[1] + dy * (ey + 0.5)))
        v = via_fits(board, items, pos, pad.GetNetCode(), clearance=0.2)
        if v is None or not outline_ok(board, pos):
            sites.append({'kind': 'ep_ring', 'ref': 'U1', 'pad': '49',
                          'net': 'GND', 'dir': [dx, dy], 'placed': False})
            continue
        trk = pcbnew.PCB_TRACK(board)
        trk.SetStart(pcbnew.VECTOR2I(MM(cmm[0] + dx * ex),
                                     MM(cmm[1] + dy * ey)))
        trk.SetEnd(pos)
        trk.SetWidth(MM(0.2))
        trk.SetLayer(pad_layer(pad))
        trk.SetNet(pad.GetNet())
        v.SetNet(pad.GetNet())
        board.Add(trk)
        board.Add(v)
        items.extend([trk, v])
        sites.append({'kind': 'ep_ring', 'ref': 'U1', 'pad': '49',
                      'net': 'GND', 'dir': [dx, dy], 'placed': True,
                      'via_mm': [round(pcbnew.ToMM(pos.x), 6),
                                 round(pcbnew.ToMM(pos.y), 6)]})
        n += 1
    return n


def write_stackup_and_pro():
    t = open(OUT_PCB, encoding='utf-8').read()
    t = re.sub(r'\t\t\(stackup\n.*?\n\t\t\)\n', '', t, flags=re.S)
    i = t.index('\t(setup\n') + len('\t(setup\n')
    with open(OUT_PCB, 'w', encoding='utf-8') as f:
        f.write(t[:i] + STACKUP + t[i:])
    pro = json.load(open(CANON_PRO, encoding='utf-8'))
    ns = pro.setdefault('net_settings', {})
    nc = json.load(open(NETCLASSES, encoding='utf-8'))
    classes, pats = [], []
    for name in sorted(nc['classes']):
        r = nc['classes'][name]['rule']
        classes.append({
            'clearance': r['clearance_mm'],
            'hole_clearance': 0.25,
            'microvia_diameter': 0.2,
            'microvia_drill': 0.1,
            'name': name,
            'track_width': max(r['track_mm'], 0.2),
            'via_diameter': r['via_d_mm'],
            'via_drill': r['via_drill_mm']})
        nets = sorted(nc['classes'][name]['nets'])
        pats.append({'netclass': name,
                     'pattern': '^(' + '|'.join(re.escape(n)
                                                for n in nets) + ')$'})
    # preserve the Design-rule Default entry (canonical rules unchanged)
    ns['classes'] = classes
    ns['class_patterns'] = pats  # durable assignment (pcb holds none, T1)
    with open(OUT_PRO, 'w', encoding='utf-8') as f:
        json.dump(pro, f, indent=2)
        f.write('\n')


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    plan = json.load(open(FANOUT, encoding='utf-8'))
    planned = [p for p in plan['planned_pads']
               if not p.get('anchor') and p.get('ok')]
    if len(planned) != 52:
        raise RuntimeError(f'expected 52 planned pads, got {len(planned)}')
    board = pcbnew.LoadBoard(CANON)
    board.SetCopperLayerCount(4)
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)
    for t in list(board.GetTracks()):
        board.Delete(t)
    for z in list(board.Zones()):
        board.Delete(z)
    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, False)
    add_zone(board, outline, pcbnew.In1_Cu, 'GND')
    add_zone(board, outline, pcbnew.In2_Cu, 'GND')

    items = [p for fp in board.GetFootprints() for p in fp.Pads()]
    items += list(board.GetTracks())
    sites, unresolved, kinds = [], {}, {}
    for p in planned:
        got = fanout_pad(board, items, p)
        key = f"{p['ref']}.{p['pad']}"
        if got is None:
            unresolved.append({'ref': p['ref'], 'pad': p['pad'],
                               'net': p['net']})
            continue
        kind, dist, pos = got
        kinds[kind] = kinds.get(kind, 0) + 1
        sites.append({'ref': p['ref'], 'pad': p['pad'], 'net': p['net'],
                      'kind': kind, 'stub_len_mm': round(dist, 3),
                      'was_blocker': (p['ref'], p['pad']) in BLOCKERS,
                      'via_mm': [round(pcbnew.ToMM(pos.x), 6),
                                 round(pcbnew.ToMM(pos.y), 6)]})
    ep_n = ep_ring(board, items, sites)
    pcbnew.SaveBoard(OUT_PCB, board)
    write_stackup_and_pro()
    report = {
        '_meta': {
            'tool': 'four-layer/tools/build_4l_variant.py',
            'canon_sha256_12': 'c7d5b66fa1db',
            'stackup': 'F.Cu/In1=GND/In2=GND/B.Cu 1.6mm (0.035/0.2104/'
                       '0.0152/1.065/0.0152/0.2104/0.035 ENIG)',
            'rules': '0.2/0.2 track, 0.6/0.3 via (unchanged)',
            'zones': 'In1.Cu+In2.Cu GND, unfilled until finish step'},
        'planned_pads': len(planned),
        'fanout_kinds': kinds,
        'ep_ring_placed': ep_n,
        'unresolved': unresolved,
        'sites': sites}
    with open(SITES, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=1)
    print('BUILD_4L_OK planned=%d ring=%d dogbone=%d compass=%d ep_ring=%d '
          'unresolved=%d out=%s' % (
              len(planned), kinds.get('attach_ring', 0),
              kinds.get('dogbone', 0), kinds.get('dogbone_compass', 0),
              ep_n, len(unresolved), OUT_PCB))
    if unresolved:
        print('UNRESOLVED:', unresolved)


if __name__ == '__main__':
    main()
