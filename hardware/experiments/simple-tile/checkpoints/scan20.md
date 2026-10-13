# scan20 checkpoint (workstream: 20 MHz 16-tile scan frontend/test engine)

Owned paths: `firmware/ice40/scan20/**` and this checkpoint file. Nothing
else will be modified; in particular the golden `firmware/ice40/src/top.vhd`,
`firmware/ice40/Makefile`, `firmware/ice40/build/*` (current bitstream) are
READ-ONLY, and all reference models under `hardware/simulation/`,
`hardware/experiments/simple-tile/{regression,fpga}` are READ-ONLY and used
by path only. No commits, no installs, no hardware claims.

## Baseline established (actual reads/commands, 2026-10-12)

- Golden controller `firmware/ice40/src/top.vhd`: 12 MHz `CLK_IN`, divider 17
  => `en_clk_scan` ~705.9 kHz; per bit = 2 scan ticks (sample in `get_bit`,
  THEN `BOARD_CLK` high in `c1`) => ~350 kHz shift rate; keyboard slots 0..9;
  coords 3 bit each (coord(5 downto 3)=row, coord(2 downto 0)=col); sticky err
  state, red LED; markers must be '11' else err.
- Protocol (`docs/architecture/protocol.md`): 16-bit frame, MSB(key0) first;
  bits 15..4 keys, 3,2 markers='11', 1=L_endrow, 0=T_endcol; sampling MSB-first
  `tile_stream(14 downto 0) & BOARD_DATA`.
- Timing model numbers (timing-chain/results/sweeps.txt, 20 MHz, route 1.5):
  min clock-high 28 ns (max corner) / 25 ns (min corner); latch deassert ->
  first clock guard >= 15 ns (max corner); sample-lead window 0.5..28 ns.
  50 % duty FAILS in max corner (neg_maxcorner_50duty, ENABLE-HIGH).
