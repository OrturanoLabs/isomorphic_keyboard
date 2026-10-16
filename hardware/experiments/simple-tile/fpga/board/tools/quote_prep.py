#!/usr/bin/env python3
"""quote_prep.py -- distributor-agnostic quote-package preparation (FPGA-01/5).

Emits, from the CURRENT board artifacts (no network, no login, no heavy run):

  docs/quote/bom_neutral.csv   -- distributor-agnostic BOM (JLC/LCSC/DigiKey/
                                  Mouser BOM-import column conventions),
                                  expanded from docs/bom.json + board Values.
  docs/quote/cpl_gw1nz_provisional.csv
                               -- JLC-style component placement list for the
                                  BOM refs only, positions lifted from the
                                  current .kicad_pcb (placement prototype).

PROVISIONAL: the board is an unrouted placement prototype (0 tracks, 99
unconnected items at r6) -- the CPL is a preparation artifact for future
quote uploads, NOT a fab file. Regenerate after routing and re-export the
final CPL from KiCad itself (kicad-cli pcb export pos) as the authoritative
file. The quote itself remains a BLOCKED gate (needs account + upload).

Self-checks (exit 1 on failure): footprint census == 65; bom.json expanded
refs == pcb BOM-bearing refs; CPL refs == BOM refs; board Value strings vs
bom.json expectations on the commodity lines.
"""
import csv
import hashlib
import io
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
PCB = os.path.join(BOARD, "out", "kicad", "tile_gw1nz.kicad_pcb")
BOMJSON = os.path.join(BOARD, "docs", "bom.json")
OUTDIR = os.path.join(BOARD, "docs", "quote")


def blocks(text, head="(footprint"):
    """Return balanced s-expr blocks whose opener is exactly `head`."""
    out = []
    i = 0
    while True:
        j = text.find(head, i)
        if j < 0:
            break
        i = j + len(head)
        # opener must be standalone (preceded by whitespace/BOF; not part
        # of a longer atom like "(pads")
        if j > 0 and text[j - 1] not in " \t\n":
            continue
        nxt = text[j + len(head):j + len(head) + 1]
        if nxt not in (" ", '"', "\n", "\t"):
            continue
        depth, k = 0, j
        while k < len(text):
            c = text[k]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    out.append(text[j:k + 1])
                    i = k + 1
                    break
            k += 1
    return out


def parse_pcb(path):
    text = open(path).read()
    sha = hashlib.sha256(text.encode()).hexdigest()[:12]
    fps = {}
    for b in blocks(text):
        ref = re.match(r'\(footprint "([^"]+)"', b).group(1)
        side_m = re.search(r'\(layer "?([FB])\.Cu"?\)', b)
        at_m = re.search(
            r"\n\s*\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", b)
        val_m = re.search(r'\(property "Value" "([^"]*)"', b) or re.search(
            r'\(fp_text value "([^"]*)"', b)
        fps[ref] = {
            "side": side_m.group(1),
            "x": float(at_m.group(1)),
            "y": float(at_m.group(2)),
            "rot": float(at_m.group(3) or 0.0),
            "value": val_m.group(1) if val_m else "",
            "pads": [],
        }
        for pb in blocks(b, head="(pad"):
            m = re.match(r'\(pad\s+(?:"([^"]*)"|([^\s()]+))', pb)
            num = m.group(1) if m.group(1) is not None else m.group(2)
            at = re.search(r"\(at ([-\d.]+) ([-\d.]+)", pb)
            net = re.search(r'\(net \d+ "([^"]+)"\)', pb)
            fps[ref]["pads"].append({
                "num": num, "x": float(at.group(1)), "y": float(at.group(2)),
                "net": net.group(1) if net else None,
            })
    return sha, fps


