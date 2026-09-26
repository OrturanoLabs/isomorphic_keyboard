#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""One-shot, reviewable edit of the tile schematic from rev A to rev B.

Function is frozen: no logic connection changes. What it does:
  1. Series source-termination resistors (33 ohm) between every driver that leaves the tile
     and its hierarchical label. The hierarchical label on the driver side becomes a local
     label "<name>_drv"; the resistor goes from that local label to a new hierarchical label
     with the original name (so the root sheet and connectors are untouched):
         L_clk (U101)  T_clk (U107)  L_latch/T_latch (U106A)  B_data/R_data (U104 Q7)  B_W (U108)
  2. One 100 nF 0603 decoupling capacitor per logic IC (C201..C209), plus PWR_FLAGs on VCC,
     GND, VCC_T and GND_T (fixes the rev-A ERC errors "power_pin_not_driven").
  3. Values set to the parts actually ordered (74LVC / 74HC), footprints changed to
     assembly-ready ones (0603 passives, TI DCT land pattern, standard SOT-23-5, SMD bulk
     cap, Kailh MX hot-swap sockets), MPN/Manufacturer fields; the Italian-market "Link"
     field is dropped.

Verification (docs/build/hardware.md): exported netlist must be identical to rev A after
  check_invariants.py netlist ... --series R201,...,R207 --ignore C201,...,C209
