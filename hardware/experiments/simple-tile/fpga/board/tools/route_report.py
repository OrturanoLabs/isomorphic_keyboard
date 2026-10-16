#!/usr/bin/env python3
"""route_report.py -- FPGA-02 preparation: one auditable comparison table

for the autorouter feasibility arms measured on the GW1NZ tile.

For each recorded arm the tool recomputes from artifacts on disk:
  * items_total   = sum(pins_per_net - 1) over the arm's DSN network
                    (matches freerouting's "unrouted items" accounting;
                    verified == 99 on both arms)
  * nets_total / nets_wired / open_nets (case+quote-drift aware via
                    ses_import_check.norm)
  * width inventory, layers used, wire-point count, artifact sha256
Router-side numbers that cannot be recomputed without the (piped, not
teed) stdout logs -- wall time, items routed/unrouted, optimizer
behavior -- are carried in a PROVENANCE block citing the checkpoint
sessions where the log excerpts were recorded at run time.

Writes docs/route_arms.json. Exits nonzero if structural invariants
break, so it doubles as a regression guard for future arms (add a new
entry to ARMS with its provenance constants and rerun).

Light tool: pure text parsing, no KiCad. Still run under
resource_guard per the heavy-checker rule of the overnight session.
"""
import hashlib
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
sys.path.insert(0, HERE)
_spec = importlib.util.spec_from_file_location(
    "sc", os.path.join(HERE, "ses_import_check.py"))
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

OUT = os.path.join(BOARD, "docs", "route_arms.json")

