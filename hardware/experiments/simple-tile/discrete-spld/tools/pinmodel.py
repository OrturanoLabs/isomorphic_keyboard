#!/usr/bin/env python3
"""Zero-delay pin-level netlist simulator for the discrete-spld experiment.

Nets carry values in {0, 1, 'Z', 'X'}.  Drivers are strong (0/1) or Hi-Z.
Resistors are modelled faithfully for LOGIC purposes:
  * to a rail (VCC/GND): weak pull of that rail's value,
  * between signal nets: transparent bridge (the two nets form one domain;
    this is documented behaviour - DC-transparent series Rs).
A domain with conflicting strong drivers resolves to 'X' and is reported.

Stateful devices clock on rising edges detected between settle rounds; all
state updates of one round happen atomically from pre-round values (classic
delta-cycle synchronous semantics), which exactly matches the synchronous
16-bit window of the scan protocol.

Supported models (all pin-level):
  resistor, cap, switch, pad,
  ic_74lvc165a, ic_74lv161a, ic_2g08, ic_2g32, ic_2g125, ic_2g126,
  ic_2g74, ic_1g04, ic_gal22v10  (driven by a DECODED JEDEC model JSON)
"""

# ---------------------------------------------------------------- rails
BASE_RAILS = {'VCC': 1, 'GND': 0}


class Sim:
    def __init__(self):
        self.nets = {}            # net -> list of (comp, pin)
        self.comps = {}           # ref -> state dict
        self.bridge_pairs = []    # (netA, netB) bridged by series R / mates
        self.pull = {}            # net -> weak value (0/1); conflicts = error
        self.drivers = {}         # (comp, pin) -> (net, ('S',0/1) | ('Z',))
        # note: keyed by pin because one ref may tie several output pins
        # onto the same net (tri-state wire-OR by design)
        self.values = {}          # net -> resolved value
        self.domains = None       # union-find net -> domain rep
        self.rails = dict(BASE_RAILS)   # net name -> rail value
        self.x_nets = []          # report collector
        self.settle_failures = 0
        self.rounds = 0

    # ----------------------------- construction
    def load_circuit(self, circ, prefix=''):
        """Instantiate a circuit JSON under a ref/net prefix (multi-tile)."""
        dev = circ['devices']
        for c in circ['components']:
            ref = prefix + c['ref']
            self.comps[ref] = {'device': c['device'],
                               'model': dev[c['device']]['sim'],
                               'state': {}, 'circuit': circ['circuit']}
        for net, pins in circ['nets'].items():
            if not net.startswith('NC_'):
                for ref, pin in pins:
                    self.nets.setdefault(prefix + net, []).append((prefix + ref, pin))
        for rn in BASE_RAILS:
            self.rails[prefix + rn] = BASE_RAILS[rn]
        return prefix

    def alias(self, net_a, net_b):
        """Electrically merge two nets (connector mate / 0-ohm link)."""
        self.bridge_pairs.append((net_a, net_b))

    def _build_domains(self):
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        # series-R bridges: resistors with no rail pin become bridges
        for ref, c in self.comps.items():
            if c['model'] != 'resistor':
                continue
            pins = self._pins_of(ref)
            if len(pins) != 2:
                continue
            (n1, _), (n2, _) = pins
            if n1 in self.rails and n2 in self.rails:
                raise ValueError(f'{ref}: rail-to-rail resistor')
            if n1 in self.rails:
                self._add_pull(n2, self.rails[n1], ref)
            elif n2 in self.rails:
                self._add_pull(n1, self.rails[n2], ref)
            else:
                union(n1, n2)
        for a, b in self.bridge_pairs:
            union(a, b)
        self.domains = {n: find(n) for n in self.nets}
        self._refresh_domain_caches()

    def _pins_of(self, ref):
        out = []
        for net, pins in self.nets.items():
            for r, p in pins:
                if r == ref:
                    out.append((net, p))
        return sorted(out, key=lambda t: t[1])

    def _add_pull(self, net, val, ref):
        if net in self.pull and self.pull[net][0] != val:
            raise ValueError(f'pull conflict on {net} ({self.pull[net][1]} vs {ref})')
        self.pull[net] = (val, ref)

    # ----------------------------- resolution
    def resolve(self):
        """Two passes: value per union-find domain, then per member net."""
        self._dom_drivers = {}
        for (comp, pin), (dnet, spec) in self.drivers.items():
            if spec[0] == 'S':
                self._dom_drivers.setdefault(
                    self.domains.get(dnet, dnet), []).append(spec[1])
        domval = {}
        for d in self._dom_members:
            strong = None
            if d in self._dom_rails:
                strong = self._dom_rails[d]      # ideal supply pins domain
            else:
                for v in self._dom_drivers.get(d, ()):
                    if strong is None:
                        strong = v
                    elif strong != v:
                        strong = 'X'
            weak = self._dom_pulls.get(d)
            if strong is not None:
                v = strong
            elif weak is not None:
                v = weak
            else:
                v = 'Z'
            domval[d] = v
        self.values = {}
        for d, nets in self._dom_members.items():
            v = domval.get(d, 'Z')
            for net in nets:
                self.values[net] = v
        return self.values

    def _refresh_domain_caches(self):
        """Precompute domain -> rails/pulls/member nets; driver values are
        filtered per resolve() call (they change every round)."""
        self._dom_members = {}
        for net in self.nets:
            self._dom_members.setdefault(self.domains.get(net, net), []).append(net)
        self._dom_rails = {}
        for rn, rv in self.rails.items():
            self._dom_rails[self.domains.get(rn, rn)] = rv
        self._dom_pulls = {}
        for n, (pv, prefr) in self.pull.items():
            d = self.domains.get(n, n)
            self._dom_pulls.setdefault(d, pv)
        # pin lookup acceleration
        self._pin2net = {}
        for net, pins in self.nets.items():
            for r, p in pins:
                self._pin2net[(r, p)] = net

    def get(self, net):
        return self.values.get(net, 'Z')

    def drive(self, comp, net, spec, pin=None):
        self.drivers[(comp, pin if pin is not None else net)] = (net, spec)

    # ----------------------------- evaluation
    def settle(self, jedec_models=None, max_rounds=12):
        """Iterate evaluation to a fixpoint.  Returns False on oscillation.
        X nets are only reported if they survive to the LAST round (round-0
        propagation noise is normal)."""
        prev = None
        for rnd in range(max_rounds):
            self.rounds += 1
            self.resolve()
            self._eval_comb()
            sync_round(self, jedec_models or {})
            self.resolve()
            snap = {k: v for k, v in self.values.items()}
            if snap == prev:
                for net, v in self.values.items():
                    if v == 'X' and net not in self.x_nets:
                        self.x_nets.append(net)
                return True
            prev = snap
        return False

    def _eval_comb(self):
        for ref, c in self.comps.items():
            m = c['model']
            fn = COMB.get(m)
            if fn:
                fn(self, ref, c)


