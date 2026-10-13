# connector-next: aggregated 19-contact drop-in interface

Extends the [`connectors/`](../connectors/README.md) baseline study (64/64
checks) for the passive simple tile (12 cherry-MX in SMD Kailh hot-swap,
18.36 mm equilateral lattice, drop-in chassis, rev-A per-tile logic, 20 MHz
acceptance context) with the derivation the review asked for: the MINIMUM
contact set preserving only the existing rev-A passive detects.

## Run

```sh
./run.sh
```

Pipeline (all artifacts in `out/`): pcbnew footprint measures
(`measure_next.py`) -> contact budget + 16-slot backplane graph
(`budget.py`) -> STEP registration (`step_axis.py`) -> placement/stagger/
mezzanine study (`study.py`) -> 3 draft coupons (`make_coupons_next.py`,
flatpak pcbnew) -> fresh kicad-cli DRC gate (**0 errors AND 0 unconnected**).
Tool log in `out/versions.txt`.

## Results (machine-checked)

- **Budget: exactly 19 contacts** (14 signals + VCC + GND + 3 dedicated
  detect-GND pads: J102.5 / J103.4 / J104.4). The baseline's +6 "DET strap"
  pads are removed as belt-and-braces; the 4x4 union graph proves per-slot
  removal flips exactly the expected neighbour detects (36/36), classes are
  preserved, and detect stubs float without a GND path. rev-B variant with
  per-leg series resistors R201..R207: 21 contacts (+2 nets). Directional
  rev-A floor: 28. (`budget.py`, 18/18 checks)
- **Placement**: the 19 pads sit in 2 tier lanes on the tile underside
  (15 signals + 4 GND-class), worst slack 1.375 mm after the +/-0.35 mm
  chassis tolerance; tiers are in *different* lanes so the chassis rail
  heights can differ.
- **Spring decision**: Harwin mini multi-directional SMT family
  (4.63x3.70 mm body): S1971-46R (free 4.55) + S1961-46R (free 3.55); the
  compact body packs on the chassis (baseline engine, 2 banks). Tiered rails
  r_sig 1.34 / r_gnd 1.49 mm put the tile bottom at 5.44 mm, clearing the
  conservative socket-depth bound 4.94 mm.
- **First-mate**: stagger = d_gnd - d_sig identity; explicit tilt sweep on
  the actual pad map gives a 0.24 deg zero-margin radius; the GND-first
  guarantee would need a ~36 mm pocket guide at +/-0.15 mm play ->
  **impractical; NO GND-first claim is made**; the requirement is recorded.
- **STEP registration** (feature match, not raw bbox): fp.x = stp.x,
  fp.y = -stp.y; solder-flat containment inside the pads 97%; board plane =
  solder-foot plate plane (spring boxes flush at the board top face within
  0.02 mm; the alternative is rejected by switch-collision). Socket depth
  below the board: 2.443 mm model-verified (4.94 mm bound retained).
- **Mezzanine @19 contacts** (fresh pcbnew measures, KiCad 10.0.6):
  DF12-20 pair fits the pin budget but the DF12 page is bannered 'Planned
  End of Life'; Gecko-20 pair (in production, measured THROUGH-BOARD tails —
  the baseline's 'SMT' label corrected) needs a certified +5.75 mm south tab;
  **DF40C-20DP(51)+DF40HC(3.5)-20DS(51)** (Hirose, in production, 0.4 mm
  SMT, 3.5 mm stack) got a custom tile-side footprint DERIVED FROM THE
  OFFICIAL STEP (0.400 mm pitch x 10x2, rows 3.185 mm); isolated-tile fit
  +3.24 mm tab; 3.5 mm stack clears the model-verified 2.94 mm bound (no
  relief pockets). Receptacle STEP was rate-limited -> receptacle footprint
  unverified -> pair gated on BOTH receptacle footprint and a NON-TAB
  layout. BM24-40 is bannered 'Not recommended for new design'. ALL
  certified tabs (incl. these two) are placement-NOFIT - see next bullet.
