#!/usr/bin/env python3
"""Generate the pin-level circuit JSONs for variant A (all-LVC + LV161A) and
variant B2 (ATF22LV10C + 2xLVC165 + 1G04).

Connectivity is authored here as explicit named-net tables.  Both variants:
  * implement exactly the rev-A tile behaviour (docs/architecture/protocol.md),
  * keep the rev-A passive plan: 10k pulls on all floating inputs, 100R key
    series + 10k key pull-downs, 33R series on the seven driven outputs,
  * drop the rev-A debug jumper headers J105..J108: VCC_T/GND_T are merged into
    VCC/GND and BTNs_k connect straight to the '165 inputs (the headers were
    1:1 jumpers; this is the ONLY structural simplification, recorded here).

Every IC pin appears in exactly one net; intentionally unconnected pads get a
single-pin net named NC_<ref>_<pin> so nothing is silently dropped.

G1 fix (2026-10-13): finish() now CONSUMES each device's 'power' pin table -
every component's declared power pins are bound to VCC/GND unless the author
already connected that exact pin to the same rail (a different-net owner is a
fatal authoring conflict).  Previously these tables were dead data and the
rail pins silently fell through to NC_*, leaving 7/9 ICs of variant A (and
analogous pins of A2/B2) unpowered.
"""
import json
import os

OUT = os.path.join(os.path.dirname(__file__), '..', 'circuits')

