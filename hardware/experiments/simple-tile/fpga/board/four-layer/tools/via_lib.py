# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Shared pcbnew helpers for the four-layer tile variant (FPGA-02).

Adapted from the proven discrete recipe
(discrete-spld/layout/build_4layer.py + finish_4layer.py). Run inside the
KiCad flatpak:

    flatpak run --filesystem=<repo> --command=python3 org.kicad.KiCad <script>

Design rules unchanged: 0.2/0.2 track/clearance, via 0.6/0.3, hole-hole
0.25, copper-edge 0.3 (variant margins measured at 0.6 conservatively).
"""
import math

import pcbnew

MM = pcbnew.FromMM

# 1.6 mm construction: 2x 0.2104 prepreg + 1.065 core + 2x0.035 outer +
# 2x0.0152 inner copper = 1.5812 mm + 2x0.01 mask = 1.6012 mm.
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


def add_zone(board, outline, layer, netname, priority=0):
    """Zone on the full stepped outline; filled later (after routing)."""
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net(board, netname))
    for i in range(outline.OutlineCount()):
        z.Outline().AddOutline(outline.Outline(i))
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
        if not outline.Contains(pcbnew.VECTOR2I(pos.x + MM(dx),
                                                pos.y + MM(dy))):
            return False
    return True


def via_fits(board, items, pos, netcode, extra=None, clearance=0.2):
    """0.6/0.3 via candidate at pos, collision-checked on all 4 copper
    layers against pads/tracks/vias, with drill-to-drill spacing. Same-net
    pad overlap is rejected (keeps vias OUT OF pads: no via-in-pad)."""
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pos)
    via.SetWidth(MM(0.6))
    via.SetDrill(MM(0.3))
    cands = [(via, pcbnew.F_Cu), (via, pcbnew.In1_Cu),
             (via, pcbnew.In2_Cu), (via, pcbnew.B_Cu)] + (extra or [])
    for it in items:
        same_pad = isinstance(it, pcbnew.PAD) and it.GetNetCode() == netcode
        if it.GetNetCode() == netcode and not same_pad:
            continue
        if same_pad:
            if it.IsOnLayer(pcbnew.F_Cu) or it.IsOnLayer(pcbnew.B_Cu):
                lay = pcbnew.F_Cu if it.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
                if via.GetEffectiveShape(lay).Collide(
                        it.GetEffectiveShape(lay), MM(0.3)):
                    return None
            continue
        for cand, lay in cands:
            if it.IsOnLayer(lay) and cand.GetEffectiveShape(lay).Collide(
                    it.GetEffectiveShape(lay), MM(clearance)):
                return None
    for it in items:
        if isinstance(it, pcbnew.PCB_VIA) or (isinstance(it, pcbnew.PAD)
                                              and it.HasHole()):
            if (it.GetPosition() - pos).EuclideanNorm() < MM(0.3 + 0.25) + (
                    it.GetDrillSizeX() if isinstance(it, pcbnew.PAD)
                    else it.GetDrill()) / 2 + MM(0.15):
                return None
    return via