# ============================================================== device models
def _pin_net(sim, ref, pin):
    return sim._pin2net.get((ref, pin))


def _ino(sim, ref, pin):
    n = _pin_net(sim, ref, pin)
    if n is None:
        return 'Z'
    return sim.get(n)


def _out(sim, ref, outpin_map):
    for pin, val in outpin_map.items():
        net = _pin_net(sim, ref, pin)
        if net is not None:
            sim.drive(ref, net, ('Z',) if val == 'Z' else ('S', val), pin=pin)


def _comb2(sim, ref, c, f):
    a1, b1, a2, b2 = (_ino(sim, ref, p) for p in ('1', '2', '5', '6'))
    y1 = f(a1, b1)
    y2 = f(a2, b2)
    _out(sim, ref, {'7': y1, '3': y2})


def _and(a, b):
    if a == 0 or b == 0:
        return 0
    if a == 1 and b == 1:
        return 1
    return 'X'


def _or(a, b):
    if a == 1 or b == 1:
        return 1
    if a == 0 and b == 0:
        return 0
    return 'X'


def _not(a):
    return {0: 1, 1: 0}.get(a, 'X')


def m_2g08(sim, ref, c):
    _comb2(sim, ref, c, _and)


def m_2g32(sim, ref, c):
    _comb2(sim, ref, c, _or)


def m_1g04(sim, ref, c):
    _out(sim, ref, {'4': _not(_ino(sim, ref, '2'))})


def _buffer_pair(active_low_oe):
    def m(sim, ref, c):
        oe1, a1 = _ino(sim, ref, '1'), _ino(sim, ref, '2')
        oe2, a2 = _ino(sim, ref, '7'), _ino(sim, ref, '5')
        en1 = (oe1 == 0) if active_low_oe else (oe1 == 1)
        en2 = (oe2 == 0) if active_low_oe else (oe2 == 1)
        if oe1 == 'X' or oe2 == 'X':
            _out(sim, ref, {'6': 'X', '3': 'X'})
            return
        _out(sim, ref, {'6': a1 if en1 else 'Z', '3': a2 if en2 else 'Z'})

    return m


