# Hardware

| Folder | Content |
|---|---|
| `kicad/tile/` | KiCad project `isomorphic_tile`: key board (12 Cherry MX keys) and logic board (shift registers, chaining logic, edge connectors), fabricated as one panel |
| `simulation/` | behavioural VHDL model of a tile (`tile.vhdl`, `74hc165.vhdl`) and grid testbenches (`tile_tb*.vhdl`); run with `make` (GHDL), view with GTKWave |
| `fabrication/rev-a/` | gerbers and BOM of the rev-A boards as manufactured |

Start with [docs/architecture/overview.md](../docs/architecture/overview.md) and
[docs/build/hardware.md](../docs/build/hardware.md). The latter covers the mandatory
ERC/DRC/invariant checks.

License: CERN-OHL-S v2 (see `LICENSE.md`).
