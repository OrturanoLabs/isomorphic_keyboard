# FPGA alternatives for the single-PCB tile (12 MX SMD hotswap, 26 user IO)

Requirements recap (from ../README/rev-A acceptance): 20 MHz shift clock,
up to 16 tiles, one PCB per tile with Cherry MX SMD hot-swap sockets, no
tile-side MCU/LED/Hall, chassis drop-in, strong open-hardware/open-flow
preference, and the tile must ride the existing rev-A 3.3 V backplane link.

EVALUATION method: same RTL (`../rtl/tile_fpga.vhdl`, `SNAP_MODE`
fall/track) + per-device tops, same zero-delay self-checks (35/35), actual
installed open toolchain runs for BOTH modes (6 bitstreams —
yosys 0.69+154, nextpnr-himbaechel 0.11.1-33, nextpnr-ice40, apycula; see
`../results/logs/`). Datasheet facts not verified against the named vendor
documents are flagged **TO VERIFY**.

BOM wording correction (post-review): "embedded flash / no config BOM" holds
ONLY for the Gowin Z family. UP5K/LP8K are SRAM-config FPGAs (NVCM is OTP and
its open-flow programming is unverified here), so they carry a config BOM
line. And "one chip" means one LOGIC IC; regulators/config still add up
(docs/power_bom.md).

## Candidate A — Gowin GW1NZ-LV1QN48 (QN48, 7x7 mm)  [PRIMARY]

Single-rail variant worth supply-checking: **GW1NZ-ZV1(QN48)** — the ZV
sibling reportedly integrates the core regulator (removes the +1 LDO BOM
line; pin-compatibility with LV1 TO VERIFY vs DS861; supply channels
unconfirmed). If it exists as advertised it is the preferred order code.

- Embedded config flash (Z-family): no config memory on the BOM; "instant-on"
  class startup (exact value TO VERIFY vs DS861). openFPGALoader supports
  GW1NZ-1 by name (idcode 0x0100681b) for JTAG download into flash/SRAM.
- IO: 41 of 48 QN48 pads placeable in nextpnr (empirical this task); need 26.
  PULL_MODE UP **and** DOWN at pads -> all ten rev-A pin pulls internal.
- Snapshot clock: "fall" mode needs NONE; "track" uses on-chip OSCZ (only
  osc BEL on GW1NZ-1 in the chipdb; base frequency TO VERIFY vs DS861).
- Rails: LV part -> low core voltage (LV1 = 1.2 V core per Gowin naming;
  TO VERIFY vs DS861), VCCIO 3.3 V to the backplane. Needs a small 1.2 V
  LDO per tile (+1 BOM line; e.g. SOT-23-5 LDO class — part open).
- Open flow: yosys synth_gowin + nextpnr-himbaechel + gowin_pack — ran for
  BOTH snapshot modes; bitstreams produced; interior Fmax 254.84 MHz (fall)
  / 193.80 MHz (track); ~34/1152 LUT4, ~37/864 DFF, 26 pads.
- Availability: used on Tang Nano; Gowin announced JLCPCB/LCSC channel
  (2026 press page fetched during this task); per-tile price low (~$1-2
  class at LCSC historically — QUOTE NEEDED, not claimed).
- Risks: DS861 rails/startup/OSCZ frequency still to fetch (www.gowinsemi.com
  doc DB returned marketing pages only); ~4 of the 41 pads are JTAG-shared
  (identify exact numbers vs DS861 before layout; flow leaves JTAG live).
- Verdict: **viable** — experimental stage; the exact requested part works
  with a fully open flow including production flash programming.

## Candidate B — Lattice iCE40UP5K-SG48 (QFN48, 7x7 mm)  [ALT, proven-flow]

- **Volatile SRAM config — NOT embedded flash.** Retained choices: OTP NVCM
  (one-time per tile; open-flow programming of the UP5K NVCM is NOT verified
  in the installed image — no probe showed a working path) or external SPI
  flash (+1 BOM, verified flow exists for the flash side via icepack +
  openFPGALoader-class tools). TO VERIFY vs Lattice iCE40 UltraPlus DS.
