# connector-next: aggregated drop-in interface study (generated)

Advances `connectors/` (baseline 64/64). Tile keeps the rev-A per-tile logic; 12 MX keys on SMD Kailh hot-swap; 18.36 mm equilateral lattice; drop-in chassis; 20 MHz / 16 tiles acceptance context; open tooling. OpenSCAD is NOT INSTALLED: 3D work is stdlib STEP registration + parametric section SVG, flagged honestly.

**Corrections over the baseline this pass** (all machine-checked here): (1) the baseline's stepped tile outline overlaps the up/down lattice neighbours by 1.46 mm (it never ran an outline-vs-outline check); connector-next uses the rev-c-exact outline (vertical margin R/2, horizontal P/2) which tiles with exactly rib_gap 1.0 mm - checks CT0/CT1. (2) the baseline called the Gecko pair 'SMT': the stocked footprints are through-board (0.55 mm drills) - check MZ3.

## Contact budget (budget.py, machine-checked)
- Aggregated rev-A budget of THIS scheme: **19 contacts** - NOT a proven global floor. The donor-fan-out variant (one GND contact per tile feeding up to 3 neighbour detect inputs) reaches 18 and its detect truth table is correct in all 17 occupancy states (check B5). Dedicated traces are kept regardless because an exhaustive single-point-fault sweep (816 cases) proves a copper fault falsifies up to 3 independent detections under fan-out vs 1 under the dedicated scheme, and 36/48 detect inputs would share nodes with other tiles' inputs (B6/B7).
- Scheme arithmetic: **exactly 19 contacts** (14 signals + VCC + GND + 3 dedicated detect-GND). The baseline's +6 'DET strap' pads are removed (existing rev-A passive detects suffice; no extra electronics anywhere).
- rev-B per-leg series-R variant (R201..R207): 21 contacts (+2: T_latch, R_data splits). Directional rev-A floor: 28 contacts.
- J102.5 / J103.4 / J104.4 detect-GND outputs get DEDICATED backplane traces, bonded to GND only through the removable tile's own copper. budget.py's 4x4 union graph proves per-slot removal: exactly the expected neighbour detects read absent, others stable, all nets in rev-A classes; detect stubs float with no GND path (18/18).

## Aggregated underside plan (exact engine, +/-0.35 mm chassis tol)
- **SIG tier** (15 pads, dia 2.5 mm, pitch 3.25): lane [-17.1, 18.9, 44.6, 24.4], worst slack 1.40 mm
- **GND tier** (4 pads, dia 2.5 mm, pitch 3.25): lane [-26.4, 34.7, 44.6, 38.7], worst slack 1.86 mm
- Tiers land in DIFFERENT lanes so the chassis can raise the GND-class rail independently.

## Spring part decision (manufacturer pages, fetched 2026-10-12)
- Compact mini multi-directional SMT springs share the 4.63x3.70 mm body: **S1971-46R** (free 4.55, defl 0.30..0.60) and **S1961-46R** (free 3.55, defl 0.20..0.60). The compact body packs on the chassis (2 banks, exact engine incl. six lattice neighbours); the tall S1941-42R (9.59x5.70) stays pack-rejected.
- Tiered rails: r_sig 1.34 mm, r_gnd 1.49 mm on the chassis board; tile bottom at 5.44 mm clears the CONSERVATIVE socket-depth bound 4.94 mm (feature-verified STEP depth 2.44 mm is reported alongside).
- stagger = 0.15 mm; identity stagger = d_gnd - d_sig at the final assembly, machine-checked.

## First-mate (stagger + tilt on the actual pad map)
First-mate is NOT a rev-A requirement: the original protocol works without contact-sequencing guarantees; the analysis below is kept as guidance only.
- Zero-margin tilt radius 0.242 deg; worst L1 pair separation 47.2 mm.
- **Verdict: NO GND-first guarantee is claimed.** It would need a ~36 mm pocket guide at +/-0.15 mm play; impractical, so the requirement is recorded instead. Marker bits stay authoritative.

## Mezzanine branch at the 19-contact budget (fresh pcbnew measures)
| pair | contacts | style | courtyard tile side (mm) | minimal tile | lifecycle |
|---|---|---|---|---|---|
| df12_pair20 | 20 (need 19) | SMT | [8.29, 6.29] | south tab +6.04 mm (certified) | 'Planned End of Life' series banner -> rejected |
| gecko_pair20_THT | 20 (need 19) | through-board (drills) | [16.14, 6.0] | south tab +5.75 mm (certified) | in production; THROUGH-BOARD tails (0.55 mm drills measured), baseline 'SMT' label corrected |