# ------------------------------------------------------------ device library
DEVICES = {
    'SN74LVC165A': {
        'sim': 'ic_74lvc165a', 'package': 'TSSOP-16',
        'footprint': 'Package_SO:TSSOP-16_4.4x5mm_P0.65mm',
        'package_note': 'PW (TSSOP-16) package: SOIC-16 (old rev-A choice) does '
                        'NOT fit the 18.36mm-lattice tile lanes (proven in '
                        'boards/*/placement_report); silicon identical family, '
                        'same TI datasheet timing table basis as timing.json',
        'pins': {'1': 'SH/LD', '2': 'CLK', '3': 'E(D4)', '4': 'F(D5)',
                 '5': 'G(D6)', '6': 'H(D7)', '7': '/QH', '8': 'GND',
                 '9': 'QH', '10': 'SER', '11': 'A(D0)', '12': 'B(D1)',
                 '13': 'C(D2)', '14': 'D(D3)', '15': 'CLKINH', '16': 'VCC'},
        'power': {'VCC': '16', 'GND': '8'},
        'datasheet': 'https://www.ti.com/lit/ds/symlink/sn74lvc165a.pdf'},
    'SN74LV161A': {
        'sim': 'ic_74lv161a', 'package': 'TSSOP-16',
        'footprint': 'Package_SO:TSSOP-16_4.4x5mm_P0.65mm',
        'package_note': 'PW (TSSOP-16) - same rationale as SN74LVC165A',
        'pins': {'1': '/CLR', '2': 'CLK', '3': 'A', '4': 'B', '5': 'C',
                 '6': 'D', '7': 'ENP', '8': 'GND', '9': '/LOAD', '10': 'ENT',
                 '11': 'QD', '12': 'QC', '13': 'QB', '14': 'QA', '15': 'RCO',
                 '16': 'VCC'},
        'power': {'VCC': '16', 'GND': '8'},
        'datasheet': 'https://www.ti.com/lit/ds/symlink/sn74lv161a.pdf'},
    'SN74LVC2G126': {
        'sim': 'ic_2g126', 'package': 'SM8',
        'footprint': 'Package_SO:SSOP-8_2.95x2.8mm_P0.65mm',
        'pins': {'1': '1OE(hi)', '2': '1A', '3': '2Y', '4': 'GND',
                 '5': '2A', '6': '1Y', '7': '2OE(hi)', '8': 'VCC'},
        'power': {'VCC': '8', 'GND': '4'},
        'datasheet': 'https://www.ti.com/lit/ds/symlink/sn74lvc2g126.pdf'},
    'SN74LVC2G125': {
        'sim': 'ic_2g125', 'package': 'SM8',
        'footprint': 'Package_SO:SSOP-8_2.95x2.8mm_P0.65mm',
        'pins': {'1': '1OE(lo)', '2': '1A', '3': '2Y', '4': 'GND',
                 '5': '2A', '6': '1Y', '7': '2OE(lo)', '8': 'VCC'},
        'power': {'VCC': '8', 'GND': '4'},
        'datasheet': 'https://www.ti.com/lit/ds/symlink/sn74lvc2g125.pdf'},
    'SN74LVC2G08': {
        'sim': 'ic_2g08', 'package': 'SM8',
        'footprint': 'Package_SO:SSOP-8_2.95x2.8mm_P0.65mm',
        'pins': {'1': '1A', '2': '1B', '3': '2Y', '4': 'GND',
                 '5': '2A', '6': '2B', '7': '1Y', '8': 'VCC'},
        'power': {'VCC': '8', 'GND': '4'},
        'datasheet': 'https://www.ti.com/lit/ds/symlink/sn74lvc2g08.pdf'},
    'SN74LVC2G32': {
        'sim': 'ic_2g32', 'package': 'SM8',
        'footprint': 'Package_SO:SSOP-8_2.95x2.8mm_P0.65mm',
        'pins': {'1': '1A', '2': '1B', '3': '2Y', '4': 'GND',
                 '5': '2A', '6': '2B', '7': '1Y', '8': 'VCC'},
        'power': {'VCC': '8', 'GND': '4'},
        'datasheet': 'https://www.ti.com/lit/ds/symlink/sn74lvc2g32.pdf'},
    'SN74LVC2G74': {
        'sim': 'ic_2g74', 'package': 'SM8',
        'footprint': 'Package_SO:SSOP-8_2.95x2.8mm_P0.65mm',
        'pins': {'1': 'CLK', '2': 'D', '3': '/Q', '4': 'GND',
                 '5': 'Q', '6': '/CLR', '7': '/PRE', '8': 'VCC'},
        'power': {'VCC': '8', 'GND': '4'},
        'datasheet': 'https://www.ti.com/lit/ds/symlink/sn74lvc2g74.pdf'},
    'SN74LVC1G04': {
        'sim': 'ic_1g04', 'package': 'SOT-23-5',
        'footprint': 'Package_TO_SOT_SMD:SOT-23-5',
        'pins': {'1': 'NC', '2': 'A', '3': 'GND', '4': 'Y', '5': 'VCC'},
        'power': {'VCC': '5', 'GND': '3'},
        'datasheet': 'https://www.ti.com/lit/ds/symlink/sn74lvc1g04.pdf'},
    'SN74LVC2G241': {
        'sim': 'ic_2g241', 'package': 'SM8',
        'footprint': 'Package_SO:SSOP-8_2.95x2.8mm_P0.65mm',
        'pins': {'1': '1OE(lo)', '2': '1A', '3': '2Y', '4': 'GND',
                 '5': '2A', '6': '1Y', '7': '2OE(hi)', '8': 'VCC'},
        'power': {'VCC': '8', 'GND': '4'},
        'datasheet': 'https://www.ti.com/lit/ds/symlink/sn74lvc2g241.pdf'},
    'ATF22LV10C-10': {
        'sim': 'ic_gal22v10', 'package': 'TSSOP-24',
        'footprint': 'Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm',
        'pins': {},   # filled from the JEDEC model at sim time
        'power': {'VCC': '24', 'GND': '12'},
        'datasheet': 'https://ww1.microchip.com/downloads/en/DeviceDoc/doc0780.pdf'},
    'R': {'sim': 'resistor', 'package': '0603',
          'footprint': 'Resistor_SMD:R_0603_1608Metric',
          'pins': {'1': '1', '2': '2'}, 'power': {}},
    'C': {'sim': 'cap', 'package': '0603',
          'footprint': 'Capacitor_SMD:C_0603_1608Metric',
          'pins': {'1': '1', '2': '2'}, 'power': {}},
    'CP': {'sim': 'cap', 'package': '1206',
           'footprint': 'Capacitor_SMD:C_1206_3216Metric',
           'pins': {'1': '1', '2': '2'}, 'power': {}},
    'SW': {'sim': 'switch', 'package': 'Kailh-hotswap',
           'footprint': 'Switch_Keyboard_Hotswap_Kailh:SW_Hotswap_Kailh_MX_1.00u',
           'pins': {'1': '1', '2': '2'}, 'power': {}},
    'PAD': {'sim': 'pad', 'package': 'chassis-pad',
            'footprint': 'Connector_Generic:Conn_01x01',
            'pins': {'1': '1'}, 'power': {}},
}

