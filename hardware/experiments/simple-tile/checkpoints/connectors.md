# Checkpoint: connectors worker (simple-tile)

Updated: 2026-10-12 (v2 rework after review)

## REVIEW FINDINGS (2026-10-12) — v1 state kept as provenance

v1 (kept in the section "Progress 2026-10-12 (final)" below) passed 43/43 checks but had
MAJOR scope defects found in review:

1. contact budget used a 4x3 matrix (12 pads) — WRONG. The user retains rev-A per-tile
   logic; the tile presents the full rev-A four-edge interface (J101/J102/J103/J104:
   8+8+6+6 = 28 pads; 14 unique signals + VCC + GND = 16 nets) plus removable-GND
   presence strap endpoints. Derived from docs/architecture/protocol.md.
2. cap() 17.86 mm square at R=15.9 makes caps collide between rows (same tile and
   across tiles). Must do pairwise collision incl. cross-tile neighbours and reject
   stock-square at this pitch; assumption becomes custom smaller/hex caps.
3. S1941 spring body (9.59 x 5.7 mm) cannot pack at 3.25 mm single row on the chassis;
   need chassis-side body packing check (stagger/multi-row allowed) or part rejection.
4. "GND at row ends = first-mate" unverified (needs contact-height staggering) —
   remove the claim.
5. Cost "0.5-1 EUR" unsourced — delete/label unknown.
6. Mezzanine NO-FIT covers only the two tested footprints — scope the conclusion.
7. run.sh exited 0 with 3 unconnected items on the coupon — the DRC gate must never
   pass with unconnected; coupon errors reported, gate honest.
8. Preserve early artifacts/notes as change provenance here (this section).

## v2 plan

- CONTACTS derived from the protocol table (28 tile pads grouped T/B/L/R with merged
  B_clk/B_data across bottom+right legs; nets named exactly as the protocol).
- Keycap model: square vs hex (lattice Voronoi cell shrunk by gap/2), pairwise
  collision within tile AND across neighbour tiles; report max square (expected
  ~15.4 mm) and the demonstrated 17.86-square overlap; select hex as assumption.
- Pad placer v2: direction groups mapped to underside lanes (edge windows or lanes),
  exact fit per group; publish net->pad mapping.
- Chassis packer: spring bodies (S1941 1/2/3-bank stagger; S1971 as small-body case),
  tip-offset flagged as assumption; fail honestly if unpackageable.
- Backplane adjacency graph for a 2x2 slot field + executable truth checks vs the
  protocol mating semantics (incl. B_first->below-GND).
- Coupons updated to the real pad plan; direct coupon gets an auto-jog router;
  run.sh gate = errors==0 AND unconnected==0.
- Re-run hermetically; record actual results.

## v2 results (2026-10-12, hermetic `run.sh` rc=0)

Study 64/64 checks; coupons 0 DRC errors + 0 unconnected (gate fails on either).

- Contact inventory: full rev-A interface from protocol.md: 28 pads (8/8/6/6),
  16 unique nets, B_clk/B_data merged bottom+right. Placed in 4 rails over 2
  island lanes, worst slack 1.38 mm after chassis tolerance; per-pad schedule in
  placement.json.
- Keycaps: square P-gap (17.86) shown to overlap (min gap 0.0, control CAP2) ->
  rejected; max square 15.4 mm; hex (Voronoi) at 0.5 mm gap verified incl.
  cross-tile. Hex is the ASSUMPTION, custom-printed caps.
- Chassis packing: S1941-42R correctly REJECTED (cannot 2-bank in the 8.6 mm
  free bands); S1971-46R packs (2 banks) but REJECTED by z (4.55 < 5.74).
  Derived part budget: free >= 5.74 mm, body <= 6.2 x 3.65 mm -> spring choice
  OPEN (Harwin EZi PD013 range to enter).
- First-mate claim removed (needs contact-height staggering; open requirement).
- Backplane graph (union-find, 4 slots x 28 pads): 8 truth checks pass,
  incl. hot-removal -> detect reads absent; six rev-A net classes preserved.
- Mezzanine scoped: DF12-20/Gecko-20 rejected by 22-contact budget (computed);
  DF12-30 budget-ok but no minimal-tile fit -> +4.79 mm tab certified.
- Coupons: spring = real J103 rail; mezz = DF12-30 tip-probed corners;
  direct 8/8 routed (row0 north strip +4 mm, row1 south). Two builder bugs
  found and fixed (dropped segs.append; track not touching pad).
- Known tight/unverified: strap_T slack 0.232 mm; spring tip offset; STEP axis
  mapping (bounds only).

## Task scope (as delegated)

Study drop-in removable 12-key passive tiles on a chassis for the `simple-tile`
experiment: single PCB, 12x Cherry MX on SMD Kailh hot-swap, minimum practical
equilateral lattice (~18.36 mm pitch), chassis structural, no tile-side
LED/Hall/MCU, acceptance target 20 MHz shift clock / up to 16 tiles, open tooling.

Deliver (in `hardware/experiments/simple-tile/connectors/` only):

