#!/usr/bin/env python3
"""Digest a kicad-cli DRC json into a compact comparable summary.

  python3 drc_digest.py <drc.json> [<drc2.json>]

Two files -> a before/after comparison table.  Unconnected items are
counted separately (they are pads, not violations).
"""
import collections
import json
import sys


def digest(path):
    d = json.load(open(path))
    vs = d.get('violations', [])
    errs = [v for v in vs if v['severity'] == 'error']
    warn = [v for v in vs if v['severity'] == 'warning']
    by_type = collections.Counter(v['type'] for v in errs)
    w_type = collections.Counter(v['type'] for v in warn)
    unc = d.get('unconnected_items', [])
    return {
        'errors': len(errs), 'error_types': dict(by_type),
        'warnings': len(warn), 'warning_types': dict(w_type),
        'unconnected': len(unc),
        'source': d.get('source'),
        'kicad': d.get('kicad_version'),
    }


def main():
    a = digest(sys.argv[1])
    if len(sys.argv) == 2:
        print(json.dumps(a, indent=1))
        return 0
    b = digest(sys.argv[2])
    print(f"{'':28s}{'BEFORE':>10s}{'AFTER':>10s}")
    print(f"{'errors':28s}{a['errors']:>10d}{b['errors']:>10d}")
    print(f"{'warnings':28s}{a['warnings']:>10d}{b['warnings']:>10d}")
    print(f"{'unconnected':28s}{a['unconnected']:>10d}{b['unconnected']:>10d}")
    keys = sorted(set(a['error_types']) | set(b['error_types']))
    for k in keys:
        print(f"  err {k:24s}{a['error_types'].get(k, 0):>10d}"
              f"{b['error_types'].get(k, 0):>10d}")
    keys = sorted(set(a['warning_types']) | set(b['warning_types']))
    for k in keys:
        print(f"  warn {k:23s}{a['warning_types'].get(k, 0):>10d}"
              f"{b['warning_types'].get(k, 0):>10d}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