def m_cap(sim, ref, c):
    pass  # zero-delay: decoupling is invisible to logic


def m_pad(sim, ref, c):
    pass  # pure connector node


def m_sw(sim, ref, c):
    # switch: pressed -> bridge.  Handled as a dynamic driver: pin1 is VCC.
    st = c['state']
    n2 = _pin_net(sim, ref, '2')
    sim.drive(ref, n2, ('S', 1) if st.get('pressed') else ('Z',), pin='2')


def m_2g241(sim, ref, c):
    # sec1: active-LOW OE; sec2: active-HIGH OE
    oe1, a1 = _ino(sim, ref, '1'), _ino(sim, ref, '2')
    oe2, a2 = _ino(sim, ref, '7'), _ino(sim, ref, '5')
    y1 = a1 if oe1 == 0 else (None if oe1 == 1 else 'X')
    y2 = a2 if oe2 == 1 else (None if oe2 == 0 else 'X')
    _out(sim, ref, {'6': 'Z' if y1 is None else y1,
                    '3': 'Z' if y2 is None else y2})


COMB = {'ic_2g08': m_2g08, 'ic_2g32': m_2g32, 'ic_1g04': m_1g04,
        'ic_2g125': _buffer_pair(True), 'ic_2g126': _buffer_pair(False),
        'ic_2g241': m_2g241,
        'cap': m_cap, 'pad': m_pad, 'switch': m_sw}


# ------------------------------------------------------- sequential devices
class Clocked:
    """Mixin behaviour executed once per settle round after COMB evaluation."""

    @staticmethod
    def rising(sim, ref, c, net):
        v = sim.get(net)
        prev = c['state'].get('_clk_prev', 0)
        now = 1 if v == 1 else 0
        c['state']['_clk_prev'] = now
        return prev == 0 and now == 1 and v == 1


def sync_round(sim, jedec_models):
    """Process stateful devices: level-sensitive parts, then rising clocks.
    All registers update from pre-round state."""
    for ref, c in sim.comps.items():
        if c['model'] == 'ic_74lvc165a':
            c['state'].setdefault('_shift', [0] * 8)
            c['state'].setdefault('_clk_prev', 0)
        elif c['model'] == 'ic_74lv161a':
            c['state'].setdefault('_q', 0)
            c['state'].setdefault('_clk_prev', 0)
        elif c['model'] == 'ic_2g74':
            c['state'].setdefault('_q', 0)
            c['state'].setdefault('_clk_prev', 0)
        elif c['model'] == 'ic_gal22v10':
            c['state'].setdefault('_q', {})
            c['state'].setdefault('_clk_prev', 0)
    # level-sensitive updates (async load/clear) apply immediately
    for ref, c in sim.comps.items():
        m, st = c['model'], c['state']
        if m == 'ic_74lvc165a':
            if _ino(sim, ref, '1') == 0:
                # async parallel load: A=pin11(D0) ... H=pin6(D7)
                order = ['11', '12', '13', '14', '3', '4', '5', '6']
                st['_shift'] = [1 if _ino(sim, ref, p) == 1 else 0 for p in order]
                st['_clk_prev'] = 1 if _ino(sim, ref, '2') == 1 else 0
            qh = st['_shift'][7]
            sim.drive(ref, _pin_net(sim, ref, '9'), ('S', qh), pin='9')
        elif m == 'ic_74lv161a':
            if _ino(sim, ref, '1') == 0:
                st['_q'] = 0
                st['_clk_prev'] = 1 if _ino(sim, ref, '2') == 1 else 0
            q = st.setdefault('_q', 0)
            rco = 1 if (q == 15 and _ino(sim, ref, '10') == 1) else 0
            sim.drive(ref, _pin_net(sim, ref, '15'), ('S', rco), pin='15')
        elif m == 'ic_2g74':
            if _ino(sim, ref, '6') == 0:
                st['_q'] = 0
            if _ino(sim, ref, '7') == 0:
                st['_q'] = 1
            sim.drive(ref, _pin_net(sim, ref, '5'), ('S', st.setdefault('_q', 0)), pin='5')
        elif m == 'ic_gal22v10':
            gal_level(sim, ref, c, jedec_models)
    # rising-clock updates
    for ref, c in sim.comps.items():
        m, st = c['model'], c['state']
        if m == 'ic_74lvc165a':
            clk = _pin_net(sim, ref, '2')
            if _ino(sim, ref, '1') == 1 and _ino(sim, ref, '15') == 0 and \
               Clocked.rising(sim, ref, c, clk):
                ser = 1 if _ino(sim, ref, '10') == 1 else 0
                st['_shift'] = [ser] + st['_shift'][:-1]
        elif m == 'ic_74lv161a':
            clk = _pin_net(sim, ref, '2')
            if _ino(sim, ref, '1') == 1 and Clocked.rising(sim, ref, c, clk):
                if _ino(sim, ref, '9') == 0:
                    st['_q'] = 0  # /LOAD -> tied parallel data = GND
                elif _ino(sim, ref, '7') == 1 and _ino(sim, ref, '10') == 1:
                    st['_q'] = (st['_q'] + 1) & 0xF
        elif m == 'ic_2g74':
            clk = _pin_net(sim, ref, '1')
            if _ino(sim, ref, '6') == 1 and _ino(sim, ref, '7') == 1 and \
               Clocked.rising(sim, ref, c, clk):
                d = _ino(sim, ref, '2')
                if d in (0, 1):
                    st['_q'] = d
        elif m == 'ic_gal22v10':
            gal_clock(sim, ref, c, jedec_models)