- **Cross-tile consequence (REVIEW fix)**: a tab certified on an isolated
  tile is NOT sufficient: with the corrected rev-c tiling outline every
  south tab collides with the south neighbour at minimal pitch, and raising
  the key pitch does NOT rescue it (gap = G - ext is pitch-independent).
  Placement-level remedy evaluation (fixed-point iteration re-certifying
  the island while the widened inset shrinks the board): **ALL tab
  candidates are NOFIT** - the shrunk board eats its own NPTH/pad edge
  clearances (worst drill-to-edge -1.39 mm). The earlier outline-only
  'remedy' wording was wrong and is withdrawn. The mezzanine/tab branch is
  rejected at placement level; the DF40 custom-footprint evidence stays as
  a gated non-tab candidate.
- **Baseline outline correction (measured here)**: the baseline stepped tile
  outline overlaps the up/down lattice neighbours by 1.46 mm (never checked
  outline-vs-outline). Connector-next uses rev-c-exact tiling
  (`TileTiling`, vertical margin R/2): exactly 1.0 mm at all 6 neighbours.

## Coupons (DRAFTS - concepts, no ERC; readiness = recorded DRC gate)

- `out/coupons_next/coupon_agg19.kicad_pcb`: 19 pads in 2 tier rails, all
  19 probed to SMD test pads.
- `out/coupons_next/coupon_mezz20.kicad_pcb`: Gecko-20 male (in production,
  THT tails) on the isolated-tile certified tab (branch NOFIT - concept
  geometry only), corner pads probed.
- `out/coupons_next/coupon_backplane.kicad_pcb`: 3-slot passive section,
  19 spring seats each (2.25 x 3.70 mm per DRG-03072/03073 drawing),
  the 3 dedicated detect-GND stubs routed per boundary
  (one backplane net per boundary, bonded to GND only through the removable
  tile), TPs on all nets incl. the stub wires.

## Honesty notes

- OpenSCAD is NOT INSTALLED; the assembly cross-check is a parametric SVG
  section (`out/section.svg`) + stdlib STEP registration - no 3D render
  claimed anywhere.
- Tile target pad dia 2.5 mm = drawing tab width 2.25 + 0.25 mm margin
  (documented relation); chassis seat pads follow DRG-03072/03073 (2.25 x
  3.70 mm, positioned-text read; drawings preserved in out/vendor_evi/).
  No fabrication release without a visual drawing confirm.
- Spring-contact pad-to-pad mask webs on the backplane coupon produce
  solder-mask-bridge *warnings* at the 0.75 mm pad gap (fab review item,
  not a gate failure).
- Prices not sourced: unknown, not quoted. No orders, no commits.
- Gecko pair mated stack height: not published on the pages fetched in this
  run -> recorded unknown (male/female drawings DRG-00182/DRG-00168 linked
  in `out/vendor.json`).

## Files

- `budget.py` - contact budget + 4x4 backplane union graph + fan-out
  counterexample (19 = scheme bound, not universal floor; B5..B7)
- `step_axis.py` - STEP registration against the footprint
- `study.py` - placement / stagger+tilt / mezzanine / SVGs / report
- `measure_next.py` - pcbnew footprint measures (flatpak)
- `df40_step.py` - DF40C-20DP custom footprint derived from the official
  Hirose STEP (in out/vendor_evi/, stdlib CARTESIAN_POINT analysis)
- `make_coupons_next.py` - coupon builder (flatpak pcbnew)
- `run.sh` - the pipeline + DRC gate
- `out/`: budget.json, budget_checks.json, mezz_next.json, step_axis.json,
  study.json, study_checks.json, vendor.json, plan.svg, section.svg,
  field.svg, report.md, versions.txt, coupons_next/ (3 coupons + DRC gate)
