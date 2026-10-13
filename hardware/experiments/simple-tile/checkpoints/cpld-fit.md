# cpld-fit checkpoint (workstream: ATF1502ASV CPLD fit for simple-tile)

Checkpoint path follows existing repo convention: `hardware/experiments/simple-tile/checkpoints/<workstream>.md`.

## Scope / ownership
- OWNED (only paths I write):
  - `hardware/experiments/simple-tile/cpld-fit/**`
  - `hardware/experiments/simple-tile/checkpoints/cpld-fit.md`
- READ-ONLY references (never modify): `logic/cpld/tile_full.vhdl`, `logic/*`,
  `regression/*`, `connectors/*`, `hardware/simulation/*`, anything else.
- Baseline: repo `isomorphic_keyboard-revc` at commit `6572e0f`
  ("Single-board tile: self-checking logic and drop-in connector experiments").
  No commits will be made. No firmware changes.
- Untracked dirs present at session start (OTHER workers' output, NOT mine, never touched):
  `fpga/`, `discrete-spld/`, `connector-next/`, `checkpoints/{fpga,discrete-spld}.md`,
  plus this checkpoint file itself (untracked).

## Task understanding (CORRECTED 2026-10-12 session 2)
- CORRECTION of the typo carried in this checkpoint since session 1: the target is
  20 MHz scan clock, 16-tile grid, one chip per tile, **NO Hall keys, NO LED, NO MCU**
  (tile side). NOT "Hall-sensor keys + LED per key". Confirmed by `logic/README.md` §0:
  "no tile-side MCU/LED/Hall".
- Advance the ATF1502ASV (TQFP-44, 32 macrocell, 3.3 V, one chip) candidate:
  * real TQFP44 pin map + per-pin I/O capability (DS20006485A Tables 1-6/1-7)
  * macrocell architecture: orthogonal AP (async preset) / AR (async reset)
    product terms implementing the 74x165-transparent parallel load
  * pin constraint file + checker script
  * self-checking Verilog TB: candidate vs actual rev-A behaviour (74HC165-class
    transparent /PL, first bit valid before first clock, frames/flags/mux)
  * Yosys -> techmapped EDIF export; explicit-fitter wrapper that fails loudly
    when no licensed fitter is provided. NO generic-FF-count fit claims.
  * BOM / JTAG pads / power (sourced from DS20006485A) + 20 MHz phase timing gaps.
- Device fit: licensed fitter only IF already installed. Verified session 1: NONE
  (no fit1502/cupl/prochip, no wine). Must NOT install proprietary tools or Wine.
- Self-checking sim via container `localhost/oss-cad-suite:2026-09-26`
  (image id 58f58619c735..., GHDL 7.0-dev, Icarus 14.0, Yosys 0.69+154) via
  `tools/oss.sh`.

## Tool inventory (verified 2026-10-12)
- host: zsh on Linux x86_64, python 3.14.7, podman; NO yosys/ghdl/iverilog on PATH
- container localhost/oss-cad-suite:2026-09-26 id 58f58619c735:
  Yosys 0.69+154 (30d62572e-dirty), GHDL 7.0.0-dev (llvm code gen),
  Icarus Verilog 14.0 devel. Invoke via `./tools/oss.sh <cmd>` from repo root.
- NO licensed Atmel/Microchip fitter (fit1502 etc.) anywhere on system;
  wine missing. Galette container exists (localhost/galette, GAL tools).
- Session-2 note: NO network access (prjbureau.com unreachable) — fusemap-detail
  claims from prjbureau are cited as secondary, not re-verified.

## Preserved state
- Session-1 checkpoint content (scope, tool inventory) preserved and corrected above.
- `cpld-fit/` did NOT exist at session-2 start: no partial RTL/synth work to preserve.

## Progress log
- [x] explored repo, confirmed baseline 6572e0f (session 1)
- [x] verified tool inventory (session 1; re-verified session 2)
- [x] read reference RTL/docs: tile_full.vhdl, yosys_proxy, logic/README, RESULTS,
      regression harness+results, protocol.md, 74hc165.vhdl, timing.json,
      DS20006485A text (pinouts, macrocell, AC/DC, JTAG, packaging, ordering)
- [x] candidate Verilog `cpld-fit/src/tile_cpld.v` (per-bit AP/AR formulation,
      race-free ordered ar/ap comb writer, !latch clock guard)
- [x] self-checking TB `cpld-fit/src/tile_cpld_tb.v` (DUT vs tile.vhdl-structure
      REF vs docs-derived EXP; 2 scans: 2-tile column traversal + rlatch reset,
      4-edge tails; transparency wiggle; first-bit-before-first-clock;
      frames/markers/B_W timing/tclk-lclk 'Z' mux)
- [x] sim RUN (real): `bash cpld-fit/sim/run_sims.sh` exit 0
      * candidate: PASS, 1180 checks, 0 errors (Icarus 14.0 in container
        58f58619c735...); log results/logs/sim_tile_cpld.log
      * mutant syncload: CAUGHT precisely on first-bit + transparency checks
      * mutant flagswap: CAUGHT on stream bits + B_W timing
- [x] Yosys ATF1502 techmap -> EDIF (real run): `bash cpld-fit/synth/run_synth.sh`
      exit 0; stats pre/post: 16x $dffsre -> 16x ATF1502_FF_D_SR_CE (AP/AR
      chain), 4-bit $adff -> 4x ATF1502_FF_D_AR (cnt), 1x $adffe -> 1x
      ATF1502_FF_D_AR_CE (bw), 2 z-muxes -> 2x ATF1502_OBUF_TRI (tclk/lclk OE);
      60 generic glue cells remain (fitter packs into PTs). EDIF validated:
      balanced s-expr, 5 device cell types, 17 ports, buttons[b]->member(11-b)
      mapping consistent, exact instance counts. NOT a fit. EDIF sha256
      269614f4e590bda23126e9beffd1a80a7d51f5744f4e4c06da63802e57db6c2e.
- [x] TQFP44 pin map + constraint CSV + checker (real run):
      `constraints/tile_cpld_tqfp44.csv` + `constraints/check_pins.py`
      (capability DB transcribed from DS Tables 1-6/1-7). PASS: 28 constraints,
      26 pinned + 2 internal; accounting reconciles 44 = 25 used MC + 4 JTAG
      (1,7,26,32) + 2 PD spares (5,19) + 1 spare (18) + GCLK1(37 used, bclk) +
      3 unused dedicated (38,39,40) + 4 VCC + 4 GND. Negative control (bclk on
      GCLR pin, tclk on TMS pin) correctly FAILS with 3 errors, exit 1.
- [x] fitter wrapper `fit/run_fitter.sh` + all four paths tested: no-arg ->
      exit 2 FIT-BLOCKED; bogus path -> 2; .exe w/o wine -> 2; dummy exec ->
      invoked w/ EDIF, exit 0 propagated (evidence: results/logs/fitter_wrapper_selftest.txt)
- [x] docs written: README.md, docs/tqfp44-pinmap.md, docs/ap-ar-mapping.md,
      docs/bom-jtag-timing.md (BOM sourced: ATF1502ASV-15AU44 per DS ordering
      section, 9x10k + 7x33R from rev-A schematic, decoupling marked
      unsourced-recommendation; JTAG pads 1/7/26/32 + VCC/GND; ICC numbers
      typ-only; 20MHz phase table T0..T6 NECESSARY-ONLY/PROVISIONAL/UNKNOWN).
- [x] FINAL clean rerun 2026-10-12 (~13:05 UTC): rm -rf results/build results/logs
      then: sim run exit 0 (1180 checks, 0 errors; both mutants caught);
      synth run exit 0 (EDIF identical sha256 269614f4e590bda23126e9beffd1a80a7d51f5744f4e4c06da63802e57db6c2e);
      check_pins exit 0; fit/run_fitter.sh no-arg exit 2.
- [x] workspace hygiene re-verified: zero tracked-file modifications;
      only owned paths added; other workers' dirs (fpga/, discrete-spld/,
      connector-next/, timing-chain/, repo-root checkpoints/) untouched.

## Running jobs / job IDs
- none (all runs complete)

## Next steps (BLOCKED on externals, in order)
1. User provides a licensed ATF1500 fitter path -> `fit/run_fitter.sh <path>`
   produces the fit report + .jed; verify AP and PT-AR both allocated per
   chain macrocell; POF2JED with `-power_reset` (DS power-up note).
2. Fitted STA fills the PROVISIONAL timing rows; system rows stay UNKNOWN
   until timing.json null assumptions are measured (timing-chain workstream).
3. Program one ATF1502ASV-15AU44 over the JTAG pads (TDI=1, TMS=7, TCK=26,
   TDO=32 + VCC/GND) and bench-check the TB vectors (transparent load,
   first-bit-before-clock) at 20 MHz.

## Next steps
1. `mkdir cpld-fit/{src,synth,fit,constraints,docs,results}`; write RTL + TB; run in container.
2. Yosys techmap flow -> EDIF + real stats.
3. Constraints + checker; fitter wrapper; docs with DS citations.
