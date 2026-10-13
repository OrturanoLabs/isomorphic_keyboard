# Checkpoint: simple-tile fpga/system experiment — FINAL

Worker scope: `hardware/experiments/simple-tile/fpga/system/**` and this
checkpoint file ONLY. No edits to existing fpga/rtl / fpga/sim /
timing-chain / logic / regression / docs / controller firmware. No git
commits. No installs. `-revc` material never touched nor recreated.
Verified at end: `git status --short` shows only my two owned paths as new
(checkpoints/fpga-system.md + fpga/system/ inside the previously-untracked
fpga/ tree); all other M/D/?? entries predate this task. Golden RTL hashes
unchanged and pinned (below).

## Deliverables (all under fpga/system/)

- `tools/extract_delays.py` -> `results/interior_delays.json`: verbatim
  fitted anchors from the EXISTING synth artifacts, per-value sha256
  provenance; pads/TBUF/interconnect/recovery explicitly unknown:true.
- `cfg/corners.json`      — explicit synthetic corners (never sign-off).
- `cfg/sources.json`      — pinned sha256 of read-only references + the
  26-IO_LOC pin-plan check target (synth/tile_gw1nz.cst == 26).
- `vhdl/system_timing_pkg.vhdl` — 39 constants transcribed from corners.json.
- `vhdl/tile_sys.vhdl` — timed FPGA tile: per-pin pad delays (cst pull
  config), merged one-pad clk node, separate latch legs (the OR), lumped
  dout/latcho/B_W delays, TBUF en/dis/pd on T_clk/L_clk, leaf budgets
  SNAP-XDOM / SNAP-WINDOW / CLK-PULSE, dbg taps, sysclk passthrough.
- `vhdl/chain_sys_tb.vhdl` — W x H grid + 20 MHz controller; golden-frame
  STREAM incl. FIRSTBIT, B_W + MUXSEL Z windows, per-tile resolved-clock
  EXACT edge counts (correct cascade math: bottom tile sees
  nbits-rel_thru(c-1), upper tiles 16*(hc-1) per pass), latch-fall counters
  (LATCH-GLITCH), RELEASE-HIGH / ENABLE-HIGH / W-LOWPHASE, DS-VALID,
  CONTENSION, DATA-SETTLE + arrival TMARKs, SYSPASS/SYSSUMMARY.
- `vhdl/latch_or_tb.vhdl` — latch-OR sources B/R/skewed-both + glitch +
  snapshot-window + safe key-change scenarios.
- `vhdl/track_cdc_tb.vhdl` — track-mode sysclk recovery contract sweep.
- `run_system.sh` — drift guard -> container sims -> host report.
- `results/`: interior_delays.json, machine.json (fpga-system/results/v3),
  report.md, summary.txt, sweeps.txt, sync.log, env.log, per-run logs.
- `README.md`.

## Environment (verified this session)

- Host: ghdl/yosys/nextpnr NOT on PATH (container-only flow).
- Container `localhost/oss-cad-suite:2026-09-26` id 58f58619c735...
  (GHDL 7.0.0-dev). Host python3 3.14.7 stdlib-only scripts.
- Authoritative run #4: ~8 min wall (sims under `--stop-time=60ms`),
  33/33 PASS, then make_report.py on the host.

## Final verified results (actual run #4, FPGA-SYSTEM PASS 33/33)

Positives 18/18: N=1/2/16 x 4 rows, 1x16 column, 4x4 grid, all at corners
syn_min/fit/syn_max (20 MHz, 1.5 ns synthetic hop, 50 % duty), 2 passes
each, bit-exact golden frames incl. first-bit-before-clock at every corner;
plus route=0 refs and 3 ns hop @ 30 ns high. Units 5/5: latch-OR B-leg /
R-leg / 7 ns-skewed both capture identically (single local fall, correct
frame); key change 30 ns before the fall captures the new value; track-mode
contract sweep 40 steps: captured 34, stale-in-window 6, contract held at
every offset >= TSYS.
Negatives 8/8, each failing on its REQUIRED assertion token (never
infrastructure): guard 0 / 4 ns -> SNAP-XDOM; deep column 16 @ max, g=25 ->
SNAP-XDOM; W-switch synthetic 2.5x stress @ max -> W-LOWPHASE; 3 ns hop @
25 ns high -> RELEASE-HIGH; sample lead 45 -> STREAM; lead 25 + 20 ns
settle req -> DATA-SETTLE; OR-glitch -> LATCH-GLITCH; key change inside the
snapshot window -> SNAP-WINDOW (measured 0.25 ns < 0.5 ns req); track
short-latch (2 ns high) -> STREAM.

