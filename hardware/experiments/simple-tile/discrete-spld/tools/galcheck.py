#!/usr/bin/env python3
"""Crosscheck a decoded GAL22V10 JEDEC fuse map against its source .pld.

Does NOT assume the assembler preserved the design: parses the .pld source
equations independently (subset grammar of galette/galasm), evaluates both
sides as boolean functions over their support, and reports MATCH/MISMATCH
per macrocell for the data SOP, the output-enable term, AR and SP.

Literal semantics on the JEDEC side (silicon truth, from galette's
needs_flip law + jedutil S-bit decoding):
  * input pin literal  (pin, '+'/'-')  ->  env[pin] / !env[pin]
  * combinatorial OLMC feedback        ->  that OLMC's pin value / its inverse
  * registered OLMC feedback           ->  '+' tab delivers !Q, '-' delivers Q
    (the 22V10 always feeds back the inverted register output)

On the source side a name X refers to the PIN value of X (combinatorial:
its SOP incl. polarity; registered: Q for active-high, !Q for active-low).
Registered source RHS is evaluated over current-state Q values.
"""
import re
import sys

import jeddec

# ------------------------------------------------ .pld parsing (subset)
TOKEN = re.compile(r"\s*(/|\(|\)|\+|\*|=|\.|[A-Za-z_][A-Za-z0-9_]*)")


def lex(s):
    out = []
    i = 0
    while i < len(s):
        m = TOKEN.match(s, i)
        if not m:
            raise ValueError(f"cannot lex {s[i:]!r}")
        out.append(m.group(1))
        i = m.end()
    return out


class P:  # tiny recursive descent: expr := term ('+' term)* ; term := factor ('*' factor)*
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expr(self):
        v = self.term()
        while self.peek() == '+':
            self.next()
            v = ('or', v, self.term())
        return v

    def term(self):
        v = self.factor()
        while self.peek() == '*':
            self.next()
            v = ('and', v, self.factor())
        return v

    def factor(self):
        tok = self.next()
        if tok == '/':
            return ('not', self.factor())
        if tok == '(':
            v = self.expr()
            assert self.next() == ')'
            return v
        if tok in ('GND', 'VCC'):
            return ('const', tok == 'VCC')
        return ('var', tok)


def parse_pld(path):
    """Return (pin_order, equations{lhs: (suffix, ast)}); AR/SP keyed as-is."""
    with open(path) as f:
        text = f.read()
    # strip comments, cut DESCRIPTION section
    lines = []
    for line in text.splitlines():
        line = line.split(';', 1)[0].strip()
        if line.startswith('DESCRIPTION'):
            break
        if line:
            lines.append(line)
    chip = lines[0]
    assert chip == 'GAL22V10', chip
    pinrow = ' '.join(lines[2:4]).split()
    eqns = {}
    for line in lines[4:]:
        if '=' not in line:
            continue
        lhs, rhs = line.split('=', 1)
        lhs = lhs.strip()
        suffix = ''
        if '.' in lhs:
            lhs, suffix = lhs.split('.')
            suffix = '.' + suffix
        eqns[lhs + suffix] = P(lex(rhs)).expr()
    return pinrow, eqns


def eval_ast(ast, env):
    op = ast[0]
    if op == 'const':
        return ast[1]
    if op == 'var':
        return env[ast[1]]
    if op == 'not':
        return not eval_ast(ast[1], env)
    if op == 'and':
        return eval_ast(ast[1], env) and eval_ast(ast[2], env)
    if op == 'or':
        return eval_ast(ast[1], env) or eval_ast(ast[2], env)
    raise ValueError(op)


def support(ast, acc):
    op = ast[0]
    if op == 'var':
        acc.add(ast[1])
    for sub in ast[1:]:
        if isinstance(sub, tuple):
            support(sub, acc)
    return acc


# ------------------------------------------------ decoded-side evaluator
class JedSide:
    """Boolean evaluator over (inputs, state) environments for a decoded JEDEC.

    inputs/state map signal NAME -> bool.  pin numbers identify hardware.
    """

    def __init__(self, model, names):
        self.m = model
        self.pinno = {int(p): n for p, n in names.items()}   # pin -> name
        self.olmc_pins = {int(p) for p in model['pins']}      # pins 14..23

    def lit_base(self, pin, inputs, state, depth):
        """Value of the '+' tab of the AND-array line for `pin`."""
        if pin in self.olmc_pins:
            o = self.m['pins'][str(pin)]
            if o['registered']:
                return not state[self.pinno[pin]]   # '+' tab delivers /Q
            return self.pin_value(pin, inputs, state, depth + 1)
        return inputs[self.pinno[pin]]

    def term_val(self, lits, inputs, state, depth=0):
        assert depth < 16, "combinatorial feedback loop"
        return all(base if ph == '+' else not base
                   for pin, ph in lits
                   for base in [self.lit_base(pin, inputs, state, depth)])

    def sop(self, terms, inputs, state, depth=0):
        return any(self.term_val(t, inputs, state, depth) for t in terms)

    def pin_value(self, pin, inputs, state, depth=0):
        o = self.m['pins'][str(pin)]
        if o['registered']:
            # pin carries current Q (active-high); active-low registered
            # would carry /Q -- handled here for completeness
            q = state[self.pinno[pin]]
            return q if o['active_high'] else not q
        s = self.sop(o['terms'], inputs, state, depth)
        return s if o['active_high'] else not s

    def next_q(self, pin, inputs, state):
        o = self.m['pins'][str(pin)]
        assert o['registered']
        d = self.sop(o['terms'], inputs, state)
        return d if o['active_high'] else not d   # XOR sits on the D path

    def oe(self, pin, inputs, state):
        t = self.m['pins'][str(pin)]['oe']
        return self.sop([t], inputs, state) if t is not None else False

    def ar(self, inputs, state):
        return self.sop([self.m['ar']], inputs, state) if self.m['ar'] else False