# interface pads: connector-next aggregate 19-contact budget (out/budget.py:
# B_clk/B_data merged across bottom+right legs, L_latch merged across left+top
# legs (rev-A merging); 3 dedicated detect-GND pads; DET straps REMOVED).
# Pad coordinates come from connector-next/out/study.json at board time.
EDGES = {
    'SIG': [('VCC', 'SIG1'), ('T_clk', 'SIG2'), ('T_data', 'SIG3'),
            ('T_endcol', 'SIG4'), ('T_W', 'SIG5'), ('B_clk', 'SIG6'),
            ('B_data', 'SIG7'), ('B_first', 'SIG8'), ('B_latch', 'SIG9'),
            ('B_W', 'SIG10'), ('L_clk', 'SIG11'), ('L_data', 'SIG12'),
            ('L_endrow', 'SIG13'), ('L_latch', 'SIG14'), ('R_latch', 'SIG15')],
    'GND_lane': [('GND', 'GND1'), ('GND_DET_T', 'GND2'), ('GND_DET_B', 'GND3'),
                 ('GND_DET_R', 'GND4')],
}


class Builder:
    def __init__(self, cid, title, source):
        self.c = {'schema': 1, 'circuit': cid, 'title': title, 'source': source,
                  'devices': {}, 'components': [], 'nets': {}, 'interface': {},
                  'checks': {}}
        self._n = {}

    def add(self, ref, device, value='', footprint=None, notes=''):
        dev = DEVICES[device]
        self.c['devices'][device] = dev
        fp = footprint or dev['footprint']
        self.c['components'].append({'ref': ref, 'device': device,
                                     'value': value or device,
                                     'footprint': fp, 'notes': notes})
        return ref

    def net(self, name, *pins):
        for p in pins:
            self._n.setdefault(name, []).append([p[0], str(p[1])])

    def connect(self, name, ref, pin):
        self._n.setdefault(name, []).append([ref, str(pin)])

    def finish(self):
        # consume the per-device 'power' pin tables (G1): bind each declared
        # power pin to its rail net; a pin already on the SAME rail is fine
        # (author made it explicit), a pin on a DIFFERENT net is fatal.
        refs = {c['ref']: c for c in self.c['components']}
        seen = {tuple(p) for pins in self._n.values() for p in pins}
        for c in self.c['components']:
            dev = DEVICES[c['device']]
            for rail, pin in sorted(dev.get('power', {}).items()):
                key = (c['ref'], str(pin))
                if key in seen:
                    owner = next(n for n, pins in self._n.items()
                                 if [key[0], key[1]] in pins)
                    if owner != rail:
                        raise RuntimeError(
                            f'power pin {c["ref"]}.{pin} authored on net '
                            f'{owner}, device table says {rail}')
                    continue
                self._n.setdefault(rail, []).append([key[0], key[1]])
                seen.add(key)
        # materialise NC nets for IC pins that appear nowhere
        seen = {tuple(p) for pins in self._n.values() for p in pins}
        for c in self.c['components']:
            dev = DEVICES[c['device']]
            for pin in dev['pins']:
                if (c['ref'], pin) not in seen:
                    self._n[f"NC_{c['ref']}_{pin}"] = [[c['ref'], pin]]
        self.c['nets'] = {k: sorted(v) for k, v in sorted(self._n.items())}
        path = os.path.join(OUT, f"{self.c['circuit']}.json")
        with open(path, 'w') as f:
            json.dump(self.c, f, indent=1, sort_keys=True)
        print(f'{path}: {len(self.c["components"])} components, '
              f'{len(self.c["nets"])} nets')


