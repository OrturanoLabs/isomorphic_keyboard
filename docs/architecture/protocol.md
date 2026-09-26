# Scan protocol and topology discovery

This page describes how the controller reads an arbitrary arrangement of tiles through a
single 3-wire link. It is derived from the rev-A schematic
(`hardware/kicad/tile/`) and the firmware (`firmware/ice40/src/top.vhd`).

## Signals between tiles

Every tile has four edge connectors. The mating pairs are top↔bottom and left↔right:

| Pin | J102 top (socket) | J103 bottom (header) | J101 left (socket) | J104 right (header) |
|---|---|---|---|---|
| 1 | VCC | VCC | VCC | VCC |
| 2 | `T_clk` (out) | `B_clk` (in, pull-up) | `L_clk` (out) | `B_clk` (in, same net as J103.2) |
| 3 | `T_data` (in, pull-down) | `B_data` (out) | `L_data` (in, pull-down) | `B_data` (out, same net as J103.3) |
| 4 | `T_endcol` (in, pull-up) | GND | `L_endrow` (in, pull-up) | GND |
| 5 | GND | `B_first` (in, pull-up) | `L_latch` (out) | `R_latch` (in, pull-down) |
| 6 | `L_latch` (out) | `B_latch` (in, pull-down) | GND | GND |
| 7 | `T_W` (in, pull-up) | `B_W` (out) | – | – |
| 8 | GND | GND | – | – |

The controller (pico-ice) is attached to the **bottom connector J103 of the bottom-right
tile**. It drives `B_clk` and `B_latch` and reads `B_data`. `B_first` is left open, so the
pull-up makes that tile "first".

Presence detection is passive:

- A tile above pulls our `T_endcol` low: its J103.4 is GND.
- A tile to the left pulls our `L_endrow` low: its J104.4 is GND.
- A tile below pulls our `B_first` low: its J102.5 is GND.

## Inside a tile

- **Two '165 shift registers** (U104 feeds the output, U103 feeds U104), loaded in parallel
  while the latch is high:
  - U104 D7…D0 hold keys 0…7.
  - U103 D7…D4 hold keys 8…11.
  - U103 D3 and D2 are tied to VCC (two marker bits that are always '1').
  - U103 D1 is `L_endrow` and D0 is `T_endcol`.
- **Latch:** `B_latch OR R_latch` (U106A) is inverted by U105 into `~rst`, which drives the
  '165 `~PL`, the '161 `~MR` and the '74 `~CLR`. The OR output is forwarded to the left and
  top neighbours (`L_latch`, one net on J101.5 and J102.6).
- **Clock:** `B_clk` (one net for the bottom and right connectors) clocks the registers.
  It is re-driven towards **either** the top or the left neighbour:
  - U107 ('125, active-low OE) drives `T_clk` when W = 0.
  - U101 ('126, active-high OE) drives `L_clk` when W = 1.
- **Serial input** (U103 DS) comes from `T_data` through U107 when W = 0, or from `L_data`
  through U101 when W = 1.
- **W** = `T_W AND B_first` (U102B). Only the **bottom tile of a column** (`B_first` = 1)
  can switch to W = 1, and only once the tile above has asserted its `B_W`.
- **Column-end detector:**
  - U109 ('161) counts clocks since the latch. Its terminal count `Tc` marks the 16th bit
    of every frame boundary.
  - U108 ('74) is a sticky flag: `D = Q OR (B_data AND Tc)`, clocked by `B_clk`,
    cleared by the latch. Its Q is `B_W`.
  - When a frame whose last bit (`T_endcol`) is '1' passes through the tile, the flag sets.
    That frame comes from the top tile of the column, so the flag signals "the top of the
    column has been read".
  - The flag propagates down the column. When it reaches the bottom tile, that tile
    switches its serial input and its clock output to the left neighbour. The chain then
    continues with the next column to the left.

## Frame format

After the latch, each tile contributes 16 bits. The FPGA shifts them in MSB-first
(`tile_stream <= tile_stream(14 downto 0) & BOARD_DATA`), so after 16 bits:

| `tile_stream` bit | Meaning |
|---|---|
| 15 … 4 | key states (key 0 at bit 15 … key 11 at bit 4), '1' = pressed |
| 3, 2 | markers, always '1'; anything else is a framing error |
| 1 | `L_endrow`: '0' = there is a tile to the left |
| 0 | `T_endcol`: '1' = this tile is the top of its column |

`map_pbs()` in the firmware reorders bits 15…4 into the physical key order.

## Scan sequence (firmware `pull_fsm`)

1. `r1`: `BOARD_LATCH` high for one scan tick. All tiles load their keys and their flags
   clear. The coordinates reset to column 1, row 0.
2. For every tile, 16 × (`get_bit`: sample `BOARD_DATA`; `c1`: `BOARD_CLK` high for one
   tick). One tick is 17 cycles of the 12 MHz clock (≈1.42 µs), so one bit takes ≈2.8 µs
   (≈350 kHz shift rate).
3. If the marker bits are not `11`, go to `err`. This is a sticky state, the red LED turns
   on, and only a reset clears it.
4. `load`: store the frame and its (row, column) in `keyboard_state`. If bit 1 is '0', a
   further column exists.
5. If bit 0 = '1' (top of column): continue with a new column if one was seen, otherwise
   the scan is done. If bit 0 = '0', read the next tile of the same column.
6. Repeat forever.

## From keys to MIDI

- Each tile slot has a 12-channel debouncer (open-logic `olo_intf_debounce`, 2 ms).
- A change detector XORs the debounced state with its value one clock earlier and
  accumulates the result in `keyboard_pending`.
- A serializer walks the pending bits and computes absolute key coordinates:
  - `y = (row − 1) · 3 + key / 4`
  - `x = (col − 1) · 4 + key mod 4 + row − 1` (each row of tiles is shifted by one key)
- Pitch = `ref_pitch − 2·x + 7·y` with `ref_pitch` = 60 (C4). One key to the left is
  −2 semitones and one row up is +7 semitones.
- It sends `0x90 pitch 0x64` (note on) or `0x80 pitch 0x00` (note off) on a 31250 baud UART,
  output inverted on `PACKAGE_MIDI` for the DIN interface.

See [known issues](../known-issues.md) for the limits of this implementation.