1. Executable parametric mechanical placement study (runner script -> SVG + JSON +
   report) using the vendored Kailh hot-swap footprint (parsed, not hand-copied),
   NPTH switch holes, switch bodies and custom keycap assumptions;
   `hardware/kicad/tile/scripts/revc_*.py` are read-only references.
2. Comparison of (A) tile-underside pads vs chassis vertical spring contacts and
   (B) SMT mezzanine connector vs passive chassis/backplane. Free edge choice;
   do NOT reuse the rev-A/B imposed connector positions.
3. Collision-checked feasible connector islands from actual footprint/geometric
   extents; no invented part dimensions (datasheet URLs or "unverified" flags).
4. Passive presence detection preserved: GND strap via the REMOVABLE NEIGHBOUR
   tile only, never via permanent backplane GND. Checkable truth table
   (empty / seated / half-mated) for all 3 detect lines.
5. Small KiCad coupons via flatpak pcbnew: spring-pad reference, mezzanine with a
   verified library footprint if available, direct-wired reference; test points.
   If routing/DRC is unavailable, mark the coupon concept not ready.
6. Cost note: one PCB per tile vs one shared passive chassis/backplane board.
7. Record tool versions, source URLs, actual check results; end with files,
   checks, recommendation.

## Ownership

- WRITE: `hardware/experiments/simple-tile/connectors/**` and this checkpoint file.
- READ-ONLY reference: everything else in the repo (esp. `hardware/kicad/tile/scripts/revc_*.py`,
  `docs/architecture/revc-single-board.md`, `revc-mcu-tile.md`, vendored footprint in
  `hardware/kicad/lib/`). No commits. No edits to other workers' dirs
  (`regression/`, `logic/`, `checkpoints/<other>.md`).

## Environment baseline (measured 2026-10-12)

- Host: python 3.14.7 (/usr/bin/python3).
- KiCad flatpak org.kicad.KiCad 10.0.6 (user install); `tools/kicad-cli.sh version` -> 10.0.6;
  `flatpak run --command=python3 org.kicad.KiCad` -> python 3.13.15, pcbnew 10.0.6 (IMPORT_OK).
- KiCad stock footprints (flatpak, 155 libs): mezzanine candidates present
  (Hirose DF12 0.5 mm plug+receptacle pairs, DF40 0.4 mm, BM23FR/BM24 0.35 mm,
  Harwin Gecko 1.25 mm, Samtec HLE 2.54 mm). TestPoint.pretty present.
  NO spring-contact footprint in stock libs -> tile side of variant A is plain pads;
  chassis-side spring pin dims must come from datasheets or be flagged unverified.
- Vendored footprint `hardware/kicad/lib/Switch_Keyboard_Hotswap_Kailh.pretty/SW_Hotswap_Kailh_MX_1.00u.kicad_mod`:
  origin = switch centre; NPTH 4.0@ (0,0), 1.75@(+/-5.08,0), 3.05@(-3.81,-2.54) and (2.54,-5.08);
  SMD pads 1@(-7.085,-2.54) 2.55x2.5, 2@(5.842,-5.08) 2.55x2.5; B.CrtYd socket body lines.
  Source: perigoso/keyswitch-kicad-library v2.3, CC-BY-SA 4.0.
- Also `Switch_Keyboard_Hotswap_Kailh.pretty/SW_Hotswap_Kailh_MX_1.00u_EdgeTrim.kicad_mod`
  (pad 1 trimmed 0.3 mm for board-edge clearance).
- 3D models present: `lib/3dmodels/SW_Hotswap_Kailh_MX.stp/.wrl` (usable later for
  real 3D clearance; this study is 2D projection + labelled height data only).

## Plan / next steps

1. Parse vendored .kicad_mod into obstacle model (holes/pads/courtyard/fab) in a
   stdlib-only runner `connectors/study.py`.
2. Parametric 12-key equilateral tile (R = 15.9 body+margin row pitch, P = R/sin60
   ~ 18.36, 3 rows x 4 keys, row shift P/2). Tile outline = parametric minimal
   border; stepped vs rectangular outline compared.
3. Two connector variants, collision-checked island search on bottom side.
4. Presence-detection truth-table checker (executable simulation of the strap path).
5. KiCad coupons via pcbnew (`connectors/make_coupons.py`), kicad-cli DRC if usable.
6. `out/`: placement.json, placement.svg, report.md, verification log, versions.txt.

## Sourcing results (2026-10-12, via webfetch)

- Harwin S1941-42R SMT multi-dir spring contact: free height 7.3 mm, top-down working
  deflection 0.3..0.8 mm, 9.59 x 5.70 x 7.25 mm, gold contact. Product page
  https://www.harwin.com/products/S1941-42R (drawing DRG-02208 PDF linked there).
- Harwin S1971-46R: free height 4.55 mm, deflection 0.3..0.6 mm top-down,
  4.63 x 3.70 x 4.55 mm, 14 A. https://www.harwin.com/products/S1971-46R (DRG-03073).
- Harwin EZi range datasheet PD013 + C055XX component spec PDF URLs captured.
- Hirose DF12 series page https://www.hirose.com/en/product/series/DF12: 0.5 mm pitch
  SMT board-to-board, 3/3.5/4/5 mm stack heights; page flagged "Planned End of Life".
  KiCad 10 stock footprints exist for plug (DF12E...DP) and receptacle (DF12C...DS).
