# fpga/system: timing-aware FPGA-chain validation — report

Verdict: **FPGA-SYSTEM PASS** (33 passed, 0 failed).  
Scope: one-FPGA tile (GW1NZ-LV1QN48 lead, `SNAP_MODE="fall"`) in the 20 MHz shift-clock chain (up to 16 tiles). **This is synthetic-corner exploration, not hardware sign-off.**

## Ground rules that this run enforces

- Golden behaviour: bit-exact vs [`tile_reg_pkg`](../../regression/tile_reg_pkg.vhdl) frames (2 passes) on N=1/2/16x4, 1x16, 4x4 grids.
- Tile leaf = UNMODIFIED golden RTL [`tile_fpga.vhdl`](../rtl/tile_fpga.vhdl) wrapped by [`tile_sys.vhdl`](../vhdl/tile_sys.vhdl) (pad delays, latch-OR on separate pads, TBUF Z timings, leaf assertions).
- Interior delay anchors are FITTED (post-route nextpnr/icetime max-analysis), extracted verbatim by [`tools/extract_delays.py`](../tools/extract_delays.py) into [`interior_delays.json`](interior_delays.json); pads/TBUF/interconnect are SYNTHETIC ([`cfg/corners.json`](../cfg/corners.json)).
- Drift guard [`results/check_system_sync.py`](check_system_sync.py): package==corners, anchors==extraction, reference hashes pinned, 26 IO_LOC pin plan.

## Fitted interior anchors used (GW1NZ fall, post-route)

| quantity | value | source |
|---|---|---|
| shift-clk interior Fmax | 254.84 MHz | ../synth/results/logs/gw1nz_fall_nextpnr.log |
| FF clk-to-q (critical path elem) | 0.46 ns | same |
| critical path total (logic+route) | 3.93 ns | same |
| cross-domain negedge latch -> posedge clk | 4.86 ns | same |
| track-mode posedge sysclk -> posedge clk | 5.59 ns | ../synth/results/logs/gw1nz_track_nextpnr.log |

Unknown by default (synthetic corners only): board_interconnect_ns, ff_recovery_window_ns, min_delay_analysis, pad_input_delay_ns, pad_output_delay_ns, tbuf_enable_disable_ns.

## Measured sweep table (synthetic corners, 20 MHz)

| N cols | H rows | corner | min guard ns | sample lead window ns | min clock high ns | W-low max OK scale % |
|---|---|---|---|---|---|---|
| 2 | 4 | fit | 10 | 1..30 | 15.0 | 250 |
| 16 | 4 | fit | 10 | 1..30 | 15.0 | 250 |
| 1 | 16 | fit | 25 | 1..30 | 15.0 | 200 |
| 2 | 4 | max | 15 | 1..30 | 22.0 | 100 |
| 16 | 4 | max | 15 | 1..30 | 22.0 | 100 |
| 1 | 16 | max | 50 | 1..30 | 22.0 | 100 |
| 1 | 4 | fit | 10 | 1..30 | 15.0 | 250 |
| 2 | 4 | min | 3 | 1..40 | 15.0 | 300 |
| 16 | 4 | min | 3 | 1..40 | 15.0 | 300 |

## Actual constraints the 20 MHz run needs (synthetic corners)

- latch deassert -> first shift clock (guard): **>= 10 ns fit / 15 ns max** for 4-deep columns (any column count); **>= 25 ns fit / 50 ns max** for a 16-high column.
  Bound rule: `guard - d_hop*(depth-1) >= 4.9 ns` (fitted xdom anchor 4.86+0.04); d_hop = latch-forward chain minus TBUF clock chain per level (~1.3 fit / 3.0 max ns).
- sample lead window (before each rising edge): **1..30 ns fit / 1..30 ns max** (min corner 1..40).
- clock high phase (W-switch containment): **>= 15.0 ns fit / 22.0 ns max** at the 50 ns period; at 3 ns synthetic hop the max corner needs 30 ns.
- returned-data arrival at the controller: measured 9..14 ns (fit..max) after the launch edge at the receiving tile's pin.

## Runs

```
PASS   pos_n1x4_fit
PASS   pos_n2x4_fit
PASS   pos_n16x4_fit
PASS   pos_n1x16_fit
PASS   pos_g4x4_fit
PASS   pos_n1x4_min
PASS   pos_n2x4_min
PASS   pos_n16x4_min
PASS   pos_n1x16_min
PASS   pos_g4x4_min
PASS   pos_n1x4_max
PASS   pos_n2x4_max
PASS   pos_n16x4_max
PASS   pos_n1x16_max
PASS   pos_g4x4_max
PASS   pos_n16x4_r0_max
PASS   pos_n1x16_r0_max
PASS   pos_n16x4_r30_max
PASS   u_latch_or_b_leg
PASS   u_latch_or_r_leg
PASS   u_latch_or_skew
PASS   u_latch_or_keyok
PASS   u_track_contract
PASS   neg_guard00_fit (negative, caught TIMING-FAIL:SNAP-XDOM)
PASS   neg_guard04_fit (negative, caught TIMING-FAIL:SNAP-XDOM)
PASS   neg_wlow_s250_max (negative, caught TIMING-FAIL:W-LOWPHASE)
PASS   neg_deepxdom_max (negative, caught TIMING-FAIL:SNAP-XDOM)
PASS   neg_lead45_fit (negative, caught TIMING-FAIL:STREAM)
PASS   neg_release_r30_max (negative, caught TIMING-FAIL:RELEASE-HIGH)
PASS   neg_lead25_settle_max (negative, caught TIMING-FAIL:DATA-SETTLE)
PASS   u_latch_or_glitch (negative, caught TIMING-FAIL:LATCH-GLITCH)
PASS   u_snap_window (negative, caught TIMING-FAIL:SNAP-WINDOW)
PASS   u_track_shortlatch (negative, caught TIMING-FAIL:STREAM)
```

## Reproduce (actual commands)

```sh
cd hardware/experiments/simple-tile/fpga/system
python3 tools/extract_delays.py        # -> results/interior_delays.json
python3 results/check_system_sync.py   # SYNC-PASS drift guard
bash run_system.sh                     # full matrix (container)
python3 results/make_report.py         # this report + machine.json
```
