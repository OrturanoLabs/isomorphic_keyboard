#!/usr/bin/env python3
"""dsn_attach_probe.py -- FPGA-02 arm-4 probe input: inject TERMINATED

attach geometry (stub + through via onto the declared inner planes)
into the 4-layer DSN, at DSN text level. This is the LEDGER-proven
4L SMD attach shape (discrete build ran clean with exactly this
wiring grammar) and the MISSING arm in the measured series:

  bare 46/99 < stubs 28/99 (dead-end) ~ plane-declarations 17/79+20
  vs THIS arm: stub+via terminating into GND(In1)/VCC1V2(In2) planes.

Sources of geometry (nothing re-derived by eye):
  * fanout_prep.json via_alternative (escape_dir + ring 0.5/0.9,
    feasible==True) -> via center = pad edge + ring along escape dir,
    recomputed with the SAME fan_box math as tools/fanout_prep.py
  * pad centers = plan box midpoints, cross-asserted against the
    batch-10 fanout probe DSN's own exported stub starts (frame
    identity pcb-mm->DSN-um x1000 must hold for every injected site)
Only power-plane nets are attached: GND and VCC1V2 (VCC ring must
route on signal layers; VCC1V2_RAW is the LDO->FB1 feed).

Wiring grammar cribbed byte-for-byte style from the in-tree discrete
4L fixture (tile_variant_a_4l.dsn lines 1142+): one B.Cu stub
(width 500 = power class) pad-center -> via-center plus
(via "Via[0-3]_600:300_um" x y (net N)(type route)).

DSN frame: µm ints = (pcb_x*1000, -pcb_y*1000). The y-flip was
measured against the batch-10 probe DSN per-pad (U1-12 mid
(10809.7,7600) -> stub (10809.7,-7600) etc). NOTE: the batch-10 probe
pcb's own stubs landed on F.Cu (pcbnew pad.GetLayer() reports F_Cu
for these B-side SMD pads) -- a wrong-layer defect of that probe;
the stub-arm conclusion (dead-ends hurt) stands because the stubs
were fixed obstacles either way, but the stubs never touched their
pads. THIS arm writes stubs on B.Cu where the power pads live.

Writes out/route/tile_gw1nz_4l_attach.dsn + dsn_4l_attach_report.json.
Exits nonzero on any assertion failure. No pcb access, no copper.
"""


def to_dsn(x_mm, y_mm):
    return (x_mm * 1000.0, -y_mm * 1000.0)
import hashlib
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
SRC = os.path.join(BOARD, "out", "route", "tile_gw1nz_4l.dsn")
PROBE_DSN = os.path.join(BOARD, "out", "route",
                         "tile_gw1nz_fanout_probe.dsn")
PLAN = os.path.join(BOARD, "docs", "fanout_prep.json")
OUT = os.path.join(BOARD, "out", "route", "tile_gw1nz_4l_attach.dsn")
REPORT = os.path.join(BOARD, "out", "route", "dsn_4l_attach_report.json")

DIRS = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}
PLANE_NETS = {"GND", "VCC1V2"}
VIA = "Via[0-3]_600:300_um"
W_UM = 500          # power class track width


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def via_center(box, dname, ring):
    x0, y0, x1, y1 = box
    dx, dy = DIRS[dname]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if dx == 1:
        return (x1 + ring, cy)
    if dx == -1:
        return (x0 - ring, cy)
    if dy == 1:
        return (cx, y1 + ring)
    return (cx, y0 - ring)


def um(v):
    """format an already-micrometre value like the KiCad exporter."""
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s else "0"