- Mill-Max catalog pages fetched but no per-part dims extracted (JS site); NOT used as
  a source. Spring-finger (Harwin) data is used instead.

## Vendored 3D model probes (host python3, measured)

- `lib/3dmodels/SW_Hotswap_Kailh_MX.wrl`: 22596 vertices, bbox x[-3.09..2.62]
  y[0.31..2.66] z[-1.42..-0.15] -- partial model (contact cage?), NOT the full socket.
- `lib/3dmodels/SW_Hotswap_Kailh_MX.stp`: 16027 CARTESIAN_POINTs, bbox x[-7.86..6.66]
  y[-0.25..6.75] z[-4.443..0]. Full-extent depth 4.44 mm from z=0 board face. Axis
  mapping to the board frame NOT verified -> used only as a worst-case bound for
  below-board socket height; labelled as such in the report.

## Consequence already visible

Chassis spring contact free height must exceed tile's deepest below-board feature
(socket, worst case 4.44 mm) + working window: S1971-46R (4.55 free) is NOT usable
with margin; S1941-42R (7.3 free) leaves ~2 mm over the socket worst case.
## Progress 2026-10-12 (study runner working)

Files (all in connectors/):
- `study.py` (parametric study, host python3, stdlib only). Working:
  parses vendored Kailh footprint S-expr (pads/NPTH/B.CrtYd polygon chained, 22 verts),
  STEP raw point bounds, equilateral lattice (P=18.3597, R=15.9), stepped+rect outlines,
  EdgeTrim per-key pad-variant selection, exact distance collision engine,
  island scan (0.25 mm grid harvest + shrink + exact recheck), variant A pad-row
  placer (GND at both ends, tol-expanded), variant B mezzanine fit + certified
  bottom-extension search, detection model + truth-table checker, SVG/JSON/report
  writers.
- `measure_footprints.py` (pcbnew probe) -> out/mezzanine_measures.json (done, pcbnew 10.0.6).
- out/: placement.json, placement.svg (valid XML, 282 el), report.md, truth_table.json, checks.json.

Latest run: `python3 study.py` -> 43/43 checks PASS (~12 s). Key results:
- stepped outline lattice-continuous (cross-tile pitch 18.36 mm both axes);
  EdgeTrim needed on keys (0,0),(0,1),(0,2) -> reuses repo's own variant (worst
  pad-to-edge 0.62 mm).
- 44 islands stepped / 54 rect; 5 full-width lanes; variant A row of 12 pads
  (d 2.5, pitch 3.25) fits with 1.45 mm slack after 0.35 mm chassis tolerance.
- Mezzanine does NOT fit minimal tile: df12 courtyard 8.29x6.29 -> +4.79 mm tab
  certified; gecko 11.14x6.0 -> +4.5 mm tab certified.
- Straps placed: T slack 0.23 (tight), B 5.53, L 3.10.
- Z: S1941-42R clears socket bound by 1.56 mm; S1971-46R rejected (-0.99).

## Progress 2026-10-12 (final - all deliverables in place)

`run.sh` passes end to end (rc=0): pcbnew footprint measure -> study (43/43
checks) -> 3 coupons -> coupon DRC gate (0 errors each).

Owned files (connectors/ + this checkpoint only):
- scripts: `study.py`, `measure_footprints.py`, `make_coupons.py`, `run.sh`,
  `README.md`
- artifacts: `out/{placement.json, placement.svg, report.md, checks.json,
  truth_table.json, mezzanine_measures.json, versions.txt}`,
  `out/coupons/{coupon_spring,coupon_mezz,coupon_direct}.{kicad_pcb,kicad_pro,
  kicad_prl,drc.json}`, `coupons.json`, `drc_gate.json`

Coupon DRC v2 (kicad-cli, KiCad 10.0.6): all three coupons 0 errors /
0 unconnected / gate pass (coupon_spring 232 silk-cosmetic warnings, mezz 38,
direct 9). Coupon readiness: concept, NOT fab-ready (no schematic/ERC; TPs are
B-side SMD because drilled probes sit inside the vendored switch courtyard).

Findings fixed along the way (for the record): pcbnew segfaults when flipping
an orphan footprint (Add before SetLayerAndFlip); vendored Kailh footprint is
authored with pads on B.Cu - no flip; KiCad DRC reads min_copper_edge_clearance
from the .kicad_pro, so coupons carry a rules block (0.4).

## Next steps (remaining)

Study complete. Ideas for a later pass: 3D assembly check (vendored STP +
chassis STEP), Harwin DRG-02208 tip-area review to firm the 2.5 mm pad
assumption, coupon silk cleanup.

## Job/process state

None running. v2 hermetic rerun: `rm -rf out __pycache__ && ./run.sh` -> rc=0,
64/64 checks, 3 coupons clean (0 errors, 0 unconnected). (Earlier hermetic pass
found and fixed a missing mkdir of out/coupons.)

## Open questions flagged for orchestrator (not blocking)

- None.