# ------------------------------------------------ comparison driver
def vars_of_space(input_names, reg_names):
    return input_names + [f"Q:{r}" for r in reg_names]


def compare(jed_path, pld_path, names):
    _, dec = jeddec.decode(jed_path)
    model = jeddec.to_sim_model(dec, names)
    js = JedSide(model, names)
    _, eqns = parse_pld(pld_path)

    reg_names = [names[int(p)] for p in sorted(model['pins'], key=int)
                 if model['pins'][p]['registered']]
    input_names = [names[p] for p in sorted(names, key=int) if p <= 13]
    allvars = sorted(set(input_names) | set(reg_names))
    results = []
    notes = []

    def src_value(name, env, depth=0):
        """Source-side value of any pin name: inputs/registers from env,
        combinatorial OLMCs evaluated recursively from their equations."""
        assert depth < 16, "combinatorial loop in source"
        if name in env:
            return env[name]
        # combinatorial helper: evaluate its equation ('.T' marks the data
        # equation of a tristated combinatorial output)
        ast = eqns.get(name) or eqns.get(name + '.T')
        assert ast is not None, f"no source equation for combinatorial {name}"
        return eval_ast(ast, SrcEnv(env, depth))

    class SrcEnv(dict):
        """env proxy resolving combinatorial helper names on demand."""
        def __init__(self, env, depth):
            super().__init__(env)
            self.depth = depth

        def __missing__(self, key):
            v = src_value(key, self, self.depth + 1)
            self[key] = v
            return v

    def probe(src_fn, jed_fn, label):
        mism = []
        n = len(allvars)
        for i in range(1 << n):
            env = SrcEnv({vn: bool((i >> k) & 1) for k, vn in enumerate(allvars)}, 0)
            inputs = {vn: env[vn] for vn in input_names}
            state = {vn: env[vn] for vn in reg_names}
            a = src_fn(env)
            b = jed_fn(inputs, state)
            if a != b:
                mism.append((i, a, b))
                if len(mism) > 3:
                    break
        ok = not mism
        results.append((label, ok, n, mism[:3]))
        return ok

    overall = True
    for pkey in sorted(model['pins'], key=int):
        pin = int(pkey)
        nm = names[pin]
        o = model['pins'][pkey]
        if o['registered']:
            src = eqns.get(nm + '.R')
            if src is None:
                continue
            overall &= probe(lambda env: eval_ast(src, env),
                             lambda ii, ss: js.next_q(pin, ii, ss),
                             f"{nm}.R next-state")
        else:
            src = eqns.get(nm) or eqns.get(nm + '.T')  # .T = tristate data
            if src is None:
                continue
            overall &= probe(lambda env: eval_ast(src, env),
                             lambda ii, ss: js.pin_value(pin, ii, ss),
                             f"{nm} comb value")
        # OE: source .E suffix when present; outputs without .E are always
        # driven (OE row left intact = TRUE).
        oe_src_ast = eqns.get(nm + '.E')
        if True:
            if oe_src_ast is None:
                src_oe = lambda env: True
            else:
                src_oe = lambda env: eval_ast(oe_src_ast, env)
            overall &= probe(src_oe, lambda ii, ss: js.oe(pin, ii, ss),
                             f"{nm} OE")
        # flag a decoded OE=FALSE (fully blown row): the pin can never drive
        if model['pins'][pkey]['oe'] is None:
            notes.append(f"{nm}: OE term is FALSE (fully blown fuse row) -> "
                         f"pin is permanently Hi-Z on silicon")

    if 'AR' in eqns:
        overall &= probe(lambda env: eval_ast(eqns['AR'], env),
                         lambda ii, ss: js.ar(ii, ss), "AR")
    return overall, results, notes, model, eqns


def main():
    jed_path, pld_path = sys.argv[1], sys.argv[2]
    names = None
    if len(sys.argv) > 3:
        import json
        names = {int(k): v for k, v in json.loads(sys.argv[3]).items()}
    overall, results, notes, model, eqns = compare(jed_path, pld_path, names)
    for note in notes:
        print(f"NOTE {note}")
    for label, ok, n, mism in results:
        print(f"{'MATCH' if ok else 'MISMATCH'}  {label:22} (vars={n})")
        for i, a, b in mism:
            print(f"    first counterexamples: row {i:05x} src={a} jed={b}")
    print(f"OVERALL: {'MATCH' if overall else 'MISMATCH'}")
    sys.exit(0 if overall else 1)


if __name__ == '__main__':
    main()
