# Vendored: Open Logic (subset)

- Upstream: https://github.com/open-logic/open-logic
- Version: 4.5.0 (from the `olo_*_dev.core` files of the original full copy)
- License: PSI HDL Library License 1.0 (LGPL v2 or later with an exception for
  static linking / use in FPGA bitstreams), see `License.txt`. The per-file copyright
  headers are kept unchanged.

Only the files used by `../top.vhd` are kept (the full copy is in git history
before the reorganisation):

| File | Used by |
|---|---|
| base/vhdl/olo_base_pkg_{array,attribute,logic,math,string}.vhd | packages |
| base/vhdl/olo_base_strobe_gen.vhd | debounce tick, UART bit timing |
| intf/vhdl/olo_intf_sync.vhd | input synchronisers |
| intf/vhdl/olo_intf_debounce.vhd | 12-channel key debouncers |
| intf/vhdl/olo_intf_uart.vhd | MIDI UART (31250 baud) |

To update: copy the same files from a newer upstream tag, rebuild, and log the new
bitstream hash in docs/LEDGER.md.
