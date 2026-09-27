# GAL experiment: rev-A/B glue logic in one ATF22V10C

`tile_glue.pld` puts the seven glue ICs of the rev-A/B tile (U101 2G126, U102 2G08,
U105 1G04, U106 2G32, U107 2G125, U108 2G74, U109 '161) into **one ATF22V10C** (Microchip,
in production, 5 V, TSSOP-24/SOIC-24). The two '165 shift registers stay, so a tile would
have 3 ICs instead of 9. The scan protocol and the FPGA firmware are unchanged.

| Macrocell | Function |
|---|---|
| Q0–Q3 (buried) | 4-bit counter of board-clock edges, cleared by the latch ('161) |
| BW | sticky column-end flag = B_W output ('74 + 2G08 + 2G32) |
| TCLK / LCLK | board clock forwarded up (W = 0) or left (W = 1) ('125/'126) |
| LATCH / NPL | latch merge to the neighbours and, inverted, to the '165 /PL ('32 + '04) |
| DS | serial input of the '165 chain: left when W = 1, top otherwise |

**All 10 macrocells are used: no margin left.**

The 22V10 allows a **single product term** for both the output enable and the
asynchronous reset. That forced two adaptations:

- T_clk is driven **low** when unselected instead of floating. At most this makes a
  falling edge, and the registers count rising edges.
- The asynchronous reset (AR) uses the feedback of the LATCH output.

Build (open source, rootless):

```sh
podman build -t localhost/galette tools/containers/galette
cd hardware/gal && podman run --rm --userns=keep-id -v "$PWD":/work:Z localhost/galette tile_glue.pld
```

This produces `tile_glue.jed`, plus `.chp` (pin diagram), `.fus` and `.pin`. Program it
with [Afterburner](https://github.com/ole00/afterburner), an open-source Arduino-based
GAL programmer. It lists ATF22V10B/CQZ; check ATF22V10C support before buying.

**Status:** assembled and fits. **Not simulated yet.** The equations were derived by
hand from the rev-A netlist.

**Verdict:** the GAL answers "fewer parts, no firmware on the tile". It does not provide
a return path for per-key LEDs, which is why rev C goes the microcontroller way.
