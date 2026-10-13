# Power rails, regulation, straps, BOM logic (both variants)

Prices: **unknown / TBD throughout** -- no invented quotes.

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
checker N5 pins this topology exactly: VCC1V2_RAW = {U2.5, FB1.1}).

LDO: SOT-23-5 fixed-1.2 V class (TLV75512-class; note the pin convention
used on the footprint: pin1=IN, pin5=OUT, pin2=GND -- MUST be re-confirmed
against the exact chosen part's datasheet before any order). Load
estimate: GW1NZ-1 core static+dynamic at 20 MHz for 34 LUTs -- milliamps
scale; exact number TBD from DS841 current tables + bench. POR/ramp rules
from DS841 3.1.3/3.1.5 and the flash-init condition are listed in
docs/candidate.md.

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

## BOM logic-count vs total (prices TBD, no quotes)

GW1NZ variant: 12 Kailh sockets, 19 chassis target pads, 1 FPGA, 1 LDO,
1 ferrite, 7 capacitors, 6 strap resistors, 11 test points = **58 parts**
(deviation from logic count: FPGA+LDO+FB+7C+6R+11TP = 27 non-key parts).
UP5K variant (review board, U1 absent): sockets+pads+flash+LDO+10C+18R+9TP
= **70 emitted** (71 with FPGA if a package that fits is ever selected).

## Verified-on-this-board claims (machine-checked)

- FPGA power pads per rail: VCC {1,25,36}, VCC1V2 {12,37}, GND {2,26,49}
  (net checker N2) -- no singleton power nets remain anywhere on the
  board (N8).
- Every config/JTAG/status net has exactly one test pad (N4).
- All strap RC values + pin nets as tabled above (N3).
