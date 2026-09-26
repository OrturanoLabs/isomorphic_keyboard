# Building and flashing the firmware

The controller firmware lives in `firmware/ice40/` and targets the **pico-ice**
(Lattice iCE40UP5K-SG48, 12 MHz clock), using the open-source flow:
GHDL + yosys (ghdl plugin) → nextpnr-ice40 → icepack.

## Toolchain

Pick one option:

1. **Rootless container (recommended, reproducible)**

   ```sh
   podman build -t localhost/oss-cad-suite:2026-09-26 tools/containers/oss-cad-suite
   cd firmware/ice40
   ../../tools/oss.sh make            # bitstream in build/hardware.bin
   ../../tools/oss.sh make sim        # GHDL simulation of sim/top_tb.vhd
   ```

2. **Local OSS CAD Suite:** `make OSS_CAD_SUITE=/path/to/oss-cad-suite`.
3. **Tools already on `PATH`:** `make`.

With the container image `oss-cad-suite:2026-09-26`, the reference bitstream of rev A has
sha256 `e3a7eaf9facde7d328df700aebb1f1d297bbbdcd1ccf5ca79be39f0315fec8d5`. A change that is
meant to be behaviour-neutral (comments, renames, refactoring) must reproduce this hash.

## Pinout (`constraints/up5k.pcf`)

| Signal | iCE40 pin | Function |
|---|---|---|
| `CLK_IN` | 35 | 12 MHz clock |
| `RESET_N` | 10 | reset button, active low |
| `BOARD_CLK` | 31 | scan clock → J103.2 of the first tile |
| `BOARD_LATCH` | 38 | latch → J103.6 |
| `BOARD_DATA` | 34 | serial data ← J103.3 |
| `PACKAGE_MIDI` | 21 | MIDI TX (inverted, to the DIN interface) |
| `LED_BLUE` / `LED_RED` / `LED_GREEN` | 40 / 41 / 39 | error of the main / scan / serializer FSM (active low) |

The tile ground and 3.3 V (J103.4/8 and J103.1) must come from the pico-ice as well.

## Flashing

`make upload-flash` (persistent, DFU alt 0) or `make upload-ram` (volatile, DFU alt 1)
uses `dfu-util`. When several boards are attached, select one with
`PICO_ICE_SERIAL=<serial>`. No `sudo` is needed once this udev rule is installed (one-time,
by an administrator):

```
# /etc/udev/rules.d/70-pico-ice.rules
SUBSYSTEM=="usb", ATTRS{idVendor}=="1209", ATTRS{idProduct}=="b1c0", MODE="0660", TAG+="uaccess"
```

Flashing through the container requires passing the USB device through
(`podman run --device /dev/bus/usb ...`). It is simpler to run `dfu-util` from the host.

## Simulation

- `make sim TB=top_tb STOP_TIME=15ms` builds and runs a testbench in `sim/build/`.
- `make wave` opens the waveform in GTKWave (`sim/gtkwave_dashboards/*.gtkw` hold saved
  views).

## Experiments

`firmware/experiments/` holds the earlier bring-up designs: I2C on the pico-ice, a slow
tile scan, and a slow scan with I2C output. They are kept for reference, and each builds
on its own with `make` in its folder.