Measured limits at 20 MHz (synthetic corners, exploration):
- Latch guard (deassert -> first clock): >= 10 ns fit / 15 ns max for
  4-deep columns (any width); >= 25 ns fit / 50 ns max for a 16-high
  column. Bound rule guard - d_hop*(depth-1) >= 4.9 ns (d_hop =
  latch-forward - TBUF clock per hop ~ 1.3 fit / 3.0 max). The 16-high
  column at max with the "obvious" 25 ns guard genuinely FAILS
  (SNAP-XDOM) — new system constraint surfaced by this model.
- Sample-lead window: 1..30 ns fit/max (1..40 min).
- Clock high >= 15 ns fit / 22 ns max (W-switch containment); 30 ns at
  3 ns hop max.
- W-enable phase: all column switches land mid-high (+10 ns fit / +17 ns
  max after the source rise) at nominal; low-phase exposure needs
  2.5x synthetic stress at fit / ~1.0-1.5x at max (wlow sweep boundary).
- Returned data arrives at the controller 9 ns (fit) / 14 ns (max) after
  launch (per-hop tracking is structural as in the discrete chain).

## Ground rule evidence

- Golden RTL, frames, protocol, logs: sha256 pinned in cfg/sources.json;
  `results/check_system_sync.py` SYNC-PASS at run start AND end (39
  constants, anchors, 10 hashes, 26 IO_LOC).
- Interior anchors (gw1nz fall post-route): Fmax 254.84 MHz, clk2q 0.46,
  crit total 3.93 (1.36 logic + 2.57 routing), xdom latch->clk 4.86 (+0.04
  setup), track sysclk->clk 5.59.

## Honest limits / remaining unknowns

- NOT hardware sign-off: pads/TBUF/interconnect/recovery windows are
  synthetic; no DS861; no metastability model; no min-delay analysis from
  the tool (min corner = synthetic proportion); route = synthetic hop.
- The discrete baseline comparison (logic/timing census) stays with the
  discrete workstream; this run references it read-only.
- FPGA-internal behaviour is the golden zero-delay RTL: the cross-domain
  and window relationships are enforced as measured budgets/assertions
  around it (cannot model FF metastability).

## Cleanup / rerun history (audit)

- Run #1 (PID 1962036): dress rehearsal, 26/32 — exposed the runner
  log-naming bug + two TB sequencing bugs + the r30 duty finding.
- Run #2 (PID 2036450): 31/33 — all chain positives/negatives correct;
  the two still-failing units (u_snap_window, u_track_shortlatch) used
  pre-fix TB code; fixed and verified standalone.
- Run #3 (PID 2104303): **33/33 FPGA-SYSTEM PASS** (was authoritative).
- Incident: a later `quick` smoke clobbered summary.txt (mode-shared file
  name). Fixed (mode-named summaries), full matrix re-run.
- Run #4 (PID 2208707): **33/33 FPGA-SYSTEM PASS** — the authoritative
  artifact set now in results/ (summary.txt, machine.json, report.md,
  sweeps.txt, per-run logs). machine.json schema fpga-system/results/v3.
- Post-run hygiene: misnamed run-#1 logs removed, elab binaries cleaned,
  runner now self-cleans.

## Running jobs

None. Reproduce:
```
cd hardware/experiments/simple-tile/fpga/system
python3 tools/extract_delays.py        # drift->results/interior_delays.json
python3 results/check_system_sync.py   # SYNC-PASS drift guard
bash run_system.sh                     # full 33-run matrix + sweeps
bash run_system.sh quick               # 3-run smoke
python3 results/make_report.py         # machine.json + report.md
```