def main():
    text = open(SRC).read()
    plan = json.load(open(PLAN))["planned_pads"]
    sites = []
    for e in plan:
        va = e.get("via_alternative") or {}
        if "kind" not in e or e["net"] not in PLANE_NETS:
            continue
        if not va.get("feasible"):
            continue
        vc = via_center(e["box"], va["escape_dir"], va["ring"])
        pc = ((e["box"][0] + e["box"][2]) / 2,
              (e["box"][1] + e["box"][3]) / 2)
        sites.append({"ref": e["ref"], "pad": e["pad"], "net": e["net"],
                      "pc": pc, "vc": vc})
    # frame assertion: every site pad-center (pcb mm) mapped through
    # to_dsn must appear as a stub START in the batch-10 probe DSN
    # wiring (same net); stub END flips the same way
    probe = open(PROBE_DSN).read()
    pwires = re.findall(
        r"\(wire \(path (\S+) 200\s+(-?[\d.]+)\s+(-?[\d.]+)\s+"
        r"(-?[\d.]+)\s+(-?[\d.]+)\)\(net (\w+)\)", probe)
    starts = {}
    for _l, sx, sy, _ex, _ey, n in pwires:
        starts.setdefault(n, []).append((float(sx), float(sy)))
    bad = []
    for s in sites:
        want = to_dsn(*s["pc"])
        pool = starts.get(s["net"], [])
        if not any(math.hypot(a - want[0], b - want[1]) < 0.5
                   for a, b in pool):
            bad.append((s["ref"], s["pad"], s["net"]))
    if bad:
        sys.exit(f"ATTACH FAIL: frame assertion broken for {bad[:4]}")
    # build wiring lines (B.Cu stubs -- power pads are B-side SMD)
    lines = []
    for s in sites:
        sx, sy = (round(v, 3) for v in to_dsn(*s["pc"]))
        vx, vy = (round(v, 3) for v in to_dsn(*s["vc"]))
        net = s["net"]
        lines.append(f"    (wire (path B.Cu {W_UM}  {um(sx)} {um(sy)}  "
                     f"{um(vx)} {um(vy)})(net {net})(type route))")
        lines.append(f'    (via "{VIA}"  {um(vx)} {um(vy)} (net {net})'
                     f"(type route))")
    wm = re.search(r"\n  \(wiring\n(\s*)\)\n\)\s*$", text)
    if not wm:
        sys.exit("ATTACH FAIL: empty (wiring) section not found")
    body = "\n".join(lines) + "\n"
    new = text[:wm.start()] + "\n  (wiring\n" + body + "  )\n)\n"
    open(OUT, "w").write(new)
    # self-check: nets 45 unchanged, wiring counts exact, no 2L via name
    wires = len(re.findall(r"\(wire \(path", new))
    vias = len(re.findall(
        r'\(via "Via\[0-3\][^"]*"\s+-?[\d.]+\s+-?[\d.]+\s+\(net ', new))
    nets = len(re.findall(r"\(net\s+\S+\s+\(pins", new))
    rep = {
        "tool": "dsn_attach_probe.py",
        "src": "out/route/tile_gw1nz_4l.dsn",
        "src_sha256_12": sha256(SRC)[:12],
        "out": "out/route/tile_gw1nz_4l_attach.dsn",
        "out_sha256_12": sha256(OUT)[:12],
        "attach_sites": len(sites),
        "by_net": {n: sum(1 for s in sites if s["net"] == n)
                   for n in sorted(PLANE_NETS)},
        "wire_width_um": W_UM,
        "via_padstack": VIA,
        "frame_assertion": "all pad centers match probe-DSN stub "
                           "starts at pcb-mm x1000 (tol 0.5 um-units)",
        "wiring_wires": wires, "wiring_vias": vias, "nets": nets,
        "sites": [{k: (s[k] if k != "pc" and k != "vc"
                       else [round(v, 3) for v in s[k]])
                   for k in ("ref", "pad", "net", "pc", "vc")}
                  for s in sites],
    }
    json.dump(rep, open(REPORT, "w"), indent=1)
    if not (len(sites) == wires == vias and nets == 45):
        print(f"ATTACH FAIL: {wires=}/{vias=}/{nets=}")
        sys.exit(1)
    print(f"ATTACH OK: sites={len(sites)} "
          f"(GND={rep['by_net'].get('GND')}, "
          f"VCC1V2={rep['by_net'].get('VCC1V2')}) width={W_UM}um "
          f"nets={nets} -> {OUT}")


if __name__ == "__main__":
    main()