Run from hardware/kicad/tile/:  python3 scripts/revb_schematic.py
"""
import re
import sys
import uuid

ROOT_UUID = "2a6329ec-b0e8-4012-8f5a-476608b8b2cc"
TILE_SHEET = "07e251ec-a89a-41e0-b307-1d6ec78f24c5"
POWER_SHEET = "9a558694-86a7-4e5b-949e-b5a09151abcf"
TILE_PATH = f"/{ROOT_UUID}/{TILE_SHEET}"
POWER_PATH = f"/{ROOT_UUID}/{TILE_SHEET}/{POWER_SHEET}"
PROJECT = "isomorphic_tile"

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
RS_VALUE, RS_MPN = "33", "RC0603FR-0733RL"

# (hierarchical label driven by the IC, local driver-side label, new series resistor)
SERIES = [
    ("L_clk", "L_clk_drv", "R201"),
    ("T_clk", "T_clk_drv", "R202"),
    ("L_latch", "latch_drv", "R203"),
    ("T_latch", "latch_drv", "R204"),
    ("B_data", "data_drv", "R205"),
    ("R_data", "data_drv", "R206"),
    ("B_W", "B_W_drv", "R207"),
]

# field updates for existing symbols: ref -> (value, footprint, manufacturer, mpn)
PARTS = {
    "U101": ("74LVC2G126", "Package_SO:SSOP-8_2.95x2.8mm_P0.65mm", "Texas Instruments", "SN74LVC2G126DCTR"),
    "U102": ("74LVC2G08", "Package_SO:SSOP-8_2.95x2.8mm_P0.65mm", "Texas Instruments", "SN74LVC2G08DCTR"),
    "U103": ("74LVC165A", "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm", "Texas Instruments", "SN74LVC165ADR"),
    "U104": ("74LVC165A", "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm", "Texas Instruments", "SN74LVC165ADR"),
    "U105": ("74LVC1G04", "Package_TO_SOT_SMD:SOT-23-5", "Texas Instruments", "SN74LVC1G04DBVR"),
    "U106": ("74LVC2G32", "Package_SO:SSOP-8_2.95x2.8mm_P0.65mm", "Texas Instruments", "SN74LVC2G32DCTR"),
    "U107": ("74LVC2G125", "Package_SO:SSOP-8_2.95x2.8mm_P0.65mm", "Texas Instruments", "SN74LVC2G125DCTR"),
    "U108": ("74LVC2G74", "Package_SO:SSOP-8_2.95x2.8mm_P0.65mm", "Texas Instruments", "SN74LVC2G74DCTR"),
    "U109": ("74HC161", "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm", "Texas Instruments", "SN74HC161DR"),
    "C101": ("100n", C0603, "Samsung", "CL10B104KB8NNNC"),
    "C102": ("100n", C0603, "Samsung", "CL10B104KB8NNNC"),
    "C103": ("4u7", "Capacitor_SMD:C_1206_3216Metric", "Samsung", "CL31B475KAHNNNE"),
    "C104": ("4u7", "Capacitor_SMD:C_1206_3216Metric", "Samsung", "CL31B475KAHNNNE"),
    "C105": ("100u", "Capacitor_SMD:CP_Elec_6.3x7.7", "", ""),   # 100 uF >= 10 V SMD Al, to be selected
}
for n in list(range(101, 110)) + list(range(122, 134)):
    PARTS[f"R{n}"] = ("10k", R0603, "Yageo", "RC0603FR-0710KL")
for n in range(110, 122):
    PARTS[f"R{n}"] = ("100", R0603, "Yageo", "RC0603FR-07100RL")
for n in range(101, 113):
    PARTS[f"SW{n}"] = ("SW_Push", "Switch_Keyboard_Hotswap_Kailh:SW_Hotswap_Kailh_MX_1.00u_EdgeTrim",
                       "Kailh", "CPG151101S11")


def uid():
    return str(uuid.uuid4())


def font(justify=None):
    j = f"\n\t\t\t(justify {justify})" if justify else ""
    return f"(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t){j}\n\t\t)"


def prop(name, value, x, y, rot=0, hide=True, justify=None):
    h = "\n\t\t\t(hide yes)" if hide else ""
    j = f"\n\t\t\t\t(justify {justify})" if justify else ""
    return (f'\t\t(property "{name}" "{value}"\n\t\t\t(at {x:g} {y:g} {rot}){h}\n'
            f'\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n\t\t\t\t(font\n'
            f'\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t){j}\n\t\t\t)\n\t\t)\n')


def symbol(lib_id, x, y, ref, value, footprint, path, pins, desc, mpn="", manuf="", power=False):
    s = (f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(at {x:g} {y:g} 0)\n\t\t(unit 1)\n\t\t(body_style 1)\n'
         f'\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n'
         f'\t\t(in_pos_files yes)\n\t\t(dnp no)\n\t\t(fields_autoplaced yes)\n\t\t(uuid "{uid()}")\n')
    s += prop("Reference", ref, x + 2.54, y - 1.27, hide=power, justify=None if power else "left")
    s += prop("Value", value, x + 2.54, y + 1.27, hide=False, justify=None if power else "left")
    s += prop("Footprint", footprint, x, y)
    s += prop("Datasheet", "", x, y)
    s += prop("Description", desc, x, y)
    if not power:
        s += prop("Manufacturer", manuf, x, y)
        s += prop("MPN", mpn, x, y)
    for p in pins:
        s += f'\t\t(pin "{p}"\n\t\t\t(uuid "{uid()}")\n\t\t)\n'
    s += (f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n\t\t\t\t(path "{path}"\n'
          f'\t\t\t\t\t(reference "{ref}")\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n')
    return s


def label(name, x, y, rot=0):
    j = "left bottom" if rot in (0, 90) else "right bottom"
    return (f'\t(label "{name}"\n\t\t(at {x:g} {y:g} {rot})\n\t\t(fields_autoplaced yes)\n'
            f'\t\t{font(j)}\n\t\t(uuid "{uid()}")\n\t)\n')


def hlabel(name, shape, x, y, rot=0):
    j = "left" if rot == 0 else "right"
    return (f'\t(hierarchical_label "{name}"\n\t\t(shape {shape})\n\t\t(at {x:g} {y:g} {rot})\n'
            f'\t\t{font(j)}\n\t\t(uuid "{uid()}")\n\t)\n')


def insert_before_sheet_instances(text, block):
    """New items go right before the trailing (sheet_instances ...) / (embedded_fonts ...)."""
    m = re.search(r"\n\t\(sheet_instances|\n\t\(embedded_fonts", text)
    i = m.start() + 1 if m else text.rstrip().rfind(")")
    return text[:i] + block + text[i:]


def embed_pwr_flag(text):
    """Copy power:PWR_FLAG from the KiCad power library into the sheet's lib_symbols."""
    if '(symbol "power:PWR_FLAG"' in text:
        return text
    lib = open(sys.argv[1] if len(sys.argv) > 1 else "power.kicad_sym", encoding="utf-8").read()
    a = lib.index('\t(symbol "PWR_FLAG"')
    b = lib.index("\n\t)\n", a) + 4
    flag = lib[a:b].replace('(symbol "PWR_FLAG"', '(symbol "power:PWR_FLAG"', 1)
    flag = "\n".join("\t" + l if l else l for l in flag.split("\n"))
    i = text.index("\n\t)\n", text.index("(lib_symbols")) + 1
    return text[:i] + flag.rstrip("\t") + text[i:]


