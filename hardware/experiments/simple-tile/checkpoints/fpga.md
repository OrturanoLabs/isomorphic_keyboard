# fpga checkpoint (workstream: FPGA tile for simple-tile) — FINAL rev.2

Convention: beside logic.md/cpld-fit.md per repo practice; the active task
checkpoint also lives at repo-root `checkpoints/fpga.md` (same workstream,
full running log there). This copy was started 11:37 by an orphaned session
and consolidated to final by the completing session (fpga/ was empty at
recovery; all fpga/** content is the completing session's). No commits, no
installs, no writes outside fpga/** + the two checkpoints/fpga.md files.

## Deliverables (all under hardware/experiments/simple-tile/fpga/)

- rtl/tile_fpga.vhdl — DUT core, `SNAP_MODE` "fall"(default)/"track"; no
  async parallel-data FF anywhere; true 'Z' clock outputs.
- rtl/top_{gw1nz,ice40up,ice40lp}.vhdl + *_track.vhdl — device tops per
  mode; merged clk_pin (26-pin board budget), osc only for "track".
- sim/tile_unit_tb.vhdl (S1–S8 incl. phase-sweep CHARACTERISATION),
  sim/tile_grid_pair_tb.vhdl (REF grid = unmodified rev-A model),
  sim/run_sims.sh.
- synth/{tile_gw1nz.cst, tile_gw1nz.sdc, tile_up5k.pcf, tile_lp8k.pcf,
  run_synth.sh}; docs/ ×4; RESULTS.md.
- Logs: sim/logs/, synth/results/logs/ (env pinned: container image id
  58f58619c735..., ghdl 7.0.0-dev, yosys 0.69+154, nextpnr-himbaechel
  0.11.1-33, apycula gowin_pack).

## Verified results (actual runs)

- Sims rev.2: 35/35 PASS, rc=0 (both modes × full matrix + mutations + S8).
  S8 sweep: track = stale on 9/9 in-window phases (expected, demonstrated,
  characterised — NOT hidden); fall = 0 mismatches; control outside the
  window matches in both.
- Synth rev.2: 6/6 bitstreams. Interior-only Fmax: GW1NZ-LV1QN48 fall
  254.84 / track 193.80 MHz (nextpnr); UP5K-SG48 40.19 / 40.74 MHz and
  LP8K-CM81 69.17 / 68.48 MHz (icetime). 26 pads used (41 NAND-probed
  usable on QN48; BUFG shares clk pad). fall mode drops OSCZ/SB_HFOSC.
- SDC (gw1nz): create_clock accepted (rc=0); set_clock_groups unsupported by
  this nextpnr SDC subset — async latch↔clk deliberately NOT STA-closed;
  interior cross report negedge latch→posedge clk = 2.98 ns.

## Corrected claims (post-review)

- "Snapshot frozen AT latch fall" is exact ONLY for SNAP_MODE=fall; track is
  approximate (last sysclk before fall; ≤1 Tsys stale window; metastability
  not waived by quasi-static keys). Documented in docs/clock_domains.md.
- GW1NZ = one LOGIC IC (rails/LDO not datasheet-verified; ZV1 regulator
  variant suggested, supply check pending). UP5K/LP8K are SRAM config
  (NOT embedded flash): external SPI flash, or OTP NVCM whose open
  programming is unverified here. Full split in docs/power_bom.md.
- 26-pin floor (B/R clock merged — rev A itself ties J103.2 to J104.2);
  LP8K track adds the module osc pin.
- All Fmax numbers = FPGA-interior; no external/async sign-off; no 20 MHz
  system or hardware pass claimed.

## Remaining gates

DS861 + Lattice DS fetch (vendor DB serves marketing only), real-silicon
recovery/STA + bench power (no open estimator), pad-pull bench check, cst is
a legal proposal not a routed board, 16-tile/20 MHz system budget per
logic/timing census.

## Running jobs

None. Reproduce: `bash fpga/sim/run_sims.sh`, `bash fpga/synth/run_synth.sh`
from repo root (container via tools/oss.sh).
