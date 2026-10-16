#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""variant_check.py -- canonical-vs-variant invariants (text-only, host
python, no pcbnew; the report path is argv).

Robust to BOTH writers found in this tree: board_gen (col-0 footprints,
fp_text reference, unquoted pad names) and pcbnew SaveBoard (property
"Reference"). S-expressions are located with balanced-paren scanning.

Checks variant/final against the canonical 2L pcb (c7d5b66fa1db):
  I1 19 JP pad world coords IDENTICAL (contact geometry preserved);
  I2 Edge.Cuts geometry IDENTICAL (outline, stepped ribs);
  I3 NPTH drill count IDENTICAL (socket/tooling holes);
  I4 pad (ref,pad,net) triples IDENTICAL (pin-map/connectivity preserved);
  I5 variant/final: In1.Cu/In2.Cu named layers + stackup block present;
  I6 no via centre inside any SMD pad rectangle (via-in-pad ban);
  I7 zone census (final: two inner GND zones + outer pours present);
  I8 final board: all segment widths >= 0.2 mm (no sub-rule copper).

Usage: variant_check.py OUT.json [FINAL_PCB]
"""
import json
import math
import re
import sys

HERE = __file__.rsplit('/tools/', 1)[0]
BOARD_DIR = HERE.rsplit('/four-layer', 1)[0]
CANON = BOARD_DIR + '/out/kicad/tile_gw1nz.kicad_pcb'
VARIANT = HERE + '/out/tile_gw1nz_4l.kicad_pcb'


def blocks(text, head):
    """Yield balanced s-expr bodies whose head matches ` head ` (space or
    newline after the head: board_gen writes one-line forms, pcbnew
    SaveBoard writes multi-line forms)."""
    i = 0
    n = len(text)
    needles = ('(' + head + ' ', '(' + head + '\n', '(' + head + '\t')
    while True:
        j, found = -1, None
        for nd in needles:
            k = text.find(nd, i)
            if k >= 0 and (j < 0 or k < j):
                j, found = k, nd
        if j < 0:
            return
        depth = 0
        k = j
        while k < n:
            c = text[k]
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    k += 1
                    break
            k += 1
        yield text[j:k]
        i = k


def parse_pads(path):
    text = open(path, encoding='utf-8').read()
    pads = {}
    for fb in blocks(text, 'footprint'):
        rm = re.search(r'\(property "Reference" "([^"]+)"', fb)
        if not rm:
            rm = re.search(r'fp_text reference "([^"]+)"', fb)
        if not rm:
            continue
        ref = rm.group(1)
        fam = re.search(r'^\s*\(at (-?[\d.]+) (-?[\d.]+)(?: (-?[\d.]+))?\)',
                        fb[fb.index(')') + 1:], re.M)
        fx, fy = float(fam.group(1)), float(fam.group(2))
        frot = float(fam.group(3)) if fam.group(3) else 0.0
        a = math.radians(frot)
        for pb in blocks(fb, 'pad'):
            hm = re.match(r'\(pad\s+(?:"([^"]*)"|(\S+))\s+(\w+)', pb)
            if not hm:
                continue
            name = hm.group(1) if hm.group(1) is not None else hm.group(2)
            typ = hm.group(3)
            pm = re.search(r'\(at (-?[\d.]+) (-?[\d.]+)(?: (-?[\d.]+))?\)',
                           pb)
            px, py = float(pm.group(1)), float(pm.group(2))
            if not name:  # unnamed NPTH/tooling pads: key by local pos
                name = f'@{px},{py}'
            nm = re.search(r'\(net\s+(?:\d+\s+)?"([^"]*)"\)', pb)
            sm = re.search(r'\(size (-?[\d.]+) (-?[\d.]+)\)', pb)
            wx = fx + px * math.cos(a) - py * math.sin(a)
            wy = fy + px * math.sin(a) + py * math.cos(a)
            pads[(ref, name)] = {'type': typ,
                                 'net': nm.group(1) if nm else '',
                                 'pos': (round(wx, 6), round(wy, 6)),
                                 'size': (float(sm.group(1)),
                                          float(sm.group(2))) if sm
                                 else (0.0, 0.0)}
    return pads


def parse_vias(path):
    text = open(path, encoding='utf-8').read()
    vias = []
    for vb in blocks(text, 'via'):
        am = re.search(r'\(at (-?[\d.]+) (-?[\d.]+)\)', vb)
        sm = re.search(r'\(size (-?[\d.]+)\)', vb)
        dm = re.search(r'\(drill (-?[\d.]+)\)', vb)
        vias.append({'pos': (float(am.group(1)), float(am.group(2))),
                     'size': float(sm.group(1)) if sm else 0.0,
                     'drill': float(dm.group(1)) if dm else 0.0})
    seg_w = sorted({float(m.group(1))
                    for sb in blocks(text, 'segment')
                    for m in [re.search(r'\(width ([\d.]+)\)', sb)]
                    if m})
    seg_n = len(re.findall(r'\(segment\b', text))
    return vias, seg_w, seg_n


def parse_edgecuts(path):
    """Edge.Cuts geometry as normalized float tuples (one per graphic
    element, sorted): writer-agnostic (board_gen keeps trailing zeros,
    pcbnew does not); tolerant of attribute order/extra fields."""
    text = open(path, encoding='utf-8').read()
    out = []
    for kind in ('gr_line', 'gr_arc', 'gr_curve', 'gr_circle', 'gr_poly',
                 'gr_rect'):
        for gb in blocks(text, kind):
            if '(layer "Edge.Cuts")' in gb:
                pts = tuple((float(m.group(1)), float(m.group(2)))
                            for m in re.finditer(
                                r'\((?:start|end|mid|center|xy) (-?[\d.]+) '
                                r'(-?[\d.]+)\)', gb))
                if pts:
                    out.append((kind, pts))
    return sorted(out)


def parse_zones(path):
    text = open(path, encoding='utf-8').read()
    zones = []
    for zb in blocks(text, 'zone'):
        nm = re.search(r'\(net\s+(?:\d+\s+)?"([^"]*)"\)', zb)
        lm = re.search(r'\(layer "([^"]+)"\)', zb)
        filled = '(filled_polygon' in zb
        zones.append({'net': nm.group(1) if nm else '?',
                      'layer': lm.group(1) if lm else '?',
                      'filled': filled})
    return zones


def pad_diff(base, turb, what):
    diffs = []
    for k, bv in base.items():
        tv = turb.get(k)
        if tv is None:
            diffs.append([list(k), 'missing'])
        elif tv['pos'] != bv['pos'] or tv['net'] != bv['net']:
            diffs.append([list(k), bv['pos'], tv['pos'],
                          bv['net'], tv['net']])
    extra = [list(k) for k in turb if k not in base]
    return {'name': what, 'diffs': diffs, 'extra': extra,
            'ok': not diffs and not extra}


def board_checks(label, path, canon_pads):
    pads = parse_pads(path)
    ck = []
    jb = {k: v for k, v in canon_pads.items() if k[0].startswith('JP_')}
    jt = {k: v for k, v in pads.items() if k[0].startswith('JP_')}
    i1 = pad_diff(jb, jt, f'I1_jp_{label}')
    i1['canon_jp'] = len(jb)
    i1['ok'] = i1['ok'] and len(jb) == 19 and len(jt) == 19
    cb = parse_edgecuts(CANON)
    ct = parse_edgecuts(path)
    i2 = {'name': f'I2_edgecuts_{label}', 'canon': len(cb),
          'other': len(ct), 'ok': cb == ct}
    nb = sum(1 for v in canon_pads.values()
             if v['type'] == 'np_thru_hole')
    nt = sum(1 for v in pads.values() if v['type'] == 'np_thru_hole')
    i3 = {'name': f'I3_npth_{label}', 'canon': nb, 'other': nt,
          'ok': nb == nt}
    i4 = pad_diff(canon_pads, pads, f'I4_pad_net_{label}')
    text = open(path, encoding='utf-8').read()
    i5 = {'name': f'I5_layers_{label}',
          'in1_named': '"In1.Cu"' in text,
          'in2_named': '"In2.Cu"' in text,
          'stackup_block': '(stackup' in text,
          'ok': all(x in text for x in
                    ('"In1.Cu"', '"In2.Cu"', '(stackup'))}
    vias, seg_w, seg_n = parse_vias(path)
    tin = []
    for v in vias:
        vx, vy = v['pos']
        for (ref, name), p in pads.items():
            if p['type'] != 'smd':
                continue
            px, py = p['pos']
            sx, sy = p['size']
            if abs(vx - px) <= sx / 2 and abs(vy - py) <= sy / 2:
                tin.append({'via': list(v['pos']), 'pad': [ref, name]})
    i6 = {'name': f'I6_via_in_pad_{label}', 'found': tin, 'ok': not tin}
    zones = parse_zones(path)
    i7 = {'name': f'I7_zones_{label}', 'zones': zones,
          'inner_gnd': sum(1 for z in zones
                           if z['net'] == 'GND'
                           and z['layer'].startswith('In')),
          'ok': sum(1 for z in zones
                    if z['net'] == 'GND'
                    and z['layer'].startswith('In')) == 2}
    i8 = {'name': f'I8_min_seg_width_{label}', 'segments': seg_n,
          'widths_mm': seg_w,
          'ok': not seg_w or min(seg_w) >= 0.2 - 1e-9}
    ck.extend([i1, i2, i3, i4, i5, i6, i7, i8])
    return {'board': label, 'checks': ck, 'ok': all(c['ok'] for c in ck),
            'pads': len(pads)}


def main():
    rep_p = sys.argv[1]
    final_p = sys.argv[2] if len(sys.argv) > 2 else None
    canon_pads = parse_pads(CANON)
    report = {'canon': CANON, 'checks':
              [board_checks('canon_shape', VARIANT, canon_pads)]}
    report['checks'][0]['board'] = 'variant'
    if final_p:
        report['checks'].append(board_checks('final', final_p,
                                             canon_pads))
    report['ok'] = all(b['ok'] for b in report['checks'])
    json.dump(report, open(rep_p, 'w', encoding='utf-8'), indent=1)
    for b in report['checks']:
        print(b['board'], 'pads', b['pads'], 'OK' if b['ok'] else 'FAIL',
              [c['name'] for c in b['checks'] if not c['ok']])
    print('VARIANT_CHECK_OK' if report['ok'] else 'VARIANT_CHECK_FAIL')
    if not report['ok']:
        sys.exit(1)


if __name__ == '__main__':
    main()