def blocks(text):
    """Yield (start, end) of every top-level (symbol ...) instance block."""
    for m in re.finditer(r"\n\t\(symbol\n", text):
        end = text.index("\n\t)\n", m.start()) + 4
        yield m.start() + 1, end


def set_prop(block, name, value, after="Datasheet"):
    pat = re.compile(r'(\t\t\(property "' + re.escape(name) + r'" )"[^"]*"')
    if pat.search(block):
        return pat.sub(lambda m: m.group(1) + '"' + value + '"', block, count=1)
    at = re.search(r'\(at ([\d.\-]+) ([\d.\-]+)', block)
    x, y = float(at.group(1)), float(at.group(2))
    i = block.index('\t\t(property "' + after + '"')
    j = block.index("\n\t\t)\n", i) + 5
    return block[:j] + prop(name, value, x, y) + block[j:]


def drop_prop(block, name):
    return re.sub(r'\t\t\(property "' + re.escape(name) + r'" "[^"]*"\n.*?\n\t\t\)\n', "", block,
                  count=1, flags=re.S)


def update_fields(path):
    text = open(path, encoding="utf-8").read()
    out, last, seen = [], 0, set()
    for a, b in blocks(text):
        blk = text[a:b]
        ref = re.search(r'\(property "Reference" "([^"]+)"', blk).group(1)
        if ref in PARTS:
            value, fp, manuf, mpn = PARTS[ref]
            blk = set_prop(blk, "Value", value)
            blk = set_prop(blk, "Footprint", fp)
            blk = drop_prop(blk, "Link")
            blk = set_prop(blk, "MPN", mpn, after="Description")
            blk = set_prop(blk, "Manufacturer", manuf, after="Description")
            seen.add(ref)
        out.append(text[last:a] + blk)
        last = b
    out.append(text[last:])
    open(path, "w", encoding="utf-8").write("".join(out))
    return seen


