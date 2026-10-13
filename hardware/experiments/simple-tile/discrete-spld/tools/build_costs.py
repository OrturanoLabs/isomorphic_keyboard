#!/usr/bin/env python3
"""Costs table for the discrete-spld variants.

Price provenance policy (task rule): 'actual sources or unknown'.  Every
orderable part number below is confirmed against its manufacturer datasheet
(existence, package) - the datasheet URLs are in circuits/*.json.  Actual
UP-TO-DATE PRICING could not be verified from this host on 2026-10-12:
digikey.com (Cloudflare challenge), mouser.com (captcha), lcsc.com
(soft-blocked shell), newark.com and microchipdirect.com (fetch errors).
All price cells are therefore 'unknown' - never invented numbers.
"""
import json
import os

BASE = os.path.join(os.path.dirname(__file__), '..')

# orderable MPNs (package codes per datasheet); qtity per tile
LINES = [
    # (device in circuits JSON, orderable MPN, package, qty A, qty A2, qty B2)
    ('SN74LVC165A', 'SN74LVC165APW (TI)', 'TSSOP-16', 2, 2, 2),
    ('SN74LV161A', 'SN74LV161APW (TI)', 'TSSOP-16', 1, 1, 0),
    ('SN74LVC2G126', 'SN74LVC2G126DCTR (TI)', 'SM8', 1, 0, 0),
    ('SN74LVC2G125', 'SN74LVC2G125DCTR (TI)', 'SM8', 1, 0, 0),
    ('SN74LVC2G08', 'SN74LVC2G08DCTR (TI)', 'SM8', 1, 1, 0),
    ('SN74LVC2G32', 'SN74LVC2G32DCTR (TI)', 'SM8', 1, 1, 0),
    ('SN74LVC2G74', 'SN74LVC2G74DCTR (TI)', 'SM8', 1, 1, 0),
    ('SN74LVC2G241', 'SN74LVC2G241DCTR (TI)', 'SM8', 0, 2, 0),
    ('SN74LVC1G04', 'SN74LVC1G04DBVR (TI)', 'SOT-23-5', 1, 1, 1),
    ('ATF22LV10C-10', 'ATF22LV10C-10XU (Microchip)', 'TSSOP-24', 0, 0, 1),
    ('R_10k', 'RC0603FR-0710KL (Yageo) or equiv.', '0603', 21, 21, 21),
    ('R_100', 'RC0603FR-07100RL or equiv.', '0603', 12, 12, 12),
    ('R_33', 'RC0603FR-0733RL or equiv.', '0603', 7, 7, 7),
    ('C_100n', 'CC0603KRX7R9BB104 or equiv.', '0603', 9, 9, 4),
    ('C_4u7', 'CL31A475KAHNNNE or equiv.', '1206', 1, 1, 1),
    ('SW', 'Kailh CPG151101S11 (MX hotswap socket)', '-', 12, 12, 12),
]


def main():
    rows = []
    for dev, mpn, pkg, qa, qa2, qb in LINES:
        rows.append({'device': dev, 'mpn': mpn, 'package': pkg,
                     'qty_variant_a': qa, 'qty_variant_a2': qa2,
                     'qty_variant_b2': qb,
                     'unit_price_usd': 'unknown',
                     'price_evidence': 'distributor fetches blocked from this '
                                       'host 2026-10-12 (digikey Cloudflare, '
                                       'mouser captcha, lcsc soft-block, '
                                       'newark/microchipdirect fetch errors)'})
    out = {'date': '2026-10-12', 'board': '2-layer tile, TMM per BOM',
           'lines': rows,
           'totals_ics': {'variant_a': 9, 'variant_a2': 9, 'variant_b2': 4},
           'note': 'chassis springs/pogo hardware is costed by the connectors '
                   'study, not here; programming fixture for ATF22LV10C: see '
                   'results/programmer_gap.md'}
    dst = os.path.join(BASE, 'results', 'costs.json')
    with open(dst, 'w') as f:
        json.dump(out, f, indent=1)
    # markdown view
    md = ['# Costs (per tile)', '',
          '| device | orderable MPN | package | qty A | qty A2 | qty B2 | unit price |',
          '|---|---|---|---|---|---|---|']
    for r in rows:
        md.append(f"| {r['device']} | {r['mpn']} | {r['package']} | "
                  f"{r['qty_variant_a']} | {r['qty_variant_a2']} | "
                  f"{r['qty_variant_b2']} | unknown |")
    md += ['',
           'Prices could not be verified from this host (see results/costs.json '
           'evidence field); all MPNs/package codes are confirmed against the '
           'manufacturer datasheets listed in circuits/*.json.']
    with open(os.path.join(BASE, 'results', 'costs.md'), 'w') as f:
        f.write('\n'.join(md) + '\n')
    print('wrote results/costs.{json,md}')


if __name__ == '__main__':
    main()
