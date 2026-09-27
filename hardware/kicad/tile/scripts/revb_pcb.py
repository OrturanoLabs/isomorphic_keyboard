#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Rev-B PCB transformation (run with KiCad's own Python, see docs/build/hardware.md).

    flatpak run --filesystem=<repo> --command=python3 org.kicad.KiCad \
        scripts/revb_pcb.py <netlist.net> [--route-in <session.ses>]

Stage 1 (default): starting from the rev-A board already on disk,
  * update every footprint from the rev-B netlist (library footprint, fields, sheet path,
    pad nets); key switches are re-centred on their 4 mm centre hole, so the switch
    positions do not move although the footprint origin convention differs;
  * go to 4 copper layers: In1 = GND / GND_T planes, In2 = VCC / VCC_T planes
    (the stack-up block itself is written by the caller, pcbnew does not expose it);
  * remove all tracks, vias and zones (the board is re-routed);
  * single-sided assembly: key board SMD on B.Cu (hot-swap sockets + resistors),
    logic board SMD on F.Cu; parts are placed by a greedy, collision-free search around a
    target point (old position, driver pin for series resistors, VCC pin for decoupling);
  * fiducials, 3 per board;
  * fan out every SMD power pad (stub + via into the inner planes) before routing;
  * export a Specctra DSN for Freerouting.
  The inner GND/VCC planes are created before the DSN export.
Stage 2 (--route-in SES, or --finish when the board was routed in place by
  KiCadRoutingTools): import the routed session if any, add a 4 mm grid of ground stitching vias, add ground pours on the outer
  layers, fill all zones and save.
