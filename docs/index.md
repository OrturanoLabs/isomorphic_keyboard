# Isomorphic keyboard — documentation

- **Current development**
  - [FPGA lead, discrete reference and retired approaches](architecture/current-development.md)
  - [Single-directory consolidation and cleanup](CONSOLIDATION.md)
  - [FPGA board readiness](../hardware/experiments/simple-tile/fpga/board/docs/readiness.md)
  - [20 MHz scan-engine results](../firmware/ice40/scan20/RESULTS.md)

- **Architecture**
  - [Overview](architecture/overview.md): tiles, stacking, controller
  - [Scan protocol and topology discovery](architecture/protocol.md): connector pinout,
    frame format, how the grid is rediscovered on every scan, MIDI mapping
  - [Electrical design](architecture/electrical.md): parts, power, signal integrity
  - [Mechanical design](architecture/mechanical.md): dimensions, key lattice, frozen
    geometry
- **Build**
  - [Firmware](build/firmware.md): toolchain, build, flash, simulation
  - [Hardware](build/hardware.md): KiCad set-up, mandatory checks, tile simulation
  - [Bill of materials](build/bom.md)
  - [Assembly](build/assembly.md)
- [Known issues](known-issues.md)
- [Engineering ledger](LEDGER.md): what was tried, what failed, and why. Read it before
  starting a work session.

## Revisions

| Revision | State | Git |
|---|---|---|
| rev A | working prototype (double-stack tiles, hot-plug, MIDI DIN) | tag `rev-a-prototype` / `rev-a` |
| rev B | signal-integrity and assembly studies, not built | reference commit `d358953` |
| single-board development | FPGA lead; discrete reference; target 20 MHz / 16 tiles | current `rev-c` working tree |
