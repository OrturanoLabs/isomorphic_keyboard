# Single-board tile: FPGA candidate experiment

One-chip-FPGA tile carrying the rev-A scan logic, replacing the 7-chip glue
+ 2x'165 + counter glue (and the 4-chip SPLD experiment) with a single FPGA.

This is an experiment, not a manufacturing-ready design. Start with
[RESULTS.md](RESULTS.md).

## Layout

- `rtl/tile_fpga.vhdl` — device-independent tile core (DUT). Selectable
  `SNAP_MODE`: "fall" (default; negedge-latch snapshot = rev-A capture
  instant, no oscillator needed) or "track" (sysclk sampling while the latch
  is high; documented approximation with a characterised dead zone).
  First-bit-before-first-clock preserved combinationally; true tri-state
  clock outputs; see docs/clock_domains.md.
- `rtl/top_{gw1nz,ice40up,ice40lp}.vhdl` + `top_*_track.vhdl` — board-level
  tops per device per mode (oscillator instantiated only for "track";
  ghdl-plugin takes no `-g`, hence the mode variants).
- `sim/` — self-checking benches + runner (`run_sims.sh`): unit scenarios
  (incl. S8 phase-sweep CHARACTERISATION), paired REF-vs-DUT grids in both
  modes, mutations.
- `rtl/top_{gw1nz,ice40up,ice40lp}.vhdl` — board-level tops: on-chip osc
  (OSCZ / SB_HFOSC) or module osc, merged connector nets, pruned straps.
- `sim/` — self-checking benches + runner (`run_sims.sh`): unit scenarios
  and paired REF(rev-A model)-vs-DUT grids with mutations.
- `synth/` — pin maps + `run_synth.sh` full flows to bitstreams.
- `docs/` — [pin budget](docs/pin_budget.md),
  [alternatives incl. TinyFPGA](docs/alternatives.md),
  [power/BOM](docs/power_bom.md), [clock domains](docs/clock_domains.md).
- `results/logs/` — pinned environment + real run logs; `results/build/`
  holds netlists/.fs/.bin (git-ignored).

## Reproduce (from the repository root)

```sh
bash hardware/experiments/simple-tile/fpga/sim/run_sims.sh
bash hardware/experiments/simple-tile/fpga/synth/run_synth.sh
```

Both use `tools/oss.sh` (container `localhost/oss-cad-suite:2026-09-26`),
falling back to host ghdl/yosys/nextpnr/apycula if installed.

References stay where they were: `hardware/simulation/` (rev-A models),
`docs/architecture/protocol.md`, `../regression/` (frames + topologies),
`../logic/` (discrete/SPLD/CPLD experiments + timing census).
