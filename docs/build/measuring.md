# Measuring the tile signals (Analog Discovery 2)

The 2026-06-15 capture (`hardware/si/measurements/`) showed about 27 % overshoot, −1.0 V
undershoot and 16–20 MHz ringing on the board clock. The simulations in `hardware/si/`
separate what the tile really does from what the measurement adds.

## What the instrument can and cannot show

- The AD2 analog inputs have about 30 MHz of bandwidth: the displayed **10–90 % rise time
  is about 11 ns**, even for a 1 ns edge. The LVC parts switch in about 0.5–1 ns, so the AD2
  never shows the real edge or the real overshoot peak. It shows a smoothed version.
- At 100 MS/s there is one sample every 10 ns, i.e. 2–5 samples per ringing period. What
  WaveForms draws between the samples is interpolation.
- The probe ground loop forms an LC resonator with the 24 pF input. Simulated view of
  a **clean** edge (`probe_effect.py`):

| Probe connection | Apparent overshoot | Apparent undershoot |
|---|---|---|
| spring ground tip (~5 nH) | 4 % | −0.14 V |
| short ground clip (~50 nH) | 4 % | −0.15 V |
| 15 cm ground clip (~200 nH) | 5 % | −0.17 V |
| AD2 flywires, signal + ground (~1 µH loop) | **47 %** | **−1.57 V** |

The first three rows are simply the AD2 front end (a 30 MHz Butterworth has 4 %
overshoot). With a 30 MHz instrument, a spring tip is not a big improvement over a short
clip. **The flywire loop, however, invents ringing of the same size as the one in the
capture.**

## Recipe for a meaningful measurement

1. Use the AD2 **BNC adapter + a 10× passive probe**, not the flywires. Connect the probe
   ground with the **spring tip or a clip shorter than 3 cm**, to a GND pin next to the
   signal. On the edge connectors, the GND pins are J103.4/J103.8 and J101.6.
2. Probe **at the receiving pins**, not at the connector:
   - clock: U103/U104 pin 2 and U109 pin 2 of the **far** tile;
   - latch: U105 pin 2.
3. Set the probe to 10× in WaveForms and trigger on the channel itself.
4. Read the result against the simulated AD2 view (`fit_measurement.py` prints it), **not**
   against the node voltage. With a 30 MHz front end a clean rev-B edge looks like a ~11 ns
   ramp with ~4 % overshoot.
5. For the real overshoot of a 1 ns edge you need at least 300–500 MHz of bandwidth, e.g. a
   borrowed lab scope. Only then compare with `tile_hop_ibis.py`.
6. Functional check without any scope: the red LED of the pico-ice lights on a framing
   error (sticky). Leave the instrument scanning for 10 minutes while plugging and
   unplugging tiles. No red LED means no double-clocked frames.

## Test points for rev B (suggestion)

A 2-pin 1.27 mm footprint (signal + GND) next to the far `B_clk` load and next to U105
pin 2 would allow a spring-tip measurement without clip leads. It is a non-functional
PCB addition and can be added in the GUI review.
