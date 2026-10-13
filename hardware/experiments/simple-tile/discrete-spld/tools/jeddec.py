#!/usr/bin/env python3
"""JEDEC decoder for the GAL22V10 / ATF22V10C(L) fuse map (QF=5892).

Ground-up decode of the actual fuse bits in a .jed file -- does NOT trust the
assembler's opinion of the design.  The fuse-map geometry is taken from two
independent published sources, checked for agreement:

  A. galette 0.3.0 source (github simon-frankau/galette, src/gal.rs +
     src/chips.rs + src/writer.rs): the assembler that produced the .jed files
     under test.  Conventions: GAL struct starts with all fuses True (JEDEC
     '1'); set_and() writes False ('0') at [row*44 + column + neg_off] to
     CONNECT a literal; unused rows are blown to all-'0' (constant-false
     product term); an all-intact row (all '1') is the constant-TRUE term.
     Row 0 = AR, row 131 = SP, OLMC blocks start at OLMC_ROWS_22V10 with the
     output-enable product term in the first row of each block.
  B. MAME jedutil (jedutil.cpp): gal22v10pinfuserows / gal22v10pinfusecolumns
     tables and config_gal22v10_pins() (S0/S1 fuse addresses 5808..5827).
     Row/word addresses in jedutil are 44 * galette_row + ... and match
     galette exactly (verified by the self-test below).

Fuse-map summary (both sources agree):
  * 132 rows x 44 columns = 5808 product-array fuses at addresses 0..5807.
  * row 0    : asynchronous reset (AR) product term, one row.
  * rows 1..130 : ten OLMC blocks; block for pin P starts at row
    START[P] with SIZE[P] rows; the FIRST row of a block is the output-enable
    product term, the remaining SIZE-1 rows are the data SOP.
    pin  : 23  22  21  20  19  18  17  16  15 14
    start:  1  10  21  34  49  66  83  98 111 122
    size :  9  11  13  15  17  17  15  13  11  9
  * row 131  : synchronous preset (SP) product term, one row.
  * 20 architecture fuses at 5808..5827: pairs (S0, S1), pin 23 first down to
    pin 14 (S0 at 5808, 5810, ... 5826; S1 at 5809, 5811, ... 5827).
    S0: 1 = active-high output, 0 = active-low.  S1: 1 = combinatorial,
    0 = registered.  (jedutil config_gal22v10_pins, matches galette
    interleave(xor, ac1) writer with reversed OLMC index.)
  * 64 signature/UES fuses at 5828..5891.

  Column c of a row addresses one of 22 AND-array lines; each line k has an
  uninverted fuse at column base[k] and an inverted fuse at base[k]+1:
    pin  : 1  2  3  4  5  6  7  8  9 10 11 13 14 15 16 17 18 19 20 21 22 23
    base : 0  4  8 12 16 20 24 28 32 36 40 42 38 34 30 26 22 18 14 10  6  2
  (galette PIN_TO_COL_22V10; jedutil gal22v10pinfusecolumns uses
  {low=base+1, high=base}.  Fuse blown ('0') = literal connected.)

Silicon semantics implemented (per Lattice/Atmel 22V10 macrocell structure,
consistent with galette's needs_flip() comment and jedutil S-bit decoding):
  * combinatorial OLMC (S1=1): pin = SOP XOR !S0 when the OE term is true,
    else Hi-Z.  Feedback = pin value (pad when Hi-Z).
  * registered OLMC   (S1=0): on rising pin-1 clock, Q <- SOP XOR !S0.
    pin = Q when OE term true else Hi-Z.  Feedback = /Q ALWAYS (the 22V10
    feeds back the inverted register output; this is why galette flips the
    negation of feedback literals for registered active-high outputs).
  * AR term true  -> all registered Q := 0 (asynchronous).
  * SP term true  -> all registered Q := 1 on next clock (synchronous).

Self-tests (run with --selftest or as part of decode):
  1. jedutil/galette geometry agreement (rows, columns, S-bit addresses).
  2. JEDEC *C fuse checksum recomputation (galette algorithm).
  3. Decoded macrocell SOPs of the file under test are printed for review;
     equivalence to the source .pld is NOT assumed - callers crosscheck with
     sim_truth.py / sim_tile.py.
"""
import json
import sys