Frozen items (switch centres, connectors J101-J108, outline) are never moved; this is
checked by tools/scripts/check_invariants.py afterwards.
"""
import math
import os
import re
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
BOARD = os.path.join(PROJ, "isomorphic_tile.kicad_pcb")
STOCK = "/app/extensions/Library/footprints"
LOCAL = os.path.join(PROJ, "..", "lib")
MM = pcbnew.FromMM

KEY_Y_MAX = 95.75           # mouse-bite row between the boards
LOGIC_Y_MIN = 109.0
FROZEN = re.compile(r"^(SW\d+|J10[1-8])$")


# ------------------------------------------------------------------ netlist -------------
def sexp(text):
    tok = re.findall(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+', text)
    stack = [[]]
    for t in tok:
        if t == "(":
            stack.append([])
        elif t == ")":
            x = stack.pop()
            stack[-1].append(x)
        else:
            stack[-1].append(t[1:-1].replace('\\"', '"') if t.startswith('"') else t)
    return stack[0][0]


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def one(node, key, default=None):
    r = find(node, key)
    return r[0] if r else default


def read_netlist(path):
    root = sexp(open(path, encoding="utf-8").read())
    comps = {}
    for c in find(one(root, "components"), "comp"):
        ref = one(c, "ref")[1]
        fields = {f[1][1]: (f[2] if len(f) > 2 else "") for f in find(one(c, "fields", []), "field")}
        sheet = one(c, "sheetpath")
        comps[ref] = dict(value=one(c, "value")[1], footprint=one(c, "footprint")[1],
                          datasheet=one(c, "datasheet")[1] if one(c, "datasheet") else "",
                          description=one(c, "description")[1] if one(c, "description") else "",
                          fields=fields, sheetname=one(sheet, "names")[1],
                          sheetstamps=one(sheet, "tstamps")[1],
                          stamp=one(c, "tstamps")[1] if one(c, "tstamps") else "",
                          sheetfile=next((p[2][1] for p in find(c, "property") if p[1][1] == "Sheetfile"), ""))
    pins = {}
    for n in find(one(root, "nets"), "net"):
        name = one(n, "name")[1]
        for nd in find(n, "node"):
            pins[(one(nd, "ref")[1], one(nd, "pin")[1])] = name
    return comps, pins


# ------------------------------------------------------------------ geometry ------------
def courtyard_box(fp, side):
    """Bounding box (x0,y0,x1,y1 in mm) of the courtyard on the given side (F/B), or None."""
    layer = pcbnew.F_CrtYd if side == "F" else pcbnew.B_CrtYd
    poly = fp.GetCourtyard(layer)
    if poly.OutlineCount() == 0:
        if fp.GetLayer() != (pcbnew.F_Cu if side == "F" else pcbnew.B_Cu):
            return None
        bb = fp.GetBoundingBox(False)
    else:
        bb = poly.BBox()
    return (pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()),
            pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))


def tht_boxes(fp):
    """Through-hole pads/holes block both sides."""
    out = []
    for p in fp.Pads():
        if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
            bb = p.GetBoundingBox()
            out.append((pcbnew.ToMM(bb.GetX()) - .3, pcbnew.ToMM(bb.GetY()) - .3,
                        pcbnew.ToMM(bb.GetRight()) + .3, pcbnew.ToMM(bb.GetBottom()) + .3))
    return out


def overlap(a, b, gap=0.2):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


class Placer:
    def __init__(self, board, outline):
        self.board, self.outline = board, outline
        self.fixed = {"F": [], "B": []}

    def obstacles(self, side, skip):
        obs = []
        for fp in self.board.GetFootprints():
            if fp is skip:
                continue
            b = courtyard_box(fp, side)
            if b:
                obs.append(b)
            obs += tht_boxes(fp)
            # SMD pads can stick out of a courtyard (e.g. the hot-swap socket tabs)
            cu = pcbnew.F_Cu if side == "F" else pcbnew.B_Cu
            for p in fp.Pads():
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and p.IsOnLayer(cu):
                    bb = p.GetBoundingBox()
                    obs.append((pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()),
                                pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
        return obs

    def inside(self, box, region, margin=0.6):
        x0, y0, x1, y1 = box
        if region == "key" and y1 > KEY_Y_MAX - 1.0:
            return False
        if region == "logic" and y0 < LOGIC_Y_MIN + 1.0:
            return False
        for x, y in ((x0 - margin, y0 - margin), (x1 + margin, y0 - margin),
                     (x0 - margin, y1 + margin), (x1 + margin, y1 + margin)):
            if not self.outline.Contains(pcbnew.VECTOR2I(MM(x), MM(y))):
                return False
        return True

    def place(self, fp, side, target, region, rotations=(0, 90, 180, 270), step=0.25, rmax=25):
        layer = pcbnew.F_Cu if side == "F" else pcbnew.B_Cu
        if fp.GetLayer() != layer:
            fp.SetLayerAndFlip(layer)
        obs = self.obstacles(side, fp)
        tx, ty = target
        for r in range(0, int(rmax / step) + 1):
            ring = [(0, 0)] if r == 0 else (
                [(i, -r) for i in range(-r, r + 1)] + [(i, r) for i in range(-r, r + 1)] +
                [(-r, j) for j in range(-r + 1, r)] + [(r, j) for j in range(-r + 1, r)])
            ring.sort(key=lambda d: d[0] * d[0] + d[1] * d[1])
            for dx, dy in ring:
                for rot in rotations:
                    fp.SetOrientationDegrees(rot)
                    fp.SetPosition(pcbnew.VECTOR2I(MM(tx + dx * step), MM(ty + dy * step)))
                    box = courtyard_box(fp, side)
                    if box and self.inside(box, region) and not any(overlap(box, o) for o in obs):
                        return True
        raise RuntimeError(f"no room for {fp.GetReference()} near {target}")


# ------------------------------------------------------------------ helpers -------------
def load_fp(fpid):
    lib, name = fpid.split(":")
    path = os.path.join(LOCAL if lib == "Switch_Keyboard_Hotswap_Kailh" else STOCK, lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise RuntimeError(f"footprint {fpid} not found in {path}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def fpid_str(fp):
    i = fp.GetFPID()
    return f"{i.GetLibNickname()}:{i.GetLibItemName()}"


def switch_centre(fp):
    for p in fp.Pads():
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH and abs(pcbnew.ToMM(p.GetSizeX()) - 4) < 0.01:
            return p.GetPosition()
    raise RuntimeError(f"{fp.GetReference()}: no 4 mm centre hole")


def pad_pos(board, ref, pad):
    fp = board.FindFootprintByReference(ref)
    p = fp.FindPadByNumber(pad)
    return pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)


def net(board, name):
    n = board.FindNet(name)
    if n is None:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
    return n


def region_poly(outline, y0, y1):
    rect = pcbnew.SHAPE_POLY_SET()
    rect.NewOutline()
    for x, y in ((0, y0), (400, y0), (400, y1), (0, y1)):
        rect.Append(MM(x), MM(y))
    out = pcbnew.SHAPE_POLY_SET(outline)
    out.BooleanIntersection(rect)
    return out


def add_zone(board, poly, layer, netname, priority=0):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net(board, netname))
    # copy the outline in place: SetOutline() takes ownership of a Python temporary and
    # crashes SaveBoard later (KiCad 10.0.6)
    for i in range(poly.OutlineCount()):
        z.Outline().AddOutline(poly.Outline(i))
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(MM(0.25))
    z.SetMinThickness(MM(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)   # SMD pads solid, THT thermal
    z.SetThermalReliefGap(MM(0.3))
    z.SetThermalReliefSpokeWidth(MM(0.35))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.Add(z)
    return z


STACKUP = """		(stackup
			(layer "F.SilkS" (type "Top Silk Screen"))
			(layer "F.Paste" (type "Top Solder Paste"))
			(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
			(layer "F.Cu" (type "copper") (thickness 0.035))
			(layer "dielectric 1" (type "prepreg") (thickness 0.2104) (material "FR4") (epsilon_r 4.4) (loss_tangent 0.02))
			(layer "In1.Cu" (type "copper") (thickness 0.0152))
			(layer "dielectric 2" (type "core") (thickness 1.065) (material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))
			(layer "In2.Cu" (type "copper") (thickness 0.0152))
			(layer "dielectric 3" (type "prepreg") (thickness 0.2104) (material "FR4") (epsilon_r 4.4) (loss_tangent 0.02))
			(layer "B.Cu" (type "copper") (thickness 0.035))
			(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
			(layer "B.Paste" (type "Bottom Solder Paste"))
			(layer "B.SilkS" (type "Bottom Silk Screen"))
			(copper_finish "ENIG")
			(dielectric_constraints no)
		)
"""


def write_stackup(path):
    """Generic 1.6 mm 4-layer stack-up (0.21 mm prepreg -> 0.3 mm microstrip ~ 55 ohm).
    pcbnew's Python API does not expose BOARD_STACKUP, so the block is written as text."""
    t = open(path, encoding="utf-8").read()
    t = re.sub(r"\t\t\(stackup\n.*?\n\t\t\)\n", "", t, flags=re.S)
    i = t.index("\t(setup\n") + len("\t(setup\n")
    open(path, "w", encoding="utf-8").write(t[:i] + STACKUP + t[i:])


def mark_board_only(board):
    """Mouse bites and fiducials have no schematic symbol: make them board-only items with
    unique references so the schematic-parity check and the BOM/CPL ignore them."""
    k = 0
    for fp in board.GetFootprints():
        name = str(fp.GetFPID().GetLibItemName())
        if name.startswith("MouseBite") or fp.GetReference().startswith("REF**"):
            k += 1
            fp.SetReference(f"MB{k}")
        elif not fp.GetReference().startswith("FID"):
            continue
        fp.SetBoardOnly(True)
        fp.SetAllowMissingCourtyard(True)
        fp.SetExcludedFromBOM(True)
        fp.SetExcludedFromPosFiles(True)
        fp.Reference().SetVisible(False)


BACK = (pcbnew.B_SilkS, pcbnew.B_Fab, pcbnew.B_Cu, pcbnew.B_Mask)


def fix_text_mirroring(board):
    """Text on back layers must be mirrored, text on front layers must not (parts that were
    flipped between sides keep stale flags otherwise)."""
    texts = [d for d in board.GetDrawings() if isinstance(d, pcbnew.PCB_TEXT)]
    for fp in board.GetFootprints():
        for f in fp.GetFields():
            # SetField() creates visible silkscreen fields: only the reference stays visible
            if f.GetName() not in ("Reference", "Value"):
                f.SetVisible(False)
        texts += list(fp.GetFields()) + [g.Cast() for g in fp.GraphicalItems()]
    for t in texts:
        if hasattr(t, "SetMirrored") and hasattr(t, "GetText"):
            t.SetMirrored(t.GetLayer() in BACK)


# ------------------------------------------------------------------ stage 1 -------------
def stage1(netlist):
    comps, pins = read_netlist(netlist)
    board = pcbnew.LoadBoard(BOARD)

    # 4 copper layers, inner layers as planes
    board.SetCopperLayerCount(4)
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)

    # Delete (not Remove): Remove() leaves dangling objects and crashes later (KiCad 10.0.6)
    for t in list(board.GetTracks()):
        board.Delete(t)
    for z in list(board.Zones()):
        board.Delete(z)

    # ---- footprints from the netlist ----
    existing = {fp.GetReference(): fp for fp in board.GetFootprints()}
    for ref, c in sorted(comps.items()):
        old = existing.get(ref)
        fpid = c["footprint"]
        if old is not None and fpid_str(old) == fpid:
            fp = old
        else:
            fp = load_fp(fpid)
            board.Add(fp)                     # flip needs the footprint to belong to a board
            if old is not None:
                if ref.startswith("SW"):
                    fp.SetPosition(switch_centre(old))
                else:
                    fp.SetPosition(old.GetPosition())
                fp.SetOrientation(old.GetOrientation())
                if old.GetLayer() == pcbnew.B_Cu and not ref.startswith("SW"):
                    fp.SetLayerAndFlip(pcbnew.B_Cu)
                board.Delete(old)
            else:
                fp.SetPosition(pcbnew.VECTOR2I(MM(150), MM(130)))
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        for k, v in c["fields"].items():
            if k not in ("Footprint", "Datasheet", "Description", "Reference", "Value"):
                fp.SetField(k, v)
        fp.SetField("Datasheet", c["datasheet"])
        fp.SetField("Description", c["description"])
        if fp.HasField("Link") and hasattr(fp, "RemoveField"):
            fp.RemoveField("Link")
        fp.SetPath(pcbnew.KIID_PATH(c["sheetstamps"] + c["stamp"]))
        fp.SetSheetname(c["sheetname"])
        fp.SetSheetfile(c["sheetfile"])
        for p in fp.Pads():
            key = (ref, p.GetNumber())
            if key in pins:
                p.SetNet(net(board, pins[key]))
    for ref, fp in existing.items():
        if ref not in comps and not ref.startswith("REF**"):
            board.Delete(fp)

    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, False)
    placer = Placer(board, outline)

    def fp_(r):
        return board.FindFootprintByReference(r)

    # ---- logic board: every SMD part on F.Cu ----
    ics = ["U103", "U104", "U109", "U101", "U107", "U102", "U106", "U108", "U105"]
    # U106 at 180 deg: its inputs (B_latch/R_latch, pins 1-2) then face R106/J104; at 0 deg
    # pin 2 was boxed in and R_latch could not be routed
    prefer = {"U106": (180,)}
    for r in ics:
        f = fp_(r)
        placer.place(f, "F", (pcbnew.ToMM(f.GetPosition().x), pcbnew.ToMM(f.GetPosition().y)), "logic",
                     rotations=prefer.get(r, (0, 90, 180, 270)))
    # series resistors first: a source termination only works right next to its driver
    drivers = {"R201": ("U101", "6"), "R202": ("U107", "6"), "R203": ("U106", "7"),
               "R204": ("U106", "7"), "R205": ("U104", "9"), "R206": ("U104", "9"),
               "R207": ("U108", "5")}
    for r, (u, p) in drivers.items():
        placer.place(fp_(r), "F", pad_pos(board, u, p), "logic")
    vcc_pin = {"U101": "8", "U102": "8", "U103": "16", "U104": "16", "U105": "5",
               "U106": "8", "U107": "8", "U108": "8", "U109": "16"}
    for i, u in enumerate(sorted(vcc_pin)):
        placer.place(fp_(f"C{201 + i}"), "F", pad_pos(board, u, vcc_pin[u]), "logic")
    for r in ["C105", "C103", "C104", "C101", "C102"] + [f"R{n}" for n in range(101, 110)]:
        f = fp_(r)
        placer.place(f, "F", (pcbnew.ToMM(f.GetPosition().x), pcbnew.ToMM(f.GetPosition().y)), "logic")

    # ---- key board: every SMD part on B.Cu (the hot-swap sockets already are) ----
    for n in range(110, 134):
        f = fp_(f"R{n}")
        placer.place(f, "B", (pcbnew.ToMM(f.GetPosition().x), pcbnew.ToMM(f.GetPosition().y)), "key")

    # ---- fiducials: 3 per board on its assembly side ----
    fids = [("FID1", "B", (110.5, 64.5), "key"), ("FID2", "B", (201.5, 48.0), "key"),
            ("FID3", "B", (110.5, 93.0), "key"),
            ("FID4", "F", (112.0, 151.0), "logic"), ("FID5", "F", (179.0, 151.0), "logic"),
            ("FID6", "F", (179.0, 112.0), "logic")]
    for ref, side, tgt, region in fids:
        f = load_fp("Fiducial:Fiducial_1mm_Mask2mm")
        f.SetReference(ref)
        f.SetValue("Fiducial")
        board.Add(f)
        placer.place(f, side, tgt, region, rotations=(0,), rmax=12)

    mark_board_only(board)

    # board markings: revision bump, and copper text moves to silkscreen (in rev A it was
    # copper on B.Cu, which now collides with the hot-swap sockets and new tracks)
    for d in board.GetDrawings():
        if isinstance(d, pcbnew.PCB_TEXT):
            if "v0.1" in d.GetText():
                d.SetText(d.GetText().replace("v0.1", "v0.2 (rev B)"))
            if d.GetLayer() == pcbnew.B_Cu:
                d.SetLayer(pcbnew.B_SilkS)
            elif d.GetLayer() == pcbnew.F_Cu:
                d.SetLayer(pcbnew.F_SilkS)

    # inner planes exist before routing, so the router drops vias into them
    key = region_poly(outline, 0, KEY_Y_MAX)
    logic = region_poly(outline, LOGIC_Y_MIN, 400)
    for poly, gnd, vcc in ((key, "GND_T", "VCC_T"), (logic, "GND", "VCC")):
        add_zone(board, poly, pcbnew.In1_Cu, gnd)
        add_zone(board, poly, pcbnew.In2_Cu, vcc)
    # (zones are filled in stage 2: the router only needs their outlines)

    # power pads get their plane vias before routing, so the router works around them
    fanout_power(board)

    pcbnew.SaveBoard(BOARD, board)
    write_stackup(BOARD)
    dsn = os.path.join(PROJ, "..", "..", "..", "production", "isomorphic_tile.dsn")
    os.makedirs(os.path.dirname(dsn), exist_ok=True)
    board = pcbnew.LoadBoard(BOARD)
    pcbnew.ExportSpecctraDSN(board, dsn)
    print("stage 1 done; DSN:", os.path.abspath(dsn))


