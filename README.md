# Isomorphic keyboard

An open-source, **modular isomorphic keyboard**. The instrument is built from identical
12-key tiles that plug into each other in any arrangement. A pico-ice (Lattice iCE40UP5K)
rediscovers the arrangement on every scan and plays it over **MIDI**. Tiles can be added,
removed and moved while playing.

![Eight rev-A tiles](docs/media/rev-a-eight-tiles.jpg)

## Status

- **rev A** (tag `rev-a-prototype`): working prototype. Double-stack tiles (key board over
  logic board), hot-plug, automatic above/below/beside detection, MIDI DIN output.
- **rev B** (branch `rev-b`, in progress): the same function with cleaner signals
  (termination, 4-layer stack-up) and a PCB ready for automated assembly.

## Repository layout

| Path | Content |
|---|---|
| `docs/` | documentation: [index](docs/index.md), [engineering ledger](docs/LEDGER.md) |
| `hardware/kicad/tile/` | KiCad project of the tile (key board + logic board) |
| `hardware/simulation/` | behavioural VHDL model of a tile and grid testbenches |
| `hardware/fabrication/rev-a/` | gerbers and BOM of the manufactured rev-A boards |
| `firmware/ice40/` | controller firmware (VHDL) for the pico-ice |
| `firmware/experiments/` | earlier bring-up designs, kept for reference |
| `tools/` | rootless container recipes, `kicad-cli` / OSS CAD Suite wrappers, check scripts |
| `LICENSES/` | full license texts |

## Quick start

```sh
# firmware (rootless podman)
podman build -t localhost/oss-cad-suite:2026-09-26 tools/containers/oss-cad-suite
cd firmware/ice40 && ../../tools/oss.sh make && make upload-flash

# hardware
flatpak install --user flathub org.kicad.KiCad
flatpak run org.kicad.KiCad hardware/kicad/tile/isomorphic_tile.kicad_pro
```

See [docs/build/firmware.md](docs/build/firmware.md) and
[docs/build/hardware.md](docs/build/hardware.md).

## Licenses

| Part | License |
|---|---|
| Hardware (`hardware/`) | CERN-OHL-S v2 |
| Firmware and tools (`firmware/`, `tools/`) | GPL-3.0 |
| Documentation (`docs/`) | CC BY 4.0 |
| Vendored Open Logic subset (`firmware/ice40/src/open-logic/`) | PSI HDL Library License 1.0 |

Full texts are in `LICENSES/`. Each top-level folder has its own `LICENSE.md`.

© Orturano Labs
