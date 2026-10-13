#!/usr/bin/env python3
"""Protocol-level testbench for the discrete-spld circuit variants.

Instantiates pin-level circuits (circuits/*.json) in tile grids, wires only
physically present neighbours (alias of the mated connector pads), drives the
controller pins (B_clk / B_latch on the bottom-right tile) and checks against
an INDEPENDENT window-level abstract model of docs/architecture/protocol.md:

  * bit-exact frame stream (frame bit order, markers 11, L_endrow, T_endcol,
    scan order: columns right->left, rows bottom->top),
  * first bit valid BEFORE the first shift clock (async /PL discipline),
  * per-tile B_W flag, window by window (sticky; set when the tile emits a
    frame whose T_endcol bit is 1; cleared by the latch),
  * per-bottom-tile clock-mux direction, window by window
    (T-driver driven iff W==0; L is the exact complement),
  * no X nets after settle, no settle failures,
  * idle tail of pulled zeros after the last frame.

Two full scans per config.  Variant B2 runs the DECODED JEDEC model
(results/truez_from_jed.json), never the .pld source assumption.

The abstract model below is the authority for the checks:
  * controller reads the bottom-RIGHT tile's B_data; per window, 16 clocks,
  * tile B_clk is driven iff (it is the controller tile) or the bottom tile
    of the column to its RIGHT has W==1 (L path driven); an upper tile's
    B_clk is its bottom tile's T output: driven iff that bottom W==0,
  * W = T_W AND B_first;  T_W = flag of the tile above (pulled 1 when no
    above) and B_first = 1 when no tile below,
  * a clocked tile emits its held frame and receives the frame emitted this
    window by its selected source (T: tile above, L: tile to the left), or
    zeros when the source emits nothing,
  * flags update at the END of a window (16th-clock semantics).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import pinmodel

BASE = os.path.join(os.path.dirname(__file__), '..')

TRISTATE_PINS = {'variant_a': ('UA7', '6', 'UA1', '6'),
                 'variant_a2': ('UV1', '6', 'UV1', '3'),
                 'variant_b2': ('UB1', '19', 'UB1', '20')}


def tristate_spec(sim, prefix, circ_name, which):
    tr, tp, lr, lp = TRISTATE_PINS[circ_name]
    ref, pin = (tr, tp) if which == 'T' else (lr, lp)
    net = sim._pin2net.get((prefix + ref, pin))
    ent = sim.drivers.get((prefix + ref, pin))
    return ent[1] if ent else ('?',)


# ------------------------------------------------------- abstract model
class AbsTile:
    __slots__ = ('c', 'r', 'frame', 'flag')

    def __init__(self, c, r, frame):
        self.c, self.r, self.frame, self.flag = c, r, frame, 0


def frame_of(shape, pressed, c, r):
    bits = 0
    for k in range(12):
        if pressed(c, r, k):
            bits |= 1 << (15 - k)
    bits |= 0b11 << 2
    if (c - 1, r) not in shape:
        bits |= 1 << 1
    if (c, r - 1) not in shape:
        bits |= 1 << 0
    return bits


class AbstractScan:
    """Window-level reference.  scan windows = 16-clock groups."""

    def __init__(self, shape, pressed):
        self.shape = set(shape)
        self.tiles = {(c, r): AbsTile(c, r, frame_of(shape, pressed, c, r))
                      for (c, r) in shape}
        cs = sorted({c for c, _ in shape})
        self.ctrl_pos = max(shape, key=lambda cr: (cr[0], cr[1]))
        self.cols = sorted({c for c, _ in shape}, reverse=True)
        self.bottoms = {}
        for c in self.cols:
            self.bottoms[c] = max(r for (cc, r) in shape if cc == c)
        self.scan_order = [(c, r) for c in self.cols
                           for (c, r) in
                           sorted([(cc, rr) for (cc, rr) in shape if cc == c],
                                  key=lambda p: -p[1])]

    def w(self, c, r):
        if (c, r - 1) in self.shape:
            t_w = self.tiles[(c, r - 1)].flag
        else:
            t_w = 1
        b_first = 0 if (c, r + 1) in self.shape else 1
        return t_w & b_first

    def b_clk_driven(self, c, r):
        """Tile receives shift clocks this window (its B_clk net toggles)."""
        if (c, r) == self.ctrl_pos:
            return True
        rb = self.bottoms[c]
        if r != rb:
            # upper tile: clock forwarded up iff bottom is clocked AND its
            # mux still points up (bottom W == 0)
            return self.b_clk_driven(c, rb) and self.w(c, rb) == 0
        # bottom tile: horizontal spine - driven iff the right-hand column's
        # bottom has W == 1 (its L path), i.e. scanning reached this column
        bc = c + 1
        if bc in self.bottoms:
            return self.b_clk_driven(bc, self.bottoms[bc]) and \
                self.w(bc, self.bottoms[bc]) == 1
        return False

    def step(self):
        """One 16-clock window.  Returns controller-received frame."""
        clocked = {cr: self.b_clk_driven(*cr) for cr in self.shape}
        emit = {}
        receive = {}
        for (c, r), t in self.tiles.items():
            if clocked[(c, r)]:
                emit[(c, r)] = t.frame
        for (c, r), t in self.tiles.items():
            if not clocked[(c, r)]:
                continue
            if self.w(c, r) == 1:
                src = (c - 1, r)
            else:
                src = (c, r - 1)
            receive[(c, r)] = emit.get(src, 0)
        # apply end of window: shift + flags
        got = emit.get(self.ctrl_pos, 0)
        for (c, r), t in self.tiles.items():
            if (c, r) in receive:
                if emit[(c, r)] & 1:      # emitted frame had T_endcol = 1
                    t.flag = 1
                t.frame = receive[(c, r)]
        return got


def build_grid(sim, circ, shape):
    P = {}
    for (c, r) in sorted(shape):
        p = f't_{c}_{r}_'
        sim.load_circuit(circ, p)
        P[(c, r)] = p
    for (c, r) in shape:
        if (c, r - 1) in shape:
            a, b = P[(c, r)], P[(c, r - 1)]
            for ta, tb in (('VCC', 'VCC'), ('GND', 'GND'),
                           ('T_clk', 'B_clk'), ('T_data', 'B_data'),
                           ('T_endcol', 'GND'), ('GND', 'B_first'),
                           ('L_latch', 'B_latch'), ('T_W', 'B_W')):
                sim.alias(a + ta, b + tb)
        if (c - 1, r) in shape:
            a, b = P[(c, r)], P[(c - 1, r)]
            for ta, tb in (('VCC', 'VCC'), ('GND', 'GND'),
                           ('L_clk', 'B_clk'), ('L_data', 'B_data'),
                           ('L_endrow', 'GND'), ('L_latch', 'R_latch')):
                sim.alias(a + ta, b + tb)
    return P


class Controller:
    def __init__(self, sim, prefix):
        self.sim = sim
        self.p = prefix
        sim.drive('CTRL', prefix + 'B_clk', ('S', 0))
        sim.drive('CTRL', prefix + 'B_latch', ('S', 0))

    def set(self, sig, v):
        self.sim.drive('CTRL', self.p + sig, ('S', v))

    def sample(self):
        return self.sim.get(self.p + 'B_data')


def run_config(circ_name, shape, press_mode, jedec_models):
    circ = json.load(open(os.path.join(BASE, 'circuits', f'{circ_name}.json')))
    sim = pinmodel.Sim()
    P = build_grid(sim, circ, shape)
    if circ_name == 'variant_b2':
        for ref, c in sim.comps.items():
            if c['model'] == 'ic_gal22v10':
                c['jedec'] = 'truez'
    sim._build_domains()
    cb = max(shape, key=lambda cr: (cr[0], cr[1]))
    ctrl = Controller(sim, P[cb])

    def pressed(c, r, k):
        if press_mode == 'released':
            return False
        if press_mode == 'pressed':
            return True
        return k == (c * 3 + r) % 12   # 'distinctive'

    for (c, r) in shape:
        for k in range(12):
            sim.comps[f'{P[(c, r)]}SW{k + 1}']['state']['pressed'] = pressed(c, r, k)

    ab = AbstractScan(shape, pressed)
    frames = [(cr, ab.tiles[cr].frame) for cr in ab.scan_order]

    errors = []
    mismatches = 0
    total_samples = 0
    first_bit_checked = False
    bottoms = {(c, ab.bottoms[c]) for c in ab.cols}

    def settle(tag):
        if not sim.settle(jedec_models):
            errors.append(f'[{tag}] settle failed to converge')

    for scan in range(2):
        sim.resolve()
        ctrl.set('B_latch', 1)
        settle('latch_hi')
        ctrl.set('B_latch', 0)
        settle('latch_lo')
        # reinitialise abstract model for the new scan (re-load frames)
        ab = AbstractScan(shape, pressed)
        if scan == 0:
            v = ctrl.sample()
            exp0 = (frames[0][1] >> 15) & 1
            first_bit_checked = (v == exp0)
            if not first_bit_checked:
                errors.append(f'first-bit-before-clock: got {v}, want {exp0}')
        for cr in shape:
            if sim.get(f'{P[cr]}B_W_drv') != 0:
                errors.append(f'scan{scan}: flag of {cr} not cleared by latch')
        for wi, (cr, exp) in enumerate(frames):
            got = 0
            for b in range(16):
                v = ctrl.sample()
                total_samples += 1
                got = (got << 1) | (1 if v == 1 else 0)
                ctrl.set('B_clk', 1)
                settle(f'w{wi}b{b} hi')
                ctrl.set('B_clk', 0)
                settle(f'w{wi}b{b} lo')
                if sim.x_nets:
                    errors.append(f'X nets after settle: {sim.x_nets[:4]}')
                    sim.x_nets.clear()
            if got != exp:
                mismatches += 1
                if mismatches <= 3:
                    d = got ^ exp
                    errors.append(f'scan{scan} window{wi} {cr}: frame got '
                                  f'{got:016b} want {exp:016b} diff {d:016b}')
            # abstract step: one window passed
            ab_got = ab.step()
            if ab_got != exp:
                errors.append(f'ABSTRACT MODEL FLAW: window{wi} ref '
                              f'{ab_got:016b} != expected {exp:016b}')
            # per-tile flags + bottom mux vs abstract model
            for (cc, rr), t in ab.tiles.items():
                gotf = sim.get(f'{P[(cc, rr)]}B_W_drv')
                if gotf != t.flag:
                    errors.append(f'scan{scan} after window{wi}: flag of '
                                  f'{(cc, rr)} = {gotf}, want {t.flag}')
            for (bc, br) in bottoms:
                wv = ab.w(bc, br)
                tsp = tristate_spec(sim, P[(bc, br)], circ_name, 'T')
                lsp = tristate_spec(sim, P[(bc, br)], circ_name, 'L')
                if wv == 0 and tsp == ('Z',):
                    errors.append(f'scan{scan} after window{wi}: {(bc, br)} '
                                  f'T-driver {tsp}, want driven (W=0)')
                if wv == 1 and tsp != ('Z',):
                    errors.append(f'scan{scan} after window{wi}: {(bc, br)} '
                                  f'T-driver {tsp}, want Z (W=1)')
                if wv == 0 and lsp != ('Z',):
                    errors.append(f'scan{scan} after window{wi}: {(bc, br)} '
                                  f'L-driver {lsp}, want Z (W=0)')
                if wv == 1 and lsp == ('Z',):
                    errors.append(f'scan{scan} after window{wi}: {(bc, br)} '
                                  f'L-driver {lsp}, want driven (W=1)')
        # idle tail
        for b in range(16):
            v = ctrl.sample()
            if v != 0:
                errors.append(f'scan{scan} idle-tail bit{b}: got {v}, want 0')
                break
            ctrl.set('B_clk', 1)
            settle('tail hi')
            ctrl.set('B_clk', 0)
            settle('tail lo')
    return {'ok': not errors, 'errors': errors[:20], 'mismatches': mismatches,
            'samples': total_samples, 'rounds': sim.rounds,
            'first_bit_ok': first_bit_checked,
            'settle_failures': sim.settle_failures}


SHAPES = {
    'single': {(0, 0)},
    'column2': {(0, 0), (0, 1)},
    'column4': {(0, r) for r in range(4)},
    'row4': {(c, 0) for c in range(4)},
    'grid2x3': {(c, r) for c in range(3) for r in range(2)},
    'grid4x4': {(c, r) for c in range(4) for r in range(4)},
}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--quick', action='store_true',
                    help='smoke subset: single + column2 + row4, distinctive only')
    ap.add_argument('--shapes', help='comma list of shapes to run')
    ap.add_argument('--circuits', help='comma list of circuits to run')
    ap.add_argument('--modes', help='comma list of press modes')
    args = ap.parse_args(argv)
    jedec_models = {'truez': json.load(open(os.path.join(
        BASE, 'results', 'truez_from_jed.json')))}
    circs = ('variant_a', 'variant_a2', 'variant_b2')
    shapes = dict(SHAPES)
    if args.quick:
        shapes = {k: SHAPES[k] for k in ('single', 'column2', 'row4')}
    if args.shapes:
        keep = set(args.shapes.split(','))
        shapes = {k: v for k, v in SHAPES.items() if k in keep}
    if args.circuits:
        keep = set(args.circuits.split(','))
        circs = tuple(c for c in circs if c in keep)
    cases = []
    for circ in circs:
        for shape_name, shape in shapes.items():
            modes = ['distinctive']
            if shape_name in ('single', 'grid4x4'):
                modes += ['pressed', 'released']
            elif shape_name in ('column2',):
                modes += ['pressed']
            if args.modes:
                keep = set(args.modes.split(','))
                modes = [m for m in modes if m in keep]
            for mode in modes:
                cases.append((circ, shape_name, shape, mode))
    fails = 0
    for circ, sname, shape, mode in cases:
        res = run_config(circ, shape, mode, jedec_models)
        status = 'PASS' if res['ok'] else 'FAIL'
        if not res['ok']:
            fails += 1
        print(f"{status}  {circ:11} {sname:9} {mode:11} "
              f"samples={res['samples']} rounds={res['rounds']} "
              f"first_bit={'ok' if res['first_bit_ok'] else 'BAD'} "
              f"settle_fail={res['settle_failures']}")
        for e in res['errors']:
            print(f'      ERR {e}')
    print(f'\n{"ALL PASS" if fails == 0 else f"{fails} FAILING"} '
          f'({len(cases)} configs)')
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