# ---------------------------------------------------------------- geometry
# pin -> base column (fuse column of the UNinverted tab; inverted tab = +1)
PIN_TO_COL = {1: 0, 2: 4, 3: 8, 4: 12, 5: 16, 6: 20, 7: 24, 8: 28, 9: 32,
              10: 36, 11: 40, 13: 42, 14: 38, 15: 34, 16: 30, 17: 26,
              18: 22, 19: 18, 20: 14, 21: 10, 22: 6, 23: 2}
# jedutil gal22v10pinfusecolumns: {pin, lowfusecolumn, highfusecolumn}
JEDUTIL_COLS = {1: (1, 0), 2: (5, 4), 3: (9, 8), 4: (13, 12), 5: (17, 16),
                6: (21, 20), 7: (25, 24), 8: (29, 28), 9: (33, 32),
                10: (37, 36), 11: (41, 40), 13: (43, 42), 14: (39, 38),
                15: (35, 34), 16: (31, 30), 17: (27, 26), 18: (23, 22),
                19: (19, 18), 20: (15, 14), 21: (11, 10), 22: (7, 6),
                23: (3, 2)}
# OLMC blocks: pin -> (start_row, size)  [galette OLMC_ROWS_22V10 reversed]
OLMC = {23: (1, 9), 22: (10, 11), 21: (21, 13), 20: (34, 15), 19: (49, 17),
        18: (66, 17), 17: (83, 15), 16: (98, 13), 15: (111, 11), 14: (122, 9)}
# jedutil pin_fuse_rows: {pin, OE_addr, term_start_addr, term_end_addr}
JEDUTIL_ROWS = {14: (5368, 5412, 5720), 15: (4884, 4928, 5324),
                16: (4312, 4356, 4840), 17: (3652, 3696, 4268),
                18: (2904, 2948, 3608), 19: (2156, 2200, 2860),
                20: (1496, 1540, 2112), 21: (924, 968, 1452),
                22: (440, 484, 880), 23: (44, 88, 396)}
# S0/S1 fuse addresses per pin (jedutil config_gal22v10_pins)
S01_ADDR = {14: (5826, 5827), 15: (5824, 5825), 16: (5822, 5823),
            17: (5820, 5821), 18: (5818, 5819), 19: (5816, 5817),
            20: (5814, 5815), 21: (5812, 5813), 22: (5810, 5811),
            23: (5808, 5809)}
NUM_ROWS, NUM_COLS = 132, 44
AR_ROW, SP_ROW = 0, 131
TOTAL_FUSES = 5892
SIG_ADDR, SIG_LEN = 5828, 64


def selftest_geometry():
    """Cross-check the two published fuse-map sources against each other."""
    for pin, (low, high) in JEDUTIL_COLS.items():
        base = PIN_TO_COL[pin]
        assert high == base and low == base + 1, f"column mismatch pin {pin}"
    for pin, (oe, ts, te) in JEDUTIL_ROWS.items():
        start, size = OLMC[pin]
        assert oe == start * NUM_COLS, f"OE row mismatch pin {pin}"
        assert ts == (start + 1) * NUM_COLS, f"term start mismatch pin {pin}"
        assert te == (start + size - 1) * NUM_COLS, f"term end mismatch pin {pin}"
    assert NUM_ROWS * NUM_COLS + 20 + SIG_LEN == TOTAL_FUSES
    # jedutil SP at fuse 5764 = row 131; AR at 0
    assert SP_ROW * NUM_COLS == 5764 and AR_ROW == 0
    # galette interleave order == jedutil pin-23-first order
    for j, pin in enumerate(range(23, 13, -1)):
        s0, s1 = S01_ADDR[pin]
        assert s0 == 5808 + 2 * j and s1 == 5809 + 2 * j
    return True


