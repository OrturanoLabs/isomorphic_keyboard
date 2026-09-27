#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Rev C concept, microcontroller tile (docs/architecture/revc-mcu-tile.md): board build.

Run by revc_mcu_route.sh (see there for the whole flow):
    revc_mcu_build.py --netlist production/revc_mcu/revc_mcu.net   # stage 1: place -> DSN
    (router)                                                        # KiCadRoutingTools
    revc_mcu_build.py --finish                                      # stage 2: pours, fill

The circuit is defined in revc_mcu_circuit.py and drawn by revc_mcu_schematic.py; this
script takes EVERY net from the netlist KiCad exports from that schematic, checks that the
board has exactly the schematic's components with the same footprints, and links each
footprint to its symbol (so KiCad's DRC schematic-parity check applies). What is decided
here is only geometry: starting from the 18.36 mm rev-C board of revc_build.py (switches on
the lattice, stepped outline), it adds the LEDs, the edge contacts, the MCU and the
passives, places them and writes the routing rules. Two copper layers.
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
circ = _load("revc_mcu_circuit", os.path.join(HERE, "revc_mcu_circuit.py"))
P, R, X0, Y0 = revc.P, revc.R, revc.X0, revc.Y0

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


def in_rule_area(board, pos, r=0.0):
    """pos, or a disc of radius r (mm) around it, touches a rule area"""
    pts = [pos] + [pos + pcbnew.VECTOR2I(MM(dx * r), MM(dy * r))
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (.7, .7), (-.7, .7), (.7, -.7), (-.7, -.7))]
    for z in board.Zones():
        if z.GetIsRuleArea() and any(z.Outline().Contains(p) for p in pts):
            return True
    return False


def keepout_rect(board, bb, margin, tracks=True):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(tracks); z.SetDoNotAllowVias(True); z.SetDoNotAllowPads(False)
    z.SetDoNotAllowZoneFills(False); z.SetDoNotAllowFootprints(False)
    ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.B_Cu); z.SetLayerSet(ls)
    o = z.Outline(); o.NewOutline()
    x0, y0, x1, y1 = bb
    for x, y in ((x0 - margin, y0 - margin), (x1 + margin, y0 - margin),
                 (x1 + margin, y1 + margin), (x0 - margin, y1 + margin)):
        o.Append(MM(x), MM(y))
    board.Add(z)


def apply_netlist(board, path):
    """nets, values and symbol links from the schematic's netlist; the board must hold
    exactly the schematic's components, with the same footprints"""
    comps, nets = circ.read_netlist(path)
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    errors = [f"{r}: on the board, not in the schematic" for r in fps if r not in comps]
    errors += [f"{r}: in the schematic, not on the board" for r in comps if r not in fps]
    for ref, c in comps.items():
        fp = fps.get(ref)
        if fp is None:
            continue
        fpid = f"{fp.GetFPID().GetLibNickname()}:{fp.GetFPID().GetLibItemName()}"
        if fpid != c["footprint"]:
            errors.append(f"{ref}: footprint {fpid} on the board, {c['footprint']} in the schematic")
        fp.SetValue(c["value"])
        fp.SetPath(pcbnew.KIID_PATH(c["path"]))
        for name, val in c["fields"].items():      # MPN, Manufacturer, Datasheet, ... (hidden)
            if name == "Footprint":
                continue
            fp.SetField(name, val)
            fp.GetField(name).SetVisible(False)
        for pad in fp.Pads():
            net = nets.get((ref, pad.GetNumber()))   # "unconnected-(...)": KiCad's single-pad net
            if net is None:
                pad.SetNetCode(0)
            else:
                pad.SetNet(revb.net(board, net))
    if errors:
        sys.exit("board does not match the schematic:\n  " + "\n  ".join(errors))
    # the short copper stubs of the edge pads take the net of their pad
    for t, pad in STUBS:
        t.SetNet(pad.GetNet())
    print("netlist applied:", len(comps), "components,", len(set(nets.values())), "nets")


STUBS = []      # (track, pad): edge-pad stubs, their net is set with the netlist


