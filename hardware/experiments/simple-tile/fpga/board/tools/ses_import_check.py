#!/usr/bin/env python3
"""ses_import_check.py -- FPGA-02 phase-C prereq: pure-python Specctra
SES (router session output) verifier, pcbnew-independent. Rationale:
when a freerouting SES comes back, pcbnew.ImportSpecctraSES must get a
file that is faithful to the DSN it was routed from; this gate checks
that contract BEFORE pcbnew is invoked (docs/LEDGER.md: pcbnew segfault
surface is real, minimize adversarial inputs).

Usage: ses_import_check.py DSN SES REPORT.json [--full]
  --full additionally requires routed nets == DSN nets (completion).

Checks (exit 1 on any failure):
  S1 resolution identity (placement + routes == DSN resolution);
  S2 every routed net name exists in the DSN network (subset; full
     equality reported as complete_routes / required under --full);
  S3 every (via "NAME" ...) instance + library_out padstack resolves to
     the DSN (via "...") table;
  S4 every wire (path LAYER ...) layer exists in the DSN structure;
  S5 wire widths are sane positive multiples of 5 in file units
     (opaque-units sanity; class-vs-width enforcement stays with DRC);
  S6 all wire/via coordinates lie within the DSN boundary path bbox;
  S7 vacuity: a renamed routed net MUST fail S2 (in-memory control).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def blocks(text, head):
    out, i = [], 0
    while True:
        j = text.find(head, i)
        if j < 0:
            break
        i = j + len(head)
        if j > 0 and text[j - 1] not in " \t\n":
            continue
        nxt = text[j + len(head):j + len(head) + 1]
        if nxt not in (" ", '"', "\n", "\t"):
            continue
        depth, k = 0, j
        while k < len(text):
            c = text[k]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    out.append(text[j:k + 1])
                    i = k + 1
                    break
            k += 1
    return out


def parse_dsn(path):
    text = open(path).read()
    res = re.search(r"\(resolution um (\d+)\)", text)
    nets = set()
    for nb in blocks(text, "(network"):
        for m in re.finditer(r'\(net\s+(\S+)\s+\(pins\s+([^)]*)\)\s*\)',
                             nb):
            nets.add(m.group(1))
    vias = set(re.findall(r'\(via "([^"]+)"', text))
    layers = set(re.findall(r"\(layer ([A-Za-z0-9_.]+)\s*\n?\s*\(type", text))
    bnd = blocks(text, "(boundary")
    pts = []
    for bb in bnd:
        # (path pcb CLEAR x0 y0 x1 y1 ...) -> pairs only
        m = re.search(r"\(path \S+ [-\d.]+((?:\s+[-\d.]+\s+[-\d.]+)+)", bb)
        if m:
            pts += [(float(a), float(b)) for a, b in
                    re.findall(r"([-\d.]+)\s+([-\d.]+)", m.group(1))]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return {"resolution": int(res.group(1)) if res else None,
            "nets": nets, "vias": vias, "layers": layers,
            "bbox": (min(xs), min(ys), max(xs), max(ys))}


def parse_ses(path):
    text = open(path).read()
    res = [int(x) for x in re.findall(r"\(resolution um (\d+)\)", text)]
    routed, vias_refs, layers_used, widths, pts = {}, set(), set(), set(), []
    for nb in blocks(text, "(network_out"):
        for m in re.finditer(r'\(net\s+(\S+)\s+', nb):
            seg = blocks(nb, "(net ")
            break
        nets = []
        for nseg in blocks(nb, "(net"):
            m = re.match(r'\(net\s+(\S+)', nseg)
            if not m:
                continue
            name = m.group(1)
            nets.append(name)
            for wb in blocks(nseg, "(wire"):
                pm = re.search(r"\(path (\S+) ([-\d]+)((?:\s+[-\d.]+\s+[-\d.]+)+)",
                               wb)
                if pm:
                    layers_used.add(pm.group(1))
                    widths.add(int(pm.group(2)))
                    for cm in re.finditer(r"([-\d.]+) ([-\d.]+)",
                                          pm.group(3)):
                        pts.append((float(cm.group(1)),
                                    float(cm.group(2))))
            for vm in re.finditer(r'\(via "([^"]+)" ([-\d.]+) ([-\d.]+)',
                                  nseg):
                vias_refs.add(vm.group(1))
                pts.append((float(vm.group(2)), float(vm.group(3))))
        for n in nets:
            routed[n] = True
    lib_vias = set(re.findall(r'\(padstack "([^"]+)"', text))
    return {"resolution": res, "routed_nets": set(routed),
            "via_refs": vias_refs, "lib_vias": lib_vias,
            "layers": layers_used, "widths": sorted(widths), "pts": pts}


def norm(name):
    return name.strip('"').upper()


def verify(dsn, ses, full=False):
    probs = []
    if not (ses["resolution"] and
            all(r == dsn["resolution"] for r in ses["resolution"])):
        probs.append(f"S1: resolutions {ses['resolution']} != "
                     f"{dsn['resolution']}")
    dmap = {norm(n): n for n in dsn["nets"]}
    extra = [n for n in ses["routed_nets"] if norm(n) not in dmap]
    if extra:
        probs.append(f"S2: routed nets not in DSN: {sorted(extra)[:5]}")
    drift = [(n, dmap[norm(n)]) for n in ses["routed_nets"]
             if norm(n) in dmap and n != dmap[norm(n)]]
    missing_via = (ses["via_refs"] | ses["lib_vias"]) - dsn["vias"]
    if missing_via:
        probs.append(f"S3: via names not in DSN: {sorted(missing_via)}")
    bad_layers = ses["layers"] - dsn["layers"]
    if bad_layers:
        probs.append(f"S4: layers not in DSN structure: {bad_layers}")
    if not ses["widths"] or min(ses["widths"]) <= 0 or \
       any(w % 5 for w in ses["widths"]):
        probs.append(f"S5: insane widths {ses['widths']}")
    div = ses["resolution"][0] if ses["resolution"] else 1
    if ses["pts"]:
        x0, y0, x1, y1 = dsn["bbox"]
        out_pts = [p for p in ses["pts"]
                   if not (x0 - 1 <= p[0] / div <= x1 + 1
                           and y0 - 1 <= p[1] / div <= y1 + 1)]
        if out_pts:
            probs.append(f"S6: {len(out_pts)} points outside boundary "
                         f"bbox (after /{div} frame scaling), "
                         f"e.g. {out_pts[:2]}")
    complete = (len(ses["routed_nets"]) == len(dsn["nets"]) and
                not extra)
    if full and not complete:
        probs.append(f"S2f: incomplete routes, missing: "
                     f"{sorted(dsn['nets'] - ses['routed_nets'])[:5]}")
    return probs, complete, drift


def main():
    dsn_path, ses_path, report = sys.argv[1], sys.argv[2], sys.argv[3]
    full = "--full" in sys.argv[4:]
    dsn = parse_dsn(dsn_path)
    ses = parse_ses(ses_path)
    probs, complete, drift = verify(dsn, ses, full)

    # S7 vacuity: rename a routed net to a name not in the DSN
    ctrl = dict(ses)
    if ctrl["routed_nets"]:
        one = sorted(ctrl["routed_nets"])[0]
        ctrl["routed_nets"] = (ctrl["routed_nets"] - {one}) | {"__ctrl__"}
        cprobs, _, x = verify(dsn, ctrl, full)
        if not any("S2" in p for p in cprobs):
            probs.append("S7: control did NOT fire")

    rep = {"ok": not probs, "problems": probs,
           "name_drift_report_only": drift,
           "_frame_note": "SES numeric coords at (resolution um 10) "
           "granularity (=0.1 um units); the KiCad DSN boundary reads "
           "in raw um -- verifier divides SES coords by the resolution "
           "value before boundary comparison (fixture-verified "
           "round-trip frame convention)",
           "dsn": os.path.basename(dsn_path),
           "ses": os.path.basename(ses_path),
           "dsn_nets": len(dsn["nets"]),
           "routed_nets": len(ses["routed_nets"]),
           "complete_routes": complete,
           "resolution": dsn["resolution"],
           "lib_vias": sorted(ses["lib_vias"]),
           "layers_used": sorted(ses["layers"]),
           "widths_seen": ses["widths"],
           "points": len(ses["pts"])}
    os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
    json.dump(rep, open(report, "w"), indent=1)
    print(("SES_IMPORT_CHECK OK: " if not probs else
           f"SES_IMPORT_CHECK FAIL: {probs}") +
          f"routed {len(ses['routed_nets'])}/{len(dsn['nets'])} nets, "
          f"complete={complete}, layers={sorted(ses['layers'])}, "
          f"widths={ses['widths']}, points={len(ses['pts'])} "
          f"-> {report}")
    sys.exit(1 if probs else 0)


if __name__ == "__main__":
    main()
