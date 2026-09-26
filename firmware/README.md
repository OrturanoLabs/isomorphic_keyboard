# Firmware

| Folder | Content |
|---|---|
| `ice40/` | controller for the pico-ice (iCE40UP5K): tile scan, topology discovery, debouncing, MIDI UART |
| `experiments/` | earlier bring-up designs: `i2c_picoice` (I2C master test), `scan_low_rate` (slow tile scan), `scan_low_rate_i2c` (slow scan + I2C output) |

There is no microcontroller firmware yet: the pico-ice FPGA sends MIDI directly.

Build, flash and simulation: [docs/build/firmware.md](../docs/build/firmware.md).
Protocol: [docs/architecture/protocol.md](../docs/architecture/protocol.md).

License: GPL-3.0 (see `LICENSE.md`). The vendored Open Logic subset keeps its own license.
