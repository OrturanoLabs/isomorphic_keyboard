# Checkpoint: simple-tile timing-aware chain experiment — FINAL

Worker scope: `hardware/experiments/simple-tile/timing-chain/**` and this checkpoint
file ONLY. No edits elsewhere; no git commits; nothing installed (vendor IBIS models
were *downloaded as data* into `timing-chain/si/models/` from TI via the documented
`hardware/si/models/fetch.sh` ids — not a tool install). Started 2026-10-12 as a
restart of an interrupted task; **no prior checkpoint or partial `timing-chain/`
existed** (verified at start). Read-only inputs used: `hardware/simulation/*.vhdl`,
`regression/tile_reg_pkg.vhdl` (golden frames), `logic/timing/timing.json`
(datasheet values), `hardware/si/*.py` (SI reference), `docs/architecture/protocol.md`.

## Environment (verified this session)

- No host ghdl/ngspice; container images used from the pre-existing set:
  `localhost/oss-cad-suite:2026-09-26` (GHDL 7.0.0-dev, image id 58f58619c735…)
  and `localhost/ngspice` (ngspice-44.2). Host python3 3.14.7 for the drift guard
  and the report generator (stdlib only).

## What was built (all under timing-chain/)

VHDL (ghdl --std=08 -fsynopsys):
- `vhdl/chain_timing_pkg.vhdl` — 34 datasheet constants from timing.json with
  corner selector; missing cells (ten/tdis min) use a documented 0 ns lower bound.
- `vhdl/logic74_timed.vhdl` — timed self-checking leaves (165A, 161A, 2G08, 2G32,
  1G04, 2G125, 2G126, 2G74): transparent async load in the '165, transport-delay
  outputs, setup/hold/recovery/pulse-width assertions (TIMING-FAIL: tokens).
- `vhdl/tile_timed.vhdl` — rev-A 9-chip tile per docs/architecture/protocol.md.
- `vhdl/chain_tb.vhdl` — W×H grid, synthetic route taps, configurable controller
  (latch guard/width, 20 MHz duty, sample lead), golden-frame comparison vs
  tile_reg_pkg (2 passes), per-net spurious-edge counters with exact expected
  counts, W-release/L-enable high-phase hazard assertions, DS-valid/contention
  monitors, TMARK instrumentation; pass = exit 0 AND TCREGPASS marker.
- `run_timing_chain.sh` — positives/negatives/sweeps matrix + host-side drift
  guard; negative runs require an in-simulation failure token and no marker
  (compilation/stop-no-end is a harness error, not a pass).

SI (ngspice):
- `si/chain_hop_20mhz.py` — 20 MHz burst (10 cycles, 25/25) + data pattern +
  W-release float; TI IBIS-lite models (typ); Rs 0/22/33/47; rev-A and
  rev-B-routed geometries; per-edge crossings (VIH 2.0 / VIL 0.8), contiguous
  dwell >= 4.3 ns, over/undershoot budgets; crossing-anchored windows;
  degenerate-deck selftest requires the checks to fire. `si/run_si.sh` harness.
- `si/si_lib.py`, `si/ibis_lite.py` = verbatim copies (read-ref) of hardware/si
  modules; `si/tile_hop_ibis_ref.py` = reference copy of the single-edge study
  used for a consistency check.

Results + docs: `results/` (logs, summary.txt, sweeps.txt, sync.log,
report.md via make_report.py), `si/results/`, `README.md`.

## Final verified results (actual runs)

Timing chain (full mode, run 2026-10-12 12:39Z): **16/16 PASS, TIMING-CHAIN PASS**.
- 11 positives PASS: N=1/2/16 cols × 4 rows and 16-high column; max corner
  (1.5 ns route, 30 ns high phase); min corner (1.5 ns route, 50 % duty);
  route=0 max corner; cross-corners latch-min/clk-max and latch-max/clk-min.
  Stream bit-exact vs golden frames incl. refetch pass; B_W/MUXSEL windows on
  column 1, exact edge counts everywhere, no spurious edges, DS valid.
- 5 negative runs all caught in-simulation (rc=1, correct token, no marker):
  recovery (guard 12 ns -> RECOVERY), clk×2.0 (-> MUXSEL, W window late),
  data×3.5 (-> STREAM), sample lead 45 (-> STREAM), documented finding
  max-corner+50 % duty (-> ENABLE-HIGH).
- Drift guard: SYNC-PASS 34/34 constants == logic/timing/timing.json.

Measured sweep table (datasheet corner, 1.5 ns synthetic route, 20 MHz):
- max corner, **all** of N=1/2/16×4 and 1×16: min latch guard 15 ns, sample-lead
  window 0.5..28 ns, min clock high 28 ns.
- min corner, all: guard 6 ns, lead 0.5..40 ns, 50 % duty OK (high 25 ns).
- The N-invariance is structural: forwarded clock and latch track per hop, so
  the binding margins are local to (1,1)/the last hop. Absolute per-hop drift
  measured: (c,1) lateness = 1.5+6.5·(c−1) ns (e.g. col 16 = 99.0 ns), upward
  hops +6.8 ns each (row 4 = +20.4 ns; col16 top = 119.4 ns ≈ 2.4 periods).

