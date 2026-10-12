# regression worker checkpoint

Task: self-checking rev-A behavioral regression harness (BUILD). **DONE.**

## Ownership (respected)
- Own ONLY: `hardware/experiments/simple-tile/regression/**` + this checkpoint.
- `git status --porcelain` on tracked areas (hardware/simulation, kicad, firmware,
  tools, docs) = 0 lines; no commits made; only untracked `hardware/experiments/`
  shows (that dir was untracked before I started).

## Files created
- regression/tile_reg_pkg.vhdl — docs-derived reference model (protocol.md),
  presence-grid parse, per-frame wire order, traversal + G-edge/B_W timing,
  ragged reachability (`stop_by_bottom_hole`, contiguous heights).
- regression/tile_grid_tb.vhdl — generic W×H grid TB of REAL tile instances;
  sample-before-shift-clock at 20 MHz; bit-exact stream asserts; per-edge B_W
  flag asserts for every traversed column; per-edge T_clk/L_clk mux asserts;
  marker/flag frame decode + identity logs; ragged classification (silent vs
  framing-error); two latch-reset scans; REGPASS marker + std.env.finish.
- regression/run_regression.sh — container (tools/oss.sh) with host-ghdl fallback
  (clean blocker exit 2 if neither), clean workdir per run, per-config logs,
  pass = exit 0 AND REGPASS marker, 4 sed mutations on build/mutants/ copies that
  must fail IN SIMULATION (elab/infra errors never count as caught), pristine
  restore + sanity rerun.
- regression/README.md, regression/.gitignore (build/, logs/, *.vcd/*.ghw),
  regression/results.md (pinned env + outcome table).

## Results (two full runs, identical): runner exit 0, 19/19
13 topology configs PASS: single(rel/press/dist), column2, column16(dist/press),
row4, row16, grid2x3, grid_mixed (2/1/3 = original tile_tb shape), grid4x4
(dist/press), ragged_gap (1/5 tiles SILENTLY lost), ragged_hole (3/5 lost,
framing error markers=00). 4 mutations caught in-simulation: markers, flag-bit
swap, W-mux swap, B_W terminal count off-by-one. sanity_after_mutations PASS.

Pinned: container localhost/oss-cad-suite:2026-09-26 id 58f58619c735...;
GHDL 7.0.0-dev (llvm 21.1.8); date 2026-10-12T06:59:24Z.

## Verified behavioural facts pinned by the harness
- Wire order buttons(11..0), "11", L_endrow, T_endcol; first bit valid before
  first clock; idle tail = pulled zeros (weak 'L' at the tile output).
- next column's first true clock = edge 1 + 16*sum(h_i-1); B_W(bottom of col)
  sets exactly at its edge 16*h col-top pass.
- Legal shapes: bottom-aligned contiguous columns w/ any heights; ragged tops OK.
- Ragged: intra-column gap => tiles above silently lost (scan ends clean);
  missing column-bottom => overhang zeros trip marker framing error.
- TB gotcha: associated-but-undriven VHDL net is 'U' (not 'Z'); grid nets carry
  implicit 'Z' drivers to model open connectors (else tile clock/latch stall).

## Running jobs
- none. Nothing pending.
