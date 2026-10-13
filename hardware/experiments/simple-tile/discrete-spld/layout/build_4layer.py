#!/usr/bin/env python3
"""4-layer routing build for the discrete-spld variant-A tile.

Run with KiCad's python:
  flatpak run --filesystem=<repo> --command=python3 org.kicad.KiCad \
      layout/build_4layer.py

Input : boards/variant_a/tile_variant_a.kicad_pcb  (fixed placement baseline,
        0 DRC errors, unrouted, NET-BINDING PASS)
Output: layout/tile_variant_a_4l.kicad_pcb  (same design, 4 copper layers),
        layout/tile_variant_a_4l.dsn        (Specctra for the autorouter)

What it does (recipe follows the proven rev-B pipeline,
hardware/kicad/tile/scripts/revb_pcb.py):
  * 4 copper layers: F.Cu signal, In1.Cu = GND plane, In2.Cu = VCC plane,
    B.Cu signal (plane layers typed LT_POWER);
  * GND/VCC zones with the full stepped outline on the inner layers
    (filled only AFTER routing, like rev-B);
  * SMD power fan-out BEFORE routing (stub + 0.6/0.3 via per GND/VCC pad):
    Freerouting cannot attach SMD pads to plane layers itself;
  * generic 1.6 mm 4-layer stack-up block written into (setup).
Design rules are NOT relaxed: the board keeps KiCad's default rule set
(DRC clearance 0.2 mm as reported by kicad-cli); before/after DRC runs are
saved for comparison.
"""
import math
import os
import re
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD_IN = os.path.join(HERE, '..', 'boards', 'variant_a',
                        'tile_variant_a.kicad_pcb')
BOARD_OUT = os.path.join(HERE, 'tile_variant_a_4l.kicad_pcb')
DSN_OUT = os.path.join(HERE, 'tile_variant_a_4l.dsn')
MM = pcbnew.FromMM

POWER = ('VCC', 'GND')

STACKUP = """\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen"))
\t\t\t(layer "F.Paste" (type "Top Solder Paste"))
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 1" (type "prepreg") (thickness 0.2104) (material "FR4") (epsilon_r 4.4) (loss_tangent 0.02))
\t\t\t(layer "In1.Cu" (type "copper") (thickness 0.0152))
\t\t\t(layer "dielectric 2" (type "core") (thickness 1.065) (material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))
\t\t\t(layer "In2.Cu" (type "copper") (thickness 0.0152))
\t\t\t(layer "dielectric 3" (type "prepreg") (thickness 0.2104) (material "FR4") (epsilon_r 4.4) (loss_tangent 0.02))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))
\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen"))
\t\t\t(copper_finish "ENIG")
\t\t\t(dielectric_constraints no)
\t\t)
"""


def net(board, name):
    n = board.FindNet(name)
    if n is None:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
    return n


def add_zone(board, poly, layer, netname, priority=0):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net(board, netname))
    for i in range(poly.OutlineCount()):
        z.Outline().AddOutline(poly.Outline(i))
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(MM(0.25))
    z.SetMinThickness(MM(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)
    z.SetThermalReliefGap(MM(0.3))
    z.SetThermalReliefSpokeWidth(MM(0.35))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.Add(z)
    return z


def outline_ok(board, pos, margin=0.6):
    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, False)
    for dx, dy in ((margin, 0), (-margin, 0), (0, margin), (0, -margin)):
        if not outline.Contains(pcbnew.VECTOR2I(pos.x + MM(dx), pos.y + MM(dy))):
            return False
    return True


def via_fits(board, items, pos, netcode, extra=None, clearance=0.2):
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pos)
    via.SetWidth(MM(0.6))
    via.SetDrill(MM(0.3))
    cands = [(via, pcbnew.F_Cu), (via, pcbnew.In1_Cu), (via, pcbnew.In2_Cu),
             (via, pcbnew.B_Cu)] + (extra or [])
    for it in items:
        same_pad = isinstance(it, pcbnew.PAD) and it.GetNetCode() == netcode
        if it.GetNetCode() == netcode and not same_pad:
            continue
        if same_pad:
            if it.IsOnLayer(pcbnew.F_Cu) or it.IsOnLayer(pcbnew.B_Cu):
                lay = pcbnew.F_Cu if it.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
                if via.GetEffectiveShape(lay).Collide(it.GetEffectiveShape(lay), MM(0.3)):
                    return None
            continue
        for cand, lay in cands:
            if it.IsOnLayer(lay) and cand.GetEffectiveShape(lay).Collide(
                    it.GetEffectiveShape(lay), MM(clearance)):
                return None
    for it in items:
        if isinstance(it, pcbnew.PCB_VIA) or (isinstance(it, pcbnew.PAD) and it.HasHole()):
            if (it.GetPosition() - pos).EuclideanNorm() < MM(0.3 + 0.25) + (
                    it.GetDrillSizeX() if isinstance(it, pcbnew.PAD) else it.GetDrill()) / 2 + MM(0.15):
                return None
    return via


