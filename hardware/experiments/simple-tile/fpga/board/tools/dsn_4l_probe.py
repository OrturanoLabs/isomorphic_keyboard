#!/usr/bin/env python3
"""dsn_4l_probe.py -- FPGA-02 preparation probe input builder: derive a

hypothetical 4-layer variant of the classed tile DSN for one autorouter
measurement (arm 'four_l_planes' in route_arms.json).

Surgery on out/route/tile_gw1nz_classes.dsn (text-level, mirroring the
in-tree discrete 4L fixture tile_variant_a_4l.dsn, which freerouting
already ran successfully):
  * structure: insert In1.Cu (power, index 1) and In2.Cu (power,
    index 2); B.Cu index bumps 1 -> 3
  * two full-board planes: GND on In1.Cu, VCC1V2 on In2.Cu, polygon =
    the pcb boundary path verbatim (same trick as the discrete fixture)
  * via padstack renamed Via[0-1]_600:300_um -> Via[0-3]_600:300_um and
    extended with inner-layer circle shapes (exact discrete text)
Everything else (network, classes, placement, rules) is untouched.

Hypothesis measured by running freerouting on the output: the router
self-fans power SMD pads with vias into the inner planes (LEDGER-proven
4L attach shape) and the signal congestion seen on 2L eases; GND/VCC1V2
pins stop consuming F.Cu/B.Cu tracks.

Writes out/route/tile_gw1nz_4l.dsn + out/route/dsn_4l_probe.json.
Exits nonzero on any inverse-check failure. No copper, no pcb access.
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
SRC = os.path.join(BOARD, "out", "route", "tile_gw1nz_classes.dsn")
OUT = os.path.join(BOARD, "out", "route", "tile_gw1nz_4l.dsn")
REPORT = os.path.join(BOARD, "out", "route", "dsn_4l_probe.json")

LAYER_F = """    (layer F.Cu
      (type signal)
      (property
        (index 0)
      )
    )
"""
LAYER_B_2L = """    (layer B.Cu
      (type signal)
      (property
        (index 1)
      )
    )
"""
LAYER_B_4L = """    (layer B.Cu
      (type signal)
      (property
        (index 3)
      )
    )
"""
LAYER_IN1 = """    (layer In1.Cu
      (type power)
      (property
        (index 1)
      )
    )
"""
LAYER_IN2 = """    (layer In2.Cu
      (type power)
      (property
        (index 2)
      )
    )
"""
VIA_2L = '(via "Via[0-1]_600:300_um")'
VIA_4L = '(via "Via[0-3]_600:300_um")'
PAD_2L = """    (padstack "Via[0-1]_600:300_um"
      (shape (circle F.Cu 600))
      (shape (circle B.Cu 600))
      (attach off)
    )"""
PAD_4L = """    (padstack "Via[0-3]_600:300_um"
      (shape (circle F.Cu 600))
      (shape (circle In1.Cu 600))
      (shape (circle In2.Cu 600))
      (shape (circle B.Cu 600))
      (attach off)
    )"""


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def plane(net, layer, coords):
    return f"    (plane {net} (polygon {layer} 0 {coords}))\n"


def main():
    text = open(SRC).read()
    base_hash = sha256(SRC)[:12]
    edits = []

    def swap(old, new, what, count=1):
        nonlocal text
        n = text.count(old)
        if n != count:
            sys.exit(f"DSN_4L FAIL: {what}: found {n}, expected {count}")
        text = text.replace(old, new)
        edits.append(what)

    # 1. layer stack
    swap(LAYER_F + LAYER_B_2L,
         LAYER_F + LAYER_IN1 + LAYER_IN2 + LAYER_B_4L, "layer_stack")
    # 2. plane polygons appended right after the boundary block
    bm = re.search(r"(    \(boundary\n(?:.*\n)*?    \)\n)", text)
    if not bm:
        sys.exit("DSN_4L FAIL: boundary block not found")
    body = bm.group(1)
    cm = re.search(r"\(path pcb 0((?:\s+[-\d.]+\s+[-\d.]+)+)\)", body)
    if not cm:
        sys.exit("DSN_4L FAIL: boundary path coords not found")
    coords = cm.group(1).rstrip()
    planes = (plane("GND", "In1.Cu", coords)
              + plane("VCC1V2", "In2.Cu", coords))
    swap(body, body + planes, "planes")
    # 3. via references + padstack definition
    swap(VIA_2L, VIA_4L, "via_struct_ref")
    swap(PAD_2L, PAD_4L, "via_padstack")
    # 6 class blocks each carry (use_via "Via[0-1]_600:300_um")
    swap("Via[0-1]_600:300_um", "Via[0-3]_600:300_um", "via_use_refs",
         count=6)
    if "Via[0-1]" in text:
        sys.exit("DSN_4L FAIL: leftover 2L via references")

    open(OUT, "w").write(text)

    # inverse check: surgical undo must reproduce the source byte-exactly
    back = text.replace(LAYER_F + LAYER_IN1 + LAYER_IN2 + LAYER_B_4L,
                        LAYER_F + LAYER_B_2L)
    back = back.replace(planes, "")
    back = back.replace(VIA_4L, VIA_2L).replace(PAD_4L, PAD_2L)
    back = back.replace("Via[0-3]_600:300_um", "Via[0-1]_600:300_um")
    orig = open(SRC).read()
    inv_ok = back == orig
    nets = len(re.findall(r"\(net\s+\S+\s+\(pins", text))
    nets0 = len(re.findall(r"\(net\s+\S+\s+\(pins", orig))
    cls = len(re.findall(r"\(class ", text))
    rep = {
        "tool": "dsn_4l_probe.py",
        "src": "out/route/tile_gw1nz_classes.dsn",
        "src_sha256_12": base_hash,
        "out": "out/route/tile_gw1nz_4l.dsn",
        "out_sha256_12": sha256(OUT)[:12],
        "edits": edits,
        "planes": {"In1.Cu": "GND", "In2.Cu": "VCC1V2"},
        "inverse_identity": inv_ok,
        "nets_equal": nets == nets0,
        "nets": nets,
        "classes_block_count": cls,
        "fixture_pattern": "discrete-spld/layout/tile_variant_a_4l.dsn",
    }
    json.dump(rep, open(REPORT, "w"), indent=1)
    if not (inv_ok and nets == nets0 == 45 and cls == 6
            and len(edits) == 5):
        print(f"DSN_4L FAIL: {rep}")
        sys.exit(1)
    print(f"DSN_4L OK: layers=4 planes[GND=In1 VCC1V2=In2] via[0-3] "
          f"nets={nets} classes={cls} inverse=True -> {OUT}")


if __name__ == "__main__":
    main()