POWER = ("VCC", "GND", "VCC_T", "GND_T")


def fanout_power(board, clearance=0.2):
    """Give every SMD pad on a power net a short stub and a via into the inner planes.
    Freerouting does not connect SMD pads to plane layers by itself."""
    items = []                                      # (shape, netcode, layers-set) of copper
    for fp in board.GetFootprints():
        for p in fp.Pads():
            items.append(p)
    items += list(board.GetTracks())
    added = 0
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or pad.GetNetname() not in POWER:
                continue
            layer = pcbnew.F_Cu if pad.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
            c = pad.GetPosition()
            half = max(pad.GetSizeX(), pad.GetSizeY()) / 2
            done = False
            # via centre at least half-pad + 0.65 mm away: the 0.6 mm via then keeps 0.35 mm
            # of solder mask between its annulus and the pad (no solder wicking into the
            # barrel; flagged by KiCadRoutingTools' fab check on the first rev-B layout)
            for dist in (0.65, 0.9, 1.2, 1.5, 1.9, 2.4, 2.9, 3.5):
                for k in range(24):
                    a = 2 * math.pi * k / 24
                    pos = pcbnew.VECTOR2I(int(c.x + math.cos(a) * (half + MM(dist))),
                                          int(c.y + math.sin(a) * (half + MM(dist))))
                    trk = pcbnew.PCB_TRACK(board)
                    trk.SetStart(c)
                    trk.SetEnd(pos)
                    trk.SetWidth(MM(0.25))
                    trk.SetLayer(layer)
                    trk.SetNet(pad.GetNet())
                    via = via_fits(board, items, pos, pad.GetNetCode(), extra=[(trk, layer)])
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
                print("fanout: no room for", fp.GetReference(), pad.GetNumber(), pad.GetNetname())
    print("fanout vias added:", added)


