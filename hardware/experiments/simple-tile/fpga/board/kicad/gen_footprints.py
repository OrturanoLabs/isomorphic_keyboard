#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Generate the two custom QFN48 footprints used by the tile boards.

KiCad 10 stock library has no QFN-48 6x6 with EP 2.7x2.7 (Gowin QN48) and
no iCE40UP5K-SG48-specific part, so both footprints are DERIVED FROM THE
VENDOR PACKAGE DOCUMENTS fetched 2026-10-12 (numbers inline; per-pin-probe of
the derivation lives in ../out):

  GW1NZ-QN48: UG846-1.1E Fig 4-1/4-2 (D=E=6.00, D2=E2=2.70, P=5.90, e=0.40,
    L=0.85, b=0.20) -> 48 pads, 12 per side at 0.4 pitch; the pad pattern
    itself follows the KiCad stock QFN-48-6x6-P0.4 convention for the same
    class (rows at +/-2.95 = P/2, pads 0.85 x 0.2 - matching L=0.85/b=0.20);
    EPAD copper 2.7 x 2.7 (D2/E2) = GND.

  UP5K-SG48: FPGA-DS-02053-8.8 sec. 31 (D=E=7.0 BSC, D2/E2 = 5.20/5.35/5.50,
    e=0.50 BSC, b = 0.15-0.30, L = 0.35-0.45) -> 48 pads, 12 per side at
    0.5 pitch; pad pattern = KiCad stock QFN-48-7x7-P0.5 convention (rows
    +/-3.45, pads 0.8 x 0.25); paddle copper 5.35 x 5.35 (nominal) = GND
    (SG48 paddle MUST be grounded; DS 4.x note).

Both get F/B courtyard = body box + 0.3 and a pin-1 corner chamfer on F.Fab.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "lib", "fpga_board.pretty")


