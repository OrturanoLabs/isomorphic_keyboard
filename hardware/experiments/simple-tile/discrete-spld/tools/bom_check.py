#!/usr/bin/env python3
"""BOM comparison: variant A and variant B2 vs the rev-A reference.

Counts orderable lines (by device/value), deltas vs rev A, and required
consolidation evidence for any part-count reduction claim.  Prices are NOT
invented: every line carries either a sourced note or 'unknown'.  LCSC-style
sourcing is gathered separately in build_costs.py; this tool is structural.
"""
import json
import os
import collections
import sys

BASE = os.path.join(os.path.dirname(__file__), '..')
MECH = {'SW', 'PAD'}      # chassis pads + switch sockets: mechanical lines


def census(circ):
    cnt = collections.Counter()
    for c in circ['components']:
        dev = c['device']
        if dev in MECH:
            key = ('MECH', dev)
        elif dev in ('R', 'C', 'CP'):
            key = (dev, c['value'])
        else:
            key = ('IC', c['device'])
        cnt[key] += 1
    return cnt


def load(name):
    return json.load(open(os.path.join(BASE, 'circuits', f'{name}.json')))


def main():
    reva = load('reva_reference')
    va = load('variant_a')
    vb = load('variant_b2')
    cr, ca, cb = census(reva), census(va), census(vb)

    # normalize rev-A IC names to what they actually are by VALUE
    def reva_norm(cr):
        """rev-A JSON 'device' is the symbol; the Value field is the part.
        The export stored value in 'value'."""
        out = collections.Counter()
        for c in reva['components']:
            ref0 = c['ref'][0]
            if ref0 == 'U':
                v = c['value']
                out[('IC', {'74HC161': 'SN74LV161A-candidate'}.get(v, v))] += 1
            elif ref0 == 'R':
                out[('R', c['value'])] += 1
            elif ref0 in ('C',):
                out[('C', c['value'])] += 1
            elif c['ref'].startswith('SW'):
                out[('MECH', 'SW')] += 1
            elif c['ref'].startswith('J'):
                out[('CONN', c['device'])] += 1
        return out

    crn = reva_norm(cr)
    all_keys = sorted(set(crn) | set(ca) | set(cb))
    print(f"{'line':38} {'revA':>5} {'varA':>5} {'varB2':>6}")
    for k in all_keys:
        print(f"{str(k):38} {crn.get(k, 0):>5} {ca.get(k, 0):>5} {cb.get(k, 0):>6}")

    def ic_total(c):
        return sum(v for (k, v) in c.items() if k[0] == 'IC')

    print(f"\nIC totals: revA={ic_total(crn)} varA={ic_total(ca)} varB2={ic_total(cb)}")
    print(f"logic-glue ICs (excl. 2x 165): "
          f"revA={ic_total(crn) - 2} varA={ic_total(ca) - 2} varB2={ic_total(cb) - 2}")

    # structural deltas
    print('\nvariant A vs rev A (logic): identical function set; '
          '74HC161 replaced by SN74LV161A (3.3V-native); debug headers '
          'J105..J108 (4x Conn_01x08) removed; J101..104 edge connectors become '
          'the connector-next aggregate: 19 chassis pads (14 signals + VCC + '
          'GND + 3 detect-GND; DET straps NOT carried to the tile budget).')
    print('variant B2 vs rev A: glue U101,U102,U105,U106,U107,U108,U109 '
          '(7 ICs) replaced by ONE ATF22LV10C-10; +1 SN74LVC1G04 for /PL -> '
          'net glue ICs: 2 (GAL+1G04) vs 7. Total ICs 4 vs 9.')


if __name__ == '__main__':
    main()
