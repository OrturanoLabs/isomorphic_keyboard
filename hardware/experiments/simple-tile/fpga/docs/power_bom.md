# Per-tile power / BOM comparison — corrected scope

Correction note (post-review): "one chip / no BOM" claims are split into
**logic IC count** (1 for all FPGA rows) vs **total tile BOM**, which adds
regulators, config storage, pull resistors and programming. Nothing below is
an invented price or power figure; vendor items pending are marked TO VERIFY.

## BOM per tile (logic section; connectors/keys/hotswap identical across rows)

| line | GW1NZ-LV1QN48 | iCE40UP5K-SG48 | iCE40LP8K via BX module | ATF22LV10C SPLD baseline (../../RESULTS) | discrete reference |
|---|---|---|---|---|---|
| logic IC(s) | 1 FPGA | 1 FPGA | 0 on tile; 1 BX module | 4 | 9 |
| config storage | none — embedded flash in the Z family (bitstream .fs built by gowin_pack; programming via openFPGALoader, GW1NZ-1 listed) | **NOT embedded flash**: SRAM config. Retained options: OTP NVCM (one-time; open-flow NVCM programming NOT verified in this image — no tool probe found it configurable) or external SPI flash (+1 IC) | module's onboard SPI flash (BX has one) | none | none |
| regulators beyond backplane VCC | +1 core LDO (1.2 V class) — rails taxonomy NOT yet verified vs DS861; the ZV1 sibling reportedly integrates a regulator (supply check pending) | +1 core LDO (1.2 V class) | none (module regulated) | none (3.3/5 V native) | none |
| decoupling caps | ~4-6 (multi-rail) | ~4-6 | ~2 extra on tile | ~4 | ~9 |
| pull-down Rs (T_data, L_data, 2 latch legs) | 0 (pad PULL_MODE=DOWN) | +4 | +4 | 0 | 0 |
| snapshot-oscillator part | 0 in "fall" mode (none needed); 0 in "track" (OSCZ on-chip) | 0 both modes (SB_HFOSC in "track") | 0 (module 16 MHz on B2; in "fall" unused) | n/a | n/a |
| programming step | JTAG, openFPGALoader | SPI flash or NVCM — open NVCM flow unverified | tinyprog USB (dev) / SPI (prod) | SPLD programmer (open Galette; exact LV part unverified in ../../) | none |

## "One chip" wording

The FPGA tile is a **one-logic-IC** design. It is not a one-part design on
GW1NZ-LV1 (core regulator still unverified/added) or UP5K/LP8K (regulator +
config flash). If the Gowin **ZV1** integrated-regulator variant is confirmed
orderable AND its rails match the backplane, the total drops to 1 IC + pulls +
caps for many topologies — not verified here.

## Power notes (no numbers invented)

- The design is ~34-44 LUT / ~37 FF; the 20 MHz shift clock dominates dynamic
  IO power and is shared with the SPLD/discrete baselines. The "fall" mode
  removes the free-running oscillator cell (measured in the flow: OSCZ and
  SB_HFOSC disappear from utilisation in fall builds) — the lowest-power FPGA
  configuration. Numeric static/dynamic figures require vendor power
  calculators or a bench measurement; none exist here — no number is quoted.
- No power estimator exists in the installed open flow for any of the three
  parts (checked: image has icetime/icepack, no icepow-class tool; apycula
  provides none) — recorded as a standing gap, not worked around.

## 16-tile system note

Per-tile bitstreams are identical (no coordinate state) — one image programs
all tiles; flashless config applies ONLY to GW1NZ (and would apply to the
ZV1 variant). The latency-chain/clock-forward structure is unchanged from
rev A: the FPGA version does not add system timing risk, but it also does not
remove the standing 16-hop interconnect budget (UNKNOWN, ../../logic/timing).
