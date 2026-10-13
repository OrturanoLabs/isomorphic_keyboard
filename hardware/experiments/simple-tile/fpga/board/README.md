# fpga/board -- single-PCB FPGA tile: placement + circuit prototype

Owner: fpga-board worker. Package/board facts come from vendor documents
(sha256-stamped in `data/*.json`) and machine checks in `tools/`; nothing
here is inferred from synthesis tool behavior.

## Layout

- `data/pins_gw1nz_qn48.json`, `data/pins_ice40up_sg48.json` -- per-pin
  provenance DBs (role, rail, vendor doc + section + sha256) for the two
  candidates. Pin 9 (GW1NZ) is excluded: automotive UG846 disagrees with
  commercial UG842 on it (VCC vs IOR2A) -- order-code hazard.
- `constraints/tile_gw1nz_board.cst`, `tile_up5k_board.pcf` -- PRODUCTION
  pin maps (26 tile IOs verified against the vendor tables; JTAG/config/
  strap pads reserved). These supersede `fpga/synth/*` (empirical chipdb
  probe proposals). Do not edit `fpga/**` from here.
- `kicad/board_gen.py` -- deterministic board builder (corrected revc
  TileTiling outline, 12 Kailh sockets, 19 connector-next chassis pads,
  passives, TPs), self-check gates GK1..GK7.
- `kicad/gen_footprints.py` -- the two custom QFN48 footprints.
- `kicad/lib/fpga_board.pretty/` -- generated custom footprints.
- `tools/pincon_check.py` -- constraint-vs-vendor-table checker (B1..B6,
  H1, S1; both variants PASS).
- `tools/footprint_verify.py` -- footprint land pattern vs vendor package
  dims, incl. negative control (both PASS; UP5K land = LAND-TBD).
- `tools/board_net_check.py` -- netlist/power-pin binding checker on the
  emitted .kicad_pcb, incl. negative controls (both PASS).
- `tools/run_board_pnr.sh` -- real yosys/nextpnr PnR of the fpga
  workstream's RTL (read-only) against the production maps (PASS 4/4).
- `docs/candidate.md`, `docs/power_reg.md`, `docs/readiness.md` --
  decision, rails/straps/BOM, and the honest gate ledger + open gaps.
- `out/` -- regenerated artifacts (json/md/logs, placement txt, DRC, PnR).

## Regenerate / re-verify

```
python3 kicad/board_gen.py                 # ~10 min; emits out/kicad/*
python3 tools/footprint_verify.py          # land pattern vs vendor dims
python3 tools/pincon_check.py              # constraints vs vendor tables
python3 tools/board_net_check.py           # emitted-board netlist check
tools/oss.sh bash hardware/experiments/simple-tile/fpga/board/tools/run_board_pnr.sh
tools/kicad-cli.sh pcb drc --format json -o out/kicad/tile_gw1nz.drc.json out/kicad/tile_gw1nz.kicad_pcb
tools/kicad-cli.sh pcb drc --format json -o out/kicad/tile_up5k.drc.json out/kicad/tile_up5k.kicad_pcb
```

## Status (2026-10-13)

Both boards are **placement-prototype clean** (0 DRC errors; unconnected
counts = unrouted nets by design; silkscreen warnings remain). They are
**not routed and not fab-ready** -- see `docs/readiness.md`.
