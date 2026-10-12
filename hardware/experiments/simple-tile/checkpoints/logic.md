# Checkpoint: simple-tile logic experiments

Worker scope: `hardware/experiments/simple-tile/logic/**` and this checkpoint file only.
No edits elsewhere; no git commits. Started 2026-10-12.

## Task

Compare three 16-tile, 20 MHz shift-clock candidates (no MCU/LED/Hall on tile, open-flow
preference):

- **A: optimized discrete baseline** — rev-A seven-glue-IC + two 74LVC165A set, optimized
  (AUC parts are ≤2.7 V only; rev-A BOM already intends LVC/HC MPNs, electrical.md).
- **B: ATF22LV10C glue + two LVC165** — existing `hardware/gal/tile_glue.pld` (10/10
  macrocells, assembled by galette, never equivalence-checked) is the starting point.
  ATF22V10C = 5 V, ATF22LV10C = 3–5.5 V (Microchip doc0780).
- **C: ATF1502ASV full tile** — 3.3 V CPLD (AS = 5 V); practical fitter is proprietary
  (Microchip); prototype RTL + documented mapping only, no fit claims from register counts.

Deliverables in progress under `logic/`:

1. `equivalence/` — self-checking GHDL experiment: transliterated GAL equations vs rev-A
   glue (counter / sticky BW flag / latch-reset / DS mux / OE-TCLK selection), with the
   driven-low-vs-Z delta observed and counted explicitly, plus a W-toggle hazard probe.
2. `pld/` — golden copy of tile_glue.pld re-assembled via galette container and diffed
   against the committed tile_glue.jed; corrected true-OE variant (fewer outputs /
   external NPL inverter option) fit-checked with galette.
3. `cpld/` — full-tile HDL preserving /PL asynchronous transparent load (first bit valid
   before first clock, per docs/architecture/protocol.md scan sequence step 2);
   yosys proxy stats only; fitter/licensing/programmer gaps documented.
4. `timing/` — machine-readable datasheet values (JSON, with source+table+conditions per
   cell; no invented numbers; missing cells flagged) + calculator for the 20 MHz budgets
   (return clock+CQ+data mux vs 50 ns and vs controller half period 25 ns; counter /
   AND-OR-FF paths; per-hop setup/hold).

## Baseline user changes observed

- Working tree already has `?? hardware/experiments/` untracked (contains README.md,
  connectors/ — pre-existing, not mine). I add only `logic/` and `checkpoints/logic.md`.
- `hardware/gal/` (tile_glue.pld, .jed, .fus, .pin, .chp, README.md) is reference-only.

## Environment facts

- No host ghdl/yosys/galette/iverilog; podman present with images `localhost/galette`,
  `localhost/oss-cad-suite:2026-09-26` (GHDL+yosys), `docker.io/library/python:3.12-slim`.
- Host python3 = 3.14.7 (calculator can run on host, stdlib json only).
- Launcher: `tools/oss.sh <cmd>` (rootless, mounts repo at /work).
- Rev-A glue reference: docs/architecture/protocol.md (derived from rev-A schematic) and
  behavioral model hardware/simulation/tile.vhdl (read-only inputs to my experiment).

## Commands run so far

- `podman images`, `git log/status` (baseline, above).
- Tool sanity: GHDL 7.0.0-dev + yosys in `localhost/oss-cad-suite:2026-09-26`; galette
  0.3.0 in `localhost/galette`. Host python3 = 3.14.7.
- `tools/oss.sh make -C hardware/experiments/simple-tile/logic/equivalence equiv`
  -> **GLUE EQUIVALENCE: PASS**: 344 frames, 261,716 sample comparisons, 0 mismatches,
  3,630 documented TCLK Z-vs-0 deltas counted for gal v1 (the delta is exercised, not
  vacuous). gal v2 + CPLD match the reference EXACTLY, TCLK included. Found+fixed one
  TB bug (expected DS bit lagged a frame: signal-vs-argument read; all four DUTs agreed,
  which exposed it as an expected-model bug).
- `tools/oss.sh make -C hardware/experiments/simple-tile/logic/equivalence hazard`
  -> **HAZARD PROBE: PASS**: T_clk net rising edges ref=2 / gal_v1=3 / gal_v2=2;
  L_clk net = 3 in all designs (matches hand trace). gal_v1's only added edge class vs
  rev A: driven 0->1 if W returns while BCLK=1. Tri-state *release* edges (pulled-up
  float-up) are inherent to rev-A's own forwarding (both T_clk and L_clk).

## Files so far (all owned)

- logic/equivalence/ref_glue.vhdl      — rev-A 7-chip glue, true-Z T_clk ('125/'126)
- logic/equivalence/gal_glue.vhdl      — 1:1 transliteration of hardware/gal/tile_glue.pld
- logic/equivalence/gal_glue_v2.vhdl   — true-OE variant model (ext 1G04 on ~PL)
- logic/equivalence/tile_wrappers.vhdl — glue + 2x T74HCT165 (tile.vhdl wiring)
- logic/equivalence/glue_equiv_tb.vhdl — self-checking TB (directed + 250 random frames)
- logic/equivalence/hazard_tb.vhdl     — W-transition edge-count probe
- logic/equivalence/Makefile           — runs in oss-cad-suite via tools/oss.sh
- logic/cpld/tile_full.vhdl            — ATF1502ASV full-tile candidate (transparent /PL)