def contacts(board):
    """Edge contacts, 3 per edge (VCC, DATA, GND). Right/bottom: springs; left/top:
    castellated edge pads. Bottom springs are exactly P/2 left of the top pads (the
    up-lattice shift)."""
    pts = revc.outline()
    xr1, xl1, top, bot = pts[3][0], pts[10][0], pts[0][1], pts[6][1]
    c1 = Y0 + R
    ys = [c1 + 0.5 + j * 1.27 for j in range(3)]
    # top: castellated pads at the edge, centred on row-0 key 1. Copper may run under the
    # plastic body of the hot-swap socket (only its pads and the switch holes are keep-out).
    # The bottom springs sit P/2 to the left = halfway between row-2 keys 1 and 2, where
    # there is no LED cut-out.
    xk = revc.key_xy(0, 1)[0] - 0.8        # 0.8 mm left: clear of the switch pin hole
    xt = [xk + 1.27, xk, xk - 1.27]
    xb = [x - P / 2 for x in xt]
    J = {e: ref for e, (ref, _) in circ.EDGE_CONTACT.items()}
    rows = [(J["R"], [(xr1 - 1.35, y) for y in ys], (2.0, 0.8), "right"),
            (J["L"], [(xl1 + 0.45, y) for y in ys], (0.7, 0.8), "left"),
            (J["B"], [(x, bot - 1.35) for x in xb], (0.8, 2.0), "bottom"),
            (J["T"], [(x, top + 0.3) for x in xt], (0.8, 0.4), "top")]
    for ref, p, (w, h), side in rows:
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
            if side in ("left", "top"):
                c = pad.GetPosition()
                if side == "left":
                    a, b = pcbnew.VECTOR2I(c.x + MM(w / 2 - .05), c.y), pcbnew.VECTOR2I(c.x + MM(w / 2 + .9), c.y)
                else:
                    a, b = pcbnew.VECTOR2I(c.x, c.y + MM(h / 2 - .05)), pcbnew.VECTOR2I(c.x, c.y + MM(h / 2 + .9))
                t = pcbnew.PCB_TRACK(board); t.SetStart(a); t.SetEnd(b); t.SetWidth(MM(0.25))
                t.SetLayer(pcbnew.B_Cu); board.Add(t); STUBS.append((t, pad))
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
        # in the schematic (J1..J4) but not in the BOM yet: the spring part is still to be
        # chosen, and the edge pads are only copper
        fp.SetExcludedFromBOM(True); fp.SetExcludedFromPosFiles(True)


def _court(fp, box):
    for (a, b), (c, d) in (((box[0], box[1]), (box[2], box[1])), ((box[2], box[1]), (box[2], box[3])),
                           ((box[2], box[3]), (box[0], box[3])), ((box[0], box[3]), (box[0], box[1]))):
        s = pcbnew.PCB_SHAPE(fp); s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(MM(a), MM(b))); s.SetEnd(pcbnew.VECTOR2I(MM(c), MM(d)))
        s.SetLayer(pcbnew.B_CrtYd); s.SetWidth(MM(0.05)); fp.Add(s)