def key_section(b, first_sw=1, r_series=100):
    """12 keys: SWk.1=VCC, SWk.2 -> 10k pd to GND + 100R to Kn net."""
    knet = {}
    for k in range(12):
        sw = f'SW{k + first_sw}'
        b.add(sw, 'SW', notes=f'key{k}')
        b.net('VCC', (sw, 1))
        b.add(f'RK{k}', 'R', '10k', notes=f'key{k} pull-down')
        b.net('GND', (f'RK{k}', 2))
        b.connect(f'SWN{k}', f'RK{k}', 1)
        b.connect(f'SWN{k}', sw, 2)
        b.add(f'RS{k}', 'R', '100', notes=f'key{k} series')
        b.connect(f'SWN{k}', f'RS{k}', 1)
        b.connect(f'KEY{k}', f'RS{k}', 2)
        knet[k] = f'KEY{k}'
    return knet


def pull(b, tag, net, rail, notes=''):
    b.add(f'RP{tag}', 'R', '10k', notes=notes or f'{net} pull')
    b.connect(net, f'RP{tag}', 1)
    b.net(rail, (f'RP{tag}', 2))


def series33(b, tag, drv, out):
    b.add(f'RO{tag}', 'R', '33', notes=f'{out} series')
    b.connect(drv, f'RO{tag}', 1)
    b.connect(out, f'RO{tag}', 2)


def decouple(b, tag, note='decoupling'):
    b.add(f'C{tag}', 'C', '100n', notes=note)
    b.net('VCC', (f'C{tag}', 1))
    b.net('GND', (f'C{tag}', 2))


def pads(b):
    """Chassis contact pads: one 1-pin PAD per aggregate contact.
    The 3 dedicated detect-GND pads are tile-side GND copper (their only
    difference is which backplane stub they touch), exactly as budget.py's
    tile-side union states."""
    for edge, rows in EDGES.items():
        for sig, jp in rows:
            ref = f'JP_{sig}'
            b.add(ref, 'PAD', notes=f'{edge} {sig}')
            b.connect('GND' if sig.startswith('GND_DET') else sig, ref, 1)


def edge_interface(b):
    return {
        'signals': {s: s for s in
                    ('T_clk', 'T_data', 'T_endcol', 'T_W', 'L_clk',
                     'L_data', 'L_endrow', 'L_latch', 'B_clk', 'B_data',
                     'B_first', 'B_latch', 'B_W', 'R_latch',
                     'VCC', 'GND', 'GND_DET_T', 'GND_DET_B', 'GND_DET_R')},
        'keys': {f'key{k}': f'KEY{k}' for k in range(12)},
        'edges': {e: [{'signal': sig, 'pad': f'JP_{sig}'} for sig, j in rows]
                  for e, rows in EDGES.items()}}


def common_passives(b):
    pull(b, 'LDA', 'L_data', 'GND')
    pull(b, 'LER', 'L_endrow', 'VCC')
    pull(b, 'BFI', 'B_first', 'VCC')
    pull(b, 'TW', 'T_W', 'VCC')
    pull(b, 'TEC', 'T_endcol', 'VCC')
    pull(b, 'RLA', 'R_latch', 'GND')
    pull(b, 'BLA', 'B_latch', 'GND')
    pull(b, 'TDA', 'T_data', 'GND')
    pull(b, 'BCK', 'B_clk', 'VCC')
    series33(b, 'LCK', 'L_clk_drv', 'L_clk')
    series33(b, 'TCK', 'T_clk_drv', 'T_clk')
    series33(b, 'LLA', 'latch_drv', 'L_latch')
    series33(b, 'BDA', 'data_drv', 'B_data')
    series33(b, 'BW', 'B_W_drv', 'B_W')
    b.add('CB1', 'CP', '4u7', notes='bulk decoupling')
    b.net('VCC', ('CB1', 1))
    b.net('GND', ('CB1', 2))


