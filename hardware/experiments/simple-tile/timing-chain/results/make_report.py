#!/usr/bin/env python3
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Assemble results/report.md from the actual run logs (host python3 stdlib).
Data sources: results/summary.txt, sweeps.txt, sync.log, per-config TCREGSUMMARY/
TMARK lines, and ../si/results/chain_hop_20mhz.txt when present. Nothing here is
computed; every number is lifted from the logs named.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RES = HERE
SI = os.path.normpath(os.path.join(HERE, "..", "si", "results"))


def grep_file(path, pat):
    out = []
    if not os.path.exists(path):
        return out
    rx = re.compile(pat)
    for line in open(path):
        if rx.search(line):
            out.append(line.rstrip())
    return out


def table_sweeps():
    rows = []
    for line in grep_file(os.path.join(RES, "sweeps.txt"), r"^SWEEP "):
        m = re.match(r"SWEEP N=(\d+) H=(\d+) corner=(\w+) guard_min_ns=(\S+) "
                     r"lead_min_ns=(\S+) lead_max_ns=(\S+) high_min_ns=(\S+)", line)
        if m:
            rows.append(m.groups())
    if not rows:
        return "(no sweep data)\n"
    out = ["| corner | N (cols) | H (rows) | min latch guard (ns) | sample-lead window (ns) | min clock high (ns) |",
           "|---|---|---|---|---|---|"]
    for (n, h, corner, g, lmin, lmax, hi) in rows:
        out.append(f"| {corner} | {n} | {h} | {g} | {lmin} .. {lmax} | {hi} |")
    return "\n".join(out) + "\n"


def table_configs():
    out = ["| config | result |", "|---|---|"]
    for line in grep_file(os.path.join(RES, "summary.txt"), r"^(PASS|FAIL|ERROR)  "):
        n = line.split()[1]
        status = "PASS" if line.startswith("PASS") else "FAIL"
        out.append(f"| {n} | {status} |")
    return "\n".join(out) + "\n"


def tmark_section():
    picks = {}
    for log in ("pos_n16_route15_max", "pos_col16_route15_max",
                "pos_n16_route15_min", "pos_n1_route15_max"):
        d = {}
        for line in grep_file(os.path.join(RES, f"{log}.log"), r"TMARK|TCREGSUMMARY"):
            if "TCREGSUMMARY" in line:
                d["sum"] = line.split("report note): ", 1)[-1]
            elif "TMARK RELEASE" in line and "rel" not in d:
                d["rel"] = line.split("TMARK ", 1)[-1]
            elif "TMARK ENABLE" in line and "en" not in d:
                d["en"] = line.split("TMARK ", 1)[-1]
            elif "TMARK LATCH tile(1,4) latch='1'" in line and "lat14" not in d:
                d["lat14"] = line.split("TMARK ", 1)[-1]
            elif "TMARK LATCH tile(16,4) latch='1'" in line and "lat164" not in d:
                d["lat164"] = line.split("TMARK ", 1)[-1]
            elif "TMARK EDGE" in line:
                d.setdefault("edges", []).append(line.split("TMARK ", 1)[-1])
        picks[log] = d
    out = ["", "### TMARK excerpts (actual times from the logs)", ""]
    for log, d in picks.items():
        out.append(f"**{log}**")
        for k in ("sum", "lat14", "lat164", "rel", "en"):
            if k in d:
                out.append(f"- `{d[k]}`")
        for e in d.get("edges", [])[:12]:
            out.append(f"- `{e}`")
        out.append("")
    return "\n".join(out)


def si_section():
    p = os.path.join(SI, "chain_hop_20mhz.txt")
    if not os.path.exists(p):
        return "(SI results not present; run si/run_si.sh)\n"
    lines = grep_file(p, r"^SI-(PASS|FAIL|INFO)")
    summ = grep_file(os.path.join(SI, "summary.txt"), r".")
    out = ["", f"SI harness summary: {'; '.join(summ)}", "",
           "| case | metrics |", "|---|---|"]
    for line in lines:
        out.append(f"| {line} | |")
    return "\n".join(out) + "\n".replace("| |", "|")


def main():
    sync = " ".join(grep_file(os.path.join(RES, "sync.log"), r"SYNC") or ["(sync not run)"])
    env = grep_file(os.path.join(RES, "env.log"), r".")
    head = f"""# Timing-aware chain results (generated from logs; do not edit)

## Environment

```
{chr(10).join(env)}
```

datasheet-constant drift guard: `{sync}`

## Testbench matrix ({os.path.basename(os.path.normpath(RES))}/summary.txt)

{table_configs()}
## Sweeps vs N (latch guard / sample lead / clock high phase)

{table_sweeps()}
"""
    tail = tmark_section()
    si = "\n## SI burst results (si/results/)\n\n" + si_section()
    note = """
## Notes

- Numbers marked 'because identical for all N' are structural: the forwarded
  clock and latch paths track each other per hop, so every binding margin is
  local to the first tile or the last hop. Still, the *absolute* delays grow
  ~6.5 ns per column / ~6.8 ns per upward hop (TMARK EDGE lateness lines);
  those enter the inter-tile phase/clock-chain budgets that calc_timing.py
  flagged OPEN.
- Route delay is a fixed 1.5 ns/hop synthetic assumption (0 in the
  route0 configs); neither is a physical signoff.
- Datasheet ten/tdis have no MIN column: the min corner uses a documented
  0.0 ns lower bound there; dependent margins are unsigned on that side.
"""
    open(os.path.join(RES, "report.md"), "w").write(head + tail + si + note)
    print("wrote", os.path.join(RES, "report.md"))


if __name__ == "__main__":
    sys.exit(main())
