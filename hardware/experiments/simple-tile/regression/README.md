[//]: # (SPDX-License-Identifier: CERN-OHL-S-2.0)

# rev-A tile scan regression harness

Self-checking *behavioural* regression for the rev-A tile scan protocol. The DUT
is the unmodified behavioural model in `hardware/simulation/` (`74hc165.vhdl`,
`tile.vhdl`). Expected streams are generated independently from the documented
protocol (`docs/architecture/protocol.md`) in `tile_reg_pkg.vhdl`; the generic
grid testbench `tile_grid_tb.vhdl` instantiates real tiles, wires only physically
present neighbours, and fails (nonzero simulator exit) on any deviation.

Zero-delay sims at a 20 MHz shift clock establish **functionality only**, not
achievable hardware timing.

## Run

```
hardware/experiments/simple-tile/regression/run_regression.sh
```

* Uses `tools/oss.sh` (OSS CAD Suite container) when the image exists, otherwise
  host `ghdl`; mode + `ghdl --version` + image id are pinned into `logs/env.log`.
* Per-config logs in `logs/<name>.log`; overall table in `logs/summary.txt`.
  `build/` and `logs/` are git-ignored; no VCD is written.
* A config passes only when GHDL exits 0 **and** its `REGPASS <name>` marker is
  in the log, so "sim crashed before the end" can never look like a pass.

## What is checked (every config, two full scans each)

* Bit-exact stream vs the docs-derived reference, sampled *before* each shift
  clock (firmware `get_bit` → `c1` discipline; first bit valid before the first
  clock is checked explicitly).
* Per-frame markers `11`, flag bits and tile identity (key pattern embeds (c,r)).
* `B_W` column-end flag of every traversed column's bottom tile, checked on
  *every* clock edge against the documented timing (sets exactly when the
  column's top frame has passed; cleared again by the next latch).
* `T_clk`/`L_clk` selection (W mux) of the controller tile on every edge:
  clock forwarded up while the column is being read, gated to `'Z'` and
  re-driven left from exactly the documented flip edge on.
* Idle tail after the last frame (pulled zeros — a complete scan leaves nothing
  behind).

## Topologies

Columns are `c = 1..W` right-to-left (controller on bottom of `c=1`), rows
bottom-up; `PRESENT` strings list row 1 first, within a row `c=1..W`.

| config | shape |
|---|---|
| `single_rel/press/dist` | 1×1, keys none/all/distinctive |
| `column2_dist`, `column16_dist/press` | 1×2, 1×16 long column (16-tile target) |
| `row4_dist`, `row16_dist` | 4×1, 16×1 pure rows (degenerate per-tile columns) |
| `grid2x3_dist`, `grid4x4_dist/press` | uniform 2×3 and 4×4 (16 tiles) |
| `grid_mixed_dist` | column heights 2/1/3 — the hardware-tested tile_tb shape (ragged *tops* are legal) |
| `ragged_gap_detect` | gap inside a column: tiles above are unreachable. Detected as **silent loss** — the scan ends cleanly, no framing error; only tile accounting catches it |
| `ragged_hole_detect` | bottom tile of a column missing while tiles exist above/left of it: the next frame reads pulled zeros → **framing error** (markers `00`) |

Ragged layouts are *characterised*, not assumed legal: the TB asserts which tiles
become unreachable and how the firmware would observe it.

## Mutation stage (harness self-test)

`run_regression.sh` copies `tile.vhdl` to `build/mutants/`, applies one sed edit,
and requires the regression to **fail**; a mutation that passes makes the suite
fail:

| mutation | breaks |
|---|---|
| `mut_markers` | fixed frame marker `"11" → "10"` |
| `mut_flagbits` | swaps `L_endrow`/`T_endcol` frame bits (flag bit mapping) |
| `mut_wsel` | swaps the W data-mux inputs (chain traversal source) |
| `mut_bwcount` | `B_W` terminal count 15 → 14 (column-end flag one bit early) |

After the mutation stage the pristine DUT is re-analysed and sanity-re-run.

## Notes for testbench writers

An associated but undriven `std_logic` net is `'U'`, **not** `'Z'`: the tile's
documented "open connector" behaviour (pin pull-ups) only appears for
*unassociated* ports. The grid TB therefore gives every inter-tile net an
implicit `'Z'` default driver. With a bare-'U' net on a clock/latch input the
tile stalls silently (observed: all-zero streams).