def stage1(netlist):
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
    # keys: SW<n> = key K<n>, numbered in row-major order (row 0 = top row, left to right)
    sws = sorted((fp for fp in board.GetFootprints() if fp.GetReference().startswith("SW")),
                 key=lambda f: (round(TOMM(revb.switch_centre(f).y)), TOMM(revb.switch_centre(f).x)))
    for n, sw in enumerate(sws):
        sw.SetReference(f"SW{n + 1}")
    # LEDs: D<n> south of SW<n>'s centre, chained in circ.CHAIN order (every link goes to a
    # neighbour). An LED whose chain runs left to right is turned 180 deg, so that DOUT faces
    # the next LED (and DIN the previous one).
    xs_ = [TOMM(revb.switch_centre(sws[n]).x) for n in circ.CHAIN]
    for k, n in enumerate(circ.CHAIN):
        c = revb.switch_centre(sws[n])
        step = xs_[k + 1] - xs_[k] if k + 1 < len(xs_) else xs_[k] - xs_[k - 1]
        led = add_fp(board, circ.FP["led"], f"D{n + 1}", "SK6812MINI-E", (TOMM(c.x), TOMM(c.y) + 5.08),
                     side="B", rot=180 if step > 0 else 0)
        # the reverse-mount LED has a board cut-out inside its footprint; routers that only
        # know the outer outline route through it, so fence it with a rule area
        xs, ys = [], []
        for g in led.GraphicalItems():
            if g.GetLayer() == pcbnew.Edge_Cuts:
                b = g.GetBoundingBox()      # plain numbers only: BOX2I.Merge on temporaries crashed
                xs += [TOMM(b.GetX()), TOMM(b.GetRight())]; ys += [TOMM(b.GetY()), TOMM(b.GetBottom())]
        if xs:
            keepout_rect(board, (min(xs), min(ys), max(xs), max(ys)), 0.35)
    # MCU and passives
    mcu = add_fp(board, circ.FP["mcu"], "U1", "ATtiny1616-MNR", side="B")
    parts, targets = [mcu], {}
    contacts(board)
    for e, rref in circ.EDGE_RES.items():
        r = add_fp(board, circ.FP["r"], rref, "100", side="B"); parts.append(r)
        # series resistor next to its edge contacts: it protects the hot-plug contact
        c = board.FindFootprintByReference(circ.EDGE_CONTACT[e][0]).GetPosition()
        targets[rref] = (TOMM(c.x), TOMM(c.y))
    for ref, v, near in circ.DECOUPLING:
        c = add_fp(board, circ.FP["c100n"] if v == "100n" else circ.FP["c4u7"], ref, v, side="B")
        parts.append(c)
        if near:        # LED decoupling next to the corner LEDs, away from the MCU
            led = board.FindFootprintByReference(near).GetPosition()
            targets[ref] = (TOMM(led.x), TOMM(led.y) + 3.0)
    tp = add_fp(board, circ.FP["tp"], "TP1", "UPDI", side="B"); parts.append(tp)
    targets["TP1"] = (revc.key_xy(2, 0)[0] + P / 2, Y0 + 2 * R + 5.5)
    apply_netlist(board, netlist)

    outline = pcbnew.SHAPE_POLY_SET(); board.GetBoardPolygonOutlines(outline, False)
    placer = revb.Placer(board, outline)
    centre = (revc.key_xy(1, 0)[0] + 1.5 * P, Y0 + R)
    targets["U1"] = centre
    failed = []
    ring = None
    for fp in parts:
        tgt = targets.get(fp.GetReference(), centre)
        fp.SetPosition(pcbnew.VECTOR2I(MM(300), MM(300)))
        try:
            placer.place(fp, "B", tgt, "key", rmax=40)
        except RuntimeError:
            failed.append(fp.GetReference())
        if fp.GetReference() == "U1":
            # keep a 2.5 mm ring free around the 0.4 mm-pitch VQFN so every pin can escape
            # straight out (a tightly packed first placement left 13 nets unroutable)
            bb = fp.GetCourtyard(pcbnew.B_CrtYd).BBox()
            ring = pcbnew.FOOTPRINT(board); ring.SetReference("KEEPOUT_U1"); board.Add(ring)
            ring.SetPosition(fp.GetPosition()); ring.SetLayer(pcbnew.B_Cu)
            g = 2.5
            _court(ring, (TOMM(bb.GetX()) - g, TOMM(bb.GetY()) - g, TOMM(bb.GetRight()) + g, TOMM(bb.GetBottom()) + g))
    if ring is not None:
        board.Delete(ring)
    print("placement failed for:", failed or "none")
    # turn the (square) MCU so that its VDD pin faces the 100 nF at C1: the shortest supply
    # loop, and the VDD pin (boxed in between GND and a key pin) escapes straight to it
    vdd = next(p for p in mcu.Pads() if p.GetNetname() == "VCC")
    c1 = board.FindFootprintByReference(circ.DECOUPLING[0][0])
    c1_vcc = next(p for p in c1.Pads() if p.GetNetname() == "VCC").GetPosition()
    best = min((0, 90, 180, 270), key=lambda a: (mcu.SetOrientationDegrees(a),
                                                 (vdd.GetPosition() - c1_vcc).EuclideanNorm())[1])
    rot = os.environ.get("MCU_ROT", "auto")      # the flow may try the other orientations
    if rot == "stored" and circ.stored_orientation() is not None:
        best = circ.stored_orientation()           # the one of the last clean board
    elif rot not in ("auto", "stored"):
        best = int(rot)
    mcu.SetOrientationDegrees(best)
    print("MCU orientation:", best)
    if assign_pins(board, mcu):
        sys.exit(3)         # the flow redraws the schematic with the new pin map and re-runs

    # no vias in or next to any SMD land (LEDs, sockets, MCU, passives, edge contacts): a
    # boxed-in pad otherwise gets a via-in-pad, which needs filled and capped vias
    # (IPC-4761 type VII); the MCU exposed pad reaches GND through the bottom pour instead
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            b = pad.GetBoundingBox()
            # 0.2 mm around the 0.4 mm-pitch MCU (it needs the room to fan out), 0.3 elsewhere
            keepout_rect(board, (TOMM(b.GetX()), TOMM(b.GetY()), TOMM(b.GetRight()), TOMM(b.GetBottom())),
                         0.2 if fp.GetReference() == "U1" else 0.3, tracks=False)
    # 2 layers (no fast inter-tile clock any more, low density): the top (switch side, no
    # parts) becomes an almost continuous GND plane, the bottom carries the parts, the
    # signals, VCC and a stitched GND pour (see revc_mcu_route.sh)
    board.SetCopperLayerCount(2)
    pcbnew.SaveBoard(BRD, board)
    write_libs(board)
    shutil.copy(os.path.join(ROOT, "hardware", "kicad", "tile", "isomorphic_tile.kicad_pro"),
                os.path.join(OUT, "revc_mcu.kicad_pro"))
    # the VQFN-20 has 0.40 mm pitch and 0.15 mm between pads: 0.2 mm clearance would make
    # every pin unreachable. 0.15 mm clearance/track is a standard fab capability.
    import json
    pro = os.path.join(OUT, "revc_mcu.kicad_pro")
    d = json.load(open(pro))
    d["board"]["design_settings"]["rules"].update(min_clearance=0.15, min_track_width=0.15, min_connection=0.15)
    for c in d["net_settings"]["classes"]:
        c["clearance"] = 0.15
    json.dump(d, open(pro, "w"), indent=2)
    # the reverse-mount LED land pattern puts its pads close to its own board cut-out by
    # design (KiCad library footprint): allow that, and only that, in a custom DRC rule
    open(os.path.join(OUT, "revc_mcu.kicad_dru"), "w").write(
        '(version 1)\n'
        '(rule "reverse-mount LED pads next to their cut-out"\n'
        '  (condition "A.Type == \'Pad\' && A.memberOfFootprint(\'D*\')")\n'
        '  (constraint edge_clearance (min 0.05mm)))\n')
    pcbnew.ExportSpecctraDSN(pcbnew.LoadBoard(BRD), os.path.join(OUT, "revc_mcu.dsn"))
    print("stage 1 done")