def shift_pair(b, first, second, ds_net):
    """U_a (first in chain, external DS) -> U_b (feeds data_drv)."""
    for u, inh in ((first, True), (second, False)):
        b.add(u, 'SN74LVC165A', notes='shift-chain ' +
              ('stage 1 (upper frame bits)' if inh else 'stage 0 (output stage)'))
        b.net('VCC', (u, 16))
        b.net('GND', (u, 8))
        b.net('GND', (u, 15))          # CLK INH tied low
        b.net('B_clk', (u, 2))
        b.net('nRST', (u, 1))
    b.connect(ds_net, first, 10)
    b.connect('CHAIN', first, 9)
    b.connect('CHAIN', second, 10)
    b.connect('data_drv', second, 9)


def keymap_on(b, knet, upper, lower):
    """upper = stage feeding chain (keys 8..11 + markers + flags),
    lower = output stage (keys 0..7).  TI letter<pin>: H,G,F,E=6,5,4,3;
    D,C,B,A=14,13,12,11."""
    pins = ['6', '5', '4', '3', '14', '13', '12', '11']
    for k in range(8):
        b.connect(knet[k], lower, pins[k])          # key0..7 -> D7..D0
    for k in range(8, 12):
        b.connect(knet[k], upper, pins[k - 8])      # key8..11 -> D7..D4
    b.net('VCC', (upper, 14), (upper, 13))          # markers D3,D2
    b.connect('L_endrow', upper, 12)                # D1
    b.connect('T_endcol', upper, 11)                # D0


def variant_a():
    b = Builder('variant_a',
                'variant A: all-LVC glue + SN74LV161A + 2x SN74LVC165A',
                'hand-authored from reva_reference.json connectivity '
                '(which itself is a kicad-cli export of hardware/kicad/tile); '
                'every device pinout verified against TI datasheets listed '
                'in devices[].datasheet')
    pads(b)
    common_passives(b)
    knet = key_section(b)
    shift_pair(b, 'UA3', 'UA4', 'DS_net')
    keymap_on(b, knet, upper='UA3', lower='UA4')
    decouple(b, 'A1'); decouple(b, 'A2'); decouple(b, 'A3')
    decouple(b, 'A4'); decouple(b, 'A5'); decouple(b, 'A6')
    decouple(b, 'A7'); decouple(b, 'A8'); decouple(b, 'A9')

    # UA1 2G126 (L side, active-high OE): 1A=B_clk -> 1Y=L_clk_drv;
    # 2A=L_data -> 2Y=DS shared node
    b.add('UA1', 'SN74LVC2G126')
    b.net('W', ('UA1', 1), ('UA1', 7), ('UA7', 1), ('UA7', 7))
    b.net('B_clk', ('UA1', 2))
    b.net('L_clk_drv', ('UA1', 6))
    b.net('L_data', ('UA1', 5))
    b.net('DS_net', ('UA1', 3))
    # UA7 2G125 (T side, active-low OE)
    b.add('UA7', 'SN74LVC2G125')
    b.net('B_clk', ('UA7', 2))
    b.net('T_clk_drv', ('UA7', 6))
    b.net('T_data', ('UA7', 5))
    b.net('DS_net', ('UA7', 3))
    # UA2 2G08: 2A=T_W,2B=B_first -> 2Y=W ; 1A=data_drv,1B=Tc -> 1Y=flag_and
    b.add('UA2', 'SN74LVC2G08')
    b.net('T_W', ('UA2', 5))
    b.net('B_first', ('UA2', 6))
    b.net('W', ('UA2', 3))
    b.net('data_drv', ('UA2', 1))
    b.net('Tc', ('UA2', 2))
    b.net('flag_and', ('UA2', 7))
    # UA6 2G32: 1A=B_latch,1B=R_latch -> 1Y=latch_drv ; 2A=B_W_drv,2B=flag_and -> 2Y=flag_d
    b.add('UA6', 'SN74LVC2G32')
    b.net('B_latch', ('UA6', 1))
    b.net('R_latch', ('UA6', 2))
    b.net('latch_drv', ('UA6', 7))
    b.net('B_W_drv', ('UA6', 5))
    b.net('flag_and', ('UA6', 6))
    b.net('flag_d', ('UA6', 3))
    # UA5 1G04: latch_drv -> nRST
    b.add('UA5', 'SN74LVC1G04')
    b.net('latch_drv', ('UA5', 2))
    b.net('nRST', ('UA5', 4))
    # UA8 2G74: B_W flag
    b.add('UA8', 'SN74LVC2G74')
    b.net('B_clk', ('UA8', 1))
    b.net('flag_d', ('UA8', 2))
    b.net('B_W_drv', ('UA8', 5))
    b.net('nRST', ('UA8', 6))
    b.net('VCC', ('UA8', 7))
    # UA9 LV161A counter
    b.add('UA9', 'SN74LV161A')
    b.net('nRST', ('UA9', 1))
    b.net('B_clk', ('UA9', 2))
    b.net('GND', ('UA9', 3), ('UA9', 4), ('UA9', 5), ('UA9', 6))
    b.net('nRST', ('UA9', 7), ('UA9', 10))
    b.net('VCC', ('UA9', 9))
    b.net('Tc', ('UA9', 15))
    b.c['interface'] = edge_interface(b)
    b.c['checks'] = {
        'frame': {'order': ['UA4:H..A (keys0..7)', 'UA3:H..E (keys8..11)',
                            'UA3:D,C markers', 'UA3:B=L_endrow', 'UA3:A=T_endcol']},
        'equivalent_to': 'reva_reference'}
    b.finish()


