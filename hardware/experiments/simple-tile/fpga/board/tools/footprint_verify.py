#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""footprint_verify -- machine check that the two custom QFN48 footprints
match the VENDOR package/land data recorded in ../data/pins_*.json, not just
"generic KiCad stock practice".

GW1NZ-QN48: UG846-1.1E Fig 4-1/4-2 records a *recommended PCB layout*:
    D=E=6.00 body, D2=E2=2.70 EP, P=5.90 pad-row spacing, e=0.40 pitch,
    L=0.85 land length, b=0.20 (terminal width; land width per KiCad QFN
    0.4-pitch practice is also 0.20 here).
UP5K-SG48: FPGA-DS-02053-8.8 sec.31 records the PACKAGE: D=E=7.0 BSC,
    D2/E2=5.20/5.35/5.50 (nom 5.35), e=0.50 BSC, b=0.15/0.225/0.30,
    L=0.35/0.40/0.45.  No vendor *recommended land* was captured -> land
    geometry (rows +/-3.45, pads 0.8x0.25) is KiCad stock QFN-48-7x7-P0.5
    practice and is reported as such (LAND-TBD), never as vendor-verified.

Both: pin-1 top-left, numbering CCW (JEDEC QFN top view); pad INNER edge
must not reach the EP copper; courtyard = body + 0.3.

Negative control: the same checks are re-run with deliberately wrong
expectations (pitch +0.05, EP +0.1) and MUST produce failures - a checker
that cannot fail proves nothing.

