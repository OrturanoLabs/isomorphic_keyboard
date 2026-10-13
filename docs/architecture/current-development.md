# Current single-board tile development

## Active choices

**FPGA is the lead; discrete logic remains the reference and a conditional
alternative.** Both preserve the hardware-tested rev A frame and topology
contract. Target: 20 MHz shift clock, up to 16 tiles, one PCB with SMD MX-style
hot-swap sockets, practical equilateral pitch and chassis-supported contacts.
No tile-side MCU, LEDs or Hall sensors are included.

Only rev A has been tested on hardware. New simulation, synthesis and placement
results are evidence for particular checks, not an assembled-system sign-off.

## FPGA progress

- The falling-latch snapshot implementation passes behavioral comparisons and
  open synthesis/place-and-route. The oscillator-tracking variant is retained
  only for characterization of its stale-sample window.
- The FPGA system suite passes **33 checks**, including deliberate assertion
  failures. Synthetic worst-corner exploration requires a longer latch guard
  for a 16-high column; real pad/interconnect/recovery values remain open.
- The commercial **GW1NZ-LV1QN48** pin map, rails and configuration straps have
  now been checked against the correct vendor documents (**DS841**, not DS861).
  Board-specific constraints produce routed bitstreams. The footprint fits the
  corrected tile placement; the studied iCE40UP5K package does not.
- The FPGA placement prototype has **zero error-severity DRC violations but
  90 unconnected pairs**: it is unrouted. Power-bank and presence-pad checks
  have negative controls. The three dedicated presence contacts share tile GND
  while their chassis traces remain separate.
- Exact core LDO selection, final routing, thermal/assembly review, physical
  contacts and measured external timing are still required.

See [FPGA board readiness](../../hardware/experiments/simple-tile/fpga/board/docs/readiness.md)
and [system test report](../../hardware/experiments/simple-tile/fpga/system/results/report.md).

## Controller test engine

`firmware/ice40/scan20/` is an isolated test fixture, not a replacement MIDI
firmware release. It supports sixteen frames and five-bit coordinates, and
completes each sixteenth shift pulse before advancing the frame.

The selected PLL produces **exactly 60 MHz** from 12 MHz. Three controller
ticks per bit produce **exactly 20 MHz**, with 33.33 ns high and 16.67 ns low.
The selected guard is 66.7 ns, above the tested synthetic deep-column floor.

**24 simulation checks pass**, including error/retry cases and caught mutants.
Standalone UP5K routing meets the 60 MHz tool constraint; timing margin is thin
and covers interior fabric only. The 120 MHz and 100.5 MHz alternatives do not
meet their constraints. Golden rev A firmware is preserved.

See [scan20 results](../../firmware/ice40/scan20/RESULTS.md).

## Discrete baseline

The nine-IC LVC/LV161A implementation is valuable as an independently checked,
no-programmer reference. Nine ICs is not a proven minimum.

Routing work found and fixed missing power-pin bindings in the canonical
circuit generator, as well as physical bottom-side footprint mirroring and the
old overlapping outline. Power/key/counter net-binding checks now pass.

The four-layer route is **not complete or acceptable for fabrication**:

- Placement prototype: zero DRC errors, **189 unconnected pairs**.
- Strict-geometry partial reference: **9 errors and 36 opens**.
- Most-connected router result: **12 opens but 1,090 strict-rule violations**;
  its sub-rule copper is rejected as a production layout.

Keep discrete effort bounded until a placement revision can improve routing.
Its role as a behavioral/electrical reference is useful even if it does not win
the final size/assembly-cost comparison. None of the partial boards is a
validated 20 MHz design.

See [discrete readiness](../../hardware/experiments/simple-tile/discrete-spld/layout/readiness.json).

## Other approaches: retired from active development, not disproven

The statement that the other approaches are discarded is **correct for the
active shortlist**, but too strong as a claim of technical impossibility:

- **SPLD/GAL:** the corrected four-IC version passed fuse and functional checks,
  but its package does not fit the fixed minimum-pitch layout and exact-part
  programming remains unverified. A relaxed-pitch placement study is reference
  evidence, not an active alternative.
- **ATF1502ASV CPLD:** functional RTL and a pin plan passed checks, but actual
  macrocell fitting and timing depend on a proprietary fitter not present here.
  Power and system timing also need validation.
- **MCU/LED/Hall direction:** outside the selected requirements; its superseded
  active project was removed.
- **Tested mezzanine-tab connections:** rejected for the dense tiled geometry
  after neighboring-board and mounting-hole checks. Spring contacts on tiered
  chassis rails are the current mechanical direction; physical fit and contact
  validation are still pending.

Comparison findings and useful verification fixtures remain as reference.
New development targets FPGA, its controller/connector integration, and the
discrete baseline only. No verified current-price comparison exists yet.
