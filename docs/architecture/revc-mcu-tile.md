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
          top edge: VCC GND DATA_T                (passive pads)
        +-------------------------------------------------+
 left   |  12 x MX switch --> GPIO (internal pull-ups)     |  right
 edge   |                                                  |  edge
 pads   |  ATtiny1616 (SOIC-20, 5 V, 20 MHz)               |  springs
 VCC    |    DATA_L  DATA_R  DATA_T  DATA_B  (1 wire each) |  VCC
 GND    |    LED --> SK6812MINI-E x 12 (optional, chained)  |  GND
 DATA_L |    UPDI (programming pad)                        |  DATA_R
        +-------------------------------------------------+
          bottom edge: VCC GND DATA_B             (springs)
```

## Parts per tile

| Part | Qty | Notes |
|---|---|---|
| ATtiny1616-SN (SOIC-20 wide) or -MN (VQFN-20 3×3) | 1 | 1.8–5.5 V; 20 MHz at ≥ 4.5 V; open toolchain (avr-gcc, avrdude/pymcuprog, SerialUPDI) |
| 100 nF + 1–4.7 µF decoupling | 2 | |
| series resistor on each edge data line (~100 Ω) | 4 | edge-rate control and ESD/short protection on the hot-plug contacts |
| Kailh MX hot-swap socket | 12 | as rev B |
| SK6812MINI-E reverse-mount RGB LED + 100 nF | 12 + (3–12) | **optional**; in the Cherry MX drawing the LED window is **south** of the centre hole, opposite the pins/socket (north), so there is no conflict |
| edge contacts | 3–5 per edge | VCC, GND, DATA (+1 VCC/+1 GND for LED current) |

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
2. SOIC-20 wide (12.8 × 10.3 mm) vs VQFN-20 (3 × 3 mm) on the crowded bottom side: the
   placement study will decide.
3. Contact parts: spring contacts (bottom/right) + edge pads (top/left). Count 3 or 5 per
   edge.
4. Programming in production: UPDI pad per tile, or UPDI through an edge contact to
   flash tiles in place.
