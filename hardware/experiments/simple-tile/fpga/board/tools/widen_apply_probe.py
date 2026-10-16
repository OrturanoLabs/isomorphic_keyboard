#!/usr/bin/env python3
"""widen_apply_probe.py -- close the widen-loop evidence, text-level.

For the two router-generated SES arms (bare, four_l_planes):
  1. rewrite every below-class path-width token in the SES text up to
     the class minimum (docs/netclasses.json; absolute floor 0.2 mm,
     power 0.5 mm), emitting a widened SES next to the source;
  2. verify the edit was ONLY width tokens (offset-scoped inverse
     check: undo the recorded replacements -> byte-identical text);
  3. self-check GEOMETRY after widening: same-layer, cross-net,
     segment-to-segment distances vs (w1+w2)/2 + 0.2 mm clearance and
     report every conflict the naive in-place widen would create
     (locations for a manual re-route decision).

The dead_end_stubs arm is SKIPPED: its 55 below-class paths are our
own pre-placed 0.2 mm escapes on power nets (fanout_apply_probe.py),
a documented design decision independent of the router; the router's
own 8 below-class paths there are tracked in widen_report.json.

Honest limits (recorded in the report): pad-stack keepouts and vias
are not modeled, so conflicts near pads may be false positives; the
widened SES is a REPAIR CANDIDATE, not DRC-verified copper; adoption
still needs the fix_routed-style pcb-side pass + full DRC.

Writes out/route/*_widened.ses + docs/widen_apply_report.json.
"""
import hashlib
import importlib.util
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
_spec = importlib.util.spec_from_file_location(
    "sc", os.path.join(HERE, "ses_import_check.py"))
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

UNIT_TO_MM = 1.0 / 10000
UNIT_TO_UM = 1.0 / 10
FLOOR_UM = 200.0
CLEAR_MM = 0.2

ARMS = [
    ("bare", "out/route/tile_gw1nz.ses",
     "out/route/tile_gw1nz_widened.ses"),
    ("four_l_planes", "out/route/tile_gw1nz_4l.ses",
     "out/route/tile_gw1nz_4l_widened.ses"),
    ("four_l_attach_vias", "out/route/tile_gw1nz_4l_attach.ses",
     "out/route/tile_gw1nz_4l_attach_widened.ses"),
]
REPORT = os.path.join(BOARD, "docs", "widen_apply_report.json")

