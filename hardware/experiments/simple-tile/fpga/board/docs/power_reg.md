# Power rails, regulation, straps, BOM logic (both variants)

Component sourcing: **dated supplier evidence captured 2026-10-14** --
see docs/bom.md + docs/bom.json. Only the PCBA quote remains TBD
(blocked gate: needs account + file upload; no invented quote).

## Tile rail topology (common)

The tile backplane interface carries one 3.3 V rail (`VCC` chassis pad).
Each tile derives its 1.2 V core locally -- no 1.2 V crosses tiles.

```
chassis VCC (3.3V) ----+--> FPGA VCCIO0/VCCIO1/VCCX (3.3V domains)
                       +--> LDO-1V2 --VCC1V2_RAW--> FB1 --VCC1V2--> FPGA core
```

## GW1NZ-LV1QN48 (primary)

Rails (UG842 Power sheet; DS841):

| board net | voltage | feeds | source req. |
|---|---|---|---|
| VCC | 3.3 V (VCCIO 1.14-3.6 V) | pins 1 (VCCIO0), 25 (VCCIO1), 36 (VCCX; rule VCCX >= VCCIO) | chassis |
| VCC1V2 | 1.2 V (1.07-1.26 V, LV grade) | pins 12+37 (core VCC) via FB1 | LDO from VCC |
| GND | 0 | pins 2, 26 (VSS) + EPAD 49 | chassis |

Regulation/filter practice per UG293-1.3.4E (schematic manual):
0.1 uF ceramic per power pin (C1/C2/C3 on VCC; C4/C5 on VCC1V2), bulk
4.7 uF per rail (C7, C6), ferrite MH2029-221Y-class on the core rail
(FB1, series between LDO output `VCC1V2_RAW` and the FPGA core pins --
checker N5 pins this topology exactly: VCC1V2_RAW = {U2.5, FB1.1, C8.1}).

LDO: **TI TLV75512PDBVR -- SELECTED + pinout VERIFIED** against TI
SBVS320D (TLV755P datasheet): SOT-23-5(DBV) pin 1=IN, 2=GND, 3=EN,
4=NC, 5=OUT, exactly matching the U2 footprint binding. Fixed 1.2 V,
500 mA, +/-1% output accuracy (inside the GW1NZ LV-core window
1.07-1.26 V). EN tied to IN (always-on; no shutdown needed, DS 6.4);
UVLO max 1.44 V << 3.3 V input. Datasheet-required capacitors are
placed: CIN = C9 1 uF at IN pin, COUT = C8 1 uF at OUT pin BEFORE the
FB1 bead (found 2026-10-14: without C8 the bead would isolate all
bypass from the LDO control loop). Sourcing: docs/bom.md (DigiKey
stock 8.3k+, US$0.30@1).
Load estimate: GW1NZ-1 core static+dynamic at 20 MHz for 34 LUTs --
milliamps scale; exact number TBD from DS841 current tables + bench.
POR/ramp rules from DS841 3.1.3/3.1.5 and the flash-init condition are
listed in docs/candidate.md.

Bench item **B1** (pre-fab is NOT blocked; pre-scale IS): scope the
TLV755P soft-start ramp on the first populated tile and confirm the
1.2 V core reaches the GW1NZ config-valid window inside the DS841
power-up spec for AUTO BOOT from internal flash.

### Decoupling placement + load/thermal budget (r6 evidence, 2026-10-15)

Placement distances measured off the r6 board by `tools/quote_prep.py`
(centre of cap -> target pin pad; pcb sha256[:12] c7d5b66fa1db == the
validator-snapshotted artifact):

| part | placed at | serves | distance |
|---|---|---|---|
| C1 (100n) | (8.56, 0.95) B | U1.1 VCCIO0 | 3.18 mm |
| C2 (100n) | (2.66, 5.35) B | U1.25 VCCIO1 | 3.18 mm |
| C3 (100n) | (2.66, 2.95) B | U1.36 VCCX | 2.26 mm |
| C4 (100n) | (13.06, 5.35) B | U1.12 VCC1V2 | 3.18 mm |
| C5 (100n) | (8.16, -0.80) B | U1.37 VCC1V2 | 4.10 mm |
| C6 (4u7 bulk) | (13.81, 7.60) B | VCC1V2 | 3.00 mm to U1.12 |
| C7 (4u7 bulk) | (-13.02, 19.20) B | VCC entry | next to JP_VCC (-9.02, 21.70) + LDO cluster (by region, not by U1 pin) |
| C8 (1u COUT) | (-8.77, 19.20) B | U2.5 OUT, BEFORE FB1 | 5.18 mm |
| C9 (1u CIN) | (-12.27, 21.45) B | U2.1 IN | 5.42 mm |
| FB1 bead | (13.06, 3.60) B | VCC1V2_RAW -> VCC1V2 | at the LOAD side: 4.59 mm to U1.12 |

