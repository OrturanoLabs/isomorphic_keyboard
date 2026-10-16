#!/usr/bin/env python3
"""dsn_check.py -- verify the exported Specctra DSN against the source pcb
(FPGA-02 prep evidence that the freerouting input is faithful).

Checks (exit 1 on failure):
  D1 net census: DSN (network (net ...)) names == pcb net names (45 at r6).
  D2 per-net pin parity: every net's DSN (pins REF-PAD ...) set equals the
     pcb's (ref,pad) set for that net.
  D3 structural inventory: boundary path present (== stepped outline),
     exactly the signal layers F.Cu/B.Cu, default rule width/clearance ==
     0.2/0.2 reference rule set, via definition present.
  D4 vacuity control: with one pcb net renamed the parity MUST fail.

Pure python, stdlib only. Writes docs/../out/route/dsn_check.json.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
PCB = os.path.join(BOARD, "out", "kicad", "tile_gw1nz.kicad_pcb")
DSN = os.path.join(BOARD, "out", "route", "tile_gw1nz.dsn")
REPORT = os.path.join(BOARD, "out", "route", "dsn_check.json")
if len(sys.argv) > 1:
    PCB = os.path.abspath(sys.argv[1])
if len(sys.argv) > 2:
    DSN = os.path.abspath(sys.argv[2])
if len(sys.argv) > 3:
    REPORT = os.path.abspath(sys.argv[3])


def blocks(text, head):
    out, i = [], 0
    while True:
        j = text.find(head, i)
        if j < 0:
            break
        i = j + len(head)
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


def pcb_nets(path):
    text = open(path).read()
    pads = {}
    for b in blocks(text, "(footprint"):
        ref = re.match(r'\(footprint "([^"]+)"', b).group(1)
        for pb in blocks(b, "(pad"):
            m = re.match(r'\(pad\s+(?:"([^"]*)"|([^\s()]+))', pb)
            num = m.group(1) if m.group(1) is not None else m.group(2)
            net = re.search(r'\(net (?:\d+ )?"([^"]+)"\)', pb)
            if net and num:
                pads.setdefault(net.group(1), set()).add(f"{ref}-{num}")
    return pads


def dsn_nets(path):
    text = open(path).read()
    seg = blocks(text, "(network")
    nets = {}
    for nb in seg:
        for m in re.finditer(r'\(net\s+(\S+)\s+\(pins\s+([^)]*)\)\s*\)', nb):
            nets[m.group(1)] = set(m.group(2).split())
    return text, nets


def dsn_classes(path):
    """Inventory of (class ...) blocks: (name, nets, width_um, clr_um)."""
    text = open(path).read()
    out = []
    for cb in blocks(text, "(class"):
        m = re.match(r'\(class "?([^"\s(]+)"?\s+(.*?)\s*\(circuit',
                     cb, re.S)
        if not m:
            continue
        nets = m.group(2).split()
        w = re.search(r"\(width (\d+)\)", cb)
        c = re.search(r"\(clearance (\d+)", cb)
        out.append({"name": m.group(1), "nets": len(nets),
                    "width_um": int(w.group(1)) if w else None,
                    "clearance_um": int(c.group(1)) if c else None})
    return out


def main():
    pcb = pcb_nets(PCB)
    text, dsn = dsn_nets(DSN)
    probs = []
    if set(dsn) != set(pcb):
        probs.append(f"D1: dsn-only={sorted(set(dsn) - set(pcb))} "
                     f"pcb-only={sorted(set(pcb) - set(dsn))}")
    else:
        diff = {n: (sorted(dsn[n] - pcb[n]), sorted(pcb[n] - dsn[n]))
                for n in dsn if dsn[n] != pcb[n]}
        if diff:
            probs.append(f"D2: pin drift: "
                         f"{dict(list(diff.items())[:3])}")

    # D4 vacuity control over the same comparison machinery
    ctrl_pcb = {"__ctrl__" if k == sorted(pcb)[0] else k: v
                for k, v in pcb.items()}
    if set(dsn) == set(ctrl_pcb):
        probs.append("D4: control did NOT fire (renamed net accepted)")

    inv = {
        "boundary_paths": len(re.findall(r"\(boundary\b", text)),
        "layers": re.findall(r'\(layer ([FB]\.Cu)', text),
        "width_um": re.findall(r"\(width (\d+)\)", text),
        "clearance_um": re.findall(r"\(clearance (\d+)", text),
        "vias": re.findall(r'\(via "([^"]+)"', text),
        "nets": len(dsn),
        "pins": sum(len(v) for v in dsn.values()),
    }
    if inv["boundary_paths"] < 1:
        probs.append("D3: no boundary path")
    if set(inv["layers"]) != {"F.Cu", "B.Cu"}:
        probs.append(f"D3: layers drift: {inv['layers']}")
    if "200" not in inv["width_um"] or "200" not in inv["clearance_um"]:
        probs.append(f"D3: default rule != 0.2/0.2: {inv}")
    if not inv["vias"]:
        probs.append("D3: no via definition")

    classes = dsn_classes(DSN)
    rep = {"ok": not probs, "problems": probs, "inventory": inv,
           "classes": classes,
           "pcb_nets": len(pcb), "dsn_nets": len(dsn),
           "source_pcb": os.path.basename(PCB), "dsn": os.path.basename(DSN)}
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    json.dump(rep, open(REPORT, "w"), indent=1)
    print(("DSN_CHECK OK: " if not probs else f"DSN_CHECK FAIL: {probs}")
          + f"nets {len(dsn)}=={len(pcb)}, pins={inv['pins']}, "
            f"boundary={inv['boundary_paths']}, vias={inv['vias']}, "
            f"rule={inv['width_um'][:2]}/{inv['clearance_um'][:2]} um, "
            f"classes={[(c['name'], c['nets'], c['width_um'], c['clearance_um']) for c in classes]}")
    sys.exit(0 if not probs else 1)


if __name__ == "__main__":
    main()
