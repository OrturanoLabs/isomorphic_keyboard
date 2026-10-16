#!/usr/bin/env python3
"""integrity_check.py -- one-command trust anchor for the 2026-10-15/16

overnight FPGA-01/FPGA-02-preparation campaign (batches 001+).

Asserts, in a single pass:
  1. the design pcb artifact is still the validator snapshot
     (sha256[:12] c7d5b66fa1db);
  2. every recorded artifact hash in docs/route_arms.json still matches
     the file on disk (ties the comparison table to its inputs);
  3. every deterministic evidence tool RERUNS CLEAN and reproduces its
     recorded outputs BYTE-IDENTICALLY (route_report, widen_check,
     widen_apply_probe, dsn_4l_probe, dsn_class_split x2) -- catches
     both nondeterminism and silent input drift;
  4. the SES gate pair behaves on four arm signatures (subset PASS)
     and the discrete fixture gate still fires --full at 46/52
     (expected-failure assertion) while subset passes;
  5. the checkpoint has all session blocks.

Writes docs/overnight_integrity.json, prints one line per check,
exit 0 iff every check passes. All reruns reuse the tools' own
argv in-place; outputs overwrite with (verified-identical) bytes.
"""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(BOARD, "..", "..", "..",
                                    "..", ".."))
OUT = os.path.join(BOARD, "docs", "overnight_integrity.json")
PCB_SHA12 = "c7d5b66fa1db"
FIX = os.path.join(REPO, "hardware", "experiments", "simple-tile",
                   "discrete-spld", "layout")


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


checks = []


def rec(cid, ok, detail=""):
    checks.append({"id": cid, "ok": bool(ok), "detail": detail})
    print(f"  {'OK ' if ok else 'FAIL'} {cid} {detail}")


def b(path_rel):
    return os.path.join(BOARD, path_rel)


def rerun(cid, cmd, sentinel, watch_paths):
    """Run a tool, assert rc0+sentinel+byte-identical watch files."""
    before = {p: sha(p) for p in watch_paths if os.path.exists(p)}
    r = subprocess.run([sys.executable] + cmd, cwd=BOARD,
                       capture_output=True, text=True)
    out = r.stdout + r.stderr
    same = all(sha(p) == v for p, v in before.items())
    ok = (r.returncode == 0 and sentinel in out and same
          and len(before) == len(watch_paths))
    rec(cid, ok, f"rc={r.returncode} identical={same} "
                 f"watched={len(before)}/{len(watch_paths)}")


def main():
    # 1. artifact anchor
    h = sha(b("out/kicad/tile_gw1nz.kicad_pcb"))[:12]
    rec("pcb_hash", h == PCB_SHA12, h)

    # 2. arms table vs files
    ra = json.load(open(b("docs/route_arms.json")))
    mm = []
    for a in ra["arms"]:
        for k, rel in (("dsn", a["artifacts"]["dsn"]),
                       ("ses", a["artifacts"]["ses"])):
            p = b(rel)
            if sha(p)[:12] != a["artifacts"][f"{k}_sha256_12"]:
                mm.append(rel)
    rec("arms_artifact_hashes", not mm, f"mismatch={mm}")

    # 3. deterministic reruns
    rerun("rerun_route_report", ["tools/route_report.py"],
          "ROUTE_REPORT OK", [b("docs/route_arms.json")])
    rerun("rerun_widen_check", ["tools/widen_check.py"],
          "WIDEN_CHECK OK", [b("docs/widen_report.json")])
    rerun("rerun_widen_apply", ["tools/widen_apply_probe.py"],
          "WIDEN_APPLY OK",
          [b("docs/widen_apply_report.json"),
           b("out/route/tile_gw1nz_widened.ses"),
           b("out/route/tile_gw1nz_4l_widened.ses")])
    rerun("rerun_dsn_4l_probe", ["tools/dsn_4l_probe.py"], "DSN_4L OK",
          [b("out/route/tile_gw1nz_4l.dsn"),
           b("out/route/dsn_4l_probe.json")])
    rerun("rerun_class_split_default", ["tools/dsn_class_split.py"],
          "DSN_CLASS_SPLIT OK",
          [b("out/route/tile_gw1nz_classes.dsn"),
           b("out/route/dsn_class_split.json")])
    rerun("rerun_class_split_fanout",
          ["tools/dsn_class_split.py",
           "out/route/tile_gw1nz_fanout_probe.dsn",
           "out/route/tile_gw1nz_fanout_classes.dsn",
           "out/route/dsn_class_split_fanout.json"],
          "DSN_CLASS_SPLIT OK",
          [b("out/route/tile_gw1nz_fanout_classes.dsn"),
           b("out/route/dsn_class_split_fanout.json")])

    # 4. SES gate behavior (subset arms PASS; fixture full must FAIL)
    gate_cases = [
        ("gate_bare_subset", "out/route/tile_gw1nz_classes.dsn",
         "out/route/tile_gw1nz.ses", "out/route/ses_tile_check.json",
         True),
        ("gate_bare_widened_subset", "out/route/tile_gw1nz_classes.dsn",
         "out/route/tile_gw1nz_widened.ses",
         "out/route/ses_tile_widened_check.json", True),
        ("gate_4l_widened_subset", "out/route/tile_gw1nz_4l.dsn",
         "out/route/tile_gw1nz_4l_widened.ses",
         "out/route/ses_tile_4l_widened_check.json", True),
    ]
    for cid, dsn, ses, rep, expect_pass in gate_cases:
        r = subprocess.run([sys.executable, "tools/ses_import_check.py",
                            dsn, ses, rep], cwd=BOARD,
                           capture_output=True, text=True)
        got = r.returncode == 0 and "SES_IMPORT_CHECK OK" in r.stdout
        rec(cid, got == expect_pass, f"rc={r.returncode}")
    fix_dsn = os.path.join(FIX, "tile_variant_a_4l.dsn")
    fix_ses = os.path.join(FIX, "tile_variant_a_4l.ses")
    r = subprocess.run([sys.executable, "tools/ses_import_check.py",
                        fix_dsn, fix_ses,
                        "out/route/ses_fixture_check.json"],
                       cwd=BOARD, capture_output=True, text=True)
    rec("gate_fixture_subset", r.returncode == 0
        and "46/52" in r.stdout, f"rc={r.returncode}")
    r = subprocess.run([sys.executable, "tools/ses_import_check.py",
                        fix_dsn, fix_ses,
                        "out/route/ses_fixture_check_full.json",
                        "--full"], cwd=BOARD, capture_output=True,
                       text=True)
    rec("gate_fixture_full_fires",
        r.returncode != 0 and "SES_IMPORT_CHECK FAIL" in r.stdout,
        f"rc={r.returncode}")

    # 5. checkpoint completeness
    ck = os.path.join(REPO, "hardware", "experiments", "simple-tile",
                      "checkpoints", "fpga-01.md")
    n = open(ck).read().count("## Session")
    rec("checkpoint_sessions", n >= 18, f"sessions={n}")

    ok = all(c["ok"] for c in checks)
    doc = {
        "tool": "integrity_check.py",
        "campaign": "fpga overnight 2026-10-15/16, "
                    "ses_fpga_overnight_20261015",
        "checks_passed": sum(c["ok"] for c in checks),
        "checks_total": len(checks),
        "overall": "PASS" if ok else "FAIL",
        "checks": checks,
    }
    json.dump(doc, open(OUT, "w"), indent=1)
    print(f"INTEGRITY {'PASS' if ok else 'FAIL'}: "
          f"{doc['checks_passed']}/{doc['checks_total']} -> {OUT}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
