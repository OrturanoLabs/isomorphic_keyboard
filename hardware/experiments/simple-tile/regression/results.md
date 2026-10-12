[//]: # (SPDX-License-Identifier: CERN-OHL-S-2.0)

# Regression results — rev-A tile scan harness

Actual recorded run. Regenerate with `run_regression.sh` (writes `logs/`;
this file mirrors one real run for the record).

## Pinned environment (from `logs/env.log`)

- date_utc: 2026-10-12T07:00:35Z (full clean-workdir run, runner exit 0)
- mode: container `localhost/oss-cad-suite:2026-09-26`,
  image id `58f58619c735ff1e6f1ce5b71a318dacbf2e8823231d96ddd4862975dbcf2640`
- simulator: GHDL 7.0.0-dev (6.0.0.r515.g6ea214092.dirty) [Dunoon edition],
  GNAT 14.3.0, llvm 21.1.8
- kernel: Linux 7.2.8-arch1-2 x86_64
- flags: `ghdl -a --std=08 -fsynopsys --workdir=build`,
  `ghdl elab-run ... tile_grid_tb -gNAME=<cfg> <generics> --stop-time=60us`
- host fallback pathology: with no container image and no host ghdl the runner
  reports the blocker and exits 2 (tested with a bogus OSS_IMAGE).

## Outcome: REGRESSION PASS — 19/19 (13 topology configs + 4 mutations + restore sanity + ragged detections included)

Topology configs (bit-exact stream vs docs-derived reference, per-edge B_W flag
timing and T/L clock-mux checks, markers + flag bits per frame, idle tail, two
latch-reset scans each):

    PASS  single_rel            1x1, keys released
    PASS  single_press          1x1, all keys pressed
    PASS  single_dist           1x1, distinctive keys
    PASS  column2_dist          vertical 1x2
    PASS  column16_dist         vertical 1x16 long column (16-tile target)
    PASS  column16_press        1x16, all pressed
    PASS  row4_dist             horizontal 4x1
    PASS  row16_dist            horizontal 16x1
    PASS  grid2x3_dist          uniform 2x3
    PASS  grid_mixed_dist       column heights 2/1/3 (hardware-tested tile_tb shape)
    PASS  grid4x4_dist          uniform 4x4 (16 tiles)
    PASS  grid4x4_press         4x4, all pressed
    PASS  ragged_gap_detect     gap inside a column -> SILENT loss of 1/5 tiles
                                (scan ends cleanly; only tile accounting reveals it)
    PASS  ragged_hole_detect    missing bottom tile of a column -> 3/5 tiles lost,
                                overhang zero frame flags framing error (markers=00)

Mutation self-test (temp copies in build/mutants/, each MUST fail in simulation):

    PASS  mut_markers   ("11"->"10")              caught: bit13 marker mismatch
    PASS  mut_flagbits  (swap endrow/endcol)      caught: flag timing -> mux check
    PASS  mut_wsel      (swap W data mux inputs)  caught: frame1 key mismatch
    PASS  mut_bwcount   (B_W terminal count 15->14) caught: mux flips one bit early
    PASS  sanity_after_mutations                  pristine DUT restored and re-passed

## Documented behaviour the harness pins down

- Wire order per 16-bit frame (first bit valid BEFORE the first shift clock,
  20 MHz behavioural): `buttons(11) .. buttons(0)`, markers `11`,
  `L_endrow` ('0' = tile to the left), `T_endcol` ('1' = top of column);
  firmware frame bit 15..0 is this wire order reversed.
- Traversal: columns right-to-left, bottom-to-top inside a column, seamless
  frames; next column's first true clock = edge `1 + 16 * sum(h_i - 1)`.
- Column-end flag `B_W` of a column's bottom tile sets exactly when the column's
  top frame has passed (its own edge `16*h`), so leftward hop starts one column
  slot earlier than the last frame's final bit position.
- Legal: bottom-aligned columns, contiguous from row 1, any per-column height
  (ragged tops are fine), bottom tile present in every traversed column.
- Ragged = unsupported, characterised rather than assumed: internal column gap
  loses the tiles above it with NO firmware-visible error (silent); a missing
  bottom tile aborts the chain and the next frame's zero markers produce a
  framing error.
