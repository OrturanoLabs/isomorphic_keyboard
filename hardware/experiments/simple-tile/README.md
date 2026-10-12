# Simple single-board tile experiments

This directory contains experiments, not manufacturing-ready designs.

Start with [RESULTS.md](RESULTS.md) for the independently verified comparison,
remaining gates and reproduction commands.

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

Existing revisions remain reference material. A candidate must pass functional
equivalence, timing, electrical, mechanical and layout checks before it can be
described as validated or manufacturing-ready. Zero-delay simulations establish
behavior only, not achievable hardware frequency.
