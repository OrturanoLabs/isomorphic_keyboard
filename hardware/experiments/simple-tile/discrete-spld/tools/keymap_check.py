#!/usr/bin/env python3
"""Keymap + interface completion for the rev-A reference circuit.

Reads circuits/reva_reference.json (KiCad XML export converted), verifies the
electrical key map against docs/architecture/protocol.md verbatim, then fills
the empty 'interface' block.  Asserts (any failure aborts with a message):

  * 12 keys SW101..SW112 wired via 100R series to BTNs0..BTNs11 in order
  * BTNs_Lk land on the '165 parallel inputs in protocol order:
      key0..7  -> U104 D7..D0 (pins 6,5,4,3,14,13,12,11)
      key8..11 -> U103 D7..D4 (pins 6,5,4,3)
      U103 D3,D2 (pins 14,13) = VCC markers, D1(12)=L_endrow, D0(11)=T_endcol
  * serial chain U103.Q7(9) -> U104.DS(10);  U104.Q7(9) -> data_drv
  * every interface input pull matches protocol.md (10k; direction verified)
  * 33R series on the seven '_drv' outputs, 100R key series, 10k pulls: counts
  * W = T_W AND B_first drives all four tristate enables (U101.1/7, U107.1/7)
  * frame bit order table printed for the report
"""
import json
import sys
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / 'circuits' / 'reva_reference.json'

LVC165 = {'D0': '11', 'D1': '12', 'D2': '13', 'D3': '14',
          'D4': '3', 'D5': '4', 'D6': '5', 'D7': '6',
          'Q7': '9', 'DS': '10', 'SH/LD': '1', 'CLK': '2', 'CLKINH': '15'}


def net_of_pin(nets, ref, pin):
    for name, pins in nets.items():
        if [ref, pin] in pins:
            return name
    return None


def on(nets, net):
    return set(tuple(p) for p in nets[net])