def via_fits(board, items, pos, netcode, extra=None, clearance=0.2):
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pos)
    via.SetWidth(MM(0.6))
    via.SetDrill(MM(0.3))
    cands = [(via, pcbnew.F_Cu), (via, pcbnew.B_Cu)] + (extra or [])
    for it in items:
        # same-net tracks/vias may touch; same-net SMD pads may not (a via on a pad or in
        # its paste opening wicks solder), so only the stub itself may reach its pad
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
            if it.IsOnLayer(lay) and cand.GetEffectiveShape(lay).Collide(it.GetEffectiveShape(lay), MM(clearance)):
                return None
    # keep clear of fiducials (their mask opening and keep-out are larger than the pad)
    for it in items:
        if isinstance(it, pcbnew.PAD) and it.GetParentFootprint().GetReference().startswith("FID"):
            if (it.GetPosition() - pos).EuclideanNorm() < MM(2.0):
                return None
    # keep drills apart from every other hole
    for it in items:
        if isinstance(it, pcbnew.PCB_VIA) or (isinstance(it, pcbnew.PAD) and it.HasHole()):
            if (it.GetPosition() - pos).EuclideanNorm() < MM(0.3 + 0.25) + (it.GetDrillSizeX() if isinstance(it, pcbnew.PAD) else it.GetDrill()) / 2 + MM(0.15):
                return None
    return via


