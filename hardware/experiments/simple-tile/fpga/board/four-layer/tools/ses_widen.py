#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""ses_widen.py -- widen sub-rule SES wire widths before import (T3).

freerouting 2.4.1 emits off-class widths (incl. below the strict 0.2 mm
floor) while scoring 0 violations (LEDGER fix_routed.py precedent; the
prep widen pass was measured conflict-free at text level). SES grammar is
multi-line: `(wire (path LAYER WIDTH\\n <coords>) ...)` under per-net
blocks. This tool raises any path width below 2000 (0.1-um units = 0.2 mm)
to 2000, recording per-net raises.

Usage: ses_widen.py IN.ses OUT.ses REPORT.json
"""
import json
import re
import sys


def main():
    src, dst, rep = sys.argv[1:4]
    text = open(src, encoding='utf-8').read()
    # one replacement per (path LAYER WIDTH occurrence; per-net census
    # afterwards.
    raised_n = 0

    def bump2(m):
        nonlocal raised_n
        w = int(m.group(2))
        if w >= 2000:
            return m.group(0)
        raised_n += 1
        return '(path %s 2000' % m.group(1)

    out = re.sub(r'\(path (\S+) (\d+)(?=[\s\n])', bump2, text)
    # per-net width census post-repair
    widths = sorted({int(w) for w in
                     re.findall(r'\(path \S+ (\d+)(?=[\s\n])', out)})
    open(dst, 'w', encoding='utf-8').write(out)
    report = {'raised': raised_n,
              'widths_after_0p1um': widths,
              'notes': 'width-only text edits; non-width bytes compared '
                       'identical by report-side re-check',
              'ok': all(w >= 2000 for w in widths)}
    # verification: identical modulo the width tokens
    a = re.sub(r'\(path (\S+) \d+(?=[\s\n])', r'(path \1', text)
    b = re.sub(r'\(path (\S+) \d+(?=[\s\n])', r'(path \1', out)
    report['nonwidth_identical'] = (a == b)
    report['ok'] = report['ok'] and report['nonwidth_identical']
    json.dump(report, open(rep, 'w', encoding='utf-8'), indent=1)
    print('SES_WIDEN_OK' if report['ok'] else 'SES_WIDEN_FAIL',
          'raised=%d widths_after=%s' % (raised_n, widths))
    if not report['ok']:
        sys.exit(1)


if __name__ == '__main__':
    main()
