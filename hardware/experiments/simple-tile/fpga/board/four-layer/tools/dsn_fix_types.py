#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""dsn_fix_types.py -- router-input repair for the 4L variant DSN.

Pure-python text tool (no pcbnew). Two measured-freerouting-trap repairs:

  T4: strip `(plane NET (polygon ...))` blocks. freerouting treats DSN
      plane declarations as 'exclude net from routing' (GND's 20 items were
      silently absorbed in the prep arm, making counts incomparable; zero
      plane geometry was emitted). Our planes are REAL pcbnew zones filled
      after import; the router must see all 45 nets / all route items.
  T11: flip the variant's pcbnew pre-placed fanout (stub wires + attach
      vias, coordinates from out/fanout_sites.json) from `(type route)` to
      `(type fix)`, so the router cannot rip them. The exporter emits every
      existing wire as `(type route)`; the PCB shapes stay collision-checked
      real fanout -- only the router-side protection flag is upgraded.

Frame (dsn_attach_probe trap T12): DSN = pcb mm * 1000 (x, -y).

Usage: dsn_fix_types.py IN.dsn SITES.json OUT.dsn REPORT.json
"""
import json
import re
import sys

FRAME = 1000.0  # pcb mm -> DSN units; y negated


def parse_num(s):
    return float(s)


def main():
    src, sites_p, dst, rep_p = sys.argv[1:5]
    text = open(src, encoding='utf-8').read()
    sites = json.load(open(sites_p, encoding='utf-8'))['sites']
    placed = [s for s in sites if s.get('placed', True) and s.get('via_mm')]

    # --- T4: strip plane blocks (single-level nesting in this grammar)
    stripped = 0

    def strip_plane(m):
        nonlocal stripped
        stripped += 1
        return '\n'
    text = re.sub(r'\n\s*\(plane\s+\S+\s+\([^()]*\)\)', strip_plane, text)

    lines = text.splitlines(keepends=True)
    via_targets = {(round(x * FRAME, 1), round(-y * FRAME, 1))
                   for x, y in (s['via_mm'] for s in placed)}
    matched_via, matched_wire = set(), set()
    out = []
    via_re = re.compile(
        r'^\s*\(\s*via\s+"[^"]*"\s+(-?[\d.]+)\s+(-?[\d.]+)\s*'
        r'\(net\s+[^)]*\)\s*\(type\s+route\)\)')
    wire_re = re.compile(
        r'^\s*\(\s*wire\s+\(path\s+(\S+)\s+(\d+)\s+'
        r'((?:-?[\d.]+\s*)+)\)\s*\(net\s+[^)]*\)\s*\(type\s+route\)\)')
    for ln in lines:
        m = via_re.match(ln)
        if m:
            key = (round(float(m.group(1)), 1), round(float(m.group(2)), 1))
            hit = min(via_targets, key=lambda t: (t[0]-key[0])**2 +
                       (t[1]-key[1])**2, default=None)
            if hit is not None and (hit[0]-key[0])**2 + \
                    (hit[1]-key[1])**2 <= 4.0:  # 0.002 mm^2 tol
                ln = ln.replace('(type route))', '(type fix))')
                matched_via.add(hit)
        m = wire_re.match(ln)
        if m:
            nums = [float(t) for t in m.group(3).split()]
            pts = list(zip(nums[::2], nums[1::2]))
            key = (round(pts[-1][0], 1), round(pts[-1][1], 1))
            hit = min(via_targets, key=lambda t: (t[0]-key[0])**2 +
                       (t[1]-key[1])**2, default=None)
            if hit is not None and (hit[0]-key[0])**2 + \
                    (hit[1]-key[1])**2 <= 4.0:
                ln = ln.replace('(type route))', '(type fix))')
                matched_wire.add(hit)
        out.append(ln)
    open(dst, 'w', encoding='utf-8').write(''.join(out))

    layers = re.findall(r'\(layer\s+(\S+)\s+\(type\s+', text)
    nets = len(re.findall(r'\(net\s+\S+\s+\(', text))  # network section
    report = {
        'planes_stripped': stripped,
        'layers': layers,
        'fix_vias_matched': len(matched_via),
        'fix_wires_matched': len(matched_wire),
        'fanout_via_sites_expected': len(via_targets),
        'unmatched_sites': sorted(
            {'%.1f/%.1f' % t for t in via_targets - matched_via}),
        'type_fix_total': len(re.findall(r'\(type fix\)', ''.join(out))),
        'type_route_remaining': len(re.findall(r'\(type route\)',
                                               ''.join(out))),
        'plane_blocks_remaining': len(re.findall(r'\(plane\s', ''.join(out))),
    }
    report['ok'] = (stripped >= 1 and report['plane_blocks_remaining'] == 0
                    and len(matched_via) == len(via_targets)
                    and len(matched_wire) == len(via_targets))
    json.dump(report, open(rep_p, 'w', encoding='utf-8'), indent=1)
    print('DSN_FIX_TYPES_OK' if report['ok'] else 'DSN_FIX_TYPES_FAIL',
          json.dumps({k: v for k, v in report.items()
                      if not isinstance(v, list)}))
    if not report['ok']:
        sys.exit(1)


if __name__ == '__main__':
    main()
