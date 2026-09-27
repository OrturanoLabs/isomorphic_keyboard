#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Rev C concept, microcontroller tile (docs/architecture/revc-mcu-tile.md).

    flatpak run --filesystem="$PWD" --command=python3 org.kicad.KiCad \
        hardware/kicad/tile/scripts/revc_mcu_build.py            # stage 1 -> DSN
    (Freerouting, memory-capped) -> production/revc_mcu/revc_mcu.ses
    ... revc_mcu_build.py --route-in production/revc_mcu/revc_mcu.ses  # stage 2

Starts from the 18.36 mm rev-C board of revc_build.py (switches on the lattice, stepped
outline). Replaces the logic with: ATtiny1616 (SOIC-20W) at 5 V, 12 keys on internal
pull-ups (switch to GND), 4 edge data lines through 100 ohm, 12 SK6812MINI-E reverse-mount
LEDs south of each switch chained from one pin (+ 100 nF every 3 LEDs), a UPDI test pad,
and 5 contacts per edge in the symmetric order VCC GND DATA GND VCC.
Pins: PB2 = DATA_B (USART TX default), PA1 = DATA_R (USART TX alternate), PC0 = DATA_T,
PC1 = DATA_L, PC2 = LED, PA0 = UPDI; keys on PA2-PA7, PB0, PB1, PB3-PB5, PC3.
"""
import importlib.util
import os
import shutil
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
OUT = os.path.join(ROOT, "production", "revc_mcu")
BRD = os.path.join(OUT, "revc_mcu.kicad_pcb")
MM, TOMM = pcbnew.FromMM, pcbnew.ToMM


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


revb = _load("revb", os.path.join(HERE, "revb_pcb.py"))
revc = _load("revc", os.path.join(HERE, "revc_build.py"))
P, R, X0, Y0 = revc.P, revc.R, revc.X0, revc.Y0

# ATtiny1616-MNR VQFN-20 3x3 mm, 0.40 mm pitch, 1.7 mm exposed pad (DS40002204A 4.3, 39.4);
# the SOIC-20 wide version (about 13 x 10 mm) does not fit between the sockets and LEDs
PIN = {"PA2": 1, "PA3": 2, "GND": 3, "VDD": 4, "PA4": 5, "PA5": 6, "PA6": 7, "PA7": 8,
       "PB5": 9, "PB4": 10, "PB3": 11, "PB2": 12, "PB1": 13, "PB0": 14, "PC0": 15, "PC1": 16,
       "PC2": 17, "PC3": 18, "PA0": 19, "PA1": 20, "EP": 21}
KEY_PINS = ["PA2", "PA3", "PA4", "PA5", "PA6", "PA7", "PB0", "PB1", "PB3", "PB4", "PB5", "PC3"]
EDGE_PIN = {"B": "PB2", "R": "PA1", "T": "PC0", "L": "PC1"}
ORDER = ["VCC", "GND", "DATA", "GND", "VCC"]           # symmetric: orientation-proof


def add_fp(board, fpid, ref, value, pos=None, side="B", rot=0):
    fp = revb.load_fp(fpid)
    board.Add(fp)
    fp.SetReference(ref); fp.SetValue(value)
    if pos:
        fp.SetPosition(pcbnew.VECTOR2I(MM(pos[0]), MM(pos[1])))
    fp.SetOrientationDegrees(rot)
    if side == "B":
        fp.SetLayerAndFlip(pcbnew.B_Cu)
    return fp


def set_net(board, fp, pad, name):
    fp.FindPadByNumber(str(pad)).SetNet(revb.net(board, name))


def contacts(board):
    """Edge contacts (5 per edge). Right/bottom: springs; left/top: castellated edge pads.
    Top pads sit in the gaps between the row-0 sockets (2 per gap), the bottom springs
    exactly P/2 to the left (the up-lattice shift)."""
    pts = revc.outline()
    xr1, xl1, top, bot = pts[3][0], pts[10][0], pts[0][1], pts[6][1]
    c1 = Y0 + R
    ys = [c1 + 0.5 + j * 1.27 for j in range(5)]
    row0 = [revc.key_xy(0, i)[0] for i in range(4)]
    gaps = [c + 8.56 for c in row0[:3]]
    xt = sorted([g - 0.635 for g in gaps] + [g + 0.635 for g in gaps], reverse=True)[:5]
    xb = [x - P / 2 for x in xt]
    rows = [("C1", "R", [(xr1 - 1.35, y) for y in ys], (2.0, 0.8), "right"),
            ("C2", "L", [(xl1 + 0.45, y) for y in ys], (0.7, 0.8), "left"),
            ("C3", "B", [(x, bot - 1.35) for x in xb], (0.8, 2.0), "bottom"),
            ("C4", "T", [(x, top + 0.3) for x in xt], (0.8, 0.4), "top")]
    for ref, edge, p, (w, h), side in rows:
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(ref); fp.SetValue(f"contacts {side}")
        fp.SetFPID(pcbnew.LIB_ID("revc", f"EdgeContacts_{side}"))
        board.Add(fp)
        fp.SetPosition(pcbnew.VECTOR2I(MM(p[0][0]), MM(p[0][1]))); fp.SetLayer(pcbnew.B_Cu)
        for n, (x, y) in enumerate(p, start=1):
            pad = pcbnew.PAD(fp)
            pad.SetNumber(str(n)); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I(MM(w), MM(h)))
            ls = pcbnew.LSET(); ls.AddLayer(pcbnew.B_Cu); ls.AddLayer(pcbnew.B_Mask)
            if side in ("right", "bottom"):
                ls.AddLayer(pcbnew.B_Paste)
            else:
                pad.SetProperty(pcbnew.PAD_PROP_CASTELLATED)
            pad.SetLayerSet(ls); fp.Add(pad)
            pad.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
            name = {"DATA": f"DATA_{edge}"}.get(ORDER[n - 1], ORDER[n - 1])
            pad.SetNet(revb.net(board, name))
            if side in ("left", "top"):
                c = pad.GetPosition()
                if side == "left":
                    a, b = pcbnew.VECTOR2I(c.x + MM(w / 2 - .05), c.y), pcbnew.VECTOR2I(c.x + MM(w / 2 + .9), c.y)
                else:
                    a, b = pcbnew.VECTOR2I(c.x, c.y + MM(h / 2 - .05)), pcbnew.VECTOR2I(c.x, c.y + MM(h / 2 + .9))
                t = pcbnew.PCB_TRACK(board); t.SetStart(a); t.SetEnd(b); t.SetWidth(MM(0.25))
                t.SetLayer(pcbnew.B_Cu); t.SetNet(pad.GetNet()); board.Add(t)
        xs = [q[0] for q in p]; ys_ = [q[1] for q in p]
        depth = {"right": 3.0, "bottom": 3.0, "left": 1.0, "top": 0.55}[side]
        if side == "right":
            box = (max(xs) + w / 2 - depth, min(ys_) - h / 2 - .2, max(xs) + w / 2 + .2, max(ys_) + h / 2 + .2)
        elif side == "left":
            box = (min(xs) - w / 2 - .2, min(ys_) - h / 2 - .2, min(xs) - w / 2 + depth, max(ys_) + h / 2 + .2)
        elif side == "bottom":
            box = (min(xs) - w / 2 - .2, max(ys_) + h / 2 - depth, max(xs) + w / 2 + .2, max(ys_) + h / 2 + .2)
        else:   # top: one courtyard per contact (they are split over the socket gaps)
            box = None
            for x, y in p:
                _court(fp, (x - w / 2 - .2, y - h / 2 - .2, x + w / 2 + .2, y - h / 2 + depth))
        if box:
            _court(fp, box)
        fp.SetBoardOnly(True); fp.SetExcludedFromBOM(True); fp.SetExcludedFromPosFiles(True)


def _court(fp, box):
    for (a, b), (c, d) in (((box[0], box[1]), (box[2], box[1])), ((box[2], box[1]), (box[2], box[3])),
                           ((box[2], box[3]), (box[0], box[3])), ((box[0], box[3]), (box[0], box[1]))):
        s = pcbnew.PCB_SHAPE(fp); s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(MM(a), MM(b))); s.SetEnd(pcbnew.VECTOR2I(MM(c), MM(d)))
        s.SetLayer(pcbnew.B_CrtYd); s.SetWidth(MM(0.05)); fp.Add(s)


def stage1():
    os.makedirs(OUT, exist_ok=True)
    src = os.path.join(ROOT, "production", "revc18", "revc18.kicad_pcb")
    board = pcbnew.LoadBoard(src)
    for t in list(board.GetTracks()):
        board.Delete(t)
    for z in list(board.Zones()):
        board.Delete(z)
    for fp in list(board.GetFootprints()):
        if not fp.GetReference().startswith("SW"):
            board.Delete(fp)
    # keys: pad 1 -> GND, pad 2 -> K<n> (SW101..SW112 in row-major order)
    sws = sorted((fp for fp in board.GetFootprints() if fp.GetReference().startswith("SW")),
                 key=lambda f: (round(TOMM(revb.switch_centre(f).y)), TOMM(revb.switch_centre(f).x)))
    for n, sw in enumerate(sws):
        set_net(board, sw, 1, "GND")
        set_net(board, sw, 2, f"K{n + 1}")
    # LEDs: south of each switch centre, chained in row-major order
    chain_in = "LED_DIN"
    for n, sw in enumerate(sws):
        c = revb.switch_centre(sw)
        led = add_fp(board, "LED_SMD:LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount", f"D{n + 1}",
                     "SK6812MINI-E", (TOMM(c.x), TOMM(c.y) + 5.08), side="B")
        set_net(board, led, 1, "GND"); set_net(board, led, 3, "VCC")
        set_net(board, led, 2, chain_in)
        chain_in = f"LED_D{n + 1}" if n < 11 else "LED_END"
        set_net(board, led, 4, chain_in)
    # MCU and passives
    mcu = add_fp(board, "Package_DFN_QFN:VQFN-20-1EP_3x3mm_P0.4mm_EP1.7x1.7mm", "U1", "ATtiny1616-MNR", side="B")
    set_net(board, mcu, PIN["VDD"], "VCC"); set_net(board, mcu, PIN["GND"], "GND")
    for pad in mcu.Pads():                       # exposed pad (and its paste sub-pads) to GND
        if pad.GetNumber() in ("21", ""):
            pad.SetNet(revb.net(board, "GND"))
    for n, p in enumerate(KEY_PINS):
        set_net(board, mcu, PIN[p], f"K{n + 1}")
    for e, p in EDGE_PIN.items():
        set_net(board, mcu, PIN[p], f"DATA_{e}_MCU")
    set_net(board, mcu, PIN["PC2"], "LED_DIN"); set_net(board, mcu, PIN["PA0"], "UPDI")
    parts = [mcu]
    for e in "BRTL":
        r = add_fp(board, "Resistor_SMD:R_0603_1608Metric", f"R{len(parts)}", "100", side="B")
        set_net(board, r, 1, f"DATA_{e}_MCU"); set_net(board, r, 2, f"DATA_{e}"); parts.append(r)
    for i, v in enumerate(["100n", "4u7", "100n", "100n", "100n", "100n"]):
        c = add_fp(board, "Capacitor_SMD:C_0603_1608Metric" if v == "100n" else "Capacitor_SMD:C_0805_2012Metric",
                   f"C{10 + i}", v, side="B")
        set_net(board, c, 1, "VCC"); set_net(board, c, 2, "GND"); parts.append(c)
    tp = add_fp(board, "TestPoint:TestPoint_Pad_D1.5mm", "TP1", "UPDI", side="B")
    set_net(board, tp, 1, "UPDI"); parts.append(tp)
    contacts(board)

    outline = pcbnew.SHAPE_POLY_SET(); board.GetBoardPolygonOutlines(outline, False)
    placer = revb.Placer(board, outline)
    centre = (revc.key_xy(1, 0)[0] + 1.5 * P, Y0 + R)
    targets = {"U1": centre}
    failed = []
    for fp in parts:
        tgt = targets.get(fp.GetReference(), centre)
        fp.SetPosition(pcbnew.VECTOR2I(MM(300), MM(300)))
        try:
            placer.place(fp, "B", tgt, "key", rmax=40)
        except RuntimeError:
            failed.append(fp.GetReference())
    print("placement failed for:", failed or "none")

    board.SetCopperLayerCount(4)
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER); board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)
    revb.add_zone(board, outline, pcbnew.In1_Cu, "GND"); revb.add_zone(board, outline, pcbnew.In2_Cu, "VCC")
    revb.POWER = ("VCC", "GND")
    revb.fanout_power(board)
    pcbnew.SaveBoard(BRD, board)
    revb.write_stackup(BRD)
    shutil.copy(os.path.join(ROOT, "hardware", "kicad", "tile", "isomorphic_tile.kicad_pro"),
                os.path.join(OUT, "revc_mcu.kicad_pro"))
    pcbnew.ExportSpecctraDSN(pcbnew.LoadBoard(BRD), os.path.join(OUT, "revc_mcu.dsn"))
    print("stage 1 done")


def stage2(ses):
    board = pcbnew.LoadBoard(BRD)
    if not pcbnew.ImportSpecctraSES(board, ses):
        sys.exit("SES import failed")
    outline = pcbnew.SHAPE_POLY_SET(); board.GetBoardPolygonOutlines(outline, False)
    revb.add_zone(board, outline, pcbnew.F_Cu, "GND"); revb.add_zone(board, outline, pcbnew.B_Cu, "GND")
    revb.fix_text_mirroring(board)
    board.BuildConnectivity(); pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(BRD, board)
    print("stage 2 done")


if __name__ == "__main__":
    if "--route-in" in sys.argv:
        stage2(sys.argv[sys.argv.index("--route-in") + 1])
    else:
        stage1()
