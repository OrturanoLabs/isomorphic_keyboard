# Snapshot modes and the asynchronous contract — FPGA tile

Rev A has one clock (board shift clock) and otherwise level-sensitive async
logic (74x165 /PL, '161/'74 async clear). The FPGA fabric has no async
parallel *data* load FF, so the '165's capture is emulated. `tile_fpga` has
**two snapshot modes** selected by the `SNAP_MODE` generic, and BOTH were
simulated (35/35 checks) and synthesized/place&routed (6 bitstreams):

| | `SNAP_MODE="fall"` (default) | `SNAP_MODE="track"` |
|---|---|---|
| capture instant | latch **falling edge** exactly (negedge FF, latch as clock) | last sysclk sample before the fall → up to 1·Tsys stale window |
| match vs rev-A '165 | exact in zero-delay sim (S8: 0 mismatches over 9 in-window phases) | approximate: misses every in-window change (S8: 9/9 stale — expected, documented, NOT a pass-equivalence) |
| extra oscillator | none (no sysclk used at all) | OSCZ / SB_HFOSC / module osc required |
| FF count | 16 shadow (SB_DFFN/DFF...) + 16 shreg + 4 cnt + 2 flag | same + nothing extra (same total); needs the osc BEL |
| timing concern | pd must be stable through the fall edge (recovery window at the FFs), latch routed as a clock net | sysclk↔latch/key CDC + latch CE recovery; quasi-static keys do NOT waive this |

## Why "quasi-static keys" is NOT a free pass

The earlier draft argued human-speed keys justify a free-running sample. That
is wrong as a general claim: the latch fall is asynchronous to any on-chip
Clock, so "last sample before the fall" is *arbitrary* — a change in the
final sysclk period before the fall is captured by a real '165 but not by a
sysclk sampler; and sampling/CE recovery timing at the FF cannot be waived
by slowness of the *source* (metastability risk is about arrival time vs the
edge, not rate). The directed, non-hidden evidence: `sim/tile_unit_tb.vhdl`
scenario **S8** sweeps sub-period phases and reports ref-vs-dut per phase
(logs: `sim/logs/unit_track.log`, `unit_fall.log`).

## Requirements of each mode (what the controller must provide)

**"fall"**:
- R1: the parallel word pd — keys + L_endrow/T_endcol straps — stable through
  the latch falling edge (a setup window around the fall; the real '165 has
  the equivalent `tWR`-type recovery spec). Zero-delay sim cannot model
  metastability; the window value must come from device STA on a real board
  (interior crossing latch→clk reported by nextpnr as 2.98 ns max delay —
  results/logs/gw1nz_fall_nextpnr.log — but no setup/hold-at-FF closure for
  an asynchronous latch source exists here).
- R2: latch acts as a clock inside the fabric (skew/loading on the latch net
  across 16 tiles is a board question, same net as rev A carries anyway).

**"track"**:
- T1: latch high ≥ 2 sysclk periods (guarantees ≥ 1 shadow sample), and keys
  stable from ≥1 sysclk before the earliest acceptable fall until it happens
  — otherwise the frame is the *previous* sample (S8 shows exactly this).
- T2: sysclk period known within tolerance (OSCZ base frequency still TO
  VERIFY vs Gowin DS861; SB_HFOSC 6–48 MHz per Lattice).
- T3: dead-zone = up to one sysclk period before each latch fall.

## What was actually timing-checked (and what was NOT)

Checked: FPGA-interior Fmax on the shift-clock domain (table in RESULTS.md),
and an interior cross-domain report (negedge latch → posedge clk, 3.0 ns
class) in the gw1nz fall build; an SDC (`synth/tile_gw1nz.sdc`) declaring
shift/latch clocks was **accepted** by nextpnr-himbaechel
(results/logs/gw1nz_sdc.log, rc=0).

NOT checked, declared openly: `set_clock_groups` is unsupported by this
nextpnr's SDC subset (probe recorded), so no async clock-group crossing was
formally excluded/closed; there is no metastability/recovery STA for the
asynchronous latch; pad input delays and board flight times are absent;
icetime/nextpnr Fmax is interior-only. "20 MHz system" remains an unmet
acceptance gate requiring a bench or per-topology STA with external models.

## Choice guidance

Use **fall** for hardware identity (it reproduces the rev-A instant
exactly, removes the oscillator cell and the sysclk domain entirely). Keep
**track** as the portable fallback for parts where routing an asynchronous
latch net as a clock is undesirable, accepting the documented T1–T3
stability contract and the S8-characterised dead zone.