# Wall/item numbers: freerouting 2.4.1 stdout was consumed through a
# pipe (tail), not teed to a file, on both arms; the verbatim log lines
# were transcribed into fpga-01.md sessions 13 and 14 at run time.
# Future arms must `tee` their router log so this block can reference a
# file path instead.
ARMS = [
    {
        "id": "bare",
        "desc": "classes.dsn as exported+split; no pre-route copper",
        "dsn": "out/route/tile_gw1nz_classes.dsn",
        "ses": "out/route/tile_gw1nz.ses",
        "provenance": {
            "source": "fpga-01.md session 13 (batch 9 log excerpt)",
            "router": "freerouting 2.4.1,localhost container,-mp 40,"
                      "--gui.enabled=false, container caps 2g/2cpu",
            "wall_s": 519.22,
            "items_routed": 46,
            "items_unrouted": 53,
            "violations": 0,
            "optimizer": "stopped: improvement < 1% threshold",
        },
    },
    {
        "id": "dead_end_stubs",
        "desc": "52 planned power-fanout surface stubs pre-placed as "
                "fixed pre-routes on a pcbnew copy (via-free 2L fanout)",
        "dsn": "out/route/tile_gw1nz_fanout_classes.dsn",
        "ses": "out/route/tile_gw1nz_fanout.ses",
        "provenance": {
            "source": "fpga-01.md session 14 (batch 10 log excerpt)",
            "router": "freerouting 2.4.1,localhost container,-mp 40,"
                      "--gui.enabled=false, container caps 2g/2cpu",
            "wall_s": 926.4,
            "items_routed": 28,
            "items_unrouted": 71,
            "violations": 0,
            "optimizer": "stopped: improvement < 1% threshold",
        },
    },
    {
        "id": "bare_rep2",
        "desc": "VARIANCE REPLICATE of bare: identical input+flags, "
                "second run (batch 16); SES byte-identical to bare",
        "dsn": "out/route/tile_gw1nz_classes.dsn",
        "ses": "out/route/tile_gw1nz_rep2.ses",
        "provenance": {
            "source": "fpga-01.md session 20 + teed log "
                      "out/route/freerouting_rep2.log (batch 16)",
            "log": "out/route/freerouting_rep2.log",
            "router": "freerouting 2.4.1,localhost container,-mp 40,"
                      "--gui.enabled=false, container caps 2g/2cpu",
            "wall_s": 608.7,
            "items_routed": 46,
            "items_unrouted": 53,
            "violations": 0,
            "optimizer": "stopped: improvement < 1% threshold",
            "variance_result": "SES sha256 == bare arm output: "
                "router deterministic for this input; 46/99 exact",
            "fanout_stage": "router-internal SMD fanout escaped "
                "115/144 pins (79.9%); 4L arm 114/144 (79.2%)",
        },
    },
    {
        "id": "four_l_planes",
        "desc": "hand-spliced 4-layer variant (dsn_4l_probe.py): GND "
                "plane on In1.Cu, VCC1V2 plane on In2.Cu, padstack "
                "extended [0-3]; NO pre-placed vias -- hypothesis was "
                "router self-attaches SMD pads into declared planes",
        "dsn": "out/route/tile_gw1nz_4l.dsn",
        "ses": "out/route/tile_gw1nz_4l.ses",
        "provenance": {
            "source": "fpga-01.md session 15 + teed log "
                      "out/route/freerouting_4l.log (batch 11)",
            "log": "out/route/freerouting_4l.log",
            "router": "freerouting 2.4.1,localhost container,-mp 40,"
                      "--gui.enabled=false, container caps 2g/2cpu",
            "wall_s": 398.0,
            "items_absorbed_by_planes": 20,
            "items_routed": 17,
            "items_unrouted": 62,
            "violations": 0,
            "optimizer": "stopped: improvement < 1% threshold",
            "measured_plane_semantics": "GND(21 pins) items absorbed "
                "from the routing list (99->79) with NO via/wire "
                "emitted on inner layers (SES layers={F.Cu,B.Cu}); "
                "VCC1V2 plane NOT absorbed (its 6 items stayed). "
                "freerouting 2.4.1 treats a declared plane as "
                "'exclude net from routing', not as attachable copper.",
        },
    },
    {
        "id": "four_l_attach_vias",
        "desc": "4L DSN + 17 injected stub+via attach sites (GND 11, "
                "VCC1V2 6) at fanout_prep via_alternative positions, "
                "B.Cu stubs at class width 500 um, grammar cribbed from "
                "the discrete 4L fixture (type route)",
        "dsn": "out/route/tile_gw1nz_4l_attach.dsn",
        "ses": "out/route/tile_gw1nz_4l_attach.ses",
        "provenance": {
            "source": "fpga-01.md session 24 + teed log "
                      "out/route/freerouting_4l_attach.log (batch 20)",
            "log": "out/route/freerouting_4l_attach.log",
            "router": "freerouting 2.4.1,localhost container,-mp 40,"
                      "--gui.enabled=false, container caps 2g/2cpu",
            "wall_s": 570.8,
            "items_absorbed_by_planes": 20,
            "items_routed": 30,
            "items_unrouted": 49,
            "violations": 19,
            "optimizer": "stopped: improvement < 1% threshold",
            "attach_fate": "0/17 injected vias survive in the SES "
                "((type route) is rippable); the router's own fanout "
                "stage placed 53 vias into the planes (pass extra-via "
                "counts 65+11+2+0+2+0); 19 clearance violations held "
                "from autoroute pass #1 to optimizer end (unresolved, "
                "carry debt around the wide stubs/via ring)",
            "recount_note": "autoroute start-line says 66 items "
                "(fanout stage settled ~13 incl. attach items); "
                "inventoried within the documented +/-2 recount noise",
        },
    },
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


LOG_STAGE_RES = {
    "fanout": re.compile(
        r"Fanout stage completed: started with (\d+) total SMD pins, "
        r"completed in ([\d.]+) seconds, escaped pins: (\d+)/(\d+) "
        r"\(([\d.]+)%\)"),
    "autoroute": re.compile(
        r"Auto-routing stage completed: started with (\d+) unrouted "
        r"\w+, completed in ([\d.]+) seconds, final score: ([\d.]+) "
        r"\((\d+) unrouted and (\d+) violations\)"),
    "optimizer": re.compile(
        r"Optimization stage completed: started with score ([\d.]+) "
        r"\((\d+) unrouted and (\d+) violations\), completed in "
        r"([\d.]+) seconds, final score: ([\d.]+) \((\d+) unrouted "
        r"and (\d+) violations\)"),
    "elapsed": re.compile(
        r"finished with state: (\w+) \(elapsed: (?:(\d+) minutes )?"
        r"([\d.]+) seconds"),
    "heap": re.compile(r"([\d.]+) MB peak heap usage"),
    "auto_start": re.compile(
        r"Auto-routing stage started on board '\w+' for (\d+) "
        r"unrouted items"),
}


def parse_log(path):
    """Per-stage table from a teed freerouting stdout log."""
    text = open(path).read()
    stages = {}
    elap = None
    for m in LOG_STAGE_RES["fanout"].finditer(text):
        stages["fanout"] = {
            "smd_pins_total": int(m.group(1)),
            "wall_s": float(m.group(2)),
            "escaped": int(m.group(3)),
            "escaped_pct": float(m.group(5)),
        }
    ar = LOG_STAGE_RES["autoroute"].search(text)
    ast = LOG_STAGE_RES["auto_start"].search(text)
    if ast:
        stages.setdefault("autoroute", {})[
            "start_unrouted_items_line"] = int(ast.group(1))
    if ar:
        stages["autoroute"] = {
            "start_unrouted_recount": int(ar.group(1)),
            "start_unrouted_items_line": int(ast.group(1)) if ast
            else None,
            "wall_s": float(ar.group(2)),
            "final_score": float(ar.group(3)),
            "final_unrouted": int(ar.group(4)),
            "violations": int(ar.group(5)),
        }
    op = LOG_STAGE_RES["optimizer"].search(text)
    if op:
        stages["optimizer"] = {
            "start_score": float(op.group(1)),
            "start_unrouted": int(op.group(2)),
            "wall_s": float(op.group(4)),
            "final_score": float(op.group(5)),
            "final_unrouted": int(op.group(6)),
            "violations": int(op.group(7)),
        }
    for m in LOG_STAGE_RES["elapsed"].finditer(text):
        elap = m
    if elap:
        mins = float(elap.group(2) or 0)
        stages["job"] = {"state": elap.group(1),
                         "elapsed_s": mins * 60 + float(elap.group(3))}
    heap = LOG_STAGE_RES["heap"].search(text)
    if heap:
        stages.setdefault("job", {})["peak_heap_mb"] = float(
            heap.group(1))
    return stages


def pins_per_net(dsn_path):
    text = open(dsn_path).read()
    out = {}
    for nb in sc.blocks(text, "(network"):
        for m in re.finditer(r"\(net\s+(\S+)\s+\(pins\s+([^)]*)\)\s*\)",
                             nb):
            pins = m.group(2).split()
            out[m.group(1)] = len(pins)
    return out


def arm_report(a):
    dsn_p = os.path.join(BOARD, a["dsn"])
    ses_p = os.path.join(BOARD, a["ses"])
    dsn = sc.parse_dsn(dsn_p)
    ses = sc.parse_ses(ses_p)
    ppc = pins_per_net(dsn_p)
    items_total = sum(max(n - 1, 0) for n in ppc.values())
    dsn_norm = {sc.norm(n): n for n in dsn["nets"]}
    routed_norm = {sc.norm(n) for n in ses["routed_nets"]}
    wired = sorted(dsn_norm[k] for k in dsn_norm if k in routed_norm)
    open_nets = sorted(dsn_norm[k] for k in dsn_norm
                       if k not in routed_norm)
    prov = dict(a["provenance"])
    absorbed = prov.get("items_absorbed_by_planes", 0)
    ok_items = (prov["items_routed"] + prov["items_unrouted"]
                + absorbed) == items_total
    stages = None
    log_ok = None
    if prov.get("log"):
        stages = parse_log(os.path.join(BOARD, prov["log"]))
        ar = stages.get("autoroute", {})
        op = stages.get("optimizer", {})
        fv = stages.get("fanout", {})
        # freerouting recounts "unrouted" inconsistently between its own
        # stage lines (start-line items vs completed-line recount vs
        # optimizer); the SES stays ground truth, the transcribed prov
        # anchors conservation. Tolerate the observed +/-2 stage noise,
        # but pin everything that must hold exactly.
        checks = [
            abs(ar.get("final_unrouted", -99)
                - prov["items_unrouted"]) <= 2,
            abs(op.get("final_unrouted", -99)
                - prov["items_unrouted"]) <= 2,
            ar.get("violations") == prov["violations"]
            and op.get("violations") == prov["violations"],
            stages.get("job", {}).get("state") == "COMPLETED",
            fv.get("smd_pins_total", 144) == 144,
        ]
        log_ok = all(checks)
        if ar and op:
            stages["recount_noise_items"] = abs(
                ar.get("final_unrouted", 0)
                - op.get("final_unrouted", 0))
    return {
        "id": a["id"],
        "desc": a["desc"],
        "artifacts": {
            "dsn": a["dsn"], "ses": a["ses"],
            "dsn_sha256_12": sha256(dsn_p)[:12],
            "ses_sha256_12": sha256(ses_p)[:12],
        },
        "nets_total": len(dsn["nets"]),
        "nets_wired": len(wired),
        "open_nets": open_nets,
        "items_total": items_total,
        "open_net_item_load": sum(max(ppc[n] - 1, 0) for n in open_nets
                                  if n in ppc),
        "pins_per_net": {k: ppc[k] for k in sorted(ppc)},
        "widths_res10": ses["widths"],
        "off_class_widths_res10": [w for w in ses["widths"]
                                   if w not in (2000, 5000)],
        "sub_rule_widths_res10": [w for w in ses["widths"] if w < 2000],
        "layers_used": sorted(ses["layers"]),
        "wire_points": len(ses["pts"]),
        "provenance": prov,
        "invariant_items_sum_ok": ok_items,
        "stages": stages,
        "log_consistency_ok": log_ok,
    }


def main():
    reports = [arm_report(a) for a in ARMS]
    by_id = {r["id"]: r for r in reports}
    base = by_id.get("bare")
    arm_comps = []
    for r in reports:
        if r["id"] == "bare" or base is None:
            continue
        wb = set(base["open_nets"]) - set(r["open_nets"])  # opened->wired
        wg = set(r["open_nets"]) - set(base["open_nets"])  # wired->opened
        arm_comps.append({
            "arm": r["id"],
            "delta_items_routed": (r["provenance"]["items_routed"]
                                   - base["provenance"]["items_routed"]),
            "delta_nets_wired": r["nets_wired"] - base["nets_wired"],
            "nets_gained_vs_baseline": sorted(wb),
            "nets_lost_vs_baseline": sorted(wg),
            "item_load_gained": sum(
                r["pins_per_net"][n] - 1 for n in wb),
            "item_load_lost": sum(
                r["pins_per_net"][n] - 1 for n in wg),
        })
    findings = {
        "bare_rep2": "BYTE-IDENTICAL SES to bare (same sha256): "
            "freerouting 2.4.1 is deterministic for this input/flags, "
            "so 46/99 is exact for the router, not an RNG sample; "
            "remaining feasibility uncertainty is input/flag "
            "sensitivity, not run variance",
        "four_l_attach_vias": "the LEDGER 4L attach shape at DSN level "
            "is NOT the discrete build's win: injected vias all ripped "
            "((type route)); router fanned out into planes itself (53 "
            "vias) but carried 19 UNRESOLVED clearance violations vs "
            "0 in every other arm; items closed 50/99 vs bare 46/99 -- "
            "more items, but violation debt makes it strictly worse "
            "for adoption. Leave attach sovereignty to the router's "
            "own fanout when planes are declared, or pre-place vias "
            "PCB-side as fixed+protect and verify",
        "dead_end_stubs": "dead-end 2L stubs reduce routed items "
            "(fixed pre-routes that do not complete an attachment "
            "block escape directions); router-fed helper copper must "
            "terminate or be added after routing",
        "four_l_planes": "DSN-declared planes make freerouting EXCLUDE "
            "the plane net from routing (GND's 20 items silently "
            "absorbed, zero inner-layer geometry emitted; VCC1V2 "
            "plane ignored). No congestion relief: 17/79 routeable "
            "items closed. A real 4L attempt needs pre-placed "
            "pad->plane vias (the LEDGER-proven pcbnew-side attach)",
    }
    for c in arm_comps:
        c["finding"] = findings.get(c["arm"], "")
    comp = {"baseline": "bare", "arms_vs_baseline": arm_comps}
    doc = {
        "tool": "route_report.py",
        "board": "tile_gw1nz r6 (sha256[:12] c7d5b66fa1db, untouched)",
        "constraints": "strict 0.2/0.2 mm rules, via 0.6/0.3, 6-class "
                       "table (power 500/200 um), 2 layers F.Cu/B.Cu",
        "arms": reports,
        "comparison": comp,
    }
    json.dump(doc, open(OUT, "w"), indent=1)
    fails = [r["id"] for r in reports
             if not r["invariant_items_sum_ok"]
             or r["log_consistency_ok"] is False]
    canon = {"bare": (99, 25, 20), "dead_end_stubs": (99, 28, 17),
             "four_l_planes": (99, 34, 11), "bare_rep2": (99, 25, 20),
             "four_l_attach_vias": (99, 29, 16)}
    for a in ARMS:
        r = by_id[a["id"]]
        exp = canon.get(a["id"])
        if exp and (r["items_total"], r["nets_wired"],
                    len(r["open_nets"])) != exp:
            fails.append(a["id"] + ":canon")
    if fails:
        print(f"ROUTE_REPORT FAIL: {fails} -> {OUT}")
        sys.exit(1)
    print(f"ROUTE_REPORT OK: arms={len(reports)} "
          f"items_total_expected=99 all-ok -> {OUT}")
    for r in reports:
        print(f"  {r['id']}: nets {r['nets_wired']}/{r['nets_total']} "
              f"open={len(r['open_nets'])} items_total={r['items_total']} "
              f"items_routed(prov)={r['provenance']['items_routed']} "
              f"wall={r['provenance']['wall_s']}s "
              f"widths={r['widths_res10']}")
        st = r.get("stages") or {}
        if st:
            fv = st.get("fanout", {})
            ar = st.get("autoroute", {})
            print(f"    log: fanout {fv.get('escaped')}/"
                  f"{fv.get('smd_pins_total')} escaped "
                  f"({fv.get('escaped_pct')}%) | autoroute "
                  f"{ar.get('start_unrouted_recount')}->"
                  f"{ar.get('final_unrouted')} open, "
                  f"viol={ar.get('violations')} | job "
                  f"{st.get('job', {}).get('elapsed_s')}s state="
                  f"{st.get('job', {}).get('state')} | "
                  f"recount_noise={st.get('recount_noise_items')} | "
                  f"consistency={r['log_consistency_ok']}")


if __name__ == "__main__":
    main()
