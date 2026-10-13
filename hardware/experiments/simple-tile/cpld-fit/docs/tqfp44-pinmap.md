<!-- SPDX-License-Identifier: CERN-OHL-S-2.0 -->

# ATF1502ASV TQFP-44 pin map and assignment for `tile_cpld`

Source of the pin function/capability data: **Microchip DS20006485A**
Table 1-6 ("Dedicated Pinouts") and Table 1-7 ("I/O Pinouts"), plus the
"Pin Configurations and Pinouts" page-2 diagram (PDF+text in
`logic/timing/datasheets/atf1502asv.{pdf,txt}`). Package: 44-lead TQFP,
10x10x1.0 mm body (DS "Package Type" / ordering section).

The validated constraint file is `constraints/tile_cpld_tqfp44.csv`; run
`python3 constraints/check_pins.py` (PASS at the recorded checkpoint). This
document is the human-facing view; the CSV+checker is the machine-checked one.

## Device pin classes (TQFP-44)

| class | pins | count |
|---|---|---|
| user I/O macrocells (32 total) | block A: 42,43,44,1,2,3,5,6,7,8,10,11,12,13,14,15 · block B: 35,34,33,32,31,30,28,27,26,25,23,22,21,20,19,18 | 32 |
| – of which dual-role JTAG | 1 (TDI), 7 (TMS), 26 (TCK), 32 (TDO) | 4 |
| – of which dual-role power-down | 5 (PD1), 19 (PD2) | 2 |
| – of which global-clock capable I/O | 35 (GCLK3) | 1 |
| dedicated INPUT-only (Di per DS: "INPUT/..") | 37 (GCLK1), 38 (OE1), 39 (GCLR), 40 (GCLK2/OE2) | 4 |
| VCC (3.0..3.6 V) | 9, 17, 29, 41 | 4 |
| GND | 4, 16, 24, 36 | 4 |

* 36 signal pins = 32 user I/O + 4 dedicated inputs (Table 1-6 note).
* Every user I/O macrocell supports: comb or registered output, per-macrocell
  output-enable (product term or global OE mux per DS "I/O Control"), buried
  feedback when used as input, pin-keeper option, programmable slew rate,
  open-collector option (DS feature list).
* JTAG pins function as JTAG for boundary-scan/ISP when the JTAG option is on;
  "If JTAG (BST or ISP) is not needed, then the four JTAG control pins are
  available as I/O pins" (DS JTAG-BST/ISP Overview). We keep JTAG ON → the 4
  pins are reserved and carry no logic signal.
* PD pins: when power-down is enabled "the PD1 or PD2 pin cannot be used as a
  logic input or output. However, the pin's macrocell may still be used to
  generate buried foldback and cascade logic signals." We keep PD OFF and the
  two pins spare (macrocells unused), so the option survives a respin.

## Full 44-pin assignment

| pin | function (DS) | block/MC | assignment | why |
|---|---|---|---|---|
| 1 | I/O + TDI (JTAG) | A / MC4 | **reserved JTAG** | ISP |
| 2 | I/O | A / MC5 | `buttons[8]` | key row, block A |
| 3 | I/O | A / MC6 | `buttons[7]` | |
| 4 | GND | — | GND | |
| 5 | I/O + PD1 | A / MC7 | **spare** | preserve PD option |
| 6 | I/O | A / MC8 | `buttons[6]` | |
| 7 | I/O + TMS | A / MC9 | **reserved JTAG** | ISP |
| 8 | I/O | A / MC10 | `buttons[5]` | |
| 9 | VCC | — | VCC | |
| 10–14 | I/O | A / MC11..MC15 | `buttons[4..0]` | |
| 15 | I/O | A / MC16 | `endrow` (L_endrow) | |
| 16 | GND | — | GND | |
| 17 | VCC | — | VCC | |
| 18 | I/O | B / MC32 | **spare** | |
| 19 | I/O + PD2 | B / MC31 | **spare** | preserve PD option |
| 20 | I/O | B / MC30 | `lclk` (tri-state, PT OE) | clock forward left |
| 21 | I/O | B / MC29 | `tclk` (tri-state, PT OE) | clock forward up |
| 22 | I/O | B / MC28 | `latcho` | |
| 23 | I/O | B / MC27 | `bw` (registered) | |
| 24 | GND | — | GND | |
| 25 | I/O | B / MC26 | `dout` (registered) | |
| 26 | I/O + TCK | B / MC25 | **reserved JTAG** | ISP |
| 27 | I/O | B / MC24 | `ldata` | |
| 28 | I/O | B / MC23 | `tdata` | |
| 29 | VCC | — | VCC | |
| 30 | I/O | B / MC22 | `bfirst` | |
| 31 | I/O | B / MC21 | `tw` | |
| 32 | I/O + TDO | B / MC20 | **reserved JTAG** | ISP |
| 33 | I/O | B / MC19 | `rlatch` | |
| 34 | I/O | B / MC18 | `blatch` | |
| 35 | I/O + GCLK3 | B / MC17 | `endcol` | plain input; GCLK3 left free |
| 36 | GND | — | GND | |
| 37 | INPUT, GCLK1 | — | `bclk` | 20 MHz scan clock on global clock buffer |
| 38 | INPUT, OE1 | — | unused | see rationale |
| 39 | INPUT, GCLR | — | unused | see rationale |
| 40 | INPUT, GCLK2/OE2 | — | unused | spare global clock/OE2 |
| 41 | VCC | — | VCC | |
| 42 | I/O | A / MC1 | `buttons[11]` | first chain bit out |
| 43 | I/O | A / MC2 | `buttons[10]` | |
| 44 | I/O | A / MC3 | `buttons[9]` | |

