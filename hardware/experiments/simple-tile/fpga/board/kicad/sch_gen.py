#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""sch_gen -- authoritative KiCad schematic generator for the FPGA tile (gw1nz).

Emits, deterministically (host python3 stdlib only):
  out/kicad/tile_gw1nz.kicad_sch       authoritative schematic (KiCad 10 fmt)
  out/kicad/lib/fpga_tile.kicad_sym    project-local symbol library
  out/kicad/sym-lib-table              project library registration
  out/sch_summary.json                 emission census + self-check SCH0

Circuit tables are stated HERE (literal) from the same primary sources the
board was built from (data/pins_gw1nz_qn48.json pin DB + the production
constraints/tile_gw1nz_board.cst + vendor-documented strap/decoupling
practice). The schematic is NOT scraped from the emitted .kicad_pcb; drift in
either direction is caught by tools/schematic_check.py, which compares the
kicad-cli-exported schematic netlist against the board netlist and against an
independent expectation table (with negative controls).

Format idioms were verified against the repo's KiCad-10.0-written rev-A
sheets (hardware/kicad/tile/*.kicad_sch, version 20260306) and by a live
kicad-cli ERC spike:
  * power symbols are (power global) with one power_in pin whose VALUE names
    the net; they do NOT satisfy ERC "power driven" checks: JP_VCC/JP_GND
    chassis pads carry pin type power_out (power physically enters through
    the spring contact) and the LDO OUT pin is power_out.
  * symbol-lib Y is screen-up, sheet Y is screen-down: pin sheet pos =
    (cx + px, cy - py).
  * NC-type symbol pins (LDO pin 4) need no X marker; unused FPGA IO pads
    are bidir + get an explicit X marker (no_connect) on the sheet.
  * labels connect only when placed ON a wire end or pin tip.
"""
import json
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))          # .../fpga/board/kicad
BOARD = os.path.abspath(os.path.join(HERE, ".."))          # .../fpga/board
OUT = os.path.join(BOARD, "out")
KOUT = os.path.join(OUT, "kicad")
sys.path.insert(0, HERE)
import pin_con_parse  # noqa: E402  (shared with pincon/board net checkers)

NS = uuid.UUID("f17a9001-1ee1-4a02-a02f-9a11ce000001")
PROJECT = "tile_gw1nz"
SHEET = uuid.uuid5(NS, "root-sheet")


def U(tag):
    return str(uuid.uuid5(NS, tag))


def N(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


EFFECTS = ("\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n"
           "\t\t\t\t)\n")


def esc(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def prop(name, value, x, y, hide=False, justify=None):
    return (f'\t\t(property "{name}" "{esc(value)}"\n\t\t\t(at {N(x)} {N(y)} 0)\n'
            + ("\t\t\t(hide yes)\n" if hide else "")
            + "\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n"
            + EFFECTS
            + (f"\t\t\t\t(justify {justify})\n" if justify else "")
            + "\t\t\t)\n\t\t)")


def pindef(num, name, ptype, x, y, rot, length=2.54):
    e = '\t\t\t\t\t\t(effects\n\t\t\t\t\t\t\t(font\n' + \
        '\t\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t\t)\n\t\t\t\t\t\t)\n'
    return (f'\t\t\t(pin {ptype} line\n\t\t\t\t(at {N(x)} {N(y)} {rot})\n'
            f'\t\t\t\t(length {N(length)})\n'
            f'\t\t\t\t(name "{name}"\n{e}\t\t\t\t)\n'
            f'\t\t\t\t(number "{num}"\n{e}\t\t\t\t)\n\t\t\t)')


def rect(x0, y0, x1, y1):
    return (f'\t\t\t\t(rectangle\n\t\t\t\t\t(start {N(x0)} {N(y0)})\n'
            f'\t\t\t\t\t(end {N(x1)} {N(y1)})\n'
            '\t\t\t\t\t(stroke\n\t\t\t\t\t\t(width 0.254)\n'
            '\t\t\t\t\t\t(type default)\n\t\t\t\t\t)\n'
            '\t\t\t\t\t(fill\n\t\t\t\t\t\t(type background)\n\t\t\t\t\t)\n'
            '\t\t\t\t)')


def circle(cx, cy, r):
    return (f'\t\t\t\t(circle\n\t\t\t\t\t(center {N(cx)} {N(cy)})\n'
            f'\t\t\t\t\t(radius {N(r)})\n'
            '\t\t\t\t\t(stroke\n\t\t\t\t\t\t(width 0.254)\n'
            '\t\t\t\t\t\t(type default)\n\t\t\t\t\t)\n'
            '\t\t\t\t\t(fill\n\t\t\t\t\t\t(type none)\n\t\t\t\t\t)\n'
            '\t\t\t\t)')


def polyline(pts):
    pp = "\n".join(f"\t\t\t\t\t\t(xy {N(a)} {N(b)})" for a, b in pts)
    return ('\t\t\t\t(polyline\n\t\t\t\t\t(pts\n' + pp + '\n\t\t\t\t\t)\n'
            '\t\t\t\t\t(stroke\n\t\t\t\t\t\t(width 0.254)\n'
            '\t\t\t\t\t\t(type default)\n\t\t\t\t\t)\n'
            '\t\t\t\t\t(fill\n\t\t\t\t\t\t(type none)\n\t\t\t\t\t)\n'
            '\t\t\t\t)')


def symbol_def(prefix, name, ref, value, footprint, datasheet, descr,
               graphics, pins, power=False, descr_prop=True):
    head = (f'\t\t(symbol "{prefix}{name}"\n'
            + ("\t\t\t(power global)\n" if power else "")
            + "\t\t\t(pin_numbers\n\t\t\t\t(hide yes)\n\t\t\t)\n"
            "\t\t\t(pin_names\n\t\t\t\t(offset 0.508)\n\t\t\t)\n"
            "\t\t\t(exclude_from_sim no)\n\t\t\t(in_bom yes)\n"
            "\t\t\t(on_board yes)\n\t\t\t(in_pos_files yes)\n"
            "\t\t\t(duplicate_pin_numbers_are_jumpers no)\n")
    props = [prop("Reference", ref, 0, 3.81 if not power else -3.81,
                  hide=power),
             prop("Value", value, 0, -3.81 if not power else 3.556)]
    if footprint is not None:
        props.append(prop("Footprint", footprint, 0, 0, hide=True))
    props.append(prop("Datasheet", datasheet, 0, 0, hide=True))
    if descr_prop:
        props.append(prop("Description", descr, 0, 0, hide=True))
    units = (f'\t\t\t(symbol "{name}_0_1"\n{graphics}\n\t\t\t)\n'
             f'\t\t\t(symbol "{name}_1_1"\n' + "\n".join(pins) +
             "\n\t\t\t)\n\t\t\t(embedded_fonts no)\n\t\t)")
    return head + "\n".join(props) + "\n" + units


# ------------------------------------------------------------ symbol library
def libdefs():
    syms = []
    for net in ("VCC", "GND", "VCC1V2"):
        g = polyline([(-2.54, 0), (2.54, 0), (0, 2.54), (-2.54, 0)])
        pins = [pindef("1", "~", "power_in", 0, 0, 270, 0)]
        syms.append(symbol_def("", f"PWR_{net}", "#PWR", net, None, "",
                               f'Power symbol creates a global label with '
                               f'name "{net}"', g, pins, power=True))
    g = rect(-1.016, -2.54, 1.016, 2.54)
    rpins = [pindef("1", "1", "passive", 0, 5.08, 270),
             pindef("2", "2", "passive", 0, -5.08, 90)]
    for sname, desc in (("R", "Resistor 0603 (project local)"),
                        ("C", "Capacitor (project local)"),
                        ("FB", "Ferrite bead 0603 (project local)")):
        syms.append(symbol_def("", sname,
                               {"R": "R", "C": "C", "FB": "FB"}[sname],
                               sname, "", "", desc, g, rpins))
    g = (rect(-2.54, -2.54, 2.54, 2.54) + "\n" + circle(-1.27, 0, 0.508) +
         "\n" + circle(1.27, 0, 0.508) + "\n" +
         polyline([(-1.27, 0), (0.635, 1.905)]))
    syms.append(symbol_def("", "SW_KAILH", "SW", "Kailh MX hotswap socket", "",
                           "", "SMD MX hot-swap key socket (Kailh CPG1511; "
                           "pin1 = VCC side, pin2 = key-net side)", g,
                           [pindef("1", "1", "passive", -3.81, 0, 180, 1.27),
                            pindef("2", "2", "passive", 3.81, 0, 0, 1.27)]))
    g = circle(0, 0, 1.27)
    syms.append(symbol_def("", "TP", "TP", "TP", "", "",
                           "test pad D1.0 (board pad, no component)", g,
                           [pindef("1", "1", "passive", 0, 0, 270, 0)]))
    g = circle(0, 0, 1.905)
    for pwr in (False, True):
        n = "JP_PAD_PWR" if pwr else "JP_PAD"
        syms.append(symbol_def(
            "", n, "JP", n, "", "",
            ("chassis spring-contact target pad D2.5 (pin type power_out: "
             "this contact FEEDS the tile's GND/VCC net)"
             if pwr else
             "chassis spring-contact target pad D2.5 (net passes through to "
             "the chassis trace)"), g,
            [pindef("1", "1", "power_out" if pwr else "passive",
                    -2.54, 0, 180, 1.27)]))
    syms.append(symbol_def(
        "", "PWR_FLAG", "PWR_FLAG", "PWR_FLAG", "", "",
        "power flag: VCC1V2 is driven by U2 (TLV75512PDBVR) through FB1 "
        "(120R@100MHz bead) - KiCad ERC cannot propagate drive through a "
        "passive bead, so this flag's power_out pin carries the filtered "
        "rail. NOT an ERC exclusion.",
        polyline([(0, 0), (0, 2.54), (2.54, 1.27)]) +
        "\n" + polyline([(2.54, 1.27), (0, 0)]),
        [pindef("1", "1", "power_out", 0, 0, 270, 0)]))
    g = rect(-7.62, -3.81, 7.62, 3.81)
    pins = [pindef("1", "IN", "power_in", -7.62, 2.54, 0),
            pindef("2", "GND", "power_in", -7.62, -2.54, 0),
            pindef("3", "EN", "input", -7.62, 0, 0),
            pindef("4", "NC", "no_connect", 7.62, 2.54, 180),
            pindef("5", "OUT", "power_out", 7.62, -2.54, 180)]
    syms.append(symbol_def(
        "", "TLV755P_DBV", "U", "TLV755P_DBV",
        "Package_TO_SOT_SMD:SOT-23-5",
        "https://www.ti.com/lit/ds/symlink/tlv755p.pdf",
        "500mA fixed LDO, SOT-23-5 DBV: 1=IN 2=GND 3=EN 4=NC 5=OUT "
        "(TI SBVS320D Tbl 4-1); OUT is power_out - it sources VCC1V2_RAW", g,
        pins))
    return syms, gw_symbol_def()


# ---------------------------------------------------- GW1NZ-QN48 symbol def
F_LEFT = [("K1", "8"), ("K2", "10"), ("K3", "11"), ("K4", "13"),
          ("K5", "16"), ("K6", "17"), ("K7", "18"), ("K8", "20"),
          ("K9", "21"), ("K10", "23"), ("K11", "33"), ("K12", "34"),
          ("B_clk", "47"), ("T_W", "38"), ("T_endcol", "39"),
          ("B_first", "40"), ("L_endrow", "41"), ("T_data", "28"),
          ("L_data", "24"), ("B_latch", "22"), ("R_latch", "32")]
F_RIGHT = [("T_clk", "35"), ("L_clk", "19"), ("L_latch", "31"),
           ("B_data", "30"), ("B_W", "27"), ("JTAG_TCK", "3"),
           ("JTAG_TMS", "4"), ("JTAG_TDI", "5"), ("JTAG_TDO", "7"),
           ("CFG_READY", "45"), ("CFG_DONE", "46"), ("CFG_RECONFIG", "48"),
           ("JTAGSEL_N", "44"), ("MODE0", "43"), ("MODE1", "42")]
F_TOP = [("VCC", "1"), ("VCC", "25"), ("VCC", "36")]
F_BOT = [("VCC1V2", "12"), ("VCC1V2", "37"), ("GND", "2"), ("GND", "26"),
         ("GND", "49"), ("NC", "6"), ("NC", "9"), ("NC", "14"),
         ("NC", "15"), ("NC", "29")]

INPUTS = {"B_clk", "T_W", "T_endcol", "B_first", "L_endrow", "T_data",
          "L_data", "B_latch", "R_latch", "JTAG_TCK", "JTAG_TMS", "JTAG_TDI",
          "CFG_RECONFIG", "JTAGSEL_N", "MODE0", "MODE1"}
OUTPUTS = {"T_clk", "L_clk", "L_latch", "B_data", "B_W", "JTAG_TDO",
           "CFG_READY", "CFG_DONE"}

# Frame-neutral series-termination positions on the five forward-driven
# outputs (docs/termination.md; mirror of board_gen.SERIES_DRV_GW1NZ --
# schematic_check S6 guards the split).  Pin order matches board r6:
# R7=T_clk(35) R8=L_clk(19) R9=L_latch(31) R10=B_data(30) R11=B_W(27).
SERIES_DRV = (("T_clk", "R7"), ("L_clk", "R8"), ("L_latch", "R9"),
              ("B_data", "R10"), ("B_W", "R11"))
SERIES_DRV_NETS = {b for b, _r in SERIES_DRV}


def gw_symbol_def():
    pins = []
    y = 27.94
    for nm, num in F_LEFT:
        t = ("bidirectional" if nm.startswith("K") else
             "input" if nm in INPUTS else "output")
        pins.append(pindef(num, nm, t, -15.24, y, 0))
        y -= 2.54
    y = 27.94
    for nm, num in F_RIGHT:
        t = ("output" if nm in OUTPUTS else "input")
        pins.append(pindef(num, nm, t, 15.24, y, 180))
        y -= 2.54
    for x, (nm, num) in zip((-5.08, 0, 5.08), F_TOP):
        pins.append(pindef(num, nm, "power_in", x, 33.02, 90))
    for x, (nm, num) in zip((-12.7, -10.16, -7.62, -5.08, -2.54,
                             0, 2.54, 5.08, 7.62, 10.16), F_BOT):
        t = ("power_in" if nm in ("VCC1V2", "GND") else "no_connect")
        pins.append(pindef(num, nm, t, x, -33.02, 270))
    g = rect(-12.7, -30.48, 12.7, 30.48)
    return symbol_def("", "GW1NZ_QN48", "U", "GW1NZ-LV1QN48C6/I5",
                      "fpga_board:GW1NZ-QN48_6x6_P0.4mm_EP2.7x2.7mm",
                      "https://cdn.gowinsemi.com.cn/DS841E.pdf",
                      "Gowin LittleBee GW1NZ-1 FPGA, QFN48 6x6 P0.4, EPAD 49 "
                      "(GND); pins 6/9/14/15/29 unused (pin 9 = UG842-vs-"
                      "UG846 order-code hazard, excluded)", g, pins)


# ------------------------------------------------------------- wire emitters
def wire(x1, y1, x2, y2, tag):
    return (f'\t(wire\n\t\t(pts\n\t\t\t(xy {N(x1)} {N(y1)}) '
            f'(xy {N(x2)} {N(y2)})\n\t\t)\n\t\t(stroke\n\t\t\t(width 0)\n'
            f'\t\t\t(type default)\n\t\t)\n\t\t(uuid "{U("w-" + tag)}")\n\t)')


def label(name, x, y, tag, justify="left bottom"):
    return (f'\t(label "{name}"\n\t\t(at {N(x)} {N(y)} 0)\n\t\t(effects\n'
            '\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n'
            f'\t\t\t(justify {justify})\n\t\t)\n\t\t(uuid '
            f'"{U("lbl-" + tag)}")\n\t)')


def no_connect(x, y, tag):
    return (f'\t(no_connect\n\t\t(at {N(x)} {N(y)})\n\t\t(uuid '
            f'"{U("nc-" + tag)}")\n\t)')


def text(content, x, y, tag, size=1.5):
    esc = content.replace('"', '\\"')
    return (f'\t(text "{esc}"\n\t\t(at {N(x)} {N(y)} 0)\n\t\t(effects\n'
            f'\t\t\t(font\n\t\t\t\t(size {size} {size})\n\t\t\t)\n'
            '\t\t\t(justify left)\n\t\t)\n\t\t(uuid '
            f'"{U("txt-" + tag)}")\n\t)')


class Emitter:
    def __init__(self):
        self.nodes = []
        self.insts = []
        self.npwr = 0
        self.touch = {}          # (ref, pin) -> connection count
        self.nets = {}           # net -> [(ref,pin)]

    def mark(self, ref, pin, net):
        self.touch[(ref, pin)] = self.touch.get((ref, pin), 0) + 1
        if net:
            self.nets.setdefault(net, []).append((ref, pin))

    def pwr(self, net, x, y):
        self.npwr += 1
        ref = f"#PWR{self.npwr:04d}"
        sym = f"fpga_tile:PWR_{net}"
        self.insts.append(symbol_inst(sym, ref, net, x, y, ("1",),
                                      hideval=True))
        self.mark(ref, "1", net)
        return ref

    def inst(self, sym, ref, value, x, y, pins, footprint="",
             datasheet="", rot=0, refdy=-6.35, valdy=6.35):
        self.insts.append(symbol_inst(sym, ref, value, x, y, pins,
                                      footprint, datasheet, rot,
                                      refdy=refdy, valdy=valdy))
        for p in pins:
            self.touch[(ref, p)] = 0


def symbol_inst(libid, ref, value, x, y, pins, footprint="", datasheet="",
                rot=0, hideval=False, refdy=-6.35, valdy=6.35):
    pin_lines = "\n".join(f'\t\t(pin "{p}"\n\t\t\t(uuid "{U(ref + ":" + p)}")\n\t\t)'
                          for p in pins)
    return (f'\t(symbol\n\t\t(lib_id "{libid}")\n\t\t(at {N(x)} {N(y)} {rot})\n'
            '\t\t(unit 1)\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n'
            '\t\t(on_board yes)\n\t\t(in_pos_files yes)\n\t\t(dnp no)\n'
            '\t\t(fields_autoplaced yes)\n'
            f'\t\t(uuid "{U("inst-" + ref)}")\n'
            + prop("Reference", ref, x + (-5.08 if abs(refdy) else 0),
                   y + refdy, justify="left") + "\n"
            # Value must ALWAYS be present in the file: KiCad names power
            # nets from the INSTANCE Value of a (power global) symbol, so
            # omitting it leaves the rail nameless. hideval only hides it
            # on-screen.
            + prop("Value", value, x + (-5.08 if abs(valdy) else 0),
                   y + valdy, hide=hideval, justify="left") + "\n"
            + prop("Footprint", footprint, x, y, hide=True) + "\n"
            + prop("Datasheet", datasheet, x, y, hide=True) + "\n"
            + prop("Description", "", x, y, hide=True) + "\n"
            + pin_lines + "\n"
            f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n'
            f'\t\t\t\t(path "/{SHEET}"\n\t\t\t\t\t(reference "{ref}")\n'
            '\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)')


def vpart(em, sym, ref, value, footprint, x, y, net1, net2, tag,
          net1_kind="label", net2_kind="gnd"):
    """vertical 2-pin passive: pin1 up, pin2 down, stubs + label/pwr."""
    em.inst(sym, ref, value, x, y, ("1", "2"), footprint)
    p1 = (x, y - 5.08)
    e1 = (x, y - 10.16)
    p2 = (x, y + 5.08)
    e2 = (x, y + 10.16)
    em.nodes.append(wire(*p1, *e1, tag + "-1"))
    em.nodes.append(wire(*p2, *e2, tag + "-2"))
    if net1_kind == "label":
        em.nodes.append(label(net1, *e1, tag + "-l1"))
    else:
        em.pwr(net1, *e1)
    if net2_kind == "label":
        em.nodes.append(label(net2, *e2, tag + "-l2"))
    else:
        em.pwr(net2, *e2)  # GND or VCC symbol
    em.mark(ref, "1", net1)
    em.mark(ref, "2", net2)


# ----------------------------------------------------------------- the sheet
def build():
    em = Emitter()
    # ---- U1 -- every connection endpoint on the 1.27 mm KiCad grid
    U1X, U1Y = 175.26, 111.76            # grid 138 x 88
    em.inst("fpga_tile:GW1NZ_QN48", "U1", "GW1NZ-LV1QN48C6/I5", U1X, U1Y,
            [str(i) for i in range(1, 50)],
            footprint="fpga_board:GW1NZ-QN48_6x6_P0.4mm_EP2.7x2.7mm",
            datasheet="DS841E.pdf (sha256 a19cdd7a..; see board/data)",
            refdy=34.29, valdy=-34.29)
    xlt, xls = U1X - 15.24, U1X - 20.32  # left pin tip / stub end
    xrt, xrs = U1X + 15.24, U1X + 20.32  # right pin tip / stub end
    y = 27.94
    for nm, num in F_LEFT:
        sy = U1Y - y                      # sheet y of the pin tip
        em.nodes.append(wire(xlt, sy, xls, sy, f"u1-{num}"))
        em.nodes.append(label(nm, xls, sy, f"u1l-{num}", "right bottom"))
        em.mark("U1", num, nm)
        y -= 2.54
    y = 27.94
    for nm, num in F_RIGHT:
        # the five series-terminated outputs leave the pin on <net>_DRV
        # (interface net name stays at the JP pad, after Rn); symbol pin
        # name stays the semantic one (F_RIGHT tuples drive pin naming)
        net = nm + "_DRV" if nm in SERIES_DRV_NETS else nm
        sy = U1Y - y
        em.nodes.append(wire(xrt, sy, xrs, sy, f"u1-{num}"))
        em.nodes.append(label(net, xrs, sy, f"u1l-{num}"))
        em.mark("U1", num, net)
        y -= 2.54
    yt, yts = U1Y - 33.02, U1Y - 38.10   # top tip 78.74 / stub end 73.66
    yb, ybs = U1Y + 33.02, U1Y + 38.10   # bottom tip 144.78 / end 149.86
    for x, (nm, num) in zip((U1X - 5.08, U1X, U1X + 5.08), F_TOP):
        em.nodes.append(wire(x, yt, x, yts, f"u1-{num}"))
        em.pwr("VCC", x, yts)
        em.mark("U1", num, "VCC")
    for x, (nm, num) in zip(
            tuple(U1X + dx for dx in (-12.70, -10.16, -7.62, -5.08, -2.54,
                                      0, 2.54, 5.08, 7.62, 10.16)),
            F_BOT):
        if nm == "NC":
            em.nodes.append(no_connect(x, yb, f"u1nc-{num}"))
            em.touch[("U1", num)] = 1
        else:
            em.nodes.append(wire(x, yb, x, ybs, f"u1-{num}"))
            em.pwr(nm, x, ybs)
            em.mark("U1", num, nm)
            if nm == "VCC1V2" and num == "12":
                # power flag on the bead-filtered rail (drive from U2 via
                # FB1 is invisible to ERC) -- documented, not an exclusion
                em.nodes.append(wire(x, ybs, x, ybs + 5.08, "u1-12f"))
                em.inst("fpga_tile:PWR_FLAG", "FLG1", "VCC1V2 via FB1",
                        x, ybs + 5.08, ("1",), refdy=-3.81, valdy=3.81)
                em.mark("FLG1", "1", "VCC1V2")
    # ---- LDO power section (left); U2: 1=IN 2=GND 3=EN 4=NC 5=OUT
    U2X, U2Y = 45.72, 53.34              # grid 36 x 42
    em.inst("fpga_tile:TLV755P_DBV", "U2", "TLV75512PDBVR", U2X, U2Y,
            ("1", "2", "3", "4", "5"),
            footprint="Package_TO_SOT_SMD:SOT-23-5",
            datasheet="tlv755p.pdf SBVS320D; 1=IN 2=GND 3=EN 4=NC 5=OUT",
            refdy=-6.35, valdy=6.35)
    em.nodes.append(wire(U2X - 7.62, U2Y - 2.54, U2X - 12.70, U2Y - 2.54,
                         "u2-in"))
    em.pwr("VCC", U2X - 12.70, U2Y - 2.54)                # U2.1 IN
    em.mark("U2", "1", "VCC")
    em.nodes.append(wire(U2X - 7.62, U2Y + 2.54, U2X - 12.70, U2Y + 2.54,
                         "u2-g"))
    em.pwr("GND", U2X - 12.70, U2Y + 2.54)                # U2.2
    em.mark("U2", "2", "GND")
    em.nodes.append(wire(U2X - 7.62, U2Y, U2X - 12.70, U2Y, "u2-en"))
    em.pwr("VCC", U2X - 12.70, U2Y)                       # U2.3 EN = IN
    em.mark("U2", "3", "VCC")
    em.nodes.append(wire(U2X + 7.62, U2Y + 2.54, U2X + 12.70, U2Y + 2.54,
                         "u2-out"))
    em.nodes.append(label("VCC1V2_RAW", U2X + 12.70, U2Y + 2.54, "u2-outl"))
    em.mark("U2", "5", "VCC1V2_RAW")
    em.nodes.append(no_connect(U2X + 7.62, U2Y - 2.54, "u2-nc"))  # U2.4 NC
    em.touch[("U2", "4")] = 1
    # caps / FB (all part origins on grid)
    vpart(em, "fpga_tile:C", "C9", "1u",
          "Capacitor_SMD:C_0603_1608Metric", 25.40, 63.50, "VCC", "GND",
          "c9", net1_kind="pwr")
    vpart(em, "fpga_tile:C", "C8", "1u",
          "Capacitor_SMD:C_0603_1608Metric", 58.42, 63.50, "VCC1V2_RAW",
          "GND", "c8")
    for ref, x, net in (("C1", 25.40, "VCC"), ("C2", 35.56, "VCC"),
                        ("C3", 45.72, "VCC"), ("C7", 55.88, "VCC")):
        vpart(em, "fpga_tile:C", ref, "100n" if ref != "C7" else "4u7",
              "Capacitor_SMD:C_0603_1608Metric" if ref != "C7"
              else "Capacitor_SMD:C_1206_3216Metric", x, 81.28, net, "GND",
              ref.lower(), net1_kind="pwr")
    for ref, x in (("C4", 25.40), ("C5", 35.56), ("C6", 45.72)):
        vpart(em, "fpga_tile:C", ref, "100n" if ref != "C6" else "4u7",
              "Capacitor_SMD:C_0603_1608Metric" if ref != "C6"
              else "Capacitor_SMD:C_1206_3216Metric", x, 99.06, "VCC1V2",
              "GND", ref.lower(), net1_kind="pwr")
    vpart(em, "fpga_tile:FB", "FB1", "FB 120R@100M",
          "Resistor_SMD:R_0603_1608Metric", 58.42, 99.06, "VCC1V2_RAW",
          "VCC1V2", "fb1", net1_kind="label", net2_kind="pwr")
    # rail test points (power rails: tie with a power symbol, no rail label)
    for ref, net, x, y in (("TP_VCC", "VCC", 73.66, 81.28),
                           ("TP_VCC1V2", "VCC1V2", 73.66, 99.06),
                           ("TP_GND", "GND", 73.66, 116.84)):
        em.inst("fpga_tile:TP", ref, net, x, y, ("1",),
                footprint="TestPoint:TestPoint_Pad_D1.0mm")
        em.nodes.append(wire(x, y, x + 5.08, y, ref + "-w"))
        em.pwr(net, x + 5.08, y)
        em.mark(ref, "1", net)
    # straps
    for ref, x, net, val, dst in (("R1", 25.40, "MODE0", "1k", "GND"),
                                  ("R2", 33.02, "MODE1", "1k", "GND"),
                                  ("R3", 40.64, "JTAG_TCK", "4k7", "GND"),
                                  ("R4", 49.53, "CFG_READY", "4k7", "VCC"),
                                  ("R5", 58.42, "CFG_DONE", "4k7", "VCC"),
                                  ("R6", 66.04, "CFG_RECONFIG", "4k7",
                                   "VCC")):
        vpart(em, "fpga_tile:R", ref, val,
              "Resistor_SMD:R_0603_1608Metric", x, 127.00, net, dst,
              ref.lower(), net2_kind="gnd" if dst == "GND" else "vcc")
    # series-termination positions R7..R11 in-line on the forward-driven
    # outputs: pin1 on the U1-side <net>_DRV, pin2 on the interface net
    # (JP pad keeps the original net name). 0R populated default ==
    # today's circuit; value selected after bench item B2.
    for k, (net, ref) in enumerate(SERIES_DRV):
        vpart(em, "fpga_tile:R", ref, "0R",
              "Resistor_SMD:R_0402_1005Metric", 320.04, 88.90 + 12.70 * k,
              net + "_DRV", net, ref.lower(), net2_kind="label")
    # JTAG / status test points
    for i, (ref, net) in enumerate((("TP_TCK", "JTAG_TCK"),
                                    ("TP_TMS", "JTAG_TMS"),
                                    ("TP_TDI", "JTAG_TDI"),
                                    ("TP_TDO", "JTAG_TDO"),
                                    ("TP_READY", "CFG_READY"),
                                    ("TP_DONE", "CFG_DONE"),
                                    ("TP_RECFG", "CFG_RECONFIG"),
                                    ("TP_JTAGSEL", "JTAGSEL_N"))):
        row, col = divmod(i, 2)
        x = 215.90 if col == 0 else 241.30
        y = 152.40 + 10.16 * row
        em.inst("fpga_tile:TP", ref, net, x, y, ("1",),
                footprint="TestPoint:TestPoint_Pad_D1.0mm")
        em.nodes.append(label(net, x, y, f"{ref}-l"))
        em.mark(ref, "1", net)
    # ---- keys
    for q in range(12):
        col, row = divmod(q, 6)
        x = 233.68 if col == 0 else 269.24
        y = 35.56 + 13.97 * row
        ref = f"SW{q + 1}"
        em.inst("fpga_tile:SW_KAILH", ref, "Kailh MX hotswap", x, y,
                ("1", "2"),
                footprint="fpga-vendored:SW_Hotswap_Kailh_MX_1.00u",
                refdy=-5.08, valdy=5.08)
        em.nodes.append(wire(x - 3.81, y, x - 8.89, y, f"{ref}-1"))
        em.pwr("VCC", x - 8.89, y)
        em.mark(ref, "1", "VCC")
        em.nodes.append(wire(x + 3.81, y, x + 8.89, y, f"{ref}-2"))
        em.nodes.append(label(f"K{q + 1}", x + 8.89, y, f"{ref}-2l"))
        em.mark(ref, "2", f"K{q + 1}")
    # ---- chassis pads (19)
    # ---- chassis pads (19)
    jp = [("JP_VCC", "VCC", "VCC IN (3.3 V from chassis)", True),
          ("JP_GND", "GND", "GND", True),
          ("JP_T_clk", "T_clk", "T_clk OUT (to above neighbour)", False),
          ("JP_T_data", "T_data", "T_data IN", False),
          ("JP_T_endcol", "T_endcol", "T_endcol IN (presence)", False),
          ("JP_T_W", "T_W", "T_W IN (presence)", False),
          ("JP_L_clk", "L_clk", "L_clk OUT (to left neighbour)", False),
          ("JP_L_data", "L_data", "L_data IN", False),
          ("JP_L_endrow", "L_endrow", "L_endrow IN (presence)", False),
          ("JP_L_latch", "L_latch", "L_latch OUT (latch forward)", False),
          ("JP_B_clk", "B_clk", "B_clk IN (20 MHz shift clock)", False),
          ("JP_B_data", "B_data", "B_data OUT (chain serial data)", False),
          ("JP_B_first", "B_first", "B_first IN (presence)", False),
          ("JP_B_latch", "B_latch", "B_latch IN", False),
          ("JP_B_W", "B_W", "B_W OUT (column end)", False),
          ("JP_R_latch", "R_latch", "R_latch IN", False),
          ("JP_GND_DET_T", "GND",
           "presence GND (J102.5: serves above neighbour's B_first)", False),
          ("JP_GND_DET_B", "GND",
           "presence GND (J103.4: serves below neighbour's T_endcol)", False),
          ("JP_GND_DET_R", "GND",
           "presence GND (J104.4: serves right neighbour's L_endrow)", False)]
    for i, (ref, net, role, pwr) in enumerate(jp):
        x, y = 355.60, 20.32 + 13.97 * i
        em.inst(f"fpga_tile:JP_PAD{'_PWR' if pwr else ''}", ref, role,
                x, y, ("1",), refdy=-4.57, valdy=4.57)
        tip = (x - 2.54, y)
        if pwr:
            # JP_PAD_PWR pad pin is the rail source (power_out): tie the
            # rail's power symbol at the contact so the pad actually feeds
            # the named net (avoids an isolated island + undriven rail).
            em.pwr(net, *tip)
        elif net == "GND":
            # presence-detect pads are bonded to tile GND: tie with a GND
            # power symbol right at the contact (pad -> hard GND on insert)
            em.pwr("GND", *tip)
        else:
            em.nodes.append(label(net, *tip, f"{ref}-l", "right bottom"))
        em.mark(ref, "1", net)
    # ---- notes
    notes = [
        ("FPGA TILE (single-PCB, rev-A frame/topology) -- authoritative "
         "schematic. Generated by board/kicad/sch_gen.py; regenerate, do "
         "not hand-edit.", 25.40, 246.38),
        ("FPGA: Gowin GW1NZ-LV1QN48C6/I5 (QN48 6x6 P0.4). Config: "
         "MODE[2:0]='000 AUTO BOOT from embedded flash (UG290); JTAG live on "
         "TCK/TMS/TDI/TDO test pads; 26 tile IO per production cst; unused "
         "pads 6/9/14/15/29 (pin 9 = UG842/UG846 order-code hazard).",
         25.40, 256.54),
        ("Rails: VCC 3.3 V from chassis (JP_VCC power_out feeds the tile); "
         "VCC1V2 1.2 V locally regulated by U2=TI TLV75512PDBVR (SBVS320D: "
         "CIN>=1u C9, COUT>=1u C8 BEFORE bead FB1; core caps C4/C5/C6 sit on "
         "the filtered side). Accuracy 1.188-1.212 V within 1.07-1.26 V "
         "spec.", 25.40, 266.70),
        ("Presence: JP_GND_DET_T/B/R are BONDED to tile GND (inserted = hard "
         "ground on the contact, removed = open); the backplane keeps the "
         "three detect traces separate (connector-next owns them).",
         25.40, 276.86),
        ("Outputs: R7..R11 (0402, 0R populated) are frame-neutral series-"
         "termination positions on T_clk/L_clk/L_latch/B_data/B_W "
         "(U1-<net>_DRV--Rn--<net>-JP). Value chosen after bench B2; the "
         "free edge knob is the RTL DRIVE attribute (OSS-proven: cst "
         "attrs are ignored, RTL attrs reach the bitstream). See "
         "docs/termination.md.",
         25.40, 287.02),
    ]
    for i, (t, x, y) in enumerate(notes):
        em.nodes.append(text(t, x, y, f"n{i}", 1.5))
    return em


def sch0(em):
    problems = []
    have = {r for (r, _p) in em.touch}
    for (ref, pin), cnt in sorted(em.touch.items()):
        if cnt == 0:
            problems.append(f"{ref}.{pin} never connected by emitter")
    want_nets = ({"VCC", "GND", "VCC1V2", "VCC1V2_RAW"} |
                 {f"K{i}" for i in range(1, 13)} |
                 # board r6: the 5 series-terminated outputs also carry
                 # their driver-side <net>_DRV stubs (SCH0 must expect them)
                 {b + "_DRV" for b in SERIES_DRV_NETS} |
                 {"T_W", "T_clk", "T_data", "T_endcol", "B_W", "B_clk",
                  "B_data", "B_first", "B_latch", "L_clk", "L_data",
                  "L_endrow", "L_latch", "R_latch", "MODE0", "MODE1",
                  "JTAG_TCK", "JTAG_TMS", "JTAG_TDI", "JTAG_TDO",
                  "CFG_READY", "CFG_DONE", "CFG_RECONFIG", "JTAGSEL_N"})
    got_nets = set(em.nets)
    if got_nets != want_nets:
        problems.append(f"net census mismatch: only-in-sch="
                        f"{sorted(got_nets - want_nets)} missing="
                        f"{sorted(want_nets - got_nets)}")
    u1 = {p for (r, p) in em.touch if r == "U1"}
    if u1 != {str(i) for i in range(1, 50)}:
        problems.append(f"U1 pins missing: {sorted({str(i) for i in range(1, 50)} - u1)}")
    return {"ok": not problems, "problems": problems,
            "census": {"refs": len(have), "parts": len(em.insts),
                       "pwr_symbols": em.npwr, "nets": len(got_nets),
                       "net_names": sorted(got_nets)}}


def main():
    os.makedirs(os.path.join(KOUT, "lib"), exist_ok=True)
    syms, gw = libdefs()
    # NOTE: KiCad 10.0.6 accepts 20230121-era sym-lib headers and migrates
    # them; the 20260306 (schematic-era) version string is REJECTED here
    # ("unable to load library"). Keep 20230121 for the standalone lib.
    lib_text = ('(kicad_symbol_lib (version 20230121) (generator '
                '"kicad_symbol_editor") (generator_version "7.0")\n' +
                "\n".join(syms) + "\n" + gw + "\n)\n")
    with open(os.path.join(KOUT, "lib", "fpga_tile.kicad_sym"), "w") as f:
        f.write(lib_text)
    with open(os.path.join(KOUT, "sym-lib-table"), "w") as f:
        f.write('(sym_lib_table\n\t(version 7)\n\t(lib (name "fpga_tile")\n'
                '\t\t(type "KiCad")\n\t\t(uri "${KIPRJMOD}/lib/'
                'fpga_tile.kicad_sym")\n\t\t(options "")\n'
                '\t\t(descr "project-local FPGA tile symbols (kicad/'
                'sch_gen.py)"))\n)\n')
    with open(os.path.join(KOUT, "fp-lib-table"), "w") as f:
        f.write('(fp_lib_table\n\t(version 7)\n'
                '\t(lib (name "fpga_board")\n\t\t(type "KiCad")\n'
                '\t\t(uri "${KIPRJMOD}/../../kicad/lib/fpga_board.pretty")\n'
                '\t\t(options "")\n\t\t(descr "tile-board local footprints '
                '(GW1NZ QN48, connector pads)"))\n'
                '\t(lib (name "fpga-vendored")\n\t\t(type "KiCad")\n'
                '\t\t(uri "${KIPRJMOD}/../../../../../../kicad/lib/'
                'Switch_Keyboard_Hotswap_Kailh.pretty")\n'
                '\t\t(options "")\n\t\t(descr "rev-A vendored Kailh hotswap '
                'socket footprints (read-only)"))\n)\n')
    emoded = build()
    check = sch0(emoded)
    prefix_syms = []
    for sdef in syms:
        prefix_syms.append(sdef.replace('\t\t(symbol "', '\t\t(symbol '
                                        '"fpga_tile:', 1))
    pref_gw = gw.replace('\t\t(symbol "', '\t\t(symbol "fpga_tile:', 1)
    sch = ('(kicad_sch\n\t(version 20260306)\n\t(generator "eeschema")\n'
           '\t(generator_version "10.0")\n'
           f'\t(uuid "{str(SHEET)}")\n\t(paper "A3")\n\t(lib_symbols\n'
           + "\n".join(prefix_syms) + "\n" + pref_gw + "\n\t)\n"
           + "\n".join(emoded.nodes) + "\n"
           + "\n".join(emoded.insts) + "\n"
           '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n)\n')
    with open(os.path.join(KOUT, "tile_gw1nz.kicad_sch"), "w") as f:
        f.write(sch)
    check["outputs"] = {
        "sch": "out/kicad/tile_gw1nz.kicad_sch",
        "sym": "out/kicad/lib/fpga_tile.kicad_sym",
        "symlib_table": "out/kicad/sym-lib-table"}
    with open(os.path.join(OUT, "sch_summary.json"), "w") as f:
        json.dump(check, f, indent=1)
    print("SCH0 self-check:", "PASS" if check["ok"] else "FAIL",
          check.get("problems") or "")
    print("census:", json.dumps(check["census"]))
    if not check["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