Consequences, stated honestly: the power-entry cluster (JP_VCC -> C7/C9 ->
U2 -> C8) is coherent; every core-rail bypass is within ~2.3-4.1 mm of
its pin at placement level; the bead sits at the FPGA (load-side pi
filter), so `VCC1V2_RAW` is unavoidably a ~31 mm long run across the
board -- at the milliamps-scale core load the IR drop is single-digit mV
(35 um Cu, ~0.3 mm trace, ~50 mOhm, ~30 mA -> ~1.5 mV), a non-issue;
real loop inductance, trace widths and the GND return are routing scope
(FPGA-02), not settled here. DC-bias: C8/C9 are 25 V X5R-class at 3.3 V /
1.2 V operating points (>= 2x derating at the highest rail) -- fine.

Load capacity est. (paper bound, no vendor power tool run here): DS841
LV static ICC 3 mA typ core; ICCX/ICCIO 0.5 mA typ each. Dynamic bound:
34/1152 LUTs (~3%) at 20 MHz -> sub-mA to few-mA core; 5 switching
outputs at ~10 pF class loads -> ~3 mA class on VCCIO
(C*V^2*f*n est., not measured). Total core+aux **well under 50 mA** vs
the 500 mA TLV75512 rating. Thermal ceiling (P = 2.1*I drop): at the
SBVS320D JEDEC thetaJA ~231 K/W recorded in session 2, TJ at TA=85 stays
<=125 C up to ~82 mA (50 mA -> +24 K -> 109 C); TI's parametric page
also lists 60.3/100.8 K/W package/board-dependent figures (review P8
provenance nit) -- at those, ceiling >= 190 mA. Conclusion insensitive
at the real mA-scale load: **LOAD CAPACITY + THERMAL BUDGET VERIFIED ON
PAPER for the selected regulator**; bench measures the true current
(B1b: scope rails + ammeter at 20 MHz on the first tile).

Straps / pulls (as placed; checker N3):
R1 1k MODE0->GND, R2 1k MODE1->GND (AUTO BOOT, UG290/UG293),
R3 4k7 JTAG_TCK->GND, R4/R5/R6 4k7 ->VCC (READY/DONE/RECONFIG_N),
JTAGSEL_N floating (internal weak pull-up keeps JTAG function).
Key pull-downs: FPGA pad internal pull-DOWN (PULL_MODE=DOWN in the cst) --
rev-A passive plan, saves 12 resistors; bench fallback = external 10k.

## iCE40UP5K-SG48 (fallback -- placement-blocked but electrically complete)

| board net | voltage | feeds |
|---|---|---|
| VCC | 3.3 V | pins 1 (VCCIO_2), 33 (VCCIO_0), 22 (SPI_VCCIO1), 24 (VPP_2V5, spec 2.30-3.46 V -> 3.3 V) + flash VCC |
| VCC1V2 | 1.2 V (1.14-1.26 V) | pins 5, 30 (core VCC) |
| VCCPLL_1V2 | 1.2 V via filter | pin 29 through R2 100 ohm + C9 4u7 + C10 100n (TN02006; PLL unused) |
| GND | 0 | paddle (pin 49, MUST be grounded, DS 4.x) |

Extra BOM vs GW1NZ: U3 SOIC-8 SPI flash (>=1 Mbit reprogrammable,
W25Q80-class; in-circuit programming: hold CRESET_B low -> FPGA SPI IOs
tri-state, DS 4.6), R1 10k CRESET_B pull-up (pure input, NO internal
pull, TN02001), R2/C9/C10 PLL filter, and **R10-R13 + R20-R31 = 16
external 10k pull-downs** (iCE40 pads pull UP only). Boot: SPI_SS (pin
16) sampled HIGH at CRESET_B release -> Master-SPI from external flash
(flash CS# pull-up on board, TN02001 3.1). Power-up order: VCC/VCCPLL
first, then SPI_VCCIO1, then VPP_2V5 (DS 4.5); this ties the LDO
enable/sequencing choice to that order -- with a passive VCC->LDO-1V2 this
ordering is satisfied since 3.3 V pre-exists 1.2 V.

## BOM logic-count vs total (component prices sourced 2026-10-14, docs/bom.md; PCBA quote TBD-blocked)

GW1NZ variant: 12 Kailh sockets, 19 chassis target pads, 1 FPGA, 1 LDO,
1 ferrite, 9 capacitors (incl. C8/C9 at the LDO), 6 strap resistors,
5 series-termination positions R7..R11 (0402, 0R populated;
docs/termination.md), 11 test points = **65 parts** (GK7 total=65 at
board r6; deviation from logic count:
FPGA+LDO+FB+9C+6R+5Rs+11TP = 34 non-key parts).
UP5K variant (review board, U1 absent): sockets+pads+flash+LDO+10C+18R+9TP
= **70 emitted** (71 with FPGA if a package that fits is ever selected).

## Verified-on-this-board claims (machine-checked)

- FPGA power pads per rail: VCC {1,25,36}, VCC1V2 {12,37}, GND {2,26,49}
  (net checker N2) -- no singleton power nets remain anywhere on the
  board (N8).
- Every config/JTAG/status net has exactly one test pad (N4).
- All strap RC values + pin nets as tabled above (N3).