def variant_a2():
    """Count-NEUTRAL documented swap candidate from fewer_ics.md:
    2G125+2G126 -> 2x SN74LVC2G241 (one active-lo + one active-hi OE per
    package, same SM8 pinout).  Pin nets identical to variant A's U1/U7
    halves.  Proof catalogue: tools/sim_tile.py full suite must pass
    unchanged - if it does, pin-level behaviour is provably identical
    (zero-delay functional level)."""
    b = Builder('variant_a2',
                'variant A2: variant A with 2x SN74LVC2G241 instead of '
                '2G125+2G126 (count-neutral, see results/fewer_ics.md)',
                'same as variant_a; buffer pair consolidation only')
    pads(b)
    common_passives(b)
    knet = key_section(b)
    shift_pair(b, 'UA3', 'UA4', 'DS_net')
    keymap_on(b, knet, upper='UA3', lower='UA4')
    for tag in ('A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9'):
        decouple(b, tag)
    # V1 clock pair: sec1 (lo OE) = T side, sec2 (hi OE) = L side
    b.add('UV1', 'SN74LVC2G241')
    b.net('W', ('UV1', 1), ('UV1', 7), ('UV2', 1), ('UV2', 7))
    b.net('B_clk', ('UV1', 2), ('UV1', 5))
    b.net('T_clk_drv', ('UV1', 6))
    b.net('L_clk_drv', ('UV1', 3))
    # V2 data pair
    b.add('UV2', 'SN74LVC2G241')
    b.net('T_data', ('UV2', 2))
    b.net('L_data', ('UV2', 5))
    b.net('DS_net', ('UV2', 6), ('UV2', 3))
    # rest identical to variant A
    b.add('UA2', 'SN74LVC2G08')
    b.net('T_W', ('UA2', 5))
    b.net('B_first', ('UA2', 6))
    b.net('W', ('UA2', 3))
    b.net('data_drv', ('UA2', 1))
    b.net('Tc', ('UA2', 2))
    b.net('flag_and', ('UA2', 7))
    b.add('UA6', 'SN74LVC2G32')
    b.net('B_latch', ('UA6', 1))
    b.net('R_latch', ('UA6', 2))
    b.net('latch_drv', ('UA6', 7))
    b.net('B_W_drv', ('UA6', 5))
    b.net('flag_and', ('UA6', 6))
    b.net('flag_d', ('UA6', 3))
    b.add('UA5', 'SN74LVC1G04')
    b.net('latch_drv', ('UA5', 2))
    b.net('nRST', ('UA5', 4))
    b.add('UA8', 'SN74LVC2G74')
    b.net('B_clk', ('UA8', 1))
    b.net('flag_d', ('UA8', 2))
    b.net('B_W_drv', ('UA8', 5))
    b.net('nRST', ('UA8', 6))
    b.net('VCC', ('UA8', 7))
    b.add('UA9', 'SN74LV161A')
    b.net('nRST', ('UA9', 1))
    b.net('B_clk', ('UA9', 2))
    b.net('GND', ('UA9', 3), ('UA9', 4), ('UA9', 5), ('UA9', 6))
    b.net('nRST', ('UA9', 7), ('UA9', 10))
    b.net('VCC', ('UA9', 9))
    b.net('Tc', ('UA9', 15))
    b.c['interface'] = edge_interface(b)
    b.c['checks'] = {'equivalent_to': 'variant_a'}
    b.finish()


