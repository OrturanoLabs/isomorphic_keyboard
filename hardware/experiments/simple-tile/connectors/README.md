# Drop-in connector study for the passive simple tile

**Retired first-round study.** Current consumers use its geometry helper and
placement inputs as library/reference data. Its old coupon generator, runner
and coupon outputs were removed because subsequent review corrected the
outline, contact budget and cross-tile assumptions. Use
[`../connector-next/`](../connector-next/README.md) and the FPGA board study for
current work; do not treat the historical conclusions below as design approval.

Executable mechanical placement + connector comparison for the `simple-tile`
experiment (see `../README.md`): a single PCB carrying 12 Cherry-MX-style keys
in SMD Kailh hot-swap sockets keeping the **rev-A per-tile logic interface**
(the tile presents the four-direction rev-A edge nets, not a key matrix),
minimum practical equilateral lattice (~18.36 mm pitch), drop-in chassis,
no tile-side MCU/LED/Hall; target 20 MHz shift clock over up to 16 tiles;
open tooling only (KiCad flatpak + host python3 stdlib).

## Historical run (retired)

```sh
# The old pipeline was retired; use ../connector-next/run.sh instead.
```

Everything lands in `out/`. The study alone: `python3 study.py` (host python3,
stdlib only). Tool versions recorded in `out/versions.txt`
(KiCad 10.0.6 flatpak, pcbnew python 3.13; host python 3.14).

## What is computed (not typed in)

- Bottom-side obstacle model parsed from the vendored
  `hardware/kicad/lib/Switch_Keyboard_Hotswap_Kailh.pretty/SW_Hotswap_Kailh_MX_1.00u.kicad_mod`
  (2 SMD pads, 5 NPTH, B.CrtYd polygon chained into the real socket outline) +
  the `..._EdgeTrim` variant for the 3 keys whose pad would violate the edge
  clearance (the repo's own documented mechanism).
- Contact inventory derived from `docs/architecture/protocol.md`:
  28 tile-side pads in 4 direction groups (top 8, bottom 8, left 6, right 6),
  16 unique nets; B_clk/B_data merged across the bottom and right legs, as in
  rev A. Plus 3 presence straps (6 pads).
- Free connector islands: 0.25 mm grid harvest, shrunk one cell, then exact
  re-verified (`study.py::scan_islands`).
- Variant A: the four groups are placed into island lanes as tolerance-checked
  pad rows (nicknamed rails); the chassis-side springs go through an exact
  body-packing check (banks + orientation search against keep-outs that include
  the six lattice-neighbour tiles' socket projections).
- Variant B: mezzanine pairs measured with pcbnew from the installed KiCad 10
  library (DF12 20/30 pos, Gecko 12/20 pos).
- Backplane adjacency graph with executable truth checks on a 2x2 slot field
  (rev-A mating semantics, detect pins riding the neighbour's GND, hot-removal
  behaviour).
- Keycap collision study: pairwise polygon gap incl. cross-tile neighbours.
- Chassis z-budget: vendor free-height/deflection numbers vs the vendored STEP
  model's raw extent (upper bound + guard; axis mapping unverified; no nominal
  3D clearance is claimed).

## Results (64/64 checks pass; coupons: 0 DRC errors, 0 unconnected)

**Variant A (chassis springs on underside pads).** All 28 rev-A contacts place
collision-free in 4 rails over 2 island lanes (worst slack 1.38 mm after the
+/-0.35 mm chassis tolerance), plus the 3 detect straps. BUT neither sourced
spring part survives both the z-budget and the packing check: S1941-42R is
z-feasible (+1.56 mm vs the socket depth bound) yet cannot pack (5.70 mm-deep
bodies exceed the 3.65 mm 2-bank limit of the 8.6 mm free chassis bands);
S1971-46R packs (2 banks, verified) but is 4.55 mm free height vs a 5.74 mm
requirement. Derived requirement for the chassis contact part:
**free height >= 5.74 mm, body <= ~6.2 x 3.65 mm, tip area of a few by tenths
of a mm** (pad dia 2.5 mm is an assumption to confirm from the chosen part's
drawing). Candidates to explore next live in the Harwin EZi range (PD013
heights 2.5..7.3 mm). Tip offset inside the body (not verified here) can only
improve packing, never worsen it.

**Variant B (SMT mezzanine to passive backplane).** Scoped to the four measured
candidates: 20-contact parts (DF12-20, Gecko-20) are too small for the 22
contacts needed (16 nets + 6 detect-strap endpoints) -- rejection is computed,
not asserted; DF12-30 passes the pin budget but does not fit the minimal tile:
a +4.79 mm south "tab" extension is required and is certified by a collision
re-scan (Gecko-20 +4.5 mm analogously). The KiCad-stocked DF12 is the 3.0 mm
stack variant, which is below the 4.94 mm socket-depth bound, so the chassis
board would also need relief pockets under the 12 sockets; the DF12 series page
is flagged "Planned End of Life". Untested connector families (e.g. 0.4 mm
board-to-board) are not covered by this study -- the conclusion is scoped.

**Recommendation.** Variant A is the only one that keeps the tile minimal,
connectorless and lattice-continuous; it is viable as soon as the chassis
spring part is chosen from the derived budget (this study has exhausted the two
sourced candidates). Variant B remains the fallback and is fully quantified
(tab size, pocket requirement, verified footprints, extra part count).

## Coupons (drafts, `out/coupons/`)

Three 2x2-key boards built with pcbnew on the study's geometry; every copper
item placed only where the collision engine allows:

- `coupon_spring.kicad_pcb` - the real variant-A bottom rail (J103 group) +
  demo detect straps, SMD probe pads. 0 DRC errors, 0 unconnected.
- `coupon_mezz.kicad_pcb` - DF12-30 plug on the certified +4.79 mm tab; corner
  pads probed (pins 1/15/16/30). 0 DRC errors.
- `coupon_direct.kicad_pcb` - direct-wired reference: each key terminal routed
  to its own probe pad (row 0 north to a top probe row on a small extension,
  row 1 south), auto-jogged around switch holes; 8/8 routed. 0 DRC errors.

The DRC gate in `run.sh` never passes with errors **or** unconnected items;
warnings (cosmetic silk of library footprints) are reported, not gated.
Coupons remain **concepts, not fab-ready**: no schematic, no ERC, no placement
review against a real chassis CAD.

## Honesty notes / limits

- Socket depth below the board is a worst-case bound from the vendored STEP's
  raw points (axis mapping unverified) + 0.5 mm guard. No nominal 3D clearance
  is claimed anywhere; 3D assembly verification is a listed next step.
- Variant-A pad diameter (2.5 mm) and spring tip anchor position are
  ASSUMPTIONS to confirm against the chosen spring part's drawing.
- Chassis body packing is proved for tip-at-pad anchoring; a measured tip
  offset can only enlarge the feasible envelope.
- Half-mated presence detection keeps a documented caveat: a neighbour tilted
  toward its strap edge reads "present" while its data may not be mated; the
  scan protocol's marker bits remain authoritative, as in rev A/B.
- Price figures are deliberately absent (no sourced quotes at this stage);
  only part-count structure is compared.

## Files

- `study.py` - study runner (checks, SVG/JSON/report)
- `measure_footprints.py` - pcbnew library-footprint measurement
- Old coupon generator and pipeline: removed; recoverable from commit `6572e0f`.
- `out/`: `placement.json`, `placement.svg`, `report.md`, `checks.json`,
  `truth_table.json`, `mezzanine_measures.json`, `versions.txt`,
  `coupons/` (+ `coupons.json`, per-coupon `*.drc.json`, `drc_gate.json`)
