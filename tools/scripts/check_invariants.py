#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Regression guard for the tile PCB.

Compares a candidate design against a reference (normally the rev-A prototype) and fails
if anything covered by the function freeze changed:

  * netlist  - connectivity of every logic IC and connector pin (nets are compared as sets
               of pins, so net renames are fine). Two-pin parts listed with --series are
               collapsed (their two nets merged) so that inserted series-termination
               resistors are tolerated; parts listed with --ignore (e.g. added decoupling
               capacitors) are dropped.
  * pcb      - position and rotation of every switch (SW*) and connector (J*), and the
               Edge.Cuts outline.

Usage:
  check_invariants.py netlist REF.net NEW.net [--series R201,R202] [--ignore C201,C202]
  check_invariants.py pcb REF.kicad_pcb NEW.kicad_pcb [--tol 0.001]

Netlists are KiCad s-expression netlists (kicad-cli sch export netlist --format kicadsexpr).
A reference file can be pulled from git, e.g.
  git show rev-a-prototype:hardware/kicad/module-tile/tastiera_isomorfa.kicad_pcb > ref.kicad_pcb
"""
import argparse
import math
import re
import sys


# ---------------------------------------------------------------- netlist ---------------
def parse_netlist(path):
    """Return {net_name: set((ref, pin))}."""
    text = open(path, encoding="utf-8").read()
    nets = {}
    # whitespace-agnostic: works for single-line (KiCad <= 9) and multi-line (KiCad 10) output
    for m in re.finditer(r'\(net\s+\(code\s+"?\d+"?\)\s+\(name\s+"([^"]*)"\)(.*?)(?=\(net\s+\(code|\Z)',
                         text, re.S):
        name, body = m.group(1), m.group(2)
        nets[name] = set(re.findall(r'\(node\s+\(ref\s+"([^"]+)"\)\s+\(pin\s+"([^"]+)"\)', body))
    return nets


def normalise(nets, series, ignore):
    """Merge nets joined by a series part, drop ignored parts, return a set of frozensets."""
    groups = [set(pins) for pins in nets.values()]
    # union-find over groups through the series parts
    for ref in series:
        idx = [i for i, g in enumerate(groups) if any(r == ref for r, _ in g)]
        if len(idx) != 2:
            sys.exit(f"series part {ref} must touch exactly 2 nets, touches {len(idx)}")
        a, b = idx
        groups[a] |= groups[b]
        groups[b] = set()
    drop = set(series) | set(ignore)
    out = set()
    for g in groups:
        g = frozenset(p for p in g if p[0] not in drop)
        if len(g) > 1 or (len(g) == 1 and not next(iter(g))[0].startswith("TP")):
            out.add(g)
    return out


def check_netlist(args):
    ref = normalise(parse_netlist(args.ref), [], [])
    new = normalise(parse_netlist(args.new), args.series, args.ignore)
    ok = True
    for g in sorted(ref - new, key=sorted):
        print("REF net missing/changed in NEW:", " ".join(f"{r}.{p}" for r, p in sorted(g)))
        ok = False
    for g in sorted(new - ref, key=sorted):
        print("NEW net not in REF:           ", " ".join(f"{r}.{p}" for r, p in sorted(g)))
        ok = False
    print("netlist:", "IDENTICAL" if ok else "DIFFERENT",
          f"({len(ref)} nets, series={args.series or '-'}, ignore={args.ignore or '-'})")
    return ok


# ---------------------------------------------------------------- pcb -------------------
def parse_pcb(path):
    text = open(path, encoding="utf-8").read()
    parts = {}
    for m in re.finditer(r'\n\t\(footprint "([^"]+)"(.*?)\n\t\)', text, re.S):
        body = m.group(2)
        at = re.search(r'\n\t\t\(at ([\d.\-]+) ([\d.\-]+)(?: ([\d.\-]+))?\)', body)
        ref = re.search(r'\(property "Reference" "([^"]+)"', body)
        side = re.search(r'\n\t\t\(layer "([^"]+)"\)', body)
        if not (at and ref):
            continue
        parts[ref.group(1)] = (float(at.group(1)), float(at.group(2)),
                               float(at.group(3) or 0) % 360, side.group(1) if side else "?",
                               m.group(1))
    edges = []
    for m in re.finditer(r'\(gr_(line|arc|rect|circle|poly)(.*?)\(layer "Edge\.Cuts"\)', text, re.S):
        nums = tuple(round(float(v), 3) for v in re.findall(r'-?\d+\.?\d*', m.group(2))[:8])
        edges.append((m.group(1),) + nums)
    return parts, sorted(edges)


def check_pcb(args):
    rparts, redges = parse_pcb(args.ref)
    nparts, nedges = parse_pcb(args.new)
    ok = True
    for ref in sorted(r for r in rparts if re.match(r"^(SW|J)\d+$", r)):
        if ref not in nparts:
            print(f"{ref}: missing in NEW")
            ok = False
            continue
        rx, ry, rr, _, rfp = rparts[ref]
        nx, ny, nr, _, nfp = nparts[ref]
        d = math.hypot(rx - nx, ry - ny)
        rot = min(abs(rr - nr), 360 - abs(rr - nr))
        if d > args.tol or rot > 0.01:
            print(f"{ref}: moved {d:.3f} mm / rotated {rot:.2f} deg ({rx},{ry},{rr}) -> ({nx},{ny},{nr})")
            ok = False
        elif rfp != nfp:
            print(f"{ref}: same place, footprint {rfp} -> {nfp} (check the mating geometry)")
    if redges != nedges:
        print(f"Edge.Cuts differ ({len(redges)} vs {len(nedges)} primitives)")
        ok = False
    print("pcb:", "INVARIANTS OK" if ok else "INVARIANTS VIOLATED")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("netlist")
    n.add_argument("ref")
    n.add_argument("new")
    n.add_argument("--series", type=lambda s: [x for x in s.split(",") if x], default=[])
    n.add_argument("--ignore", type=lambda s: [x for x in s.split(",") if x], default=[])
    p = sub.add_parser("pcb")
    p.add_argument("ref")
    p.add_argument("new")
    p.add_argument("--tol", type=float, default=0.001)
    args = ap.parse_args()
    ok = check_netlist(args) if args.cmd == "netlist" else check_pcb(args)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
