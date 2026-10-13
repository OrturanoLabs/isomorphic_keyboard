# scan20 — 20 MHz 16-tile scan frontend / test engine (UP5K standalone)

`scan20` is a STANDALONE bring-up test fixture for the isomorphic keyboard
tile chain at a 20 MHz shift rate. It scans the tile chain, walks the grid,
and exposes every frame plus observability strobes for checking. It is **not**
a MIDI-capable drop-in replacement for the golden controller
`firmware/ice40/src/top.vhd` (12 MHz, divider-17, ~350 kHz shift), which is
untouched. The marker-error injection / auto-retry behaviour is a TEST-ENGINE
facility for fault-injection, not a production MIDI-scan behaviour.

Ownership: everything in `firmware/ice40/scan20/**` plus the checkpoint
`hardware/experiments/simple-tile/checkpoints/scan20.md`. The golden firmware,
its Makefile, and all reference models are used READ-ONLY by path:

- `hardware/experiments/simple-tile/fpga/rtl/tile_fpga.vhdl`
  (unmodified fall-snapshot tile FPGA cores in simulation)
- `hardware/experiments/simple-tile/regression/tile_reg_pkg.vhdl`
  (docs-derived expected streams / frames)
- `hardware/experiments/simple-tile/fpga/system/results/machine.json`
  (fpga-system synthetic-corners constraints, READ-ONLY)

## What is kept from the golden controller (docs/architecture/protocol.md)

- 16-bit frame, keys msb-first; bits 15..4 keys, bits 3,2 markers = `11`,
  bit 1 `L_endrow`, bit 0 `T_endcol`; `shreg <= shreg(14 downto 0) & data`.
- Sample-before-shift: every bit is registered BEFORE the clock edge that
  advances the chain past it.
- Grid walk: columns right-to-left (column 1 at the controller), tiles of a
  column bottom-up (row 1 at bottom); `T_endcol` ends the grid.
- Framing error when markers /= `11`.

## Deliberate deviations

- sysclk-tick engine: exact-20 MHz shift from an on-chip PLL (see below).
- `SAMPLE_LEAD_TICKS` (1): data registered one full sysclk period before the
  next launch (sample-before-launch hold guard).
- Coordinates are 5 bits per axis (`COORD_BITS >= 5`), so a 16-tall column
  (needs 4) and beyond (up to 32) is representable.
- Error RECOVERY instead of the golden sticky state: framing error, the
  16-frame cap, or the watchdog parks the bus quiet (~= RECOVERY_TICKS+2)
  and starts a fresh episode (`AUTO_RETRY`), else HALT waits for `start`.
- Hard per-episode watchdog (8-tick quantised).

## Chosen configuration: f60 (EXACT)

| config | sysclk from 12 MHz | ticks/bit | high+low | shift rate | latch->clk guard | lead | UP5K STA |
|--------|--------------------|-----------|----------|------------|------------------|------|----------|
| f60    | 60.000 MHz exact (DIVF=79 DIVQ=4, VCO 960) | 3 | 2+1 = 33.33/16.67 ns | **20.000 MHz exact** | 66.7 ns | 16.67 ns | **CLOSED** |
| f120   | 120.000 MHz exact (DIVF=79 DIVQ=3) | 6 | 4+2 = 33.33/16.67 ns | 20.000 MHz exact | 58.3 ns | 8.33 ns | no (max ~66-69 MHz) |
| f100p5 | 100.500 MHz — 100.0 infeasible (DIVF=66 DIVQ=3, VCO 804) | 5 | 3+2 = 29.85/19.90 ns | 20.100 MHz (+0.5%) | 59.7 ns | 9.95 ns | no (max ~62-69 MHz) |

f60 is the chosen standalone build: exact 20.000 MHz shift, and it closes
timing. f120/f100p5 were attempted at explicit `--freq`, do not close, and
are kept as documented datapoints only. No 20 MHz shift is ever faked by
wrong division: f100p5's true +0.5% rate is printed wherever it appears.

The guard/lead/duty config is not guesswork: the fpga-system run
(`hardware/experiments/simple-tile/fpga/system/results/machine.json`,
33/33, SYNTHETIC corners, explicitly **not** hardware sign-off) bounds a
16-deep column at **guard >= 50 ns** (max corner), lead window 1..30 ns,
clock-high >= 22 ns. f60 uses guard 66.7 ns >= 50 ns, lead 16.67 ns in
window, high 33.33 ns >= 22 ns (and >= the 28 ns chain-model floor the tb
also enforces), latch width 1.0 us. Simulation pins the same numbers
(`MODEL_MIN_GUARD_PS=50000` on the 16-tall grid).

## Internal structure

- `src/scan20_core.vhdl` — scan engine. Every state exit / mid-pulse event
  is driven by a registered one-tick-early arm flag (`arm_*`) so each FF's
  fan-in cone is `state_bit AND arm_bit`; long waits use a /8 prescaler with
  2048-tick coarse idle wraps; a two-tick `ST_FRAME -> ST_ACT` keeps the
  frame bookkeeping off the high cone. All board pins come straight from
  registers (no combinational glitch path on `board_clk`/`board_latch`).
- `src/scan20_top.vhdl` — iCE40UP5K wrapper: `SB_PLL40_PAD` (params from
  generics, bitstream JSON re-verified vs icepll), core held in reset until
  PLL LOCK, status LEDs (red=error seen, green=episode busy, blue=clean
  scan seen). `PACKAGE_MIDI` held at the golden UART idle level.
- `sim/scan20_tb.vhdl` + `sim/run_sims.sh` — self-checking regression
  driving the unmodified fall tile cores; 24 expectations, see RESULTS.md.
- `synth/cfg_f{60,120,100p5}.vhdl`, `synth/scan20_up5k.pcf` (byte-identical
  copy of the golden pinout), `synth/run_synth.sh`.

## Run it

```sh
# from this repo checkout; container localhost/oss-cad-suite:2026-09-26
bash firmware/ice40/scan20/sim/run_sims.sh     # 24/24 expected, exit 0
bash firmware/ice40/scan20/synth/run_synth.sh  # f60 closes; prints summary

# host oss-cad-suite fallback (no container):
OSS_HOST=1 bash firmware/ice40/scan20/sim/run_sims.sh
OSS_HOST=1 bash firmware/ice40/scan20/synth/run_synth.sh
```

## Honest limits (also see RESULTS.md)

- STA is INTERIOR ONLY (fabric, `u_top.sysclk` domain): nextpnr/icetime
  estimates on the UP5K sg48 netlist. The external scan chain (BOARD_*
  pads, cables, connectors, SN74LVC165A/tile FPGAs, recovery/hold on the
  far end) is NOT part of this STA. No external-chain closure is claimed.
- The f60 interior margin is thin (see RESULTS.md for the exact numbers);
  this is a routed-netlist estimate with tool-default corners, not
  silicon sign-off, and the design has never been flashed or scoped.
- `BOARD_DATA` is sampled without a synchroniser: the input only changes in
  response to our own launches, so it is stable around every sample point
  by construction of the link protocol; a physically different driver
  (cable reflections, ESD events) is outside that model.