def main():
    tile = open("tile.kicad_sch", encoding="utf-8").read()
    if '"R201"' in tile:
        sys.exit("already applied (R201 present)")

    # --- 1. series resistors in the tile sheet -------------------------------------------
    new = ""
    x0, y0, dx = 40.64, 271.78, 30.48          # free strip at the bottom of the A3 sheet
    new += ('\t(text "Rev B: series source termination (33 ohm) on every driver leaving the tile.\\n'
            'SI analysis: hardware/si/, docs/architecture/electrical.md"\n'
            f'\t\t(exclude_from_sim no)\n\t\t(at {x0 - 2.54:g} {y0 - 12.7:g} 0)\n\t\t{font("left bottom")}\n'
            f'\t\t(uuid "{uid()}")\n\t)\n')
    for i, (hname, drv, ref) in enumerate(SERIES):
        m = re.search(r'\t\(hierarchical_label "' + re.escape(hname) + r'"\n\t\t\(shape (\w+)\)\n'
                      r'\t\t\(at ([\d.\-]+) ([\d.\-]+) (\d+)\)\n.*?\n\t\)\n', tile, re.S)
        if not m:
            sys.exit(f"hierarchical label {hname} not found")
        shape, lx, ly, lrot = m.group(1), float(m.group(2)), float(m.group(3)), int(m.group(4))
        # driver side keeps the exact anchor point -> connectivity of that wire is unchanged
        tile = tile[:m.start()] + label(drv, lx, ly, lrot) + tile[m.end():]
        x = x0 + i * dx
        new += symbol("Device:R", x, y0, ref, RS_VALUE, R0603, TILE_PATH, ["1", "2"],
                      "Resistor", RS_MPN, "Yageo")
        new += label(drv, x, y0 - 3.81, 90)                       # pin 1 (top)
        new += hlabel(hname, shape, x, y0 + 3.81, 270)            # pin 2 (bottom)
    tile = insert_before_sheet_instances(tile, new)
    open("tile.kicad_sch", "w", encoding="utf-8").write(tile)

    # --- 2. decoupling + PWR_FLAG in the power sheet ------------------------------------
    power = open("power.kicad_sch", encoding="utf-8").read()
    power = embed_pwr_flag(power)
    pwr = [int(n) for n in re.findall(r'"#PWR0*(\d+)"', open("tile.kicad_sch").read() + power
                                      + "".join(open(f).read() for f in ("counter.kicad_sch", "keyboard.kicad_sch", "isomorphic_tile.kicad_sch")))]
    nxt = max(pwr) + 1
    new = ('\t(text "Rev B: one 100 nF (0603) per logic IC, placed next to its VCC pin on the PCB:\\n'
           'C201 U101, C202 U102, C203 U103, C204 U104, C205 U105, C206 U106, C207 U107, C208 U108, C209 U109"\n'
           f'\t\t(exclude_from_sim no)\n\t\t(at 20.32 162.56 0)\n\t\t{font("left bottom")}\n\t\t(uuid "{uid()}")\n\t)\n')
    for k in range(9):
        x, y = 25.4 + k * 17.78, 177.8
        ref = f"C{201 + k}"
        new += symbol("Device:C", x, y, ref, "100n", C0603, POWER_PATH, ["1", "2"],
                      "Unpolarized capacitor", "CL10B104KB8NNNC", "Samsung")
        new += symbol("power:VCC", x, y - 3.81, f"#PWR0{nxt}", "VCC", "", POWER_PATH, ["1"],
                      'Power symbol creates a global label with name \\"VCC\\"', power=True); nxt += 1
        new += symbol("power:GND", x, y + 3.81, f"#PWR0{nxt}", "GND", "", POWER_PATH, ["1"],
                      'Power symbol creates a global label with name \\"GND\\" , ground', power=True); nxt += 1
    # PWR_FLAGs: VCC and GND are supplied through the edge connectors
    for k, net in enumerate(("VCC", "GND")):
        x, y = 190.5, 172.72 + k * 15.24
        new += symbol(f"power:{net}", x, y, f"#PWR0{nxt}", net, "", POWER_PATH, ["1"],
                      f'Power symbol creates a global label with name \\"{net}\\"', power=True); nxt += 1
        new += symbol("power:PWR_FLAG", x, y, f"#FLG0{201 + k}", "PWR_FLAG", "", POWER_PATH, ["1"],
                      "Special symbol for telling ERC where power comes from", power=True)
    power = insert_before_sheet_instances(power, new)
    open("power.kicad_sch", "w", encoding="utf-8").write(power)

    # --- 2b. PWR_FLAG on the key-board rails VCC_T / GND_T (root sheet power symbols) -----
    root = embed_pwr_flag(open("isomorphic_tile.kicad_sch", encoding="utf-8").read())
    new = ""
    for k, net in enumerate(("VCC_T", "GND_T")):
        m = re.search(r'\(lib_id "power:(?:VCC|GND)"\)\n\t\t\(at ([\d.\-]+) ([\d.\-]+) \d+\)'
                      r'(?:(?!\n\t\)\n).)*?\(property "Value" "' + net + '"', root, re.S)
        if not m:
            sys.exit(f"power symbol {net} not found in the root sheet")
        new += symbol("power:PWR_FLAG", float(m.group(1)), float(m.group(2)), f"#FLG0{203 + k}",
                      "PWR_FLAG", "", f"/{ROOT_UUID}", ["1"],
                      "Special symbol for telling ERC where power comes from", power=True)
    root = insert_before_sheet_instances(root, new)
    open("isomorphic_tile.kicad_sch", "w", encoding="utf-8").write(root)

    # --- 3. values / footprints / MPN on every sheet ------------------------------------
    seen = set()
    for f in ("tile.kicad_sch", "power.kicad_sch", "counter.kicad_sch", "keyboard.kicad_sch",
              "isomorphic_tile.kicad_sch"):
        seen |= update_fields(f)
    missing = sorted(set(PARTS) - seen)
    print("updated", len(seen), "symbols; missing:", missing or "none")


if __name__ == "__main__":
    main()
