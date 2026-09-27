#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Rev C concept board: single-board tile on the minimum equilateral lattice for Cherry MX.

    flatpak run --filesystem="$PWD" --command=python3 org.kicad.KiCad \
        hardware/kicad/tile/scripts/revc_build.py            # stage 1 -> DSN
    ... Freerouting on production/revc18/revc18.dsn ...
    flatpak run ... revc_build.py --route-in production/revc18/revc18.ses   # stage 2

Geometry (key-board frame of rev A/B, y down):
  * MX body 15.6 mm (Cherry datasheet) + 0.3 mm -> row pitch r = 15.935 mm, key pitch
    p = r / (sqrt(3)/2) = 18.4 mm (equilateral, every neighbour 18.4 mm away);
  * 4 x 3 keys, rows shifted by p/2 to the left going down (same topology as rev A/B);
  * stepped outline with a G = 1.0 mm gap to every neighbour (left/right and top/bottom);
    left-side row steps sit G/2 lower and right-side steps G/2 higher, so the step
    segments also keep the gap (as in rev A: 62 vs 61 mm);
  * tile lattice: right (+4p, 0) = (+73.6, 0), up (+p/2, -3r) = (+9.2, -47.8) mm.
Electronics: the rev-B logic (same ICs; U103/U104/U109 in TSSOP-16, C105 as 1210 ceramic) folded on
the bottom; stacking-connector nets merged 1:1; J101-J104 replaced by contact rows
(1.27 mm pitch) with the same pin order and nets:
  right: 6 spring contacts (active)   left: 6 edge pads (passive)    -> mate along x
  bottom: 8 spring contacts (active)  top: 8 edge pads (passive, castellations) -> along y
