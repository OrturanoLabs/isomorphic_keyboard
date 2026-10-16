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
  workstream's RTL (read-only) against the production maps (PASS;
  `RUN_VARIANTS="gw1nz"` narrows a re-run when only one cst changed).
- `kicad/sch_gen.py` -- authoritative schematic generator (gw1nz):
  emits `out/kicad/tile_gw1nz.kicad_sch` + local symbol lib. TRUE KiCad
  ERC at severity-all = **0 violations, no exclusions**
  (`out/kicad/tile_gw1nz.erc.json`).
- `tools/schematic_check.py` -- schematic<->board<->cst reconciliation
  S1..S7 + 3 negative controls (fresh ERC rerun, 45-net census,
  pad parity 144==144, cst port<->net<->pin mapping, strap + series
  node-set checks) -- PASS.
- `tools/drive_attr_ab.sh` -- durable proof that VHDL `attribute DRIVE`
  reaches the bitstream through the OSS flow while cst attrs are dead
  (fs_A==production hash, fs_B differs in exactly the 5 OBUF/TBUF cells).
- `tools/quote_prep.py` -- distributor-agnostic quote-package preparation:
  emits `docs/quote/bom_neutral.csv` + `docs/quote/cpl_gw1nz_provisional.csv`
  from the current pcb + bom.json with self-checks (census 65, ref parity,
  Value drift). Preparation for the BLOCKED quote gate; the board is
  still an unrouted prototype and the final CPL comes from KiCad's own
  exporter after routing.
- `tools/netclass_prep.py` -- FPGA-02 preparation: machine-checked
  net-class assignment of all 45 r6 nets (edge/level_out/channel_in/
  keys/power/config) with the strict reference rules, emitting
  `docs/netclasses.json` (self-checks N1-N5: exact partition, series
  topology re-read off the pcb, vacuity control). Preparation only.
- `docs/candidate.md`, `docs/power_reg.md`, `docs/readiness.md`,
  `docs/termination.md`, `docs/bom.md`/`docs/bom.json` -- decision,
  rails/straps/regulator (incl. r6 decoupling-placement table +
  load/thermal budget closure), honest gate ledger + open gaps, output
  termination decision-record (19 contacts kept; r6 series-R positions
  R7..R11 0R-populated; RTL DRIVE = proven free knob; cst attrs =
  UNVERIFIED vendor hints), and sourced BOM with the not-obtained-quote
  blocker recorded.
- `docs/quote/` -- quote-package checklist + generated neutral BOM /
  provisional CPL (2026-10-15; quote itself still NOT OBTAINED, needs
  account + upload on the routed board).
- `docs/routing_plan.md` -- FPGA-02 preparation: r6 routing census,
  measured escape geometry, rule-set candidates and the 2L-vs-4L
  comparison procedure (preparation only; FPGA-02 stays pending).
- `out/` -- regenerated artifacts (json/md/logs, placement txt, DRC, PnR).

## Regenerate / re-verify

```
python3 kicad/board_gen.py                 # ~10 min; emits out/kicad/*
python3 kicad/sch_gen.py                   # emits out/kicad/tile_gw1nz.kicad_sch + lib
python3 tools/footprint_verify.py          # land pattern vs vendor dims
python3 tools/pincon_check.py              # constraints vs vendor tables
python3 tools/board_net_check.py           # emitted-board netlist check
python3 tools/schematic_check.py           # sch<->board<->cst S1..S7 (reruns ERC)
tools/oss.sh bash hardware/experiments/simple-tile/fpga/board/tools/run_board_pnr.sh
tools/kicad-cli.sh pcb drc --format json -o out/kicad/tile_gw1nz.drc.json out/kicad/tile_gw1nz.kicad_pcb
tools/kicad-cli.sh pcb drc --format json -o out/kicad/tile_up5k.drc.json out/kicad/tile_up5k.kicad_pcb
```

## Status (2026-10-15, board r6)

Both boards are **placement-prototype clean** (0 DRC errors; unconnected
counts = unrouted nets by design; silkscreen-class warnings remain).
Electrical design is **scoped and verified at the gates above**: core
regulator selected + pinout-verified (TLV75512PDBVR), authoritative
schematic at TRUE ERC = 0 with schematic<->board<->cst parity proven
(incl. the r6 series-R split, 45 nets / 144 pads), output termination
decision-recorded with a frame-neutral mitigation implemented (R7..R11
0402 0R-populated positions -- placement proven, NOT routed proof).
Boards are still **not routed and not fab-ready**, the PCBA assembly
quote is **not obtained** (ordered FPGA-01/5 requirement, no waiver),
and FPGA-01 stays **IN PROGRESS** -- see `docs/readiness.md` and
`docs/bom.md`.
