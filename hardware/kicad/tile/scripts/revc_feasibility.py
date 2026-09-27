#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Rev C feasibility study: can the tile be ONE board instead of the rev-A/B double stack?

Run with KiCad's Python (repo root):
    flatpak run --filesystem="$PWD" --command=python3 org.kicad.KiCad \
        hardware/kicad/tile/scripts/revc_feasibility.py [--place]

Steps
 1. Stack transform: the logic board sits under the key board, J105/J106 mating J107/J108.
    The pad offsets give logic -> key coordinates (+10.96, -60.90) mm.
 2. Tile lattice from the edge connectors: right neighbour (+80, 0) mm, upper neighbour
    (+10, -51.96) mm; mated header/socket pads are 13.9 mm apart.
 3. Fold the logic board onto the BOTTOM of the key board (the top carries the switches):
    every logic footprint is moved by the stack offset and flipped to B.Cu, J105-J108 go away
    (their nets are merged 1:1 in a single-board schematic), the logic board outline, tabs
    and mouse bites are deleted and the key-board outline is closed.
 4. Report every conflict of the folded layout:
    * edge connectors (THT) whose pins land inside a switch body (top side) or hit a switch
      hole / hot-swap socket pad;
    * SMD courtyard overlaps on the bottom.
 5. --place: keep the edge connectors where the lattice needs them and try to place all the
    logic SMD parts on the bottom with the rev-B collision-free placer; report what fits.
