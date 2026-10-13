<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->

# BOM, JTAG pads, power, and 20 MHz timing gaps — ATF1502ASV one-chip tile

Scope: one CPLD per tile, 16 tiles, 20 MHz scan clock, **no tile-side
MCU/Hall/LED**. Values below cite Microchip DS20006485A (-15 speed grade,
all AC at CL = 35 pF per Table 1-4 / Figure 1-2) unless marked otherwise.
**No pricing is quoted anywhere (unsourced); nothing has been ordered.**

## 1. Bill of materials (one tile)

| qty | item | notes / source |
|---|---|---|
| 1 | **ATF1502ASV-15AU44** (TQFP-44, industrial −40..+85 °C, 32 MC, 3.3 V) | exact ordering code per DS "Product Identification System"; `-T` = tape&reel variant. Availability/current status NOT verified (no network this session). |
| 9 | 10 kΩ pull resistors | values from the rev-A tile schematic (`hardware/kicad/tile/tile.kicad_sch`: R101–R109 = 10k). Pulled nets (per `hardware/simulation/tile.vhdl`): T_W↑, T_endcol↑, T_data↓, B_first↑, B_latch↓, B_clk/R_clk↑ (one net), L_endrow↑, L_data↓, R_latch↓. |
| 7 | 33 Ω series resistors | rev-A schematic R201–R207 = 33 (edge net series elements). |
| 4 | 100 nF decoupling, one per VCC pin (9, 17, 29, 41) | engineering practice — **not DS-mandated text**; the transcribed DS has no decoupling section. Marked design input, not a sourced claim. |
| 1 | 10 µF bulk | same status as above. |
| 0 | JTAG header ICs | pads only, see §2. |
| 12 | key contacts | unchanged from rev A tile keys; switch sourcing is outside this workstream. |
| — | edge connectors | **disjoint workstream** (`connector-next/`), not decided here. |

**IC count per tile: 1** (vs 9 for the all-LVC discrete candidate A, 4 for
the B2 ATF22LV10C+2×165+1G04 candidate — counts per logic/README.md).

### pin-keeper ≠ pull-up (important)