def gal_level(sim, ref, c, jedec_models):
    """Combinational + async parts of the decoded GAL, evaluated per round."""
    model = jedec_models[c.get('jedec', 'truez')]
    st = c['state']
    st.setdefault('_q', {})           # pin -> 0/1 registered state
    # async reset (AR is level-sensitive)
    if gal_eval_term(sim, ref, model, model['ar'], st):
        for pin in [p for p, o in model['pins'].items() if o['registered']]:
            st['_q'][pin] = 0
    # drive combinatorial pins
    for pin, o in model['pins'].items():
        net = _pin_net(sim, ref, pin)
        if net is None:
            continue
        if o['registered']:
            q = st['_q'].get(pin, 0)
            val = q if o['active_high'] else (1 - q)
            oe = gal_eval_term(sim, ref, model, o['oe'], st) \
                if o['oe'] is not None else False
            sim.drive(ref, net, ('S', val) if oe else ('Z',), pin=pin)
        else:
            sop = any(gal_eval_term(sim, ref, model, t, st) for t in o['terms'])
            val = sop if o['active_high'] else not sop
            oe = gal_eval_term(sim, ref, model, o['oe'], st) if o['oe'] is not None else False
            sim.drive(ref, net, ('S', int(val)) if oe else ('Z',), pin=pin)


def gal_clock(sim, ref, c, jedec_models):
    model = jedec_models[c.get('jedec', 'truez')]
    st = c['state']
    clknet = _pin_net(sim, ref, str(model['clock_pin']))
    if not Clocked.rising(sim, ref, c, clknet):
        return
    if gal_eval_term(sim, ref, model, model['sp'], st):
        nxt = {p: 1 for p, o in model['pins'].items() if o['registered']}
    else:
        nxt = {}
        for pin, o in model['pins'].items():
            if not o['registered']:
                continue
            d = any(gal_eval_term(sim, ref, model, t, st) for t in o['terms'])
            nxt[pin] = int(d if o['active_high'] else not d)
    st['_q'].update(nxt)


def gal_signal(sim, ref, model, pin, st, depth=0):
    """Value of the AND-array line source for a pin (input or feedback)."""
    assert depth < 16
    spi = str(pin)
    o = model['pins'].get(spi)
    if o is None:
        net = _pin_net(sim, ref, spi)
        return sim.get(net) == 1 if net else False
    if o['registered']:
        # silicon: the '+' tab of a registered OLMC delivers /Q
        return st['_q'].get(spi, 0) == 0
    # combinatorial: feedback = internal node (pre-driver), incl. polarity
    sop = any(gal_eval_term(sim, ref, model, t, st, depth + 1) for t in o['terms'])
    return sop if o['active_high'] else not sop


def gal_eval_term(sim, ref, model, term, st, depth=0):
    if term is None:
        return False
    for pin, ph in term:
        base = gal_signal(sim, ref, model, pin, st, depth)
        if not (base if ph == '+' else not base):
            return False
    return True
