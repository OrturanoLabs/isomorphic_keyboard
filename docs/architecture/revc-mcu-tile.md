# Rev C tile with a microcontroller (architecture draft)

Status: **draft for review**. It supersedes the "74xx logic folded on one board" idea of
[revc-single-board.md](revc-single-board.md). The geometry work there (lattice,
edge windows, contact placement) still applies.

## Why the architecture changes

Rev C goals (owner, 2026-09-27):

- a single board;
- the minimum equilateral MX lattice (18.36 mm);
- few, simple, widely available parts;
- modular;
- **strictly open-source tooling**;
- room for a **return path**: per-key LEDs, or any tile-side output.

With 74xx logic, a return path costs extra shift registers and 1–2 extra lines per edge
(7–9 contacts per edge). The 18.4 mm tile has no room for that: the 74xx version already
leaves 13 connections unrouted on 4 layers, and the top edge fits only 7 contacts.

A small microcontroller per tile replaces all nine logic ICs:

- one **bidirectional** data line per edge carries key events up and LED commands down,
  so no extra contacts are needed;
- per-key addressable LEDs hang off one pin.

Why not a small FPGA per tile: it would need 1.2 V + 3.3 V regulators, cannot use 5 V
I/O, needs an external configuration flash, comes in fine-pitch packages and costs
2–6 €, for a job (12 keys, a few messages, 12 LEDs) that a 1 € microcontroller does
easily. The FPGA stays where parallel work pays off: the controller.

## Tile block diagram

```
          top edge: VCC DATA_T GND                (passive pads)
        +-------------------------------------------------+
 left   |  12 x MX switch --> GPIO (internal pull-ups)     |  right
 edge   |                                                  |  edge
 pads   |  ATtiny1616 (VQFN-20, 5 V, 20 MHz)               |  springs
 VCC    |    DATA_L  DATA_R  DATA_T  DATA_B  (1 wire each) |  VCC
 GND    |    LED --> SK6812MINI-E x 12 (optional, chained)  |  GND
 DATA_L |    UPDI (programming pad)                        |  DATA_R
        +-------------------------------------------------+
          bottom edge: VCC DATA_B GND             (springs)
```

## Parts per tile

| Part | Qty | Notes |
|---|---|---|
| ATtiny1616-MNR (VQFN-20 3×3 mm; the SOIC-20 wide does not fit) | 1 | 1.8–5.5 V; 20 MHz at ≥ 4.5 V; open toolchain (avr-gcc, avrdude/pymcuprog, SerialUPDI) |
| 100 nF + 1–4.7 µF decoupling | 2 | |
| series resistor on each edge data line (~100 Ω) | 4 | edge-rate control and ESD/short protection on the hot-plug contacts |
| Kailh MX hot-swap socket | 12 | as rev B |
| SK6812MINI-E reverse-mount RGB LED + 100 nF | 12 + (3–12) | **optional**; in the Cherry MX drawing the LED window is **south** of the centre hole, opposite the pins/socket (north), so there is no conflict |
| edge contacts | 3 per edge | VCC, DATA, GND: springs on the right/bottom edges, pads on the left/top edges |

That is about 7 parts without LEDs, instead of about 63 in rev B. There are no key
resistors: the switch goes to GND and the pin uses its internal pull-up.

## Switches and LEDs

- The Cherry MX drawing ("1-Pole w/LED") puts the LED window **south** of the centre hole:
  two 1 mm holes at ±1.27 mm, 5.08 mm from the centre. The switch pins, and therefore the
  hot-swap socket, are **north**, so the LED and the socket do not collide.
- For a reverse-mount SMD LED under the PCB, use "RGB"/"SMD-ready" switches with a clear
  top housing or light pipe: Cherry MX RGB, and most Gateron/Kailh/Outemu RGB variants.
  The KiCad footprint `LED_SMD:LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount` includes
  the PCB cut-out.
- SK6812MINI-E pins (KiCad symbol `LED:SK6812MINI-E`): 1 VSS, 2 DIN, 3 VDD, 4 DOUT.
- Keycaps: 3D printed. Use translucent material, or add a window over the LED.

## Pin budget (ATtiny1616, 20-pin; from the Microchip datasheet DS40002204A)