def assign_pins(board, mcu):
    """Pin swapping: give the 15 interchangeable signals the pins whose angle around the MCU
    matches, in order, the angle of where each signal goes, so that the fan-out has no
    crossings. Returns True if the stored pin map changed."""
    import math
    c = mcu.GetPosition()
    ang = lambda p: math.atan2(TOMM(p.y - c.y), TOMM(p.x - c.x))     # noqa: E731
    pad_of_port = {port: mcu.FindPadByNumber(str(circ.PIN[port])) for port in circ.FLEX_PORTS}
    ports = sorted(circ.FLEX_PORTS, key=lambda p: ang(pad_of_port[p].GetPosition()))
    target = {}
    for net in circ.FLEX_NETS:
        pts = [p.GetPosition() for fp in board.GetFootprints() if fp.GetReference() != "U1"
               for p in fp.Pads() if p.GetNetname() == net]
        target[net] = math.atan2(sum(TOMM(p.y - c.y) for p in pts) / len(pts),
                                 sum(TOMM(p.x - c.x) for p in pts) / len(pts))
    nets = sorted(circ.FLEX_NETS, key=lambda n: target[n])
    wrap = lambda a: abs((a + math.pi) % (2 * math.pi) - math.pi)   # noqa: E731
    k = len(ports)
    shift = min(range(k), key=lambda s: sum(wrap(ang(pad_of_port[ports[(i + s) % k]].GetPosition())
                                                 - target[nets[i]]) for i in range(k)))
    new = {nets[i]: ports[(i + shift) % k] for i in range(k)}
    orientation = int(round(mcu.GetOrientationDegrees())) % 360
    if new == circ.pinmap():
        if circ.stored_orientation() != orientation:
            circ.save_pinmap(new, orientation)
        print("pin map: unchanged")
        return False
    circ.save_pinmap(new, orientation)
    print("pin map: updated", circ.PINMAP_FILE)
    return True