## Step 2 done: galette (commands + real results)

- `podman run ... localhost/galette tile_glue_golden.pld` (byte-copy of the committed
  pld, assembled in logic/pld/) -> clean; `diff results/tile_glue_golden.jed
  hardware/gal/tile_glue.jed` -> **byte-identical**: committed fuse map reproduces with
  current open galette.
- `tile_glue_truez.pld` (true-Z T_clk via HX=/TW+/BFIRST feedback into TCLK.E; NPL
  dropped to external 1G04) -> assembles clean (needed `HX.T` before `HX.E`; first
  attempt error recorded). Fuse listing: TCLK OE row carries one feedback literal
  (vs golden: OE row empty = always driven). LCLK OE row carries two literals
  (TW*BFIRST) as designed.
- `tile_glue_truez_npl.pld` PROBE (true-Z AND keep NPL = 11 macrocells) -> galette
  FAILS: "this pin can't be used as output" (pin 13 input-only; 10 OLMCs = pins
  14-23). This is the evidence for the external-inverter trade.
- Artifacts: logic/pld/results/{*.jed,*.fus,*.pin,*.chp,galette_log.md}.

## Step 3 done: CPLD proxy + architecture verification

- yosys (container) generic synth of cpld/tile_full.vhdl: 1x $aldff (16-bit transparent
  async-load chain) + $adff (4-bit counter) + $adffe (BW flag) = 21 FF bits, 2x $tribuf.
  Labelled PROXY in cpld/results/: synthesizable structure, NOT an ATF1502 fit.
- ATF1502ASV macrocell verification (DS20006485A text + prjbureau fusemap
  options/logic.html): FF has AR (PT3 or GCLR / pt3+GCLR) and AS (PT5) on SEPARATE
  product terms -> simultaneous async preset+clear per bit is structurally possible, so
  the transparent /PL mapping is architecture-consistent. STILL: no open fitter exists
  (fuseconv reads/writes fuses; place-and-route is Microchip ProChip, closed) -> the
  transparent-load hardware realization is UNVERIFIED/BLOCKED; simulation behavior
  passes, silicon mapping unproven. No fit/perf claim from register counts.

## Step 4 done: machine-readable timing + budgets (real values, real sources)

- Downloaded + pdftotext'd: doc0780M (ATF22LV10C §3.3 AC, LV-side DC tested at 3.6 V,
  CL=35 pF), TI SN74LVC165A SCLSA16, SN74HC161 SCLS297D (NO 3.3 V column -> UNKNOWN),
  SN74LV161A SCLS404F (3.3 V replacement), LVC2G08/32/125/126/1G04/2G74 SCES19x/20x,
  ATF1502ASV DS20006485A (-15, CL=35 pF), Lattice iCE40UP5K FPGA-DS-02008-2.4
  (tSU=-0.5 ns, tH=5.55 ns, tCO max 10 ns, no min).
- logic/timing/timing.json + calc_timing.py (host python3, stdlib). Full output:
  logic/timing/results/budget.txt. Headline numbers (50 ns period):
  - A discrete: worst hop setup slack +20.9 ns PASS; hold +3.3 ns PASS (min corners);
    flag RCO->AND->OR->FF t_su = 28.0 ns PASS (LV161A); HC161 variant UNKNOWN.
  - B GAL: hop slack LV10C-15 **+1.5 ns** (passes max corners, thin) / LV10C-10 +11.5 ns;
    hold +6.5 ns; BW D +23.5 ns (-15); counter fmax_int 50/80 MHz vs 20 PASS.
  - C CPLD: hop +22.0 ns (tCOP) / +19.0 ns (tCOP+tOD1 conservative); fCNT 76.9 PASS;
    BW path +23/+20 ns but flagged ESTIMATE pending fitter STA (no fit claim).
  - Controller return into iCE40UP5K: full period +36.0 ns (165) / +42.5 ns (CPLD);
    half period +11.0 / +17.5 ns. Return HOLD at FPGA: UNKNOWN (FPGA tCO min not
    published; methodology noted: current FSM samples-before-clock avoids it).

## Final step done: README + end-state verification

- Wrote `logic/README.md`: methods, results tables, licensing/programmer gaps, costs
  deliberately unquoted (not sourced), recommendation =
  **B2 (truez PLD + external 74LVC1G04, ATF22LV10C-10) conditional on proving LV10C
  programming on Afterburner**; fallback A with HC161 swapped to LV161A (HC161 has no
  3.3 V data — rev-A finding); C blocked on closed fitter + unverified AP/AR mapping.