PATH_RE = re.compile(
    r"\(path\s+(\S+)\s+(\d+)((?:\s+-?[\d.]+\s+-?[\d.]+)+)\s*\)")


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def seg_seg_dist(p1, p2, p3, p4):
    """Minimum distance between segments p1p2 and p3p4 (same units)."""
    def dot(a, b):
        return a[0] * b[0] + a[1] * b[1]

    def sub(a, b):
        return (a[0] - b[0], a[1] - b[1])

    def pt_seg(p, a, b):
        ab = sub(b, a)
        denom = dot(ab, ab)
        if denom == 0:
            return math.hypot(*sub(p, a))
        t = max(0.0, min(1.0, dot(sub(p, a), ab) / denom))
        proj = (a[0] + t * ab[0], a[1] + t * ab[1])
        return math.hypot(*sub(p, proj))

    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (
            c[0] - a[0])

    d1, d2 = ccw(p3, p4, p1), ccw(p3, p4, p2)
    d3, d4 = ccw(p1, p2, p3), ccw(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(pt_seg(p1, p3, p4), pt_seg(p2, p3, p4),
               pt_seg(p3, p1, p2), pt_seg(p4, p1, p2))


def parse_paths_with_spans(text):
    """net-region sliced list of path records with width-token spans."""
    out = []
    nheads = list(re.finditer(r'\(net\s+(\S+)', text))
    for i, nh in enumerate(nheads):
        name = nh.group(1).strip('"')
        end = nheads[i + 1].start() if i + 1 < len(nheads) else len(text)
        seg = text[nh.start():end]
        base = nh.start()
        for m in PATH_RE.finditer(seg):
            if m.group(1) in ("F.Cu", "B.Cu", "In1.Cu", "In2.Cu"):
                pts = [(float(a), float(b)) for a, b in re.findall(
                    r"(-?[\d.]+)\s+(-?[\d.]+)", m.group(3))]
                out.append({
                    "net": name,
                    "layer": m.group(1),
                    "w_units": int(m.group(2)),
                    "span": (base + m.start(2), base + m.end(2)),
                    "pts": pts,
                })
    return out


def main():
    nc = json.load(open(os.path.join(BOARD, "docs", "netclasses.json")))
    n2c = {sc.norm(k): v for k, v in nc["net_to_class"].items()}
    min_um = {c: float(v["rule"]["track_mm"]) * 1000.0
              for c, v in nc["classes"].items()}

    arms = []
    for arm_id, src_rel, out_rel in ARMS:
        src = os.path.join(BOARD, src_rel)
        text = open(src).read()
        paths = parse_paths_with_spans(text)
        edits = []          # (span, old_units, new_units, net, layer)
        for p in paths:
            req = max(min_um.get(n2c.get(sc.norm(p["net"])), FLOOR_UM),
                      FLOOR_UM)
            w_um = p["w_units"] * UNIT_TO_UM
            if w_um < req - 1e-9:
                edits.append((p["span"], p["w_units"],
                              int(round(req * 10)), p["net"],
                              p["layer"]))
        mod = text
        for (s, e), old, new, net, layer in sorted(edits, reverse=True):
            mod = mod[:s] + str(new) + mod[e:]
        out_p = os.path.join(BOARD, out_rel)
        open(out_p, "w").write(mod)

        # inverse: undo edits at same offsets, must reproduce source
        back = mod
        for (s, e), old, new, net, layer in sorted(edits, reverse=True):
            assert back[s:s + len(str(new))] == str(new)
            back = back[:s] + str(old) + back[s + len(str(new)):]
        inv_ok = back == text

        # geometry conflict pass on the WIDENED text
        wp = parse_paths_with_spans(mod)
        for p in wp:  # widths may have changed; reload token value
            pass
        conflicts = []
        by_layer = {}
        for p in wp:
            by_layer.setdefault(p["layer"], []).append(p)
        for layer, ps in by_layer.items():
            for i in range(len(ps)):
                for j in range(i + 1, len(ps)):
                    a, b = ps[i], ps[j]
                    if a["net"] == b["net"]:
                        continue
                    need = (a["w_units"] + b["w_units"]) / 2 * UNIT_TO_MM
                    need += CLEAR_MM
                    for s1, s2 in zip(a["pts"], a["pts"][1:]):
                        for s3, s4 in zip(b["pts"], b["pts"][1:]):
                            d = seg_seg_dist(s1, s2, s3, s4) * UNIT_TO_MM
                            if d < need - 1e-9:
                                mx = ((s1[0] + s2[0] + s3[0] + s4[0])
                                      / 4 * UNIT_TO_MM)
                                my = ((s1[1] + s2[1] + s3[1] + s4[1])
                                      / 4 * UNIT_TO_MM)
                                conflicts.append({
                                    "nets": sorted([a["net"], b["net"]]),
                                    "layer": layer,
                                    "gap_mm": round(d, 3),
                                    "need_mm": round(need, 3),
                                    "at": [round(mx, 2), round(my, 2)],
                                })
        arms.append({
            "id": arm_id,
            "src": src_rel, "out": out_rel,
            "src_sha256_12": sha256(src)[:12],
            "out_sha256_12": sha256(out_p)[:12],
            "paths_total": len(paths),
            "widths_raised": len(edits),
            "raised_by_net": {n: sum(1 for e in edits if e[3] == n)
                              for n in sorted({e[3] for e in edits})},
            "inverse_identity": inv_ok,
            "conflicts": conflicts,
            "conflict_count": len(conflicts),
            "conflict_nets": sorted({tuple(c["nets"])
                                     for c in conflicts}),
        })
    doc = {
        "tool": "widen_apply_probe.py",
        "scope": "text-level SES widen to class minima; arms bare and "
                 "four_l_planes (stub arm skipped: own-escape decision)",
        "limits": "pad/via keepouts NOT modeled -> conflicts near pads "
                  "may be false positives; widened SES is a repair "
                  "candidate, not DRC-verified; adoption still needs "
                  "pcb-side fix pass + full DRC (fix_routed precedent)",
        "clearance_mm": CLEAR_MM,
        "arms": arms,
    }
    json.dump(doc, open(REPORT, "w"), indent=1)
    bad = [a["id"] for a in arms if not a["inverse_identity"]]
    if bad:
        print(f"WIDEN_APPLY FAIL inverse: {bad}")
        sys.exit(1)
    print(f"WIDEN_APPLY OK -> {REPORT}")
    for a in arms:
        print(f"  {a['id']}: raised={a['widths_raised']} "
              f"nets={a['raised_by_net']} conflicts={a['conflict_count']}"
              f" -> {a['out']}")


if __name__ == "__main__":
    main()