def stitch_ground(board, pitch=4.0):
    """Grid of ground stitching vias tying the outer pours to the In1 plane."""
    items = [p for fp in board.GetFootprints() for p in fp.Pads()] + list(board.GetTracks())
    n = 0
    for netname, y0, y1 in (("GND_T", 40, KEY_Y_MAX), ("GND", LOGIC_Y_MIN, 160)):
        net_ = board.FindNet(netname)
        y = y0 + pitch / 2
        while y < y1:
            x = 100 + pitch / 2
            while x < 210:
                pos = pcbnew.VECTOR2I(MM(x), MM(y))
                if outline_ok(board, pos, margin=1.0):
                    via = via_fits(board, items, pos, net_.GetNetCode(), clearance=0.3)
                    if via is not None:
                        via.SetNet(net_)
                        board.Add(via)
                        items.append(via)
                        n += 1
                x += pitch
            y += pitch
    print("stitching vias added:", n)


def outline_ok(board, pos, margin=0.6):
    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, False)
    for dx, dy in ((margin, 0), (-margin, 0), (0, margin), (0, -margin)):
        if not outline.Contains(pcbnew.VECTOR2I(pos.x + MM(dx), pos.y + MM(dy))):
            return False
    y = pcbnew.ToMM(pos.y)
    return not (KEY_Y_MAX - 1 < y < LOGIC_Y_MIN + 1)