- 17 GPIO are usable, because PA0 stays **UPDI** so the tile can always be reprogrammed.
- Use: 12 keys + 4 edge data lines + 1 LED data = **17**.
- The one USART can map its TX pin to PB2 (default) or PA1 (alternate), and supports
  one-wire half-duplex (loop-back + open-drain). So 2 edges use the hardware USART and
  the other 2 use timer/pin-change based software serial. At the planned 100–250 kbit/s
  and 20 MHz this is comfortable.

## Power (5 V)

- The whole tile runs from 5 V, with no regulator (MCU and LEDs are specified for 5 V).
- The controller side (pico-ice, 3.3 V I/O) needs **one** level-shifted adapter to the
  first tile's bottom edge.
- LED budget: about 5 mA average per LED at moderate brightness × 120 keys (10 tiles) ≈
  0.6 A, all flowing through the contacts near the controller. Use 2 VCC + 2 GND
  contacts per edge, have the firmware cap the brightness, and feed from USB (≤ 0.9 A for
  USB 3, 0.5 A for USB 2) or an external 5 V supply.

## Protocol (first sketch)

- **Physical:** each edge is one open-drain, pulled-up line (idle high) with half-duplex
  UART framing. An unconnected edge reads high with no traffic, and a neighbour answers
  a probe, which gives presence detection without the rev-A/B GND tricks.
- **Enumeration:** the controller talks to the tile on its bottom edge. Each tile
  forwards discovery on its other edges, and the result is a spanning tree rooted at the
  controller with a relative position (row, column) for every tile, the same information
  the rev-A/B W/first/endcol logic produces.
- **Hot-plug:** periodic re-discovery (every ~100 ms) plus an event when an edge changes
  state.
- **Upstream:** key-down / key-up events, (tile id, key).
- **Downstream:** LED frames (tile id, 12 × RGB) and configuration.
- **Latency:** ~10 hops at 250 kbit/s with small frames is well under 1 ms.

## Controller

- The pico-ice RP2040 (pico-sdk, BSD) runs the tile protocol, the note mapping, USB-MIDI
  and DIN MIDI.
- The iCE40 is no longer required for scanning. It stays available for other uses.

## Open questions

1. ATtiny1616 (≈1.2 $, most established open toolchain, SOIC hand-solderable) vs
   CH32V003 (≈0.14 $, TSSOP-20, open ch32fun toolchain). The draft uses the ATtiny1616.
2. ~~SOIC-20 vs VQFN-20~~: VQFN-20 (the SOIC does not fit between sockets and LEDs).
3. ~~Contact count~~: 3 per edge (VCC, DATA, GND).
4. Programming in production: UPDI pad per tile, or UPDI through an edge contact to
   flash tiles in place.

## Routed layout (2 layers)

`hardware/kicad/tile/scripts/revc_mcu_route.sh` builds and routes the tile, open source end
to end (KiCad 10 Python + KiCadRoutingTools in a rootless container). The routed board is
kept in `hardware/kicad/revc-mcu-tile/` and passes KiCad DRC with 0 errors and 0
unconnected items. `tools/scripts/check_via_in_pad.py` finds no via within 0.2 mm of a
same-net SMD pad.

- **Stack-up:** 2 layers. The top (switch side, no parts) is an almost continuous GND
  plane, the reference for every signal. The bottom carries all parts, the signals, VCC as
  0.3–0.4 mm tracks and a GND pour stitched to the top plane on a 3 mm grid.
- **Rules:** 0.15 mm track and clearance (needed by the 0.40 mm-pitch VQFN), 0.6/0.3 mm
  vias, 0.25 mm hole clearance, 0.3 mm from the board edge.
- **No via-in-pad:** a via-only rule area surrounds every SMD land (0.3 mm, 0.2 mm on the
  MCU), so no pad needs filled and capped vias.
- **LED chain:** a serpentine. Rows 0 and 2 run left to right and row 1 right to left, so
  every link goes to a neighbour; the LEDs of the left-to-right rows are turned 180°. The
  chain order by key index is `0 1 2 3 7 6 5 4 8 9 10 11`, and the firmware must map
  chain positions with it.
- **LED cut-outs:** a track-and-via rule area fences each reverse-mount LED cut-out (routers
  see only the outer outline). A custom DRC rule (`revc_mcu.kicad_dru`) accepts the
  library land pattern's pads next to their own cut-out.
- **Decoupling:** 100 nF + 4.7 µF at the MCU and 100 nF next to the corner LEDs (D1, D4,
  D9, D12).