- Fixed reference tile model available READ-ONLY:
  `hardware/experiments/simple-tile/fpga/rtl/tile_fpga.vhdl`
  (SNAP_MODE="fall" = latch-fall shadow + '165 transparency, zero-delay) and
  expected-stream package
  `hardware/experiments/simple-tile/regression/tile_reg_pkg.vhdl`
  (parse_present/traversed_columns/reachable_frames/expected_stream/
  buttons_for, FRAME_BITS=16).
- Tools: podman image `localhost/oss-cad-suite:2026-09-26` EXISTS;
  `tools/oss.sh` works (git toplevel resolves). Host fallback present at
  `$HOME/.local/share/oss-cad-suite/bin` (yosys 0.63+89, nextpnr-ice40
  0.9-102, ghdl 7.0.0-dev, iverilog/verilator absent).
- `icepll -i 12 -o 100`: not exact; nearest 100.5 MHz (DIVR=0 DIVF=66
  DIVQ=3, VCO 804 MHz). 100.0 MHz infeasible from 12 MHz; document honestly.

## Plan (files to create, all under firmware/ice40/scan20/)

- src/scan20_core.vhdl — synthesizable scan engine. Generics:
  SYS_HZ (doc only), TICKS_PER_BIT (5), TICKS_HIGH (3 => 30/20 ns @100),
  SAMPLE_LEAD_TICKS (1 => sample one sysclk BEFORE launch), LATCH_TICKS,
  GUARD_TICKS (>=15 ns), FRAME_GAP_TICKS, IDLE_TICKS, TIMEOUT_TICKS,
  RECOVERY_TICKS, COORD_BITS (5), MAX_TILES (16), AUTO_RETRY.
  Semantics kept from golden: 16-bit frame, MSB-first shift, sample-before-
  shift, r1/latch, marker check '11', T_endcol/L_endrow grid walk, coords
  (col=1.. right-to-left, row=1.. bottom-up). Deviations are deliberate:
  >=5-bit coords, error->RECOVERY (auto re-scan) instead of sticky halt.
  Must complete 16th pulse (high+low) before FRAME_DONE. Registered outputs
  only (no combinational glitches on board_clk/board_latch).
  Observability strobes: dbg_sample/dbg_launch, frame_valid, scan_done.
- src/scan20_top.vhdl — standalone UP5K pico-ice top: SB_PLL40_CORE (params
  generic, verified vs icepll), core instance, status LEDs. Test fixture.
- sim/scan20_tb.vhdl + run_sims.sh — grids 1 / column2 / column16 / 4x4 /
  mixed against unchanged fall cores; self-checks: complete frame count,
  per-frame coords+data vs tile_reg_pkg, latch reload (2 scans), exact edge
  counts (16/frame, no extra edges), duty/guard measurement vs model numbers,
  sample-before-launch, marker-error injection + recovery, timeout recovery;
  mutants of scan20_core must all be caught.
- synth/scan20_up5k.pcf + run_synth.sh — yosys(ghdl)+nextpnr-ice40 UP5K
  sg48 with EXPLICIT --freq per config (100.5/120/60 attempts; pick best
  that closes; report achieved interior Fmax, no external-chain claims).
- README.md/RESULTS.md — actual achieved numbers, system gaps, no 20 MHz
  hardware claim.

## Status

- [x] recon + baseline numbers
- [x] RTL written (core/top exist from interrupted session; tb written, never run)
- [x] sims green (functional): 24/24 host AND container, exit 0
- [x] mutants caught: 4/4 (lead-pairing, 17th launch, duty, row-walk)
- [x] negative floors caught: 4/4 (duty<config assert, guard, lead window, latch)
- [x] synth/PnR: f60 CLOSES at explicit 60.000 MHz; f120/f100p5 honestly
      reported as NOT closing (nextpnr max ~62-69 MHz family); PLL params
      bitstream-verified vs icepll; no wrong-division 20 MHz anywhere
- [x] docs finalised: firmware/ice40/scan20/{README.md,RESULTS.md}

## Resume log (2026-10-13, after power interruption)

State found on disk vs old checkpoint:
- `src/scan20_core.vhdl` (482 lines), `src/scan20_top.vhdl` (223 lines),
  `sim/scan20_tb.vhdl` (617 lines) EXIST (written after last checkpoint);
  content reviewed, kept. run_sims.sh / synth/ / docs still MISSING.
- No leftover scan20 jobs running (only an unrelated krt router podman job
  and idle yosys-smtbmc workers belong to other workstreams - untouched).
- `fpga/system/results/machine.json` (READ-ONLY) confirms FPGA-SYSTEM 33/33,
  scope "SYNTHETIC corners; NOT hardware sign-off"; binding numbers adopted:
  deep-column (16-tall) guard >= 50 ns (max corner), lead window 1..30 ns,
  clock-high >= 22 ns (max corner) / tb floor 28 ns keeps 33.3 ns anyway.

Verified this session:
- `icepll -i 12 -o 120` => EXACT 120.000 MHz (DIVR=0 DIVF=79 DIVQ=3, VCO 960).
- `icepll -i 12 -o 60`  => EXACT 60.000 MHz (DIVR=0 DIVF=79 DIVQ=4, VCO 960).
- `icepll -i 12 -o 100` => 100.500 only (DIVF=66 DIVQ=3, VCO 804) - 100.0
  infeasible, documented, not claimed.
- Host tools present: ghdl 7.0.0-dev, yosys 0.63+89, nextpnr-ice40 0.9-102;
  container image localhost/oss-cad-suite:2026-09-26 exists (primary path).

Config table (shift rate = sysclk/TICKS_PER_BIT):
- f60  EXACT 20.000 MHz: 3 ticks/bit = HIGH 2 (33.33 ns) + LOW 1 (16.67 ns),
  GUARD 4 ticks = 66.7 ns (>= 50 ns deep-col max), LEAD 1 = 16.67 ns in window.
- f120 EXACT 20.000 MHz: 6 ticks/bit = HIGH 4 (33.33 ns) + LOW 2 (16.67 ns),
  GUARD 7 ticks = 58.33 ns (>= 50 ns; 6 ticks = exactly 50.0 ns physical but
  49.998 on the sim 1 ps grid, so GUARD 7 used consistently sim+synth),
  LEAD 1 = 8.33 ns in window.
- f100p5 20.100 MHz (+0.5%, NOT exact): 5 ticks/bit = HIGH 3 + LOW 2,
  GUARD 6 = 59.7 ns. Documented comparison config only.

## Running log (real commands -> real results)

- 2026-10-12 initial: reads as above; `command -v podman`=/usr/bin/podman,
  image exists; host cad-suite fallback verified by version strings;
  `icepll -i 12 -o 100` -> achieved 100.5 MHz (VCO 804) as logged above.
- 2026-10-13 resume: icepll 60/120 exactness confirmed (see above);
  next: write sim/run_sims.sh, compile tb, iterate to green; then synth.
- 2026-10-13 sims: wrote sim/run_sims.sh (24 expectations: 16 positive grids
  n1x1/col2/col16/4x4/mixed3x4+inj+timeout at BOTH f60/f120; 4 negative
  floors; 4 sed-mutants). TB fixes during bring-up (mine, none in golden
  refs): (a) quiet-recovery off-by-one -> REC_TICKS-1 post-strobe ticks
  (strobe tick itself is quiet; total quiet = REC ticks); (b) async +
  clocked duty monitors now exempt the abort-truncated fall (error strobe
  up); (c) abort_checked made episode-sticky; (d) script bugs (../../../
  depth, ghdl --elab-run, grep -mi, local var order). Result HOST:
  24/24 PASS, all logs in sim/build/logs/. Marker-injection tests show
  episodes=3 clean=2 errf=1 (recovery works); timeout mode errt=2 clean=0.
  Container parity confirmed 2026-10-13 (GHDL r515, 24/24).
- 2026-10-13 timing closure (UP5K sg48, explicit --freq per cfg): original
  single-big-FSM-process netlist peaked at 43-49 MHz interior Fmax
  (nextpnr). Restructures, each re-verified with the FULL 24/24 sim suite:
  (1) 16-bit shared counters prescaled (/8 for RECOVERY/TIMEOUT, 2048-tick
      coarse for IDLE; recovery >= REC+2 ticks, idle rounded up);
  (2) EVERY state exit / mid-pulse event via registered one-tick-early
      arm flags (fan-in = state AND arm); watchdog bite registered;
  (3) busy = registered decode of episode states (documented 1-tick lag);
  (4) frame decision inputs snapshotted (fr_ok/fr_top/fr_lend at the 16th
      pulse exit) + ST_FRAME/ST_ACT two-tick frame phase (invisible to the
      chain: the 16th pulse completes before ST_FRAME by construction);
  (5) all episode restarts hop through the 1-tick auto-forward ST_IDLE so
      entering ST_LATCH has a single-state fanin.
  Outcome (container, authoritative): f60 nextpnr 61.44/66.01 PASS at
  60.000+, icetime 16.42 ns (60.91 MHz) "PASSED"; host cross-check
  nextpnr 62.61/63.60 PASS, icetime 16.63 ns (60.14) PASS. f120: max
  66.05/68.57 -> NOT closing (reported); f100p5: max 62.50/69.19 ->
  NOT closing (reported; would be 20.100 MHz anyway). Chosen: f60 EXACT.
  PLL JSON bitstream params verified per cfg (pll_check): 60.0000/120.0000/
  100.5000 as designed. f60 utilisation: 190/5280 LC (3%), 1 PLL, 9 IO.
- final: README.md + RESULTS.md written with external-gap list (interior-
  only STA, synthetic guard origins, thin 60.9 MHz margin, never flashed).
  Golden firmware/Makefile/other workstreams untouched (git status clean
  outside scan20/ + this checkpoint at completion).