def variant_b2():
    b = Builder('variant_b2',
                'variant B2: ATF22LV10C-10 (truez) + 2x SN74LVC165A + SN74LVC1G04',
                'hand-authored: GAL behaviour taken from the DECODED fuse map '
                '(results/truez_from_jed.json, proven == source equations); '
                'same passive plan as variant A')
    pads(b)
    common_passives(b)
    knet = key_section(b)
    shift_pair(b, 'UB2', 'UB3', 'DS_net')
    keymap_on(b, knet, upper='UB2', lower='UB3')
    for tag in ('B1', 'B2', 'B3', 'B4'):
        decouple(b, tag)

    # UB1 ATF22LV10C-10, pins per logic/pld/results/tile_glue_truez.pin
    b.add('UB1', 'ATF22LV10C-10',
          notes='true-Z T_clk design; Q0..Q3,HX pins are Hi-Z on silicon '
                '(blown OE fuses, see results/galcheck_truez.txt) -> leave open')
    b.net('B_clk', ('UB1', 1))
    b.net('B_latch', ('UB1', 2))
    b.net('R_latch', ('UB1', 3))
    b.net('T_W', ('UB1', 4))
    b.net('B_first', ('UB1', 5))
    b.net('T_data', ('UB1', 6))
    b.net('L_data', ('UB1', 7))
    b.net('data_drv', ('UB1', 8))        # BDATA input = tile's own serial out
    b.net('GND', ('UB1', 12))
    b.net('T_clk_drv', ('UB1', 19))
    b.net('L_clk_drv', ('UB1', 20))
    b.net('latch_drv', ('UB1', 21))
    b.net('DS_net', ('UB1', 23))
    b.net('B_W_drv', ('UB1', 18))
    b.net('VCC', ('UB1', 24))
    # Q0..Q3 (14..17) and HX (22) intentionally unconnected; NC pins 9,10,11,13
    # UB4 1G04: latch_drv -> nRST for the two 165s
    b.add('UB4', 'SN74LVC1G04')
    b.net('latch_drv', ('UB4', 2))
    b.net('nRST', ('UB4', 4))
    b.c['interface'] = edge_interface(b)
    b.c['checks'] = {
        'frame': {'order': ['UB3:H..A (keys0..7)', 'UB2:H..E (keys8..11)',
                            'UB2:D,C markers', 'UB2:B=L_endrow', 'UB2:A=T_endcol']},
        'gal_jedec_model': 'results/truez_from_jed.json'}
    b.finish()


if __name__ == '__main__':
    variant_a()
    variant_a2()
    variant_b2()