Not pinned: `npl` and `ds` stay **internal** in this fit (they exist in the
RTL for TB observability; the one-chip design has no external /PL or DS node).
A debug build could route them to pins 18 (+ one PD pin, accepting PD-off).

## Accounting (checker-verified)

`25 used I/O + 4 JTAG + 2 PD-spare + 1 spare = 32 macrocells`;
`1 of 4 dedicated inputs used (37 = bclk)`; `4 VCC + 4 GND`;
reconciled total = **44** = pin count.

## Rationale for the non-obvious choices

* **bclk → GCLK1 (pin 37), not GCLK2/GCLK3.** The DS AC table specifies
  tCOP/tSU/fCNT against the global clock network. GCLK1 leaves GCLK2's shared
  OE2 function and the GCLK3 macrocell (MC17) available.
* **GCLR (39) intentionally unused.** The parallel load must *preset* stages
  to '1' for pd bits that are high — GCLEAR can only clear all 32 registers.
  The load is built from per-macrocell AR/AP product terms instead
  (`docs/ap-ar-mapping.md`), which also keeps the flag/counter clear
  orthogonal. Note for the (user-provided) fitter run: AR is PT, not GCLEAR;
  check the fitter does not auto-promote `latch` to GCLR in a way that
  removes the per-bit preset composition — the .jed must show AR and AP both
  active on chain macrocells.
* **OE1/OE2 unused.** Outputs `tclk`/`lclk` are tri-stated by a
  **per-macrocell product-term OE** (`w` / `/w`), as rev A's U107/U101 do —
  any global OE would force both clocks off together. All other outputs are
  always driven.
* **Tie-offs.** Unused dedicated inputs 38/39/40 and spare I/O must not float:
  use the fitter option for pin-keepers (DS "Programmable Pin-Keeper Option")
  on used I/O inputs if no external pull exists, and enable keepers or tie
  unused pins per board design. Pin-keepers are *not* substitutes for the
  protocol pull resistors (`bom-jtag-timing.md` §BOM).
* **EDIF bit order:** in `results/tile_cpld_atf1502.edif`, array port member
  `buttons(k)` carries RTL `buttons[11-k]` (checked in run_synth.sh). Keep
  this in mind when the fitter maps net names to physical pins.

## Known fitter-decision risks (to verify in the REAL fit once it exists)

* 25 user I/O + global clock input is within 32 macrocells but routing the
  16-bit feedback chain (shreg[i-1] → D of bit i) inside one logic block is a
  placement constraint the fitter must satisfy; DS "Extra Feedback" says
  buried feedback exists per macrocell regardless of pin use — OK in
  principle, unverified in a fitter.
* Product-term OE polarity (`w` vs `/w`) is a 1-PT function each — fine per
  DS "I/O Control" — but the global-bus routing of `w`, `latch`, `bclk`,
  `blatch`, `rlatch` fanouts is a fitter concern, not provable here.