- **DF40 (plug+receptacle, 20 pos, 0.4 mm SMT, IN PRODUCTION)**: custom tile-side footprint DERIVED FROM THE MANUFACTURER STEP (df40_step.py: 2x10 pins, pitch 0.400 mm measured, rows 3.185 mm, feet 1.055x0.22 mm). Isolated-tile fit needs a +3.24 mm south tab - but the tab remedy is placement-NOFIT (see cross-tile section), so the pair is gated on a NON-TAB placement variant; its 3.5 mm stack would clear the model-verified socket bound 2.94 mm without chassis relief pockets. Receptacle-side footprint: STEP download was rate-limited this session -> NOT verified - candidate gate retained. 2D-drawing PDFs download fine but render ALL dimension text as outline curves (machine-unreadable; flagged).
- **BM24-40**: measured but 'Not recommended for new design' banner -> rejected.
- **Gecko MS1**: SMT male stocked (with peg drills), no stocked SMT female -> full-SMT Gecko pair not buildable from the library.

## Cross-tile tiles and certified tabs (REVIEW item)
A certified tab on an ISOLATED tile is not enough - two levels of proof were run and are reported separately:

1. **Outline separation.** Every certified tab COLLIDES with the south neighbour at minimal pitch (worst gap 0.0 mm); raising the key pitch does NOT rescue it (band corridor = G - ext, pitch-independent).
2. **Placement-level remedy evaluation.** Widening the inset G SHRINKS the PCB (tiles stay at their stations); the fixed-point iteration over (G, re-certified tab) was run per candidate with drill/NPTH-to-edge, socket-pad-to-edge, cross-neighbour switch-body gap, and net tab area all re-measured on the shrunk board. **ALL tab candidates are NOFIT** - the shrunk board eats its own NPTH/pad edge clearances before the tab stabilises. The earlier outline-only 'remedy verified' wording was wrong and is withdrawn.

| mezzanine | isolated tab (mm) | inset at fixed point | re-certified tab | drill-to-edge | pad-to-edge | verdict |
|---|---|---|---|---|---|---|
| df40_custom20 | +3.24 | 8.49 | +7.49 | -0.73 | 0.0 | **NOFIT** |
| df12_pair20 | +6.04 | 13.0 | +12 | -1.385 | 0.0 | **NOFIT** |
| gecko_pair20_THT | +5.75 | 13.0 | +12 | -1.385 | 0.0 | **NOFIT** |

Consequence: the mezzanine/via-tab branch is rejected at the placement level for the minimal lattice. Branch A (vertical spring contacts) does not use tabs and is unaffected.
## Spring land pattern (DRG evidence, not assumption)
Chassis-side solder pads for the Harwin S1971-46R / S1961-46R use the manufacturer's RECOMMENDED PCB PAD LAYOUT: 2.25 x 3.70 mm, read from the drawings DRG-03072/DRG-03073 by positioned text extraction (PDFs preserved in out/vendor_evi/). Tile-side target pads stay dia 2.5 mm = documented tab width 2.25 + 0.25 mm margin. No fabrication release: the land pattern association comes from text positions, and the drawing should still be visually confirmed before any order.

## Coupons (DRAFTS: no schematic/ERC; readiness = recorded DRC only)
- `coupon_agg19`: tile bottom, 19 aggregated pads in 2 tier rails, every pad probed to an SMD TP.
- `coupon_mezz20`: Gecko-20 male (in production) on the certified +4.5 mm tab, corner pads probed.
- `coupon_backplane`: 3-slot passive section: 19 spring seats per slot, the 3 dedicated detect-GND stubs routed per boundary (one net per boundary, bonded through the removable tile only), TPs throughout.
Fresh kicad-cli DRC gate per coupon: 0 errors AND 0 unconnected; see out/coupons_next/drc_gate.json.

## Honesty notes / limits
- Pad dia 2.5 mm and tip anchoring stay ASSUMPTIONS until the land pattern is traced from DRG-03072/03073 (vendor.json URLs); coupon is a concept.
- Prices not sourced - unknown.
- OpenSCAD unavailable; no 3D render claimed anywhere.

## Checks: 28/28 passed (out/study_checks.json)