Top contacts sit p/2 to the right of the bottom ones (the up-lattice shift).
"""
import importlib.util
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
OUT = os.path.join(ROOT, "production", "revc18")
BRD = os.path.join(OUT, "revc18.kicad_pcb")
MM, TOMM = pcbnew.FromMM, pcbnew.ToMM
spec = importlib.util.spec_from_file_location("revb", os.path.join(HERE, "revb_pcb.py"))
revb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(revb)

BODY = 15.6 + 0.3
R = BODY                                   # row pitch
P = R / (math.sqrt(3) / 2)                 # key pitch (18.40)
G = 1.0                                    # gap to the neighbouring tile
X0, Y0 = 135.92, 53.08                     # top-left key centre (as rev A/B)
OLD_P, OLD_R = 20.0, 20.0 * math.sqrt(3) / 2
PITCH_C = 1.27                             # contact pitch


def key_xy(k, i):
    return X0 + i * P - k * P / 2, Y0 + k * R


def outline():
    xl = [X0 - k * P / 2 - P / 2 + G / 2 for k in range(3)]
    xr = [X0 - k * P / 2 + 3 * P + P / 2 - G / 2 for k in range(3)]
    top, bot = Y0 - R / 2 + G / 2, Y0 + 2.5 * R - G / 2
    b01, b12 = Y0 + R / 2, Y0 + 1.5 * R
    return [(xl[0], top), (xr[0], top), (xr[0], b01 - G / 2), (xr[1], b01 - G / 2),
            (xr[1], b12 - G / 2), (xr[2], b12 - G / 2), (xr[2], bot), (xl[2], bot),
            (xl[2], b12 + G / 2), (xl[1], b12 + G / 2), (xl[1], b01 + G / 2), (xl[0], b01 + G / 2)]


def contact_rows():
    """(ref, kind, [(x, y)], pad (w, h), courtyard depth, side) for the four edges."""
    pts = outline()
    xr1, xl1 = pts[3][0], pts[10][0]
    c1 = Y0 + R
    top, bot = pts[0][1], pts[6][1]
    ys = [c1 + 0.5 + j * PITCH_C for j in range(6)]            # below the row-1 centre
    xb = X0 + 0.5 * P - P / 2 + P / 2                           # between row-2 keys 1 and 2
    xb = key_xy(2, 1)[0] + P / 2
    xs_b = [xb + 3.5 * PITCH_C - j * PITCH_C for j in range(8)]  # pin 1 at the highest x
    xs_t = [x + P / 2 for x in xs_b]
    return [("C1", "J104", [(xr1 - 1.35, y) for y in ys], (2.0, 0.8), 3.0, "right"),
            ("C2", "J101", [(xl1 + 0.45, y) for y in ys], (0.7, 0.8), 1.0, "left"),
            ("C3", "J103", [(x, bot - 1.35) for x in xs_b], (0.8, 2.0), 3.0, "bottom"),
            ("C4", "J102", [(x, top + 0.3) for x in xs_t], (0.8, 0.4), 0.55, "top")]


def make_contacts(board, nets_by_conn):
    for ref, conn, pts, (w, h), depth, side in contact_rows():
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(ref)
        fp.SetValue(f"contacts {side} (was {conn})")
        fp.SetFPID(pcbnew.LIB_ID("revc", f"EdgeContacts_{side}"))
        board.Add(fp)
        fp.SetPosition(pcbnew.VECTOR2I(MM(pts[0][0]), MM(pts[0][1])))
        fp.SetLayer(pcbnew.B_Cu)
        for n, (x, y) in enumerate(pts, start=1):
            pad = pcbnew.PAD(fp)
            pad.SetNumber(str(n))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I(MM(w), MM(h)))
            ls = pcbnew.LSET()
            ls.AddLayer(pcbnew.B_Cu); ls.AddLayer(pcbnew.B_Mask)
            if side in ("right", "bottom"):
                ls.AddLayer(pcbnew.B_Paste)
            pad.SetLayerSet(ls)
            if side in ("left", "top"):
                # passive half: pads that reach the board edge (castellations / edge plating)
                pad.SetProperty(pcbnew.PAD_PROP_CASTELLATED)
            fp.Add(pad)
            pad.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
            name = nets_by_conn[conn].get(str(n))
            if name:
                pad.SetNet(revb.net(board, name))
        # courtyard: the contact row plus its body depth into the board
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        if side == "right":
            box = (max(xs) + w / 2 - depth, min(ys) - h / 2 - .2, max(xs) + w / 2 + .2, max(ys) + h / 2 + .2)
        elif side == "left":
            box = (min(xs) - w / 2 - .2, min(ys) - h / 2 - .2, min(xs) - w / 2 + depth, max(ys) + h / 2 + .2)
        elif side == "bottom":
            box = (min(xs) - w / 2 - .2, max(ys) + h / 2 - depth, max(xs) + w / 2 + .2, max(ys) + h / 2 + .2)
        else:
            box = (min(xs) - w / 2 - .2, min(ys) - h / 2 - .2, max(xs) + w / 2 + .2, min(ys) - h / 2 + depth)
        for (a, b), (c, d) in (((box[0], box[1]), (box[2], box[1])), ((box[2], box[1]), (box[2], box[3])),
                               ((box[2], box[3]), (box[0], box[3])), ((box[0], box[3]), (box[0], box[1]))):
            s = pcbnew.PCB_SHAPE(fp)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(pcbnew.VECTOR2I(MM(a), MM(b))); s.SetEnd(pcbnew.VECTOR2I(MM(c), MM(d)))
            s.SetLayer(pcbnew.B_CrtYd); s.SetWidth(MM(0.05))
            fp.Add(s)
        fp.SetBoardOnly(True)
        fp.SetExcludedFromBOM(True)
        fp.SetExcludedFromPosFiles(True)
        if side in ("left", "top"):
            # edge pads sit inside the router's board-edge keep-out: give each one a short
            # stub towards the inside, so the router can reach it
            for pad in fp.Pads():
                c = pad.GetPosition()
                if side == "left":
                    a = pcbnew.VECTOR2I(c.x + MM(w / 2 - 0.05), c.y)
                    b = pcbnew.VECTOR2I(c.x + MM(w / 2 + 0.9), c.y)
                else:
                    a = pcbnew.VECTOR2I(c.x, c.y + MM(h / 2 - 0.05))
                    b = pcbnew.VECTOR2I(c.x, c.y + MM(h / 2 + 0.9))
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(a); t.SetEnd(b); t.SetWidth(MM(0.25)); t.SetLayer(pcbnew.B_Cu)
                t.SetNet(pad.GetNet())
                board.Add(t)


def keepout_circle(board, centre, radius):
    """Rule area (no tracks, no vias) around a fiducial; exported to the router as keep-out."""
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True); z.SetDoNotAllowVias(True); z.SetDoNotAllowPads(False)
    z.SetDoNotAllowZoneFills(False); z.SetDoNotAllowFootprints(False)
    ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.B_Cu)
    z.SetLayerSet(ls)
    o = z.Outline(); o.NewOutline()
    for k in range(16):
        a = 2 * math.pi * k / 16
        o.Append(int(centre.x + MM(radius) * math.cos(a)), int(centre.y + MM(radius) * math.sin(a)))
    board.Add(z)


def stage1():
    os.makedirs(OUT, exist_ok=True)
    board = pcbnew.LoadBoard(os.path.join(ROOT, "hardware", "kicad", "tile", "isomorphic_tile.kicad_pcb"))
    # nets of the connectors that disappear
    nets_by_conn = {}
    for c in ("J101", "J102", "J103", "J104"):
        nets_by_conn[c] = {p.GetNumber(): p.GetNetname() for p in board.FindFootprintByReference(c).Pads()}
    canon = {"VCC_T": "VCC", "GND_T": "GND"}
    for a, b in (("J105", "J107"), ("J106", "J108")):
        fa, fb = board.FindFootprintByReference(a), board.FindFootprintByReference(b)
        for p in fa.Pads():
            kn = fb.FindPadByNumber(p.GetNumber()).GetNetname()
            c = canon.get(kn, kn)
            canon[p.GetNetname()] = c; canon[kn] = c
    for c in nets_by_conn:
        nets_by_conn[c] = {k: canon.get(v, v) for k, v in nets_by_conn[c].items()}
    # stack offset (logic -> key board)
    pa = {p.GetNumber(): p.GetPosition() for p in board.FindFootprintByReference("J105").Pads()}
    pb = {p.GetNumber(): p.GetPosition() for p in board.FindFootprintByReference("J107").Pads()}
    off = pcbnew.VECTOR2I(int(sum((pb[k] - pa[k]).x for k in pa) / len(pa)),
                          int(sum((pb[k] - pa[k]).y for k in pa) / len(pa)))

    for t in list(board.GetTracks()):
        board.Delete(t)
    for z in list(board.Zones()):
        board.Delete(z)
    for d in list(board.GetDrawings()):
        board.Delete(d)
    for fp in list(board.GetFootprints()):
        r = fp.GetReference()
        if r in ("J101", "J102", "J103", "J104", "J105", "J106", "J107", "J108") or r.startswith(("MB", "FID")):
            board.Delete(fp)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            c = canon.get(p.GetNetname())
            if c and c != p.GetNetname():
                p.SetNet(revb.net(board, c))

    # switches on the new lattice (index from the old lattice)
    for fp in board.GetFootprints():
        if not fp.GetReference().startswith("SW"):
            continue
        c = revb.switch_centre(fp)
        x, y = TOMM(c.x), TOMM(c.y)
        k = round((y - Y0) / OLD_R)
        i = round((x - (X0 - k * OLD_P / 2)) / OLD_P)
        nx, ny = key_xy(k, i)
        fp.SetPosition(fp.GetPosition() + pcbnew.VECTOR2I(MM(nx) - c.x, MM(ny) - c.y))

    # outline
    pts = outline()
    for (a, b), (c_, d) in zip(pts, pts[1:] + pts[:1]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(MM(a), MM(b))); s.SetEnd(pcbnew.VECTOR2I(MM(c_), MM(d)))
        s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(MM(0.05))
        board.Add(s)

    # logic: fold onto the bottom, smaller packages where needed
    old_centre = (125.96 + 30, 70.40)
    new_centre = (key_xy(1, 0)[0] + 1.5 * P, Y0 + R)
    logic = [fp for fp in board.GetFootprints() if TOMM(fp.GetPosition().y) > 100]
    for fp in logic:
        fp.SetPosition(fp.GetPosition() + off)
        fp.SetLayerAndFlip(pcbnew.B_Cu)
    for ref, fpid in (("U109", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm"),
                      ("U103", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm"),
                      ("U104", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm"),
                      ("C105", "Capacitor_SMD:C_1210_3225Metric")):
        old = board.FindFootprintByReference(ref)
        new = revb.load_fp(fpid)
        board.Add(new)
        new.SetPosition(old.GetPosition()); new.SetLayerAndFlip(pcbnew.B_Cu)
        new.SetReference(ref); new.SetValue(old.GetValue())
        for f in old.GetFields():
            if f.GetName() not in ("Reference", "Value", "Footprint"):
                new.SetField(f.GetName(), f.GetText())
        new.SetPath(old.GetPath()); new.SetSheetname(old.GetSheetname()); new.SetSheetfile(old.GetSheetfile())
        for p in new.Pads():
            q = old.FindPadByNumber(p.GetNumber())
            if q is not None:
                p.SetNet(q.GetNet())
        board.Delete(old)
    make_contacts(board, nets_by_conn)

    outline_poly = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline_poly, False)
    placer = revb.Placer(board, outline_poly)
    order = ["U103", "U104", "U109", "U101", "U107", "U102", "U106", "U108", "U105"] + \
            [f"R20{i}" for i in range(1, 8)] + [f"C20{i}" for i in range(1, 10)] + \
            ["C105", "C103", "C104", "C101", "C102"] + [f"R10{i}" for i in range(1, 10)] + \
            [f"R{n}" for n in range(110, 134)]
    failed = []
    for r in order:
        fp = board.FindFootprintByReference(r)
        x, y = TOMM(fp.GetPosition().x), TOMM(fp.GetPosition().y)
        tgt = (new_centre[0] + 0.92 * (x - old_centre[0]), new_centre[1] + 0.92 * (y - old_centre[1]))
        fp.SetPosition(pcbnew.VECTOR2I(MM(300), MM(300)))
        try:
            placer.place(fp, "B", tgt, "key", rmax=30)
        except RuntimeError:
            failed.append(r)
    for ref, tgt in (("FID1", (X0 - 4, Y0 - 4)), ("FID2", (key_xy(0, 3)[0] + 4, Y0 - 4)),
                     ("FID3", (key_xy(2, 0)[0], Y0 + 2 * R + 5))):
        f = revb.load_fp("Fiducial:Fiducial_1mm_Mask2mm")
        f.SetReference(ref); f.SetValue("Fiducial"); board.Add(f)
        for fpad in f.Pads():
            fpad.SetLocalClearance(MM(1.0))
        try:
            placer.place(f, "B", tgt, "key", rotations=(0,), rmax=15)
            keepout_circle(board, f.GetPosition(), 1.6)
        except RuntimeError:
            failed.append(ref)
    revb.mark_board_only(board)
    print("placement failed for:", failed or "none")

    board.SetCopperLayerCount(4)
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    # In1 = solid GND plane, In2 = solid VCC plane (a VCC pour around In2 signals broke into
    # islands in the first trial)
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)
    revb.add_zone(board, outline_poly, pcbnew.In1_Cu, "GND")
    revb.add_zone(board, outline_poly, pcbnew.In2_Cu, "VCC")
    revb.POWER = ("VCC", "GND")
    revb.fanout_power(board)
    pcbnew.SaveBoard(BRD, board)
    revb.write_stackup(BRD)
    import shutil
    shutil.copy(os.path.join(ROOT, "hardware", "kicad", "tile", "isomorphic_tile.kicad_pro"),
                os.path.join(OUT, "revc18.kicad_pro"))
    b = pcbnew.LoadBoard(BRD)
    pcbnew.ExportSpecctraDSN(b, os.path.join(OUT, "revc18.dsn"))
    print(f"stage 1 done: p = {P:.3f} mm, r = {R:.3f} mm, lattice right (+{4 * P:.2f}, 0), "
          f"up (+{P / 2:.2f}, -{3 * R:.2f})")


def stage2(ses):
    board = pcbnew.LoadBoard(BRD)
    if not pcbnew.ImportSpecctraSES(board, ses):
        sys.exit("SES import failed")
    outline_poly = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline_poly, False)
    revb.KEY_Y_MAX, revb.LOGIC_Y_MIN = 200, 300      # single board: no tab band to avoid
    # ground stitching over the whole board
    items = [p for fp in board.GetFootprints() for p in fp.Pads()] + list(board.GetTracks())
    gnd = board.FindNet("GND"); n = 0
    y = 40.0
    while y < 100:
        x = 100.0
        while x < 205:
            pos = pcbnew.VECTOR2I(MM(x), MM(y))
            if revb.outline_ok(board, pos, margin=1.0):
                v = revb.via_fits(board, items, pos, gnd.GetNetCode(), clearance=0.3)
                if v is not None:
                    v.SetNet(gnd); board.Add(v); items.append(v); n += 1
            x += 4.0
        y += 4.0
    print("stitching vias:", n)
    revb.add_zone(board, outline_poly, pcbnew.F_Cu, "GND")
    revb.add_zone(board, outline_poly, pcbnew.B_Cu, "GND")
    revb.fix_text_mirroring(board)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(BRD, board)
    print("stage 2 done")


if __name__ == "__main__":
    if "--route-in" in sys.argv:
        stage2(sys.argv[sys.argv.index("--route-in") + 1])
    else:
        stage1()
