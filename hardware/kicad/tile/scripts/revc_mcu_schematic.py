#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Rev C microcontroller tile: write the KiCad schematic from revc_mcu_circuit.py.

    flatpak run --filesystem="$PWD" --command=python3 org.kicad.KiCad \
        hardware/kicad/tile/scripts/revc_mcu_schematic.py production/revc_mcu/revc_mcu.kicad_sch

Symbols come from KiCad's stock libraries (inside the KiCad flatpak) and are embedded in the
file, as KiCad itself does. Every pin gets a short wire and a global label (signals), a
power symbol (VCC, GND) or a no-connect flag, so the drawing stays readable and ERC can
check it. The layout is by function: keys, microcontroller, edge contacts, LED chain,
decoupling, programming.
"""
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import revc_mcu_circuit as C  # noqa: E402

SYMLIB = "/app/extensions/Library/symbols"
PROJECT = "revc_mcu"
ROOT_UUID = str(uuid.uuid5(uuid.NAMESPACE_URL, "isomorphic_keyboard/revc_mcu/root"))
G = 2.54


def uid(*key):
    """stable UUIDs: the same circuit gives the same file (clean diffs, stable PCB links)"""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "isomorphic_keyboard/revc_mcu/" + "/".join(map(str, key))))


def S(s):
    return ("s", s)


def num(v):
    return f"{round(v, 4):g}"


def font(justify=None, hide=False):
    e = ["effects", ["font", ["size", "1.27", "1.27"]]]
    if justify:
        e.append(["justify"] + justify.split())
    if hide:
        e.append(["hide", "yes"])
    return e


# --- library symbols -----------------------------------------------------------------------
_lib_cache = {}


def lib_block(lib, name):
    """text of one top-level symbol of a .kicad_sym file (line scan, then parse only it)"""
    if lib not in _lib_cache:
        _lib_cache[lib] = open(os.path.join(SYMLIB, lib + ".kicad_sym")).read().split("\n")
    lines = _lib_cache[lib]
    head = f'\t(symbol "{name}"'
    for i, ln in enumerate(lines):
        if ln == head:
            j = i + 1
            while not (lines[j].startswith("\t(symbol ") or lines[j] == ")"):
                j += 1
            return C.sx_parse("\n".join(lines[i:j]))
    raise KeyError(f"{lib}:{name}")


def rename(e, old, new):
    """rename the symbol and its unit sub-symbols (old_1_1 -> new_1_1)"""
    e[1] = S(new)
    for x in C.sx_find(e, "symbol"):
        x[1] = S(new + C.sx_val(x[1])[len(old):])
    return e


def flat_symbol(lib_id):
    """lib symbol with 'extends' resolved (parent graphics + pins, child properties)"""
    lib, name = lib_id.split(":")
    e = lib_block(lib, name)
    ext = C.sx_find(e, "extends")
    if ext:
        parent = flat_symbol(f"{lib}:{C.sx_val(ext[0][1])}")
        pname = C.sx_val(parent[1]).split(":")[-1]
        parent = rename(parent, pname, name)
        child_props = {C.sx_val(p[1]): p for p in C.sx_find(e, "property")}
        out = []
        for x in parent:
            if isinstance(x, list) and x and x[0] == "property" and C.sx_val(x[1]) in child_props:
                out.append(child_props.pop(C.sx_val(x[1])))
            else:
                out.append(x)
        # remaining child-only properties go before the unit sub-symbols
        k = next(i for i, x in enumerate(out) if isinstance(x, list) and x and x[0] == "symbol")
        e = out[:k] + list(child_props.values()) + out[k:]
    e = [x for x in e if not (isinstance(x, list) and x and x[0] == "extends")]
    return e


def lib_entry(lib_id):
    e = flat_symbol(lib_id)
    e[1] = S(lib_id)
    return e


def pins_of(sym):
    """{number: (x, y, angle)} in library coordinates (y up), units 0/1 only"""
    out = {}
    name = C.sx_val(sym[1]).split(":")[-1]
    for u in C.sx_find(sym, "symbol"):
        unit = C.sx_val(u[1])[len(name) + 1:].split("_")[0]
        if unit not in ("0", "1"):
            continue
        for p in C.sx_find(u, "pin"):
            at = C.sx_find(p, "at")[0]
            n = C.sx_val(C.sx_find(p, "number")[0][1])
            out[n] = (float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0)
    return out


def prop_of(sym, name):
    for p in C.sx_find(sym, "property"):
        if C.sx_val(p[1]) == name:
            at = C.sx_find(p, "at")[0]
            return float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0
    return 0.0, 0.0, 0.0


# --- schematic items -------------------------------------------------------------------------
items, lib_syms, pwr = [], {}, {"n": 0}


def symbol(lib_id, ref, value, x, y, footprint="", fields=None, in_bom=True, on_board=True, rot=0,
           key=None):
    if lib_id not in lib_syms:
        lib_syms[lib_id] = lib_entry(lib_id)
    sym = lib_syms[lib_id]
    key = key or ref
    e = ["symbol", ["lib_id", S(lib_id)], ["at", num(x), num(y), str(rot)], ["unit", "1"],
         ["body_style", "1"], ["exclude_from_sim", "no"], ["in_bom", "yes" if in_bom else "no"],
         ["on_board", "yes" if on_board else "no"], ["in_pos_files", "yes" if in_bom else "no"],
         ["dnp", "no"], ["uuid", S(uid("sym", key))]]
    lib_prop = {C.sx_val(p[1]): C.sx_val(p[2]) for p in C.sx_find(sym, "property")}
    props = [("Reference", ref, False), ("Value", value, False), ("Footprint", footprint, True),
             ("Datasheet", lib_prop.get("Datasheet", ""), True),
             ("Description", lib_prop.get("Description", ""), True)]
    props += [(k, v, True) for k, v in (fields or {}).items()]
    for name, val, hide in props:
        px, py, _ = prop_of(sym, name) if name in ("Reference", "Value") else (0, 0, 0)
        if ref.startswith("#"):
            hide = hide or name == "Reference"
        e.append(["property", S(name), S(val), ["at", num(x + px), num(y - py), "0"],
                  ["show_name", "no"], ["do_not_autoplace", "no"], font(hide=hide)])
    for n in pins_of(sym):
        e.append(["pin", S(n), ["uuid", S(uid("pin", key, n))]])
    e.append(["instances", ["project", S(PROJECT), ["path", S("/" + ROOT_UUID),
                                                     ["reference", S(ref)], ["unit", "1"]]]])
    items.append(e)
    return sym


def wire(x1, y1, x2, y2, key):
    items.append(["wire", ["pts", ["xy", num(x1), num(y1)], ["xy", num(x2), num(y2)]],
                  ["stroke", ["width", "0"], ["type", "default"]], ["uuid", S(uid("wire", key))]])


LABEL_JUSTIFY = {0: "left", 90: "left", 180: "right", 270: "right"}


def glabel(net, x, y, ang, key):
    items.append(["global_label", S(net), ["shape", "passive"], ["at", num(x), num(y), str(ang)],
                  ["fields_autoplaced", "yes"], font(LABEL_JUSTIFY[ang]), ["uuid", S(uid("gl", key))],
                  ["property", S("Intersheetrefs"), S("${INTERSHEET_REFS}"), ["at", num(x), num(y), "0"],
                   font(LABEL_JUSTIFY[ang], hide=True)]])


def power(net, x, y, direction, key):
    """power symbol at (x, y); direction = where the stub points (screen: 'up', 'down', ...)"""
    pwr["n"] += 1
    lib_id = "power:GND" if net == "GND" else "power:VCC"
    if net == "GND":
        rot = {"down": 0, "up": 180, "right": 90, "left": 270}[direction]
    else:
        rot = {"up": 0, "down": 180, "left": 90, "right": 270}[direction]
    symbol(lib_id, f"#PWR{pwr['n']:02d}", net, x, y, in_bom=False, on_board=False, rot=rot, key=("pwr", key))


def no_connect(x, y, key):
    items.append(["no_connect", ["at", num(x), num(y)], ["uuid", S(uid("nc", key))]])


def text(s, x, y, size=2.0, key=None):
    items.append(["text", S(s), ["exclude_from_sim", "no"], ["at", num(x), num(y), "0"],
                  ["effects", ["font", ["size", num(size), num(size)], ["bold", "yes"]], ["justify", "left", "bottom"]],
                  ["uuid", S(uid("text", key or s))]])


def place(part, x, y, stub=2 * G, rot=0):
    """symbol + one stub per pin, ending in a label / power symbol / no-connect;
    rot: 0 or 90 (counter-clockwise on screen)"""
    sym = symbol(part["lib_id"], part["ref"], part["value"], x, y, part["footprint"], part["fields"],
                 part["in_bom"], rot=rot)
    pins = pins_of(sym)
    seen = {}
    for n, (px, py, ang) in sorted(pins.items(), key=lambda t: int(t[0]) if t[0].isdigit() else 0):
        net = part["pins"].get(int(n)) if n.isdigit() else None
        if n.isdigit() and int(n) not in part["pins"]:
            raise SystemExit(f"{part['ref']} pin {n} not in the circuit definition")
        sx, sy = px, -py                          # library (y up) -> screen (y down)
        if rot == 90:
            sx, sy, ang = sy, -sx, ang + 90
        ex, ey = x + sx, y + sy
        if (ex, ey) in seen:                      # stacked pins (same position): one connection
            if seen[(ex, ey)] != net:
                raise SystemExit(f"{part['ref']} stacked pins with different nets")
            continue
        seen[(ex, ey)] = net
        dx, dy = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}[int(ang) % 360]
        if net is None:
            no_connect(ex, ey, (part["ref"], n))
            continue
        tx, ty = ex + dx * stub, ey + dy * stub
        wire(ex, ey, tx, ty, (part["ref"], n))
        direction = {(-1, 0): "left", (1, 0): "right", (0, 1): "down", (0, -1): "up"}[(dx, dy)]
        if net in ("VCC", "GND"):
            power(net, tx, ty, direction, (part["ref"], n))
        else:
            ang_l = {"left": 180, "right": 0, "down": 270, "up": 90}[direction]
            glabel(net, tx, ty, ang_l, (part["ref"], n))


def main(out_path):
    parts = {p["ref"]: p for p in C.parts()}
    g = lambda v: round(v / G) * G   # noqa: E731  (keep everything on the 2.54 mm grid)
    text("Keys: switch to GND, MCU internal pull-ups", g(20), g(30))
    for n in range(12):
        col, row = divmod(n, 6)
        place(parts[f"SW{n + 1}"], g(45 + col * 45), g(45 + row * 20))
    text("Microcontroller (5 V, UPDI programming on TP1)", g(140), g(30))
    place(parts["U1"], g(175), g(95), stub=3 * G)
    place(parts["TP1"], g(175), g(150))
    text("Edge data lines: 100 ohm series, 3 contacts per edge (VCC, DATA, GND)", g(250), g(30))
    for i, e in enumerate("BRTL"):
        place(parts[C.EDGE_RES[e]], g(275), g(50 + i * 25), rot=90)
        place(parts[C.EDGE_CONTACT[e][0]], g(330), g(50 + i * 25))
    text("Per-key LEDs, chained DIN -> DOUT from the MCU: " + " ".join(f"D{n + 1}" for n in C.CHAIN),
         g(20), g(163))
    for k, n in enumerate(C.CHAIN):
        row, col = divmod(k, 6)
        place(parts[f"D{n + 1}"], g(40 + col * 62), g(185 + row * 40))
    text("Decoupling: C1, C2 at U1; C3..C6 next to D1, D4, D9, D12", g(20), g(250))
    for i, (ref, _, _) in enumerate(C.DECOUPLING):
        place(parts[ref], g(35 + i * 25), g(266))
    # PWR_FLAG on the supply nets (they come in through the edge contacts)
    for i, net in enumerate(("VCC", "GND")):
        x, y = g(230 + i * 25), g(262)
        symbol("power:PWR_FLAG", f"#FLG0{i + 1}", "PWR_FLAG", x, y, in_bom=False, on_board=False,
               key=("flag", net))
        wire(x, y, x, y + 2 * G, ("flag", net))
        power(net, x, y + 2 * G, "down", ("flag", net))
    text("Isomorphic keyboard - rev C microcontroller tile (generated by revc_mcu_schematic.py)",
         g(20), g(285), 2.5)

    root = ["kicad_sch", ["version", "20260306"], ["generator", S("eeschema")],
            ["generator_version", S("10.0")], ["uuid", S(ROOT_UUID)], ["paper", S("A3")],
            ["title_block", ["title", S("Rev C microcontroller tile")], ["rev", S("C")],
             ["company", S("OrturanoLabs")],
             ["comment", "1", S("Generated from hardware/kicad/tile/scripts/revc_mcu_circuit.py")]],
            ["lib_symbols"] + list(lib_syms.values())]
    root += items
    root += [["sheet_instances", ["path", S("/"), ["page", S("1")]]], ["embedded_fonts", "no"]]
    with open(out_path, "w") as f:
        f.write(C.sx_str(root) + "\n")
    print("schematic:", out_path, "|", len(parts), "parts")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "revc_mcu.kicad_sch")