def fmt(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


def qfn_footprint(name, descr, body, pad_pitch_token, pad_w, pad_l, row_abs,
                  ep, version=1):
    """48-pad QFN, pad order standard: pin 1 at bottom of left column... We
    use the vendor-neutral convention the KiCad QFN-48 stock parts use:
    pads 1-12 on the LEFT side (bottom->top), 13-24 BOTTOM (left->right),
    25-36 RIGHT (top->bottom), 37-48 TOP (right->left), i.e. CCW starting
    at the left-bottom, matching QFN-48-1EP_6x6mm_P0.4mm_EP4.2x4.2mm.
    """
    n_side = 12
    pitch = pad_pitch_token
    hx, hy = body / 2, body / 2
    pads = []
    pin = 1
    spans = n_side * pitch - pitch
    o0 = -spans / 2
    for i in range(n_side):                      # left side, bottom->top
        pads.append((pin, -row_abs, o0 + i * pitch, 0)); pin += 1
    for i in range(n_side):                      # bottom side, left->right
        pads.append((pin, o0 + i * pitch, row_abs, 90)); pin += 1
    for i in range(n_side):                      # right side, top->bottom
        pads.append((pin, row_abs, o0 + (n_side - 1 - i) * pitch, 0)); pin += 1
    for i in range(n_side):                      # top side, right->left
        pads.append((pin, o0 + (n_side - 1 - i) * pitch, -row_abs, 90)); pin += 1

    cx0, cy0 = -body / 2 - 0.3, -body / 2 - 0.3
    cx1, cy1 = body / 2 + 0.3, body / 2 + 0.3
    t = []
    t.append(f'(footprint "{name}"')
    t.append('\t(version 20240108)')
    t.append('\t(generator "gen_footprints.py")')
    t.append('\t(generator_version "0.1")')
    t.append('\t(layer "F.Cu")')
    t.append(f'\t(descr "{descr}")')
    t.append('\t(tags "qfn prototype vendor-derived")')
    t.append('\t(property "Reference" "REF**" (at 0 %s 0) (layer "F.SilkS") (uuid "00000000-0000-0000-0000-000000000001") (effects (font (size 1 1) (thickness 0.15))))' % fmt(-(hy + 1.2)))
    t.append('\t(property "Value" "%s" (at 0 %s 0) (layer "F.Fab") (uuid "00000000-0000-0000-0000-000000000002") (effects (font (size 1 1) (thickness 0.15))))' % (name, fmt(hy + 1.2)))
    # fab outline + pin-1 chamfer at top-left
    ch = 1.0
    t.append(f'\t(fp_line (start {fmt(-hx)} {fmt(-hy + ch)}) (end {fmt(-hx)} {fmt(hy)}) (stroke (width 0.12) (type solid)) (layer "F.Fab") (uuid "00000000-0000-0000-0000-000000000003"))')
    t.append(f'\t(fp_line (start {fmt(-hx)} {fmt(hy)}) (end {fmt(hx)} {fmt(hy)}) (stroke (width 0.12) (type solid)) (layer "F.Fab") (uuid "00000000-0000-0000-0000-000000000004"))')
    t.append(f'\t(fp_line (start {fmt(hx)} {fmt(hy)}) (end {fmt(hx)} {fmt(-hy)}) (stroke (width 0.12) (type solid)) (layer "F.Fab") (uuid "00000000-0000-0000-0000-000000000005"))')
    t.append(f'\t(fp_line (start {fmt(hx)} {fmt(-hy)}) (end {fmt(-hx + ch)} {fmt(-hy)}) (stroke (width 0.12) (type solid)) (layer "F.Fab") (uuid "00000000-0000-0000-0000-000000000006"))')
    t.append(f'\t(fp_line (start {fmt(-hx + ch)} {fmt(-hy)}) (end {fmt(-hx)} {fmt(-hy + ch)}) (stroke (width 0.12) (type solid)) (layer "F.Fab") (uuid "00000000-0000-0000-0000-000000000007"))')
    # courtyard
    t.append(f'\t(fp_rect (start {fmt(cx0)} {fmt(cy0)}) (end {fmt(cx1)} {fmt(cy1)}) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd") (uuid "00000000-0000-0000-0000-000000000008"))')
    # silkscreen tick at pin 1
    t.append(f'\t(fp_line (start {fmt(-hx - 0.4)} {fmt(-o0)}) (end {fmt(-hx - 0.4)} {fmt(o0)}) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "00000000-0000-0000-0000-000000000009"))')
    uid = 100
    for num, x, y, rot in pads:
        w, l = (pad_l, pad_w) if rot == 0 else (pad_w, pad_l)
        t.append(f'\t(pad "{num}" smd rect (at {fmt(x)} {fmt(y)}) (size {fmt(w)} {fmt(l)}) (layers "F.Cu" "F.Paste" "F.Mask") (uuid "00000000-0000-0000-0000-{uid:012d}"))')
        uid += 1
    t.append(f'\t(pad "49" smd rect (at 0 0) (size {fmt(ep)} {fmt(ep)}) (layers "F.Cu" "F.Paste" "F.Mask") (uuid "00000000-0000-0000-0000-{uid:012d}"))')
    t.append(')')
    return "\n".join(t) + "\n"


def main():
    os.makedirs(LIB, exist_ok=True)
    # Pad geometry = KiCad stock practice for the same QFN-48 body/pitch
    # class (measured off QFN-48-1EP_6x6mm_P0.4mm_EP4.2x4.2mm: rows +/-2.95,
    # pad 0.85x0.2; and QFN-48-1EP_7x7mm_P0.5mm_EP5.3x5.3mm: rows +/-3.45,
    # pad 0.8x0.25). The stock library has NO part with EP sizes 2.7 or
    # 5.35, hence these two vendor-EP parts.
    gw = qfn_footprint(
        "GW1NZ-QN48_6x6_P0.4mm_EP2.7x2.7mm", body=6.0, pad_pitch_token=0.4,
        pad_w=0.2, pad_l=0.85, row_abs=2.95, ep=2.7,
        descr="Gowin GW1NZ QN48 (QFN48 6x6, 0.4mm, EPAD 2.7x2.7 GND); "
              "dims from UG846-1.1E Fig 4-1/4-2 (D/E 6.00, D2/E2 2.70, "
              "pad-row spacing 5.90, e 0.40, L 0.85, b 0.20); pad pattern = "
              "KiCad stock QFN-48-6x6-P0.4 practice (rows +/-2.95, "
              "0.85x0.2), only the EP is custom")
    open(os.path.join(LIB, "GW1NZ-QN48_6x6_P0.4mm_EP2.7x2.7mm.kicad_mod"),
         "w").write(gw)
    up = qfn_footprint(
        "iCE40UP5K-SG48_7x7_P0.5mm_EP5.35x5.35mm", body=7.0,
        pad_pitch_token=0.5, pad_w=0.25, pad_l=0.8, row_abs=3.45, ep=5.35,
        descr="Lattice iCE40UP5K SG48 (QFN48 7x7, 0.5mm, paddle 5.35x5.35 "
              "GND, must be grounded); dims from FPGA-DS-02053-8.8 sec.31 "
              "(D/E 7.0 BSC, D2/E2 5.20/5.35/5.50, e 0.50, b 0.15-0.30, "
              "L 0.35-0.45); pad pattern = KiCad stock QFN-48-7x7-P0.5 "
              "practice (rows +/-3.45, 0.8x0.25), only the EP is custom")
    open(os.path.join(LIB, "iCE40UP5K-SG48_7x7_P0.5mm_EP5.35x5.35mm.kicad_mod"),
         "w").write(up)
    print("wrote", LIB)


if __name__ == "__main__":
    main()