def abs_pt(fp, px, py):
    r = math.radians(fp["rot"])
    return (fp["x"] + px * math.cos(r) - py * math.sin(r),
            fp["y"] + px * math.sin(r) + py * math.cos(r))


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    sha, fps = parse_pcb(PCB)
    bom = json.load(open(BOMJSON))

    # S1: pcb footprint census
    if len(fps) != 65:
        sys.exit(f"S1 FAIL: pcb census {len(fps)} != 65")

    # BOM-bearing refs on the pcb (JP_ targets/TP_ test pads are copper
    # board features, not assembly items)
    bom_refs = sorted(r for r in fps
                      if not r.startswith(("JP_", "TP_")))
    # expanded bom.json refs
    bj_refs = sorted(r for line in bom["lines"] for r in line["refs"])
    if bom_refs != bj_refs:
        sys.exit("S2 FAIL: pcb/bom.json ref mismatch\npcb-only: %s\nbom-only: %s"
                 % (sorted(set(bom_refs) - set(bj_refs)),
                    sorted(set(bj_refs) - set(bom_refs))))

    pkg = {"U1": "QFN-48 0.4mm 6x6 (EP)", "U2": "SOT-23-5 (DBV)",
           "FB1": "0603", "SW": "Kailh CPG1511 socket",
           "C6": "1206", "C7": "1206", "C8": "0603", "C9": "0603",
           "R7": "0402", "R8": "0402", "R9": "0402", "R10": "0402",
           "R11": "0402"}
    for c in "C1 C2 C3 C4 C5".split():
        pkg[c] = "0603"
    for r in "R1 R2 R3 R4 R5 R6".split():
        pkg[r] = "0603"

    # S4: board Value strings vs expectations on commodity lines
    expect_val = {**{c: "100n" for c in "C1 C2 C3 C4 C5".split()},
                  **{c: "1u" for c in ("C8", "C9")},
                  **{c: "4u7" for c in ("C6", "C7")},
                  **{r: "1k" for r in ("R1", "R2")},
                  **{r: "4k7" for r in "R3 R4 R5 R6".split()},
                  **{r: "0R" for r in "R7 R8 R9 R10 R11".split()},
                  "FB1": "FB 120R@100M"}  # board class string; MPN in bom.json
    bad = {r: fps[r]["value"] for r, v in expect_val.items()
           if fps[r]["value"] != v}
    if bad:
        sys.exit(f"S4 FAIL: board Value drift: {bad}")

    # -- bom_neutral.csv -------------------------------------------------
    path1 = os.path.join(OUTDIR, "bom_neutral.csv")
    with open(path1, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Qty", "Value", "Manufacturer", "MPN",
                    "Description", "Package", "Fitted",
                    "Primary sourcing (evidence 2026-10-14)", "Notes"])
        for line in bom["lines"]:
            refs = line["refs"]
            src = (f'{line.get("supplier", "")} {line.get("sku", "")} '
                   f'{line.get("url", "")}').strip()
            notes = line.get("assembly_note", "")
            if line.get("commodity"):
                src = "commodity, any distributor (megastock)"
            pkg_l = pkg.get(refs[0], pkg.get(re.match(r"[A-Z]+", refs[0])
                                             .group(0), ""))
            val = fps[refs[0]]["value"] or line.get("mpn", "")
            w.writerow([",".join(refs), line["qty"], val,
                        line.get("mfr", ""), line.get("mpn", ""),
                        line.get("desc", ""), pkg_l, "Y", src, notes])
    # S3: rows cover exactly the bom refs (re-parse our own file)
    got = []
    with open(path1) as f:
        for row in csv.reader(f):
            if row and row[0] != "Designator":
                got.extend(row[0].split(","))
    if sorted(got) != bom_refs:
        sys.exit("S3 FAIL: bom_neutral.csv refs drift")

    # -- cpl_gw1nz_provisional.csv ---------------------------------------
    path2 = os.path.join(OUTDIR, "cpl_gw1nz_provisional.csv")
    with open(path2, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X (mm)", "Mid Y (mm)",
                    "Layer", "Rotation"])
        for r in bom_refs:
            fp = fps[r]
            w.writerow([r, f'{fp["x"]:.4f}', f'{fp["y"]:.4f}',
                        "bottom" if fp["side"] == "B" else "top",
                        f'{fp["rot"]:.1f}'])

    # -- decoupling proximity report (stdout; transcribed into docs) -----
    def pin(ref, net=None, num=None):
        for p in fps[ref]["pads"]:
            if net and p["net"] == net:
                return abs_pt(fps[ref], p["x"], p["y"])
            if num and p["num"] == num:
                return abs_pt(fps[ref], p["x"], p["y"])
        raise KeyError((ref, net, num))

    targets = {  # cap -> list of (label, point)
        "C1": [("U1.1 VCCIO0", pin("U1", num="1"))],
        "C2": [("U1.25 VCCIO1", pin("U1", num="25"))],
        "C3": [("U1.36 VCCX", pin("U1", num="36"))],
        "C4": [("U1.12 VCC1V2", pin("U1", num="12"))],
        "C5": [("U1.37 VCC1V2", pin("U1", num="37"))],
        "C6": [("U1.12/37 VCC1V2 (bulk)", pin("U1", num="12")),
               ("U1.37", pin("U1", num="37"))],
        "C7": [("U1.1 VCC (bulk)", pin("U1", num="1"))],
        "C8": [("U2.5 OUT (VCC1V2_RAW)", pin("U2", num="5"))],
        "C9": [("U2.1 IN (VCC)", pin("U2", num="1"))],
    }
    print("== decoupling proximity (r6 placement; centre -> target pin pad) ==")
    for c in "C1 C2 C3 C4 C5 C6 C7 C8 C9".split():
        fp = fps[c]
        ds = [math.dist((fp["x"], fp["y"]), pt) for _, pt in targets[c]]
        lbl = targets[c][0][0]
        print(f'{c:>3} ({fp["x"]:7.3f},{fp["y"]:7.3f})[{fp["side"]}] -> '
              f'{lbl}: min {min(ds):6.3f} mm')
    fb = fps["FB1"]
    d_out = math.dist((fb["x"], fb["y"]), pin("U2", num="5"))
    d_core = math.dist((fb["x"], fb["y"]), pin("U1", num="12"))
    print(f'FB1 ({fb["x"]:7.3f},{fb["y"]:7.3f})[{fb["side"]}] -> U2.5: '
          f"{d_out:.3f} mm, -> U1.12: {d_core:.3f} mm")
    u2 = fps["U2"]
    print(f'U2 ({u2["x"]:.3f},{u2["y"]:.3f})[{u2["side"]}] pads:',
          {p["num"]: p["net"] for p in u2["pads"]})
    print(f"\npcb sha256[:12] = {sha}; footprints = {len(fps)}; "
          f"BOM refs = {len(bom_refs)}; files: {path1}, {path2}")
    print("QUOTE_PREP OK (S1-S4)")


if __name__ == "__main__":
    main()