def fanout_power(board):
    """Every SMD pad on a power net gets a short stub + via into the planes
    BEFORE routing, so the router works around the vias (rev-B lesson).
    Pass 1 uses the tight ladder (<=5 mm); leftover pads in the crowded
    strips get one retry pass with an extended ladder (<=8 mm); anything
    still open is printed and returned (never silently skipped)."""
    items = [p for fp in board.GetFootprints() for p in fp.Pads()]
    items += list(board.GetTracks())

    def targets():
        out = []
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if (pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
                        and pad.GetNetname() in POWER):
                    out.append((fp, pad))
        return out

    def density(fp, pad):
        """local copper crowding: pads within 3 mm of this pad."""
        c = pad.GetPosition()
        n = 0
        for f2 in board.GetFootprints():
            for p2 in f2.Pads():
                if (p2.GetPosition() - c).EuclideanNorm() < MM(3.0):
                    n += 1
        return n

    added = 0
    # worst-first: crowded pads fan out before their corridors are taken
    pending = sorted(targets(), key=lambda fp_pad: -density(*fp_pad))
    for ladder_i, ladder in enumerate(
            ((0.65, 0.9, 1.2, 1.5, 1.9, 2.4, 2.9, 3.5, 4.2, 5.0),
             (0.65, 0.9, 1.2, 1.5, 1.9, 2.4, 2.9, 3.5, 4.2, 5.0, 6.0, 8.0),
             (0.65, 0.9, 1.2, 1.5, 1.9, 2.4, 2.9, 3.5, 4.2, 5.0, 6.0, 8.0))):
        still = []
        for fp, pad in pending:
            layer = pcbnew.F_Cu if pad.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
            c = pad.GetPosition()
            half = max(pad.GetSizeX(), pad.GetSizeY()) / 2
            done = False
            for dist in ladder:
                for k in range(48):
                    a = 2 * math.pi * k / 48
                    pos = pcbnew.VECTOR2I(int(c.x + math.cos(a) * (half + MM(dist))),
                                          int(c.y + math.sin(a) * (half + MM(dist))))
                    trk = pcbnew.PCB_TRACK(board)
                    trk.SetStart(c)
                    trk.SetEnd(pos)
                    trk.SetWidth(MM(0.25))
                    trk.SetLayer(layer)
                    trk.SetNet(pad.GetNet())
                    via = via_fits(board, items, pos, pad.GetNetCode(),
                                   extra=[(trk, layer)])
                    if via is not None and outline_ok(board, pos):
                        via.SetNet(pad.GetNet())
                        board.Add(trk)
                        board.Add(via)
                        items += [trk, via]
                        added += 1
                        done = True
                        break
                if done:
                    break
            if not done:
                still.append((fp, pad))
        pending = still
        if not pending:
            break
    print(f'fanout vias added: {added}')
    for fp, pad in pending:
        print('fanout: no room for', fp.GetReference(), pad.GetNumber(),
              pad.GetNetname())
    return added, [f'{fp.GetReference()}.{pad.GetNumber()}'
                   for fp, pad in pending]


def write_stackup(path):
    t = open(path, encoding='utf-8').read()
    t = re.sub(r'\t\t\(stackup\n.*?\n\t\t\)\n', '', t, flags=re.S)
    i = t.index('\t(setup\n') + len('\t(setup\n')
    open(path, 'w', encoding='utf-8').write(t[:i] + STACKUP + t[i:])


def apply_errata(board, path):
    """Rebind the rail pins listed in errata_rails.json (G1 circuit gap).
    Every rebind is printed - nothing silent.
    Retired 2026-10-13: gen_circuits.py now consumes the devices' 'power'
    pin tables, so the canonical circuit JSON carries the rail pins itself;
    when the overlay file is absent this is a no-op."""
    import json
    if not os.path.exists(path):
        print('errata overlay absent (canonical circuit carries rails) - skipped')
        return 0
    ed = json.load(open(path))
    err = ed.get('variant_a', ed)
    pins = err['pins']
    n = 0
    for e in pins:
        fp = board.FindFootprintByReference(e['ref'])
        if fp is None:
            raise RuntimeError(f"errata: {e['ref']} not on board")
        pad = fp.FindPadByNumber(e['pin'])
        if pad is None:
            raise RuntimeError(f"errata: {e['ref']}.{e['pin']} not found")
        old = pad.GetNetname()
        pad.SetNet(net(board, e['net']))
        print(f"errata: {e['ref']}.{e['pin']} {old or '<no net>'} -> {e['net']}")
        n += 1
    print(f'errata applied: {n} rail pins rebound')
    return n


def main():
    board = pcbnew.LoadBoard(BOARD_IN)
    board.SetCopperLayerCount(4)
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)
    for t in list(board.GetTracks()):
        board.Delete(t)
    for z in list(board.Zones()):
        board.Delete(z)

    apply_errata(board, os.path.join(HERE, 'errata_rails.json'))

    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, False)
    add_zone(board, outline, pcbnew.In1_Cu, 'GND')
    add_zone(board, outline, pcbnew.In2_Cu, 'VCC')
    fanout_power(board)

    pcbnew.SaveBoard(BOARD_OUT, board)
    write_stackup(BOARD_OUT)
    board = pcbnew.LoadBoard(BOARD_OUT)
    pcbnew.ExportSpecctraDSN(board, DSN_OUT)
    print('stage done:', BOARD_OUT, 'and DSN', DSN_OUT)


if __name__ == '__main__':
    main()
