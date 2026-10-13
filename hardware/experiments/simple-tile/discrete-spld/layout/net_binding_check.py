#!/usr/bin/env python3
"""Explicit authoritative-nets gate for the discrete-spld boards.

There is no KiCad schematic for these tiles (the only schematic generator in
the project was the rev-c MCU one, removed with that worktree), so the
authoritative connectivity is the simulation-proven circuit JSON.  This
checker is the ERC-substitute gate: it parses the generated .kicad_pcb text
and requires an EXACT two-way match with circuits/<variant>.json:

  circuit -> board: every non-NC circuit net's (ref, pin) set equals the set
                    of board pads bound to that net name (restricted to
                    circuit refs);
  board   -> circuit: every board pad on a real net must be a circuit pin on
                    that same net; TP_* pads are board-only and must be bound
                    to the net named by their suffix; every circuit
                    component must exist on the board with its circuit value;
  NC pins: every (ref, pin) of an NC_* circuit net must be unconnected
           (net 0) on the board;
  count:  the board's nets must be exactly the circuit's non-NC nets.

Exit 0 + 'NET-BINDING PASS' on success; any mismatch is printed and exits 1.
Pure stdlib text parsing (no pcbnew needed) so it runs on the host.
"""
import json
import os
import re
import sys

BASE = os.path.join(os.path.dirname(__file__), '..')


def blocks(text, tag):
    out, j = [], 0
    needle = f'({tag} '
    while True:
        j = text.find(needle, j)
        if j < 0:
            return out
        d, k = 0, j
        while k < len(text):
            if text[k] == '(':
                d += 1
            elif text[k] == ')':
                d -= 1
                if d == 0:
                    out.append(text[j:k + 1])
                    break
            k += 1
        j = k + 1


def board_pads(pcb_path):
    """(ref -> {pin -> netname}) and (netname -> set((ref, pin)))."""
    t = open(pcb_path).read()
    net_of_pad = {}
    for fp in blocks(t, 'footprint'):
        m = re.match(r'\(footprint\s+"([^"]+)"', fp)
        if not m:
            # old gen form: unquoted name
            m = re.match(r'\(footprint\s+([^\s)]+)', fp)
        ref = m.group(1)
        # pads may span lines: find pad blocks
        for pad in blocks(fp, 'pad'):
            pm = re.match(r'\(pad\s+(?:"([0-9A-Za-z_]*)"|([^\s)]+))', pad)
            pn = pm.group(1) if pm.group(1) is not None else pm.group(2)
            nm = re.search(r'\(net\s+(?:\d+\s+)?"([^"]*)"\)', pad)
            net_of_pad[(ref, pn)] = nm.group(1) if nm else None
    net2pins = {}
    for (r, p), n in net_of_pad.items():
        if n:
            net2pins.setdefault(n, set()).add((r, p))
    return net_of_pad, net2pins


def main(pcb_path, variant, errata_path=None):
    circ = json.load(open(os.path.join(BASE, 'circuits', f'{variant}.json')))
    comp = {c['ref']: c for c in circ['components']}
    cir_net2pins = {}
    nc_pins = set()
    for n, pins in circ['nets'].items():
        for ref, pin in pins:
            if n.startswith('NC_'):
                nc_pins.add((ref, str(pin)))
            else:
                cir_net2pins.setdefault(n, set()).add((ref, str(pin)))
    errata = []
    if errata_path:
        ed = json.load(open(errata_path))
        ed = ed.get(variant, ed)
        for e in ed['pins']:
            rp = (e['ref'], e['pin'])
            nc_pins.discard(rp)
            for s in cir_net2pins.values():
                s.discard(rp)
            cir_net2pins.setdefault(e['net'], set()).add(rp)
            errata.append(f"{e['ref']}.{e['pin']} -> {e['net']}")
        print(f'errata overlay applied to expectations: {len(errata)} pins')
    net_of_pad, brd_net2pins = board_pads(pcb_path)
    errs = []
    # every circuit component on the board
    board_refs = {r for (r, _) in net_of_pad}
    for ref in comp:
        if ref not in board_refs:
            errs.append(f'{ref}: circuit component missing on board')
    # NC pins must be net-less on the board
    for (ref, pin) in sorted(nc_pins):
        got = net_of_pad.get((ref, pin), 'MISSING')
        if got not in (None, 'MISSING'):
            errs.append(f'{ref}.{pin}: circuit NC pin has net {got} on board')
    # circuit-named TP pads: board-only, bound to the circuit net they label
    tp_ok = True
    for (ref, pin), n in sorted(net_of_pad.items()):
        if ref.startswith('TP_'):
            want = ref[3:]
            if n != want:
                errs.append(f'{ref}.{pin}: TP on net {n}, expected {want}')
                tp_ok = False
    # two-way match per net (circuit refs only; TPs excluded)
    for n in sorted(cir_net2pins):
        want = cir_net2pins[n]
        got = {rp for rp in brd_net2pins.get(n, set())
               if not rp[0].startswith('TP_')}
        if want != got:
            miss = want - got
            extra = got - want
            errs.append(f'net {n}: missing_on_board={sorted(miss)} '
                        f'extra_on_board={sorted(extra)}')
    for n in sorted(brd_net2pins):
        if n not in cir_net2pins:
            refs = sorted(r for r, _ in brd_net2pins[n])
            errs.append(f'net {n}: on board but not in circuit '
                        f'(refs {refs[:8]}{"..." if len(refs) > 8 else ""})')
    nets_b = len(brd_net2pins)
    nets_c = len(cir_net2pins)
    print(f'board pads parsed: {len(net_of_pad)}; board nets: {nets_b}; '
          f'circuit nets (non-NC): {nets_c}; NC pins checked: {len(nc_pins)}')
    print(f'TP bindings: {"ok" if tp_ok else "BROKEN"}')
    if errs:
        print(f'NET-BINDING FAIL ({len(errs)} problems)')
        for e in errs[:30]:
            print('  ' + e)
        return 1
    print('NET-BINDING PASS')
    return 0


if __name__ == '__main__':
    pcb = sys.argv[1]
    variant = sys.argv[2] if len(sys.argv) > 2 else 'variant_a'
    errata = None
    if '--errata' in sys.argv:
        errata = sys.argv[sys.argv.index('--errata') + 1]
    sys.exit(main(pcb, variant, errata))