# ---------------------------------------------------------------- parsing
def parse_jed(path):
    """Parse a JEDEC file into (fuses list[bool/int], meta dict).

    fuses[i] in {0, 1}; length TOTAL_FUSES.  *F0 default is handled.
    """
    with open(path, 'rb') as f:
        raw = f.read().decode('ascii', errors='replace')
    meta = {'path': path}
    fuses = {}
    default = 0
    qf = None
    csum_seen = None
    i = 0
    fields = raw.replace('\x02', '').replace('\x03', '').split('*')
    for fld in fields:
        fld = fld.strip()
        if not fld:
            continue
        if fld.startswith('F') and fld[1:2].isdigit():
            default = int(fld[1:].split()[0])
        elif fld.startswith('QF'):
            qf = int(fld[2:].split()[0])
        elif fld.startswith('G') and fld[1:2].isdigit():
            meta['security_bit'] = int(fld[1:].split()[0])
        elif fld.startswith('C') and fld[1:2].lower() in '0123456789abcdef':
            csum_seen = int(fld[1:].split()[0], 16)
        elif fld.startswith('L'):
            head, _, rest = fld[1:].partition(' ')
            addr = int(head)
            bits = ''.join(rest.split())
            for k, ch in enumerate(bits):
                fuses[addr + k] = int(ch)
        elif fld.startswith('D') or fld[0] in '0123456789abcdef':
            pass  # DESCRIPTION section / trailing file checksum
    assert qf == TOTAL_FUSES, f"QF={qf}, expected {TOTAL_FUSES}"
    fuselist = [fuses.get(i, default) for i in range(TOTAL_FUSES)]
    meta['checksum_declared'] = csum_seen
    return fuselist, meta, raw


def jedec_fuse_checksum(fuselist):
    """galette writer.rs CheckSummer: pack bits LSB-first into bytes, sum."""
    total, byte, bit = 0, 0, 0
    for b in fuselist:
        if b:
            byte |= 1 << bit
        bit += 1
        if bit == 8:
            total = (total + byte) & 0xffff
            byte, bit = 0, 0
    return total + byte


# ---------------------------------------------------------------- decoding
def row_literals(fuselist, row):
    """Decode one product row -> list of (pin, phase) with phase in {'+','-'};
    'all-intact' -> TRUE (empty AND); any column with both phases blown ->
    the row is contradictory -> FALSE."""
    base = row * NUM_COLS
    lits, contradiction, any_blown = [], False, False
    for pin, c in PIN_TO_COL.items():
        noninv = fuselist[base + c] == 0      # blown => literal connected
        inv = fuselist[base + c + 1] == 0
        if noninv and inv:
            contradiction = True
        elif noninv:
            lits.append((pin, '+')); any_blown = True
        elif inv:
            lits.append((pin, '-')); any_blown = True
    if contradiction:
        return ('false', [])
    return ('term', lits)  # empty lits == constant TRUE


def decode(path):
    fuselist, meta, raw = parse_jed(path)
    selftest_geometry()
    out = {'path': path, 'security_bit': meta.get('security_bit', 0),
           'checksum_declared': meta['checksum_declared'],
           'checksum_computed': jedec_fuse_checksum(fuselist),
           'signature': ''.join(str(b) for b in fuselist[SIG_ADDR:SIG_ADDR + SIG_LEN]),
           'ar': row_literals(fuselist, AR_ROW),
           'sp': row_literals(fuselist, SP_ROW),
           'olmc': {}}
    for pin, (start, size) in OLMC.items():
        s0a, s1a = S01_ADDR[pin]
        s0, s1 = fuselist[s0a], fuselist[s1a]
        out['olmc'][pin] = {
            's0': s0, 's1': s1,
            'registered': s1 == 0,
            'active_high': s0 == 1,
            'oe': row_literals(fuselist, start),
            'terms': [row_literals(fuselist, start + 1 + k)
                      for k in range(size - 1)],
        }
    return fuselist, out