Key findings:
1. W-switch containment: at max corner + 1.5 ns route a 50 % duty clock lets
   the column-switch land ~2–3 ns PAST the local falling edge (net transition
   +28.6/29.1 ns vs fall at 26.5): the T_clk release models a spurious
   pull-up float edge and L_clk enables in the low phase. 28 ns high phase
   restores it (sweep); min corner is clean at 50 %. This is exactly the class
   of hazard the task targets; it is a finding about the *synthetic timing
   envelope*, with ten/tdis min unsigned.
2. Guard: recovery of SH/LD→first-clock binds at the FIRST tile: G ≥
   route+OR+INV+3.5−route ≈ 12.5 max corner (measured bracket 12–15),
   ≈ 5.2 min (bracket 5–6).
3. Controller sampling: data arrival at the controller is 19 ns (max) / 5 ns
   (min) after launch; the sample-lead windows measured above match.

SI (localhost/ngspice, ngspice-44.2):
- selftest: degenerate deck fails both checks as required (non-vacuous harness).
- Consistency with the pre-existing single-edge study: identical far/near
  overshoot/undershoot at the same corners (A rs0 66/76 %, B rs33 10/14 %,
  B rs22 17/27 %, B rs47 2/2 %).
- Burst outcome (typ corner, single-check per case): 9 pass / 15 fail.
  Clock far node passes ONLY for rev-A rs=47 (20 % over). Near node passes for
  rev-A rs≥33 and rev-B rs≥22. rev-B far node: no Rs value passes the clock
  checks at 20 MHz — repeated-edge dwell/double-cross (VIL-dn=3 every fall at
  rs=47) and/or overshoot. Data pattern over the same channel passes for
  rev-A rs=47 and rev-B rs=22/33 (per-cell chatter or over/under fails the
  rest). W-release float through the 10k pull-up: VIL->VIH ~189-247 ns with
  3-5 threshold crossings in every geometry — a slow, multi-crossing float
  edge, i.e. a real spurious-shift risk unless the W release is contained in
  the clock-high phase (see finding 1).
- No IBIS min/max corner exists in this IBIS-lite flow; budgets are documented
  assumptions. NOT a 20 MHz hardware pass.

## Remaining gaps (explicit)

- The interconnect is a fixed synthetic 1.5 ns/hop (or 0), not measured/field-
  solved; the SI hop models one line in two geometries at typ corner.
- ten/tdis min corners are unbounded (datasheet-only min); the '74 ~CLR
  proxy and the missing LV161A ~MR recovery cell remain as documented.
- Controller internals (FPGA sample route, its 5.55 ns hold requirement,
  PLL/cadence work) are not modelled — out of scope here (fpga workstream).
- The SI far-load tree (6 receivers over 134 mm) fails 20 MHz clock checks in
  the typ model for every Rs in the sweep — mitigation (stronger termination,
  fewer loads, Schmitt inputs or longer high phase) is a design decision, not
  part of this experiment's scope.
- Pull resistors in the VHDL are rail-strength steps; release-float RC physics
  is covered only by the ngspice float case.

## Running jobs

None. Reproduce:
`bash hardware/experiments/simple-tile/timing-chain/run_timing_chain.sh`
`bash hardware/experiments/simple-tile/timing-chain/si/run_si.sh`
`python3 hardware/experiments/simple-tile/timing-chain/results/make_report.py`

## Recovery round (2026-10-12 ~17:00Z, second session)

Caller reported: its SI verification run timed out at 300 s after selftest PASS
and container 9ed9a818fcab (python3 chain_hop + ngspice) was still RUNNING.

Recovery actions taken (inspection first, no duplicate expensive job):
- `podman ps` + `ps`: container alive, python `-c` wrapper, ngspice churning
  through decks (changing PIDs/tmpdirs between polls = healthy progress).
- Progress evidence: results mtimes (selftest.log written, main txt 0 bytes =
  python pipe buffer, never flushed); `podman exec` listed the live deck
  (fam B, rs=22 release = late-run position); host pipe consumers
  (podman-run client / tee) were GONE (dead pipe) so stdout would have died
  on flush, with only the PNG surviving via the mount.
- Chose to let it finish rather than kill: `podman wait 9ed9a818fcab` -> the
  container COMPLETED on its own at 16:54:58 (`SI-DONE rc=1`, 7m49s CPU);
  selftest had passed at 16:47. So the timeout was a TOOL timeout, not a
  stuck run. Retrieved the complete stdout from journald
  (`journalctl --user -t hungry_feynman`) into
  `si/results/chain_hop_20mhz_retrieved.txt` (37 lines).
- Independent verification results:
  * Timing chain full run (bg, completed): **SYNC-PASS 34/34**, **16/16 PASS**,
    verdict TIMING-CHAIN PASS (evidence: results/verify_full.log).
  * SI: journald-retrieved orphan run == byte-identical to my recorded run
    (32/32 per-case lines) == the hardened-runner rerun (below).
- Hardening applied (legitimate per caller): chain_hop_20mhz.py prints are
  now unbuffered, SI-PROGRESS start/done lines with per-case elapsed seconds
  (slowest case measured 67 s), and a 300 s per-case ngspice budget wraps the
  three decks with SI-TIMEOUT marking + sweep continuation. This changes no
  results (verified byte-identical).
- Regenerated results/report.md from the current logs.

No jobs running at checkpoint write. Files touched this round (all owned):
si/chain_hop_20mhz.py, si/results/* (retrieved/txt/png/log artifacts),
results/verify_full.log, results/report.md, this checkpoint.