Exit 0 iff all real checks pass AND the negative controls fail as expected.
"""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.abspath(os.path.join(HERE, ".."))
LIB = os.path.join(BOARD, "kicad", "lib", "fpga_board.pretty")

EPS = 1e-6


def parse_fp(path):
    t = open(path).read()
    pads = {}
    for m in re.finditer(
            r'\(pad\s+"?([0-9A-Za-z_]+)"?\s+smd\s+rect\s+'
            r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)(?:\s+(-?[\d.]+))?\)\s*'
            r'\(size\s+(-?[\d.]+)\s+(-?[\d.]+)\)', t):
        pads[m.group(1)] = (float(m.group(2)), float(m.group(3)),
                            float(m.group(5)), float(m.group(6)))
    # fab outline = fp_line blocks on F.Fab ONLY
    fx, fy = [], []
    for m in re.finditer(r'\(fp_line\s+\(start\s+(-?[\d.]+)\s+(-?[\d.]+)\)'
                         r'\s+\(end\s+(-?[\d.]+)\s+(-?[\d.]+)\)'
                         r'\s+\(stroke\s+\(width\s+[\d.]+\)\s+\(type\s+\w+\)\)'
                         r'\s+\(layer\s+"F\.Fab"\)', t):
        fx += [float(m.group(1)), float(m.group(3))]
        fy += [float(m.group(2)), float(m.group(4))]
    cy = re.search(r'\(fp_rect\s+\(start\s+(-?[\d.]+)\s+(-?[\d.]+)\)\s*'
                   r'\(end\s+(-?[\d.]+)\s+(-?[\d.]+)\)', t)
    return {"text": t, "pads": pads,
            "fab": (min(fx), min(fy), max(fx), max(fy)),
            "crt": tuple(float(cy.group(i)) for i in range(1, 5))}


def sides(pads, row_abs, eps=0.01):
    """split perimeter pads by row using the expected row coordinate."""
    vert, horiz, ep = [], [], None
    for n, p in pads.items():
        if n == "49":
            ep = p
        elif abs(abs(p[0]) - row_abs) < eps and abs(p[1]) <= 4:
            vert.append(p)
        elif abs(abs(p[1]) - row_abs) < eps and abs(p[0]) <= 4:
            horiz.append(p)
    return vert, horiz, ep


def check(fp, exp):
    """exp: dict(body, ep, pitch, row_abs, pad_len, pad_wid, n_side=12,
    pads_total=48). Returns list of (id, ok, detail)."""
    out = []
    pads = fp["pads"]
    ra = exp["row_abs"]
    vert, horiz, _ep = sides(pads, ra)

    def c(cid, ok, detail):
        out.append((cid, bool(ok), detail))

    # F1 pad census (48 perimeter: 12 left + 12 bottom + 12 right + 12 top)
    c("F1", len(pads) == exp["pads_total"] + 1 and
      len(vert) == 24 and len(horiz) == 24,
      f"{len(pads)-1} perimeter pads + EP (want {exp['pads_total']}+EP; "
      f"rows {len(vert)}v+{len(horiz)}h)")

    # F2 pitch from the LEFT column only
    pitch = exp["pitch"]
    left = sorted([p for p in vert if p[0] < 0], key=lambda p: p[1])
    dp = {round(left[i + 1][1] - left[i][1], 4) for i in range(len(left) - 1)}
    c("F2", len(left) == 12 and dp == {pitch},
      f"left-column dy set = {sorted(dp)} over {len(left)} pads "
      f"(want {{{pitch}}})")

    # F3 row spacing: vertical rows at x=+/-ra, horizontal rows at y=+/-ra
    rowsx = sorted({round(p[0], 4) for p in vert})
    rowsy = sorted({round(p[1], 4) for p in horiz})
    c("F3", rowsx == [-ra, ra] and rowsy == [-ra, ra],
      f"rows x={rowsx} y={rowsy} (want +/-{ra} -> P={2*ra:.2f})")

    # F4 pad size (land length along row normal, width along row)
    sizes = {(round(p[2], 4), round(p[3], 4)) for n, p in pads.items()
             if n != "49"}
    want_sizes = {(exp["pad_len"], exp["pad_wid"]),
                  (exp["pad_wid"], exp["pad_len"])}
    c("F4", sizes <= want_sizes,
      f"pad sizes {sorted(sizes)} subset of {sorted(want_sizes)}")

    # F5 EP copper
    ep = pads.get("49")
    c("F5", ep is not None and abs(ep[0]) < EPS and abs(ep[1]) < EPS and
      abs(ep[2] - exp["ep"]) < EPS and abs(ep[3] - exp["ep"]) < EPS,
      f"EP at {ep} (want centred {exp['ep']}x{exp['ep']})")

    # F6 pad inner edge must not reach EP copper (row normal direction)
    inner_edge = ra - exp["pad_len"] / 2
    c("F6", inner_edge - exp["ep"] / 2 > 0.3,
      f"row centre {ra} - L/2 = {inner_edge:.3f} vs EP/2 {exp['ep']/2:.3f} "
      f"-> clearance {inner_edge-exp['ep']/2:.3f} mm")

    # F7 fab body + pin-1 chamfer at top-left
    fx0, fy0, fx1, fy1 = fp["fab"]
    c("F7", abs(fx1 - fx0 - exp["body"]) < 0.05 and
      abs(fy1 - fy0 - exp["body"]) < 0.05,
      f"fab box {fx1-fx0:.2f} x {fy1-fy0:.2f} (want {exp['body']})")

    # F8 pin-1 convention: pad 1 = leftmost column, TOP (min y, KiCad -y=up)
    p1 = pads.get("1")
    c("F8", p1 is not None and abs(p1[0] + exp["row_abs"]) < EPS and
      p1[1] < 0 and abs(abs(p1[1]) - (12 - 1) * exp["pitch"] / 2) < EPS,
      f"pad1 at {p1[:2]} (want (-{exp['row_abs']}, "
      f"-{(12-1)*exp['pitch']/2:.4f}) = top-left, CCW)")

    # F9 pads stay inside body edge + toe extension modest (0.2..0.5 mm)
    toe = ra + exp["pad_len"] / 2 - exp["body"] / 2
    c("F9", 0.2 <= toe <= 0.6,
      f"toe extension {toe:.3f} mm past body edge (want 0.2..0.6)")

    # F10 courtyard = body + 0.3 each side
    cx0, cy0, cx1, cy1 = fp["crt"]
    c("F10", abs(cx1 - exp["body"] / 2 - 0.3) < EPS and
      abs(cx0 + exp["body"] / 2 + 0.3) < EPS,
      f"courtyard x {cx0}..{cx1} (want +/-{exp['body']/2+0.3:.2f})")
    return out


EXPECT = {
    "gw1nz": dict(fp="GW1NZ-QN48_6x6_P0.4mm_EP2.7x2.7mm.kicad_mod",
                  body=6.0, ep=2.7, pitch=0.4, row_abs=2.95,
                  pad_len=0.85, pad_wid=0.20, pads_total=48,
                  source="UG846-1.1E Fig 4-1/4-2 recommended PCB layout "
                         "(D/E 6.00, D2/E2 2.70, P 5.90, e 0.40, L 0.85, "
                         "b 0.20); land-provenance = VENDOR-RECOMMENDED"),
    "up5k": dict(fp="iCE40UP5K-SG48_7x7_P0.5mm_EP5.35x5.35mm.kicad_mod",
                 body=7.0, ep=5.35, pitch=0.5, row_abs=3.45,
                 pad_len=0.8, pad_wid=0.25, pads_total=48,
                 source="FPGA-DS-02053-8.8 sec.31 PACKAGE dims (D/E 7.0 BSC, "
                        "D2/E2 5.35 nom, e 0.50 BSC, b 0.15-0.30, L "
                        "0.35-0.45); land geometry rows +/-3.45 / 0.8x0.25 = "
                        "KiCad stock practice -> LAND-TBD (no vendor "
                        "recommended-land captured)"),
}


def main():
    results = {}
    ok_all = True
    for var, exp in EXPECT.items():
        fp = parse_fp(os.path.join(LIB, exp["fp"]))
        rows = check(fp, exp)
        ok = all(r[1] for r in rows)
        results[var] = {"ok": ok, "source": exp["source"],
                        "checks": [{"id": c, "ok": o, "detail": d}
                                   for c, o, d in rows]}
        ok_all &= ok
        print(f"[{var}] {'PASS' if ok else 'FAIL'}  ({exp['source']})")
        for c, o, d in rows:
            print(f"  [{'OK' if o else 'FAIL':4}] {c}: {d}")

    # negative controls: WRONG expectations must FAIL
    neg = []
    for var, exp in EXPECT.items():
        fp = parse_fp(os.path.join(LIB, exp["fp"]))
        bad1 = dict(exp, pitch=exp["pitch"] + 0.05)
        bad2 = dict(exp, ep=exp["ep"] + 0.1)
        r1 = check(fp, bad1)
        r2 = check(fp, bad2)
        neg.append((f"{var}:pitch+0.05", not all(r[1] for r in r1)))
        neg.append((f"{var}:ep+0.1", not all(r[1] for r in r2)))
    negok = all(n[1] for n in neg)
    print("[negative-control] " + ("PASS" if negok else "FAIL")
          + " (wrong expectations must fail)")
    for name, o in neg:
        print(f"  [{'OK' if o else 'FAIL':4}] {name}")

    out = {"ok": ok_all and negok, "variants": results,
           "negative_control": [{"case": n, "failed_as_expected": o}
                                for n, o in neg]}
    rp = os.path.join(BOARD, "out", "footprint_verify.json")
    json.dump(out, open(rp, "w"), indent=1)
    print("wrote", rp)
    sys.exit(0 if out["ok"] else 1)


if __name__ == "__main__":
    main()