- End-state re-run after `make clean all`: GLUE EQUIVALENCE: PASS (344 frames / 261,716
  samples / 0 mismatches / 3,630 documented Z-vs-0 deltas), HAZARD PROBE: PASS
  (T_clk ref=2/v1=3/v2=2; L_clk 3-3-3). Reproduced identically.
- Scope check: only `logic/**` + this checkpoint added; `git status --short` shows only
  `?? hardware/experiments/` (pre-existing untracked root). No commits made.

## Deliverables index (commands that reproduce)

- Equivalence+hazard: `tools/oss.sh make -C hardware/experiments/simple-tile/logic/equivalence clean all`
- PLD: `podman run --rm --userns=keep-id -v <pld-dir>:/work:Z -w /work localhost/galette tile_glue_golden.pld`
  (same for tile_glue_truez.pld; tile_glue_truez_npl.pld fails by design = fit evidence)
- CPLD proxy: `tools/oss.sh sh -c 'cd hardware/experiments/simple-tile/logic/cpld && yosys -m ghdl -Q -T yosys_proxy.ys -l results/results_yosys.log'`
- Timing: `python3 hardware/experiments/simple-tile/logic/timing/calc_timing.py`
  (datasheets in timing/datasheets/, URLs + tables per cell in timing.json)

## Review-fix round (independent reviewer, 2026-10-12)

Applied to owned files only; functional TBs untouched (counts re-confirmed identical at
the end of the previous session: equiv 344 frames / 261,716 samples / 0 mismatches / 3,630
documented deltas; hazard 2/3/2 and 3/3/3).

timing.json:
- added `assumptions` block: route_delays_ns (clock_fwd_hop, data_hop, latch_hop,
  ctrl_cable_out, ctrl_cable_in, fpga_sample_route) + controller_ns (latch_pulse_width,
  latch_deassert_to_first_clk), ALL null by default (no invented numbers; CLI overridable).

calc_timing.py (rewritten):
- verdicts now NECESSARY-ONLY / UNKNOWN / PROVISIONAL / PASS / FAIL (was: PASS everywhere
  with corners). Datasheet-only sums are component constraints, not sign-off.
- hop setup/max includes clock+data interconnect terms (null -> UNKNOWN system row).
- controller return setup adds FPGA tCO (10 ns max) launch + cable out/in + FPGA sampling
  route (null -> UNKNOWN); half-period bound incl. tCO now 1.0 ns slack (was 11.0).
- C candidate DS-mux rows are PROVISIONAL (tIN+tFSU is not a fitted mux; closed-fitter STA).
- hold helper fixed: negative hold slack = FAIL (was UNKNOWN).
- latch discipline split: local pulse width (need >= 8 ns from tW/tAW/max) vs
  deassert->first-clock recovery incl. 16-tile latch forward-chain aggregate
  (A 76.8 ns / B 240 ns / C 240 ns device-only necessary bounds) + skew param; both UNKNOWN
  system-level for the unimplemented 20 MHz controller; the 1.42 us FSM tick explicitly
  does NOT qualify. First-bit path conditional (aggregate latch path + capacitive recovery
  unmeasured). "sample-before-clock absorbs skew" assertion REMOVED; per-hop proven only,
  inter-tile phase/clock-chain checks flagged OPEN.
- CLI: `--set dotted.key=value`; `--selftest` synthetic zero/nonzero/negative/hold cases.

Commands + results (this round):
- `python3 calc_timing.py` -> results/budget.txt regenerated (system rows UNKNOWN, new
  component bounds as above).
- `python3 calc_timing.py --selftest` -> results/calc_selftest.txt: 7/7 SELFTEST-PASS
  (default UNKNOWNs; zero fill system==bound (29.1); +1ns fill gives +2.0 exactly (31.1);
  100 ns fill -> FAIL slack -179.1; synthetic hold 0.1 vs 0.5 -> FAIL).

README.md (revised with reviewer wording):
- hazard section retitled "characterization, NOT a safety proof"; W-settles-clock-low now
  stated as an FSM-dependent unproven ordering (BW sets synchronously at a rising edge;
  hot-plug fully asynchronous); marker bits no longer claimed to catch all corruption.
- equivalence method gap stated: models transliterate .pld source equations; no JEDEC-to-
  simulation check (golden .jed byte-reproduced ties source<->assembler only); single-tile
  equivalence != inter-tile topology.
- B1/B2 ranking only "on this evidence"; neither valid/recommended without topology
  validation + LV10C programming proof.
- no "whole flow open" claim: LV10C programmer support unverified; costs unquoted.
- recommendation replaced with "Conditional candidate summary" (B2 leading candidate,
  4 explicit conditions; A fallback; C blocked). No orders, no firmware changes.

Files changed this round: logic/timing/timing.json, logic/timing/calc_timing.py,
logic/README.md, results/budget.txt, results/calc_selftest.txt, this checkpoint.

Pending (owned by caller/main reviewer): conditions 1-4 listed in logic/README.md summary.
No running jobs. Task complete within scope.