def write_libs(board):
    """project footprint libraries next to the board: the generated edge-contact footprints
    (library 'revc') and the local Kailh socket library, so that the schematic's footprint
    links resolve (ERC) and 'Update PCB from Schematic' works in the GUI"""
    lib = os.path.join(OUT, "revc.pretty")
    shutil.rmtree(lib, ignore_errors=True)
    io = pcbnew.PCB_IO_KICAD_SEXPR()     # the path-guessing helpers find no plugin here
    io.CreateLibrary(lib)
    for ref, _ in circ.EDGE_CONTACT.values():
        io.FootprintSave(lib, board.FindFootprintByReference(ref))
    kailh = os.path.relpath(os.path.join(ROOT, "hardware", "kicad", "lib"), OUT)
    write_fp_lib_table(OUT, "${KIPRJMOD}/" + kailh)


def write_fp_lib_table(folder, kailh_dir):
    open(os.path.join(folder, "fp-lib-table"), "w").write(
        '(fp_lib_table\n\t(version 7)\n'
        f'\t(lib (name "revc")(type "KiCad")(uri "${{KIPRJMOD}}/revc.pretty")(options "")'
        '(descr "rev C edge contacts, generated by revc_mcu_build.py"))\n'
        f'\t(lib (name "Switch_Keyboard_Hotswap_Kailh")(type "KiCad")'
        f'(uri "{kailh_dir}/Switch_Keyboard_Hotswap_Kailh.pretty")(options "")'
        '(descr "Kailh MX hot-swap socket (keyswitch-kicad-library v2.3)"))\n)\n')


def stage2(ses=None):
    """ses: Freerouting session to import, or None when KiCadRoutingTools routed BRD in place."""
    board = pcbnew.LoadBoard(BRD)
    if ses and not pcbnew.ImportSpecctraSES(board, ses):
        sys.exit("SES import failed")
    outline = pcbnew.SHAPE_POLY_SET(); board.GetBoardPolygonOutlines(outline, False)
    # GND stitching (3 mm grid): ties the bottom pour islands to the almost continuous top pour
    revb.KEY_Y_MAX, revb.LOGIC_Y_MIN = 200, 300
    # a VCC plane on top (from route_planes) keeps GND on the bottom only; with a GND plane
    # or no plane on top, stitch the bottom GND pour to it
    top_plane = any(z.GetLayer() == pcbnew.F_Cu and not z.GetIsRuleArea() and z.GetNetname() == "VCC"
                    for z in board.Zones())
    top_gnd = any(z.GetLayer() == pcbnew.F_Cu and not z.GetIsRuleArea() and z.GetNetname() == "GND"
                  for z in board.Zones())
    items = [p for fp in board.GetFootprints() for p in fp.Pads()] + list(board.GetTracks())
    gnd = board.FindNet("GND"); n = 0
    y = 40.0
    while y < 100 and not top_plane:
        x = 100.0
        while x < 205:
            pos = pcbnew.VECTOR2I(MM(x), MM(y))
            if revb.outline_ok(board, pos, margin=1.0) and not in_rule_area(board, pos, 0.35):
                v = revb.via_fits(board, items, pos, gnd.GetNetCode(), clearance=0.3)
                if v is not None:
                    v.SetNet(gnd); board.Add(v); items.append(v); n += 1
            x += 3.0
        y += 3.0
    print("stitching vias:", n)
    if not top_plane and not top_gnd:
        revb.add_zone(board, outline, pcbnew.F_Cu, "GND")
    revb.add_zone(board, outline, pcbnew.B_Cu, "GND")
    revb.fix_text_mirroring(board)
    board.BuildConnectivity(); pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(BRD, board)
    print("stage 2 done")


if __name__ == "__main__":
    if "--route-in" in sys.argv:
        stage2(sys.argv[sys.argv.index("--route-in") + 1])
    elif "--finish" in sys.argv:
        stage2(None)
    else:
        stage1(sys.argv[sys.argv.index("--netlist") + 1])
