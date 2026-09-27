#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Rev C microcontroller tile: the circuit, in one place.

revc_mcu_schematic.py draws it as a KiCad schematic; revc_mcu_build.py places and routes
the board and takes every net from the netlist that KiCad exports from that schematic
(the schematic is the reference, as in any KiCad project). Plain Python, no KiCad import.
"""
import json
import os

# ATtiny1616-MNR VQFN-20 3x3 mm, 0.40 mm pitch, 1.7 mm exposed pad (DS40002204A 4.3, 39.4);
# the SOIC-20 wide version (about 13 x 10 mm) does not fit between the sockets and LEDs
PIN = {"PA2": 1, "PA3": 2, "GND": 3, "VDD": 4, "PA4": 5, "PA5": 6, "PA6": 7, "PA7": 8,
       "PB5": 9, "PB4": 10, "PB3": 11, "PB2": 12, "PB1": 13, "PB0": 14, "PC0": 15, "PC1": 16,
       "PC2": 17, "PC3": 18, "PA0": 19, "PA1": 20, "EP": 21}
# Fixed pins: PA0 = UPDI; PB2 = USART TX (default) and PA1 = USART TX (alternate) carry the
# bottom and right edges (hardware one-wire USART). Every other signal -- keys K1..K12 (row-
# major order on the board, row 0 = top row), the top and left edge lines (software serial,
# any pin has a pin-change interrupt) and the LED data (bit-banged) -- can use any of the 15
# remaining GPIOs. The board build picks that assignment from the geometry, so that the
# traces leave the 0.4 mm-pitch package without crossing, and stores it in PINMAP_FILE;
# the schematic is drawn from it and the firmware reads it.
FIXED = {"UPDI": "PA0", "DATA_B_MCU": "PB2", "DATA_R_MCU": "PA1"}
FLEX_PORTS = ["PA2", "PA3", "PA4", "PA5", "PA6", "PA7", "PB0", "PB1", "PB3", "PB4", "PB5",
              "PC0", "PC1", "PC2", "PC3"]
FLEX_NETS = [f"K{n + 1}" for n in range(12)] + ["DATA_T_MCU", "DATA_L_MCU", "LED_DIN"]
PINMAP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "revc-mcu-tile",
                           "pinmap.json")


def pinmap():
    """{net: port} for the 15 flexible signals (the stored board-derived one, else a default)"""
    if os.path.exists(PINMAP_FILE):
        m = json.load(open(PINMAP_FILE))["flexible"]
        assert sorted(m) == sorted(FLEX_NETS) and sorted(m.values()) == sorted(FLEX_PORTS)
        return m
    return dict(zip(FLEX_NETS, FLEX_PORTS))


def stored_orientation():
    """MCU orientation (degrees) the stored pin map was made for, or None"""
    if os.path.exists(PINMAP_FILE):
        return json.load(open(PINMAP_FILE)).get("mcu_orientation")
    return None


def save_pinmap(m, orientation):
    os.makedirs(os.path.dirname(PINMAP_FILE), exist_ok=True)
    full = {**{n: p for n, p in FIXED.items()}, **m}
    json.dump({"comment": "ATtiny1616 port for each signal of the rev C tile; written by "
                          "revc_mcu_build.py from the board geometry (flexible), fixed by design (fixed)",
               "mcu_orientation": orientation, "fixed": FIXED, "flexible": dict(sorted(m.items(), key=lambda t: FLEX_NETS.index(t[0]))),
               "port_of": dict(sorted(full.items()))},
              open(PINMAP_FILE, "w"), indent=2)
    open(PINMAP_FILE, "a").write("\n")
# tiles never rotate, so the order need not be symmetric: 3 contacts per edge
ORDER = ["VCC", "DATA", "GND"]
# contacts: right/bottom = spring contacts (active half), left/top = edge pads (passive half)
EDGE_CONTACT = {"R": ("J1", "right"), "L": ("J2", "left"), "B": ("J3", "bottom"), "T": ("J4", "top")}
EDGE_RES = {"B": "R1", "R": "R2", "T": "R3", "L": "R4"}
# LED chain: key indices in chain order. It starts at D6, next to the MCU (which sits between
# D6 and D7), and every link goes to a neighbouring key: D6 D5 | D1 D2 D3 D4 | D8 D7 | D12 D11
# D10 D9. The firmware maps chain position -> key with this list.
CHAIN = [5, 4, 0, 1, 2, 3, 7, 6, 11, 10, 9, 8]
# decoupling: C1 + C2 at the MCU, C3..C6 next to the corner LEDs
DECOUPLING = [("C1", "100n", None), ("C2", "4u7", None), ("C3", "100n", "D1"), ("C4", "100n", "D4"),
              ("C5", "100n", "D9"), ("C6", "100n", "D12")]

FP = {
    "mcu": "Package_DFN_QFN:VQFN-20-1EP_3x3mm_P0.4mm_EP1.7x1.7mm",
    "sw": "Switch_Keyboard_Hotswap_Kailh:SW_Hotswap_Kailh_MX_1.00u_EdgeTrim",
    "led": "LED_SMD:LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount",
    "r": "Resistor_SMD:R_0603_1608Metric",
    "c100n": "Capacitor_SMD:C_0603_1608Metric",
    "c4u7": "Capacitor_SMD:C_0805_2012Metric",
    "tp": "TestPoint:TestPoint_Pad_D1.5mm",
}


def parts():
    """[{ref, lib_id, value, footprint, fields, pins: {number: net or None (= no connect)},
    in_bom}] -- net names are global (no sheet prefix)."""
    out = []

    def add(ref, lib_id, value, footprint, pins, fields=None, in_bom=True):
        out.append(dict(ref=ref, lib_id=lib_id, value=value, footprint=footprint, pins=pins,
                        fields=fields or {}, in_bom=in_bom))

    u = {PIN["VDD"]: "VCC", PIN["GND"]: "GND", PIN["EP"]: "GND"}
    for net, port in {**FIXED, **pinmap()}.items():
        u[PIN[port]] = net
    add("U1", "MCU_Microchip_ATtiny:ATtiny1616-M", "ATtiny1616-MNR", FP["mcu"], u,
        {"Manufacturer": "Microchip", "MPN": "ATTINY1616-MNR"})
    for n in range(12):
        add(f"SW{n + 1}", "Switch:SW_Push", "MX hot-swap", FP["sw"], {1: "GND", 2: f"K{n + 1}"},
            {"Manufacturer": "Kailh", "MPN": "CPG151101S11"})
    din = "LED_DIN"
    for k, n in enumerate(CHAIN):
        dout = f"LED_D{n + 1}" if k < len(CHAIN) - 1 else None     # last DOUT: no connect
        add(f"D{n + 1}", "LED:SK6812MINI-E", "SK6812MINI-E", FP["led"],
            {1: "GND", 2: din, 3: "VCC", 4: dout}, {"Manufacturer": "Opsco", "MPN": "SK6812MINI-E"})
        din = dout
    for e, rref in EDGE_RES.items():
        add(rref, "Device:R", "100", FP["r"], {1: f"DATA_{e}_MCU", 2: f"DATA_{e}"},
            {"Manufacturer": "Yageo", "MPN": "RC0603FR-07100RL"})
    for ref, v, _ in DECOUPLING:
        mpn = "CL10B104KB8NNNC" if v == "100n" else "CL21A475KAQNNNE"
        add(ref, "Device:C", v, FP["c100n"] if v == "100n" else FP["c4u7"], {1: "VCC", 2: "GND"},
            {"Manufacturer": "Samsung", "MPN": mpn})
    for e, (jref, side) in EDGE_CONTACT.items():
        pins = {i + 1: (f"DATA_{e}" if s == "DATA" else s) for i, s in enumerate(ORDER)}
        kind = "spring contacts" if side in ("right", "bottom") else "edge pads"
        # not in the BOM yet: the spring contact part is still to be chosen, the edge pads are copper
        add(jref, "Connector_Generic:Conn_01x03", f"{kind} {side}", f"revc:EdgeContacts_{side}", pins,
            in_bom=False)
    add("TP1", "Connector:TestPoint", "UPDI", FP["tp"], {1: "UPDI"}, in_bom=False)
    return out


# --- minimal s-expression reader/writer (KiCad files and netlists) -----------------------
def sx_parse(text):
    tok, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            tok.append(c); i += 1
        elif c.isspace():
            i += 1
        elif c == '"':
            j, s = i + 1, []
            while text[j] != '"':
                if text[j] == "\\":
                    j += 1
                s.append(text[j]); j += 1
            tok.append(("s", "".join(s))); i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()":
                j += 1
            tok.append(text[i:j]); i = j
    stack = [[]]
    for t in tok:
        if t == "(":
            stack.append([])
        elif t == ")":
            e = stack.pop(); stack[-1].append(e)
        else:
            stack[-1].append(t)
    return stack[0][0]


def sx_str(e, ind=0):
    if isinstance(e, tuple):
        return '"' + e[1].replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(e, str):
        return e
    if all(not isinstance(x, list) for x in e):
        return "(" + " ".join(sx_str(x) for x in e) + ")"
    pad = "\t" * (ind + 1)
    head = [sx_str(x) for x in e if not isinstance(x, list)]
    body = [pad + sx_str(x, ind + 1) for x in e if isinstance(x, list)]
    return "(" + " ".join(head) + "\n" + "\n".join(body) + "\n" + "\t" * ind + ")"


def sx_val(x):
    return x[1] if isinstance(x, tuple) else x


def sx_find(e, key):
    return [x for x in e if isinstance(x, list) and x and x[0] == key]


def read_netlist(path):
    """KiCad s-expression netlist -> ({ref: {value, footprint, path, fields}}, {(ref, pin): net})"""
    root = sx_parse(open(path).read())
    comps, nets = {}, {}
    for c in sx_find(sx_find(root, "components")[0], "comp"):
        ref = sx_val(sx_find(c, "ref")[0][1])
        sheet = sx_val(sx_find(sx_find(c, "sheetpath")[0], "tstamps")[0][1])
        comps[ref] = dict(value=sx_val(sx_find(c, "value")[0][1]),
                          footprint=sx_val(sx_find(c, "footprint")[0][1]) if sx_find(c, "footprint") else "",
                          path=sheet + sx_val(sx_find(c, "tstamps")[0][1]),
                          fields={sx_val(sx_find(f, "name")[0][1]): (sx_val(f[2]) if len(f) > 2 else "")
                                  for f in sx_find(sx_find(c, "fields")[0], "field")} if sx_find(c, "fields") else {})
    for net in sx_find(sx_find(root, "nets")[0], "net"):
        name = sx_val(sx_find(net, "name")[0][1])
        for node in sx_find(net, "node"):
            nets[(sx_val(sx_find(node, "ref")[0][1]), sx_val(sx_find(node, "pin")[0][1]))] = name
    return comps, nets