DS "Programmable Pin-Keeper Option for Inputs and I/Os": keepers *hold the
last driven level* ("eliminate the need for external pull-up resistors and
eliminate their DC power consumption"). But a keeper on a pin that was never
driven sits at an **undefined** level after power-on, while the protocol's
presence detection relies on *defined* disconnected levels (endrow/endcol/
bfirst pulled up = "no neighbor", latch/data pulled down). **The discrete
pull resistors stay.** Keepers may still reduce AC-induced drain as an
additional fitter option on used inputs — a fit-time decision for the real
fitter run.

## 2. JTAG / programming pads

* TAP pins (dual-role user I/O per DS Table 1-6): **TDI = pin 1, TMS = pin 7,
  TCK = pin 26, TDO = pin 32**; 3.3 V TTL/CMOS levels (DS "JTAG-BST/ISP
  Overview"). **No TRST** — "the TAP controller is automatically reset at
  power-up". Modes: SAMPLE/PRELOAD, EXTEST, BYPASS, IDCODE, HIGHZ.
* Board: 6-pad 0.1" pogo footprint TDI/TMS/TCK/TDO + VCC + GND; route them as
  a dedicated net — the constraint plan reserves the 4 macrocells so no tile
  logic shares them (checker-enforced).
* Internal pull-up design option exists on TMS and TDI only (DS note under
  Figure 1-3); treat as fitter-time option, not a substitute for resistor
  pulls on protocol pins.
* Programming behaviors to design around (DS): during ISP the other I/Os are
  driven per design/Hi-Z; **if programming is interrupted, all inputs and
  I/Os default to high-Z** and pin-keepers preserve the previous state —
  safe for the passive pull network, but means a half-programmed tile looks
  "absent" (no driven frame) rather than "broken": firmware-visible as a
  framing/​timeout condition, to be handled by the not-yet-built controller.
* SVF: "Serial Vector Format (SVF) files can be created by Microchip provided
  software utilities". An open .jed→SVF/XSVF+JTAG path exists in principle
  (prjbureau utilities; Afterburner ≥0.6.0 experimental, needs a 3.3 V-IOREF
  Arduino — per logic/README.md §6), **but the .jed input can only come from
  the proprietary fitter** → the open programming half is real, the artifact
  is missing. With a third-party programmer, "the JTAG ISP port can be
  disabled, thereby allowing four additional I/O pins" — not needed here
  (25/32 macrocells used).

## 3. Power (all DS Table 1-2 / figures)

| parameter | value | DS conditions |
|---|---|---|
| ICC1 standby | **45 mA typical** (no maximum specified) | VCC = max, VIN = 0 or VCC, standard power |
| ICC3 standby, reduced-power mode | 30 mA typical | same conditions; reduced-power macrocells add tRPA = 13 ns worst-case to the control-path delays |
| ICC2 power-down | 0.75 mA typ / 5 mA max | PD pin high |
| dynamic ICC at 20 MHz | **not characterized** in DS (Figure 1-5 sweeps VCC at f = 0) | → UNKNOWN until bench-measured on the fitted design |

Implications (typicals only):
* ~149 mW per CPLD at ICC1 typ; 16 tiles ≈ **0.72 A typical** standby draw on
  the 3.3 V rail in standard-power mode (≈0.48 A in reduced-power mode, with
  the tRPA delay adder un-budgeted without STA). The chassis power plan must
  treat these as *typical, f≈0* numbers — a real budget needs measured
  dynamic current. This matches and sharpens the logic workstream's finding.
* Thermal: 149 mW × θJA 40 °C/W (TQFP, DS thermal table) ≈ +6 °C — no thermal
  concern at typical standby multiples.
* VCC 3.0–3.6 V operating (Table 1-1); absolute-max pin range −2.0..+7.0 V
  (≤20 ns pulses); IIL/IIH ≤ ±10 µA; IOZ ≤ ±40 µA — the connector system's
  pull network is compatible (10 kΩ ≫ needed drive); CIN/CI/O = 8 typ/10 max
  pF per pin (Table 1-3) — feeds the interconnect model of the (disjoint)
  timing-chain workstream.
* Power-up: VCC rise must be monotonic; registers initialize on the VRST
  crossing; DS recommends the **Large** hysteresis fitter option near 3.0 V
  (POF2JED flag `-power_reset`); "if VCC falls below 2.0 V it must shut off
  completely before being turned on again". The scan protocol's latch-first
  behavior makes functional state independent of FF POR values.

## 4. 20 MHz timing — phase decomposition and gaps

50 ns period / 25 ns half-period. Verdicts use the repo convention
(logic/README.md §5): **NECESSARY-ONLY** = datasheet component sums,
**PROVISIONAL** = composed but not fitted, **UNKNOWN** = needs a measured
system parameter. This table enumerates the CPLD-side phases; the
interconnect/system numbers stay with the disjoint timing-chain workstream
(`logic/timing/timing.json` `assumptions` are all null there, so no system
sign-off exists).

| # | phase | DS-sourced numbers | verdict |
|---|---|---|---|
| T0 | latch pulse acts on chain (AP/AR write) | tIN 2 + tLAC 6 + tPRE/tCLR 4 ≈ **12 ns** composed max | NECESSARY-ONLY floor for the controller's latch width; the actual controller pulse width is **UNKNOWN** (assumption null; 16-tile latch forward skew = `latch_hop` null) |
| T0b | latch deassert → first clock edge (AP/AR removal, recover, then Q stable/released to shift) | **not separately specified** in Table 1-4 | **gap**: needs fitter STA; assumption `latch_deassert_to_first_clk` null |
| T1 | first-bit availability (no clock involved — AP/AR held value) | tCOP n/a; async path tPRE 4 + tOD1 3 ≈ 7 ns after latch action | NECESSARY-ONLY; system-side sampling is UNKNOWN |
| T2 | bit launch per hop: bclk → `dout` | tCOP ≤ 8 ns (GCK path) + tOD within; route = null | NECESSARY-ONLY: 8 ns; hop budget at receiver tSU 11 → 50 − 8 − 11 = **31 ns** for accumulated route/skew/jitter per worst-convoluted path — system verdict UNKNOWN |
| T3 | counter self-constraint | internal counter fCNT ≥ 76.9 MHz (tCNT 13 ns) vs 20 MHz | NECESSARY-ONLY satisfied (component-level) |
| T4 | flag feedback CE path (dout·(cnt==15) → CE of `bw` FF) | register tSU 4 / tFH… fast-input tFSU 2–3; compose: tRD/tCOMB + tFIN + tFSU — fit-dependent | PROVISIONAL only — needs fitter STA |
| T5 | W-driven clock-forward OE switching | tZX1 ≤ 7 ns enable / tXZ ≤ 6 ns disable @ CL 35 pF | NECESSARY-ONLY bounds; the zero-delay release-edge behavior is characterised (logic README §2) but real-silicon ordering for a 20 MHz controller remains to be proven there |
| T6 | reduced-power trade | tRPA 13 ns adder on reduced-power macrocells | design decision pending STA |

**STA itself is BLOCKED**: tLAD/tLAC/tUIM/tSEXP adders depend on the actual PT
packing, which requires the proprietary fitter (fit/run_fitter.sh). What is
NOT claimed anywhere here: that "21 FFs < 32 macrocells" implies a fit —
product-term allocation, block placement, switch-matrix routing, GCLK
networking and OE allocation are exactly the closed-fitter steps.

## 5. Explicit gap list (hand-off to the 16-tile controller/timing workstream)

1. Controller latch pulse width + deassert→first-clock gap (assumptions null).
2. Route/skew numbers for clock forward, data return, latch forward
   (`route_delays_ns.*` all null in timing.json).
3. FPGA return-path hold (FPGA tCO min unpublished — logic/README §5).
4. Measured dynamic ICC at 20 MHz.
5. Fused-silicon AP/AR verification + fitted STA (needs licensed fitter).
6. Bench re-check of the W-transition release edge at temperature/load.