Output: production/revc/ (board + report.md + images). Nothing in hardware/ is modified.
"""
import importlib.util
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
OUT = os.path.join(ROOT, "production", "revc")
MM, TOMM = pcbnew.FromMM, pcbnew.ToMM
KEY_Y_MAX = 95.75

spec = importlib.util.spec_from_file_location("revb", os.path.join(HERE, "revb_pcb.py"))
revb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(revb)


def pad_positions(fp):
    return {p.GetNumber(): p.GetPosition() for p in fp.Pads() if p.GetNumber()}


def stack_offset(board):
    d = []
    for a, b in (("J105", "J107"), ("J106", "J108")):
        pa, pb = pad_positions(board.FindFootprintByReference(a)), pad_positions(board.FindFootprintByReference(b))
        d += [(pb[k] - pa[k]) for k in pa]
    dx = sum(v.x for v in d) / len(d)
    dy = sum(v.y for v in d) / len(d)
    return pcbnew.VECTOR2I(int(dx), int(dy))


def is_logic(fp):
    y = TOMM(fp.GetPosition().y)
    return y > 100 and not fp.GetReference().startswith("MB")


def close_key_outline(board):
    """Delete Edge.Cuts below the key board and close its bottom edge at y = 96."""
    removed = 0
    for d in list(board.GetDrawings()):
        if d.GetLayer() != pcbnew.Edge_Cuts:
            continue
        ys = (TOMM(d.GetStart().y), TOMM(d.GetEnd().y))
        if min(ys) >= 96 - 1e-6 and max(ys) > 96 + 1e-6 or min(ys) > 96 + 1e-6:
            board.Delete(d)
            removed += 1
    for x0, x1 in ((118.5, 132.25), (159.5, 173.25)):          # where the tabs were
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(MM(x0), MM(96)))
        s.SetEnd(pcbnew.VECTOR2I(MM(x1), MM(96)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.05))
        board.Add(s)
    return removed


def boxes_overlap(a, b, gap=0.0):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def bbox(poly_or_box):
    bb = poly_or_box
    return (TOMM(bb.GetX()), TOMM(bb.GetY()), TOMM(bb.GetRight()), TOMM(bb.GetBottom()))


def conflicts(board):
    """Human-readable list of geometric conflicts on the folded board."""
    out = []
    switches = [f for f in board.GetFootprints() if f.GetReference().startswith("SW")]
    sw_bodies = {f.GetReference(): bbox(f.GetCourtyard(pcbnew.F_CrtYd).BBox()) for f in switches}
    sw_holes = []
    for f in switches:
        for p in f.Pads():
            if p.HasHole():
                r = TOMM(p.GetDrillSizeX()) / 2
                c = p.GetPosition()
                sw_holes.append((f.GetReference(), TOMM(c.x), TOMM(c.y), r))
    sock_pads = []
    for f in switches:
        for p in f.Pads():
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                sock_pads.append((f.GetReference(), bbox(p.GetBoundingBox())))
    for ref in ("J101", "J102", "J103", "J104"):
        fp = board.FindFootprintByReference(ref)
        for p in fp.Pads():
            c = p.GetPosition(); x, y = TOMM(c.x), TOMM(c.y); r = TOMM(p.GetSizeX()) / 2
            for s, box in sw_bodies.items():
                # courtyard is the body + 0.25 mm; count only pins inside the real 14 mm body
                if box[0] + 0.25 < x < box[2] - 0.25 and box[1] + 0.25 < y < box[3] - 0.25:
                    out.append(f"{ref} pin {p.GetNumber()} ({x:.2f}, {y:.2f}) is under the body of {s} "
                               "(THT pin end on the switch side)")
            for s, hx, hy, hr in sw_holes:
                if math.hypot(x - hx, y - hy) < r + hr + 0.25:
                    out.append(f"{ref} pin {p.GetNumber()} hits a {2 * hr:.2f} mm hole of {s}")
            for s, box in sock_pads:
                if boxes_overlap((x - r, y - r, x + r, y + r), box, 0.2):
                    out.append(f"{ref} pin {p.GetNumber()} overlaps a hot-swap socket pad of {s}")
    smd = [f for f in board.GetFootprints()
           if f.GetLayer() == pcbnew.B_Cu and f.GetCourtyard(pcbnew.B_CrtYd).OutlineCount()]
    for i, a in enumerate(smd):
        for b in smd[i + 1:]:
            if boxes_overlap(bbox(a.GetCourtyard(pcbnew.B_CrtYd).BBox()),
                             bbox(b.GetCourtyard(pcbnew.B_CrtYd).BBox())):
                out.append(f"bottom courtyards overlap: {a.GetReference()} / {b.GetReference()}")
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    board = pcbnew.LoadBoard(os.path.join(ROOT, "hardware", "kicad", "tile", "isomorphic_tile.kicad_pcb"))
    off = stack_offset(board)
    rep = [f"# Rev C single-board feasibility\n",
           f"Stack offset logic -> key board: ({TOMM(off.x):.3f}, {TOMM(off.y):.3f}) mm\n"]
    for t in list(board.GetTracks()):
        board.Delete(t)
    for z in list(board.Zones()):
        board.Delete(z)
    for fp in list(board.GetFootprints()):
        r = fp.GetReference()
        if r in ("J105", "J106", "J107", "J108") or r.startswith("MB"):
            board.Delete(fp)
    moved = []
    for fp in list(board.GetFootprints()):
        if is_logic(fp):
            fp.SetPosition(fp.GetPosition() + off)
            fp.SetLayerAndFlip(pcbnew.B_Cu)
            moved.append(fp.GetReference())
    for d in list(board.GetDrawings()):
        if isinstance(d, pcbnew.PCB_TEXT) and TOMM(d.GetPosition().y) > 100:
            board.Delete(d)
    n = close_key_outline(board)
    rep.append(f"Moved {len(moved)} logic footprints to the key-board bottom; removed {n} "
               "outline segments of the logic board and tabs.\n")
    c = conflicts(board)
    rep.append(f"\n## Folded as-is: {len(c)} conflicts\n")
    rep += [f"- {x}" for x in c]
    pcbnew.SaveBoard(os.path.join(OUT, "revc_folded.kicad_pcb"), board)

    if "--alt" in sys.argv:
        # same logic, smaller packages: 74HC161 in TSSOP-16, bulk cap as a 1210 ceramic; the
        # 2.54 mm edge connectors cannot stay (see conflicts), take them off the board
        for ref, fpid in (("U109", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm"),
                          ("C105", "Capacitor_SMD:C_1210_3225Metric")):
            old = board.FindFootprintByReference(ref)
            new = revb.load_fp(fpid)
            board.Add(new)
            new.SetPosition(old.GetPosition())
            new.SetLayerAndFlip(pcbnew.B_Cu)
            new.SetReference(ref)
            for p in new.Pads():
                q = old.FindPadByNumber(p.GetNumber())
                if q is not None:
                    p.SetNet(q.GetNet())
            board.Delete(old)
        for ref in ("J101", "J102", "J103", "J104"):
            board.Delete(board.FindFootprintByReference(ref))
        rep.append("\nVariant --alt: U109 TSSOP-16, C105 1210, edge connectors removed.\n")

    if "--place" in sys.argv:
        outline = pcbnew.SHAPE_POLY_SET()
        board.GetBoardPolygonOutlines(outline, False)
        placer = revb.Placer(board, outline)
        ok, fail = [], []
        order = ["U103", "U104", "U109", "U101", "U107", "U102", "U106", "U108", "U105"] + \
                [f"R20{i}" for i in range(1, 8)] + [f"C20{i}" for i in range(1, 10)] + \
                ["C105", "C103", "C104", "C101", "C102"] + [f"R10{i}" for i in range(1, 10)] + \
                ["FID4", "FID5", "FID6"]
        for r in order:
            fp = board.FindFootprintByReference(r)
            if fp is None:
                continue
            tgt = (TOMM(fp.GetPosition().x), TOMM(fp.GetPosition().y))
            fp.SetPosition(pcbnew.VECTOR2I(MM(300), MM(300)))       # out of the way while searching
            try:
                placer.place(fp, "B", tgt, "key", rmax=30)
                ok.append(r)
            except RuntimeError:
                fail.append(r)
        rep.append(f"\n## Placement of the logic SMD parts on the bottom\n")
        rep.append(f"placed {len(ok)}: {', '.join(ok)}\n")
        rep.append(f"**no room** for {len(fail)}: {', '.join(fail) or '-'}\n")
        pcbnew.SaveBoard(os.path.join(OUT, "revc_placed.kicad_pcb"), board)
    open(os.path.join(OUT, "report.md"), "w").write("\n".join(rep) + "\n")
    print("\n".join(rep))


if __name__ == "__main__":
    main()