def trim_stacking_courtyard(board, ref="J107", y_from=80.93, y_to=80.73):
    """J107 (frozen rev-A position) ends 0.49 mm from the SW111 hot-swap socket body, but its
    0.5 mm courtyard margin overlaps the socket courtyard (drawn on the body outline).
    Pull that one courtyard edge in to a 0.3 mm margin; the parts themselves do not move."""
    fp = board.FindFootprintByReference(ref)
    n = 0
    for g in fp.GraphicalItems():
        if g.GetLayer() != pcbnew.B_CrtYd:
            continue
        for get, set_ in ((g.GetStart, g.SetStart), (g.GetEnd, g.SetEnd)):
            p = get()
            if abs(pcbnew.ToMM(p.y) - y_from) < 0.01:
                set_(pcbnew.VECTOR2I(p.x, MM(y_to)))
                n += 1
    print(f"{ref}: {n} courtyard points moved")


# ------------------------------------------------------------------ stage 2 -------------
def stage2(ses=None):
    """ses: Freerouting session to import; None when the board was routed in place
    (KiCadRoutingTools writes the routed board directly)."""
    board = pcbnew.LoadBoard(BOARD)
    if ses and not pcbnew.ImportSpecctraSES(board, ses):
        sys.exit("SES import failed")
    stitch_ground(board)
    trim_stacking_courtyard(board)
    fix_text_mirroring(board)
    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, False)
    key = region_poly(outline, 0, KEY_Y_MAX)
    logic = region_poly(outline, LOGIC_Y_MIN, 400)
    for poly, gnd in ((key, "GND_T"), (logic, "GND")):
        add_zone(board, poly, pcbnew.F_Cu, gnd)
        add_zone(board, poly, pcbnew.B_Cu, gnd)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(BOARD, board)
    print("stage 2 done")


if __name__ == "__main__":
    if "--route-in" in sys.argv:
        stage2(sys.argv[sys.argv.index("--route-in") + 1])
    elif "--finish" in sys.argv:
        stage2(None)
    elif "--export-dsn" in sys.argv:          # routed-in-place board -> DSN for a completion pass
        b = pcbnew.LoadBoard(BOARD)
        pcbnew.ExportSpecctraDSN(b, sys.argv[sys.argv.index("--export-dsn") + 1])
    else:
        stage1(sys.argv[1])
