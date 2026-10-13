# Simple single-board tile experiments

This directory contains experiments, not manufacturing-ready designs.

Start with [current development](../../../docs/architecture/current-development.md)
for the active FPGA/discrete shortlist and consolidated results.
[FOLLOWUP_RESULTS.md](FOLLOWUP_RESULTS.md) records the preceding comparison,
remaining gates and reproduction commands. [RESULTS.md](RESULTS.md) preserves
the first experiment round committed as `6572e0f`.

## Requirements

- Preserve the hardware-tested rev A tile frame and topology behavior.
- One PCB; Cherry MX-style SMD hot-swap sockets; practical equilateral pitch.
- No tile-side MCU, LEDs, or Hall sensors.
- Acceptance target: 20 MHz shift clock and up to 16 tiles.
- Chassis-supported, drop-in removable tiles.
- Strong preference for open hardware and a fully open build/programming flow.

## Work ownership

- `regression/`: self-checking reference behavior tests and results.
- `logic/`: discrete/SPLD/CPLD experiments, timing constraints and results.
- `connectors/`: mechanical placement and drop-in coupon studies.
- `checkpoints/`: one durable progress record per delegated worker.
- `fpga/`: open-toolchain FPGA RTL, behavioral comparisons and routed bitstreams.
- `fpga/system/`: timing-aware chain and latch-domain tests.
- `fpga/board/`: vendor-checked pin constraints and current placement prototype.
- `discrete-spld/`: pin-level circuits, decoded JEDEC checks and placement boards.
- `cpld-fit/`: CPLD candidate RTL, pin plan and unfitted synthesis handoff.
- `connector-next/`: aggregated interface and corrected cross-tile assembly study.
- `timing-chain/`: timed logic-chain models and 20 MHz SPICE burst experiments.

Existing revisions remain reference material. A candidate must pass functional
equivalence, timing, electrical, mechanical and layout checks before it can be
described as validated or manufacturing-ready. Zero-delay simulations establish
behavior only, not achievable hardware frequency.

SPLD/CPLD comparison artifacts are retained as reference, not active development
targets. The current scan-controller test fixture is `firmware/ice40/scan20/`.