- IO: 39 usable (empirical probe); need 26. Pads pull UP only -> +4 pull-down
  resistors on the tile BOM.
- Snapshot clock: "fall" needs none; "track" uses SB_HFOSC on-chip (48 MHz),
  verified in the flow.
- Rails: 1.2 V core + 3.3 V IO -> same +1 LDO note.
- Open flow: yosys + nextpnr-ice40 + icepack, ran for both modes; icetime
  interior Fmax ~40 MHz class (fall 40.19 / track 40.74) — comfortably above
  the 20 MHz shift cadence at the LOGIC level only.
- Verdict: **viable** with +flash/-OTP config trade-off vs A.

## Candidate C — TinyFPGA BX (iCE40LP8K-CM81 module as tile core) [REQUIRED-BY-TASK]

Two ways to use it:

C1. **Bare iCE40LP8K-CM81 on the tile PCB**: CM81 = 0.4 mm-pitch WLCSP-class
    BGA — poor fit for the cheap 2-layer tile board; SRAM-only config (no
    NVCM — TO VERIFY vs Lattice LP/HX DS) -> external SPI flash in production
    (+1 BOM); no HF on-chip oscillator (only ~10 kHz LFOSC — too slow), so
    SNAP_MODE="track" needs a board oscillator (+1 BOM) while "fall" needs
    none. icetime Fmax 69 MHz class (interior, both modes).
    Verdict: technically workable, mechanically painful, config adds BOM.

C2. **Whole BX module soldered/plugged onto the tile PCB**: module provides
    LP8K + 8 Mbit SPI flash config + 16 MHz oscillator on B2 (amaranth
    tinyfpga_bx.py resource) + USB bootloader. Our flow builds LP8K-CM81
    bitstreams (both modes); 26 user IO (+1 sysclk in "track") <= 31 BX edge
    GPIO (tight but fits). Downsides: cost per tile (module ≫ component
    price; current TinyFPGA production status must be checked — lifecycle
    RISK, no quote claimed), thickness, and the module carries LED/USB parts
    our "no LED on tile" rule doesn't want (they can stay unpowered/unused
    but the BOM pays for them). The no-tile-MCU rule is honoured (the USB
    bootloader is config infrastructure, not a tile MCU; no LED driven).
    Verdict: **viable for prototyping the tile concept immediately**,
    questionable as the manufacturing choice.

## Screened out (with reason)

- Lattice MachXO2/XO3 (embedded flash, right size): open flow for MachXO2
  exists only as experimental nextpnr arch with trellis data gaps; no
  credible place&route path in the installed image -> cannot honestly run.
- Lattice ECP5 (e.g. LFE5U-12F): gold-standard open flow, but minimum
  package caBGA256 10x10 mm and SRAM-only config (+flash); massively
  oversized for 44 LUTs. (TinyFPGA EX is ECP5-based — same mismatches.)
- Gowin GW1N-1/GW1N-2 (embedded flash, cousins of A): also himbaechel-
  supported (chipdb present) and openFPGALoader-listed; GW1NZ chosen for
  its low-power Z variant + Tang Nano precedent. Valid fallbacks if supply
  says so.
- ATF22LV10C+165+1G04 SPLD (4 ICs) and ATF1502ASV one-chip: see
  ../../RESULTS.md — those stay the discrete/SPLD reference experiments;
  ATF1502 programming on the exact LV part is still unverified there and
  its fitter is proprietary.

## Decision summary

FPGA option beats the SPLD experiments on: one logic IC per tile (26 IO fit),
fully open build-to-flash flow (verified end-to-end on all three; production
flash programming only fully open for GW1NZ), behaviour self-checked vs the
rev-A model in BOTH snapshot modes. Costs/risks: 1.2 V-class LDO (A/B),
config storage except on GW1NZ, FPGA unit price above a small SPLD, and all
candidates still owe: datasheet pinout/rails/startup fetch, 20 MHz x 16-tile
bench or external-model STA, bench power, and connector-timing closure
(standing gates in ../../RESULTS.md + logic/timing).