def main():
    d = json.load(open(PATH))
    nets = d['nets']
    fails = []

    def check(cond, msg):
        print(('PASS ' if cond else 'FAIL ') + msg)
        if not cond:
            fails.append(msg)

    # (a) switch -> series 100R -> BTNs k
    for k in range(12):
        sw = f'SW{101 + k}'
        n_sw = net_of_pin(nets, sw, '2')
        r_ser = f'R{110 + k}'
        ok = [r_ser, '1'] in nets.get(n_sw, []) and \
             [f'R{122 + k}', '1'] in nets.get(n_sw, []) and \
             net_of_pin(nets, r_ser, '2') == f'BTNs{k}'
        check(ok, f'key{k}: {sw}.2 --(10k pd {122+k}, 100R {110+k})--> BTNs{k}')

    # (b) BTNs_Lk -> parallel inputs
    want = [(f'BTNs_L{k}', 'U104', ['6', '5', '4', '3', '14', '13', '12', '11'][k]) for k in range(8)]
    want += [(f'BTNs_L{k}', 'U103', ['6', '5', '4', '3'][k - 8]) for k in range(8, 12)]
    for net, ref, pin in want:
        check([ref, pin] in nets.get(net, []), f'{net} -> {ref}.{pin}')

    check(on(nets, 'VCC') >= {('U103', '14'), ('U103', '13')},
          'U103 D3,D2 (pins 14,13) tied to VCC (marker bits)')
    check(('U103', '12') in on(nets, 'L_endrow'), 'U103 D1(12) = L_endrow')
    check(('U103', '11') in on(nets, 'T_endcol'), 'U103 D0(11) = T_endcol')

    # (c) serial chain
    check(('U104', '10') in on(nets, net_of_pin(nets, 'U103', '9')),
          'U103.Q7(9) -> U104.DS(10)')
    check(('U104', '9') in on(nets, 'data_drv'), 'U104.Q7(9) -> data_drv')
    check({('R205', '1'), ('R206', '1'), ('U102', '1')} <= on(nets, 'data_drv'),
          'data_drv feeds series R205/R206 and U102.1 (flag AND)')

    # (d) pulls (10k, correct rail)
    pull = {'L_data': 'GND', 'R_latch': 'GND', 'B_latch': 'GND', 'T_data': 'GND',
            'L_endrow': 'VCC', 'B_first': 'VCC', 'T_W': 'VCC', 'T_endcol': 'VCC',
            'B_clk': 'VCC'}
    for net, rail in pull.items():
        rr = None
        for c in d['components']:
            if c['ref'].startswith('R') and c['value'] == '10k':
                ps = [net_of_pin(nets, c['ref'], '1'), net_of_pin(nets, c['ref'], '2')]
                if net in ps:
                    rr = (c['ref'], ps)
        ok = rr is not None and rail in rr[1]
        check(ok, f'pull {net} -> {rail} 10k ({rr[0] if rr else "MISSING"})')

    # (e) series resistance counts
    from collections import Counter
    vals = Counter(c['value'] for c in d['components'] if c['ref'].startswith('R'))
    check(vals['100'] == 12 and vals['10k'] == 21 and vals['33'] == 7,
          f"resistor census {dict(vals)} == 100:12, 10k:21, 33:7")
    drv = {'L_clk': ('R201', 'L_clk_drv'), 'T_clk': ('R202', 'T_clk_drv'),
           'L_latch': ('R203', 'latch_drv'), 'T_latch': ('R204', 'latch_drv'),
           'B_data': ('R205', 'data_drv'), 'R_data': ('R206', 'data_drv'),
           'B_W': ('R207', 'B_W_drv')}
    for net, (r, drvn) in drv.items():
        ok = ([r, '2'] in nets.get(net, [])) and net_of_pin(nets, r, '1') == drvn
        check(ok, f'series 33R {r}: {drvn} -> {net}')

    # W connectivity
    wnet = net_of_pin(nets, 'U102', '3')
    check({('U101', '1'), ('U101', '7'), ('U107', '1'), ('U107', '7')} <= on(nets, wnet),
          f'W net ({wnet}) drives U101.1/7 and U107.1/7')
    check(('U102', '5') in on(nets, 'T_W') and ('U102', '6') in on(nets, 'B_first'),
          'U102 2A=T_W (pin5), 2B=B_first (pin6)')
    check(('U109', '15') in on(nets, net_of_pin(nets, 'U102', '2')),
          'U109 Tc(15) -> U102.2 (flag AND)')

    # frame order print
    print('\nframe bit order (controller receives MSB-first):')
    order = [('key0', 'U104', 'D7', '6'), ('key1', 'U104', 'D6', '5'),
             ('key2', 'U104', 'D5', '4'), ('key3', 'U104', 'D4', '3'),
             ('key4', 'U104', 'D3', '14'), ('key5', 'U104', 'D2', '13'),
             ('key6', 'U104', 'D1', '12'), ('key7', 'U104', 'D0', '11'),
             ('key8', 'U103', 'D7', '6'), ('key9', 'U103', 'D6', '5'),
             ('key10', 'U103', 'D5', '4'), ('key11', 'U103', 'D4', '3'),
             ('marker', 'U103', 'D3', '14'), ('marker', 'U103', 'D2', '13'),
             ('L_endrow', 'U103', 'D1', '12'), ('T_endcol', 'U103', 'D0', '11')]
    for i, (what, ref, dpin, pin) in enumerate(order):
        print(f'  bit {15 - i:2}: {what:8} {ref}.{dpin} (pin {pin})')

    # fill interface block
    d['interface'] = {
        'signals': {'T_clk': 'T_clk', 'T_data': 'T_data', 'T_endcol': 'T_endcol',
                    'T_W': 'T_W', 'T_latch': 'T_latch', 'L_clk': 'L_clk',
                    'L_data': 'L_data', 'L_endrow': 'L_endrow', 'L_latch': 'L_latch',
                    'B_clk': 'B_clk', 'B_data': 'B_data', 'B_first': 'B_first',
                    'B_latch': 'B_latch', 'B_W': 'B_W', 'R_latch': 'R_latch',
                    'R_data': 'R_data', 'VCC': 'VCC', 'GND': 'GND'},
        'keys': {f'key{k}': f'BTNs_L{k}' for k in range(12)},
        'edges': {
            'top': {'VCC': ['J102', '1'], 'T_clk': ['J102', '2'],
                    'T_data': ['J102', '3'], 'T_endcol': ['J102', '4'],
                    'GND': ['J102', '5'], 'L_latch': ['J102', '6'],
                    'T_W': ['J102', '7'], 'GND2': ['J102', '8']},
            'bottom': {'VCC': ['J103', '1'], 'B_clk': ['J103', '2'],
                       'B_data': ['J103', '3'], 'GND': ['J103', '4'],
                       'B_first': ['J103', '5'], 'B_latch': ['J103', '6'],
                       'B_W': ['J103', '7'], 'GND2': ['J103', '8']},
            'left': {'VCC': ['J101', '1'], 'L_clk': ['J101', '2'],
                     'L_data': ['J101', '3'], 'L_endrow': ['J101', '4'],
                     'L_latch': ['J101', '5'], 'GND': ['J101', '6']},
            'right': {'VCC': ['J104', '1'], 'B_clk': ['J104', '2'],
                      'B_data': ['J104', '3'], 'GND': ['J104', '4'],
                      'R_latch': ['J104', '5'], 'GND2': ['J104', '6']}},
        'note': 'B_clk/B_data are single nets shared by the bottom and right '
                'legs, exactly as rev A; T_latch and L_latch are two 33R-tapped '
                'copies of latch_drv.'}
    with open(PATH, 'w') as f:
        json.dump(d, f, indent=1, sort_keys=True)
    print(f'\ninterface block written; {len(fails)} failures')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