def fmt_lits(lits, names=None):
    if not lits:
        return "'1'"
    parts = []
    for pin, ph in sorted(lits):
        nm = names.get(pin, f"P{pin}") if names else f"P{pin}"
        parts.append(nm if ph == '+' else f"/{nm}")
    return ' * '.join(parts)


def render(decoded, names=None):
    """Human-readable equation dump (in silicon truth, including flips)."""
    L = []
    L.append(f"file: {decoded['path']}")
    ok = 'OK' if decoded['checksum_declared'] == decoded['checksum_computed'] else 'MISMATCH'
    L.append(f"fuse checksum: declared={decoded['checksum_declared']:04x} "
             f"computed={decoded['checksum_computed']:04x} -> {ok}")
    sig = decoded['signature']
    L.append(f"signature/UES: {sig}")
    L.append(f"AR: {fmt_lits(decoded['ar'][1]) if decoded['ar'][0]=='term' else 'FALSE'}")
    L.append(f"SP: {fmt_lits(decoded['sp'][1]) if decoded['sp'][0]=='term' else 'FALSE'}")
    for pin in sorted(decoded['olmc'], reverse=True):
        o = decoded['olmc'][pin]
        mode = 'reg' if o['registered'] else 'com'
        pol = 'hi' if o['active_high'] else 'lo'
        oe = o['oe']
        oes = 'FALSE' if oe[0] == 'false' else fmt_lits(oe[1], names)
        sop_terms = []
        for kind, lits in o['terms']:
            if kind == 'false':
                continue
            sop_terms.append(fmt_lits(lits, names))
        sop = ' + '.join(sop_terms) if sop_terms else "'0'"
        L.append(f"P{pin}: S0={o['s0']} S1={o['s1']} [{mode},{pol}] OE={oes} SOP={sop}")
    return '\n'.join(L)


# -------------------------------------------------- simulation model
def to_sim_model(decoded, pin_names):
    """Emit a flat JSON model consumed by tools/pinmodel.py.

    Terms stay as (pin, phase) literal lists; the simulator resolves pin
    numbers to signals and applies the registered-feedback inversion rule at
    evaluation time.  A decoded model is therefore a faithful statement of
    the FUSES, not of the source .pld.
    """
    def terms_of(kind_lits):
        kind, lits = kind_lits
        return None if kind == 'false' else lits
    m = {'device': 'GAL22V10-decoded-from-jedec', 'source': decoded['path'],
         'clock_pin': 1, 'ar': terms_of(decoded['ar']), 'sp': terms_of(decoded['sp']),
         'pin_names': {str(k): v for k, v in pin_names.items()}, 'pins': {}}
    for pin, o in decoded['olmc'].items():
        m['pins'][str(pin)] = {
            'registered': o['registered'], 'active_high': o['active_high'],
            'oe': terms_of(o['oe']),
            'terms': [t for t in (terms_of(x) for x in o['terms']) if t is not None],
        }
    return m


def main():
    selftest_geometry()
    print("self-test: galette/jedutil fuse-map geometry agreement OK")
    pin_names = None
    args = sys.argv[1:]
    out_json = None
    if '--names' in args:
        i = args.index('--names')
        pin_names = {int(k): v for k, v in json.loads(args[i + 1]).items()}
        del args[i:i + 2]
    if '--out' in args:
        i = args.index('--out')
        out_json = args[i + 1]
        del args[i:i + 2]
    for path in args:
        fuselist, dec = decode(path)
        print(render(dec, pin_names))
        c_ok = dec['checksum_declared'] == dec['checksum_computed']
        print(f"checksum declared==computed: {c_ok}")
        assert c_ok, f"JEDEC checksum mismatch in {path}"
        if out_json:
            assert pin_names, "--out needs --names"
            with open(out_json, 'w') as f:
                json.dump(to_sim_model(dec, pin_names), f, indent=1)
            print(f"wrote {out_json}")


if __name__ == '__main__':
    main()
