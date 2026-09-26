# Known issues

Issues found while documenting rev A. Items marked *frozen* are deliberately **not** fixed
during the rev-B hardware work, because the functional behaviour is frozen. They are
candidates for a later firmware release.

## Firmware (`firmware/ice40/src/top.vhd`)

- *frozen* — **Tile slot 0 is never used.** `tile_counter` is incremented in state `r2`
  before the first `load`, so the first tile is stored in slot 1. With
  `keyboard_t` = `array (0 to 9)`, 9 tiles fit and a 10th would index out of range.
- *frozen* — **The framing error is sticky.** When the two marker bits are not `11`, the
  pull FSM stays in `err` (red LED) until a reset. A glitch on the board clock, such as a
  double-clocked shift register caused by ringing, stops the scan. This makes signal
  integrity visible to the player.
- *frozen* — `main_fsm` never reaches `done`, and the states `s1`/`s2` of the pull FSM are
  unused.
- The comment on `ref_pitch` said 96 = C7; the value is 60 = C4. The comment has been fixed.

## Hardware (rev A)

- The symbol values do not match the ordered parts (74AUC/74HC/74LS vs 74LVC/SN74HC).
  74AUC is not rated for 3.3 V. Check the chip markings on a built tile.
- There is no series termination on the inter-board drivers, and decoupling is limited.
  See [electrical](architecture/electrical.md).
- The ERC reports 4 errors `power_pin_not_driven`, because there is no PWR_FLAG on
  VCC/GND.
- The mouse-bite footprints have no courtyard and share `REF**n` references. They cause
  186 DRC/parity warnings.
- Components sit on both sides of both boards, which forces double-sided assembly.

## Repository

- History before the 2026-09 cleanup contains large generated files (bitstreams,
  waveforms, KiCad backups). The history was deliberately not rewritten.
