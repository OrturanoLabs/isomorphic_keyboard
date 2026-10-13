# Socket-rotation / GAL-fit study (follow-up)

Question from review: does a per-key 180-degree hot-swap socket rotation
legally open enough underside area to fit the ATF22LV10C TSSOP-24
(courtyard 7.7 x 8.3 mm) on the 18.36 mm lattice tile - and if not,
how much pitch is needed?

All numbers below come from `tools/rotation_study.py` (stdlib), output
`results/rotation_study.txt`.  Obstacle model = the vendored Kailh
footprint's own geometry: NPTH holes, SMD pads, and the CLOSED
B-courtyard polygon (re-chained from the vendored legacy arcs - the same
construction the connectors study uses), keep-outs hole+0.5 / pad+0.3
(connectors study params), plus the fixed connector-next 19-contact pad
lanes (SIG at y=21.72, GND lane at y=37.345).

## Rotation legality

Whole-unit 180 deg rotation (switch + socket + its pads/holes as a rigid
cloud) is legal on this tile:

* hex keycap: 60-deg rotation symmetry covers 180 deg;
* switch contact pin holes (+/-5.08, 0) are 180-symmetric about the
  switch centre;
* the plastic-peg NPTH set rotates with the unit as holes do (no absolute
  "north" for the pegs - the vendored cloud defines the pattern, and the
  rotated cloud is itself a consistent MX hole pattern);
* no contradiction found in the vendored footprint, checked by
  re-mapping every hole/pad point through the rotation.

## Pattern sweep results (0.25 mm free-space maps)

| pattern | biggest free rect | SIG/GND lane hits vs rotated courtyards | same-tile pad/court overlap pairs | 6-neighbour collisions |
|---|---|---|---|---|
| all-0 baseline | 63.25 x 6.25 | 0 | 0 | 0 |
| rows-alt | 63.25 x 11.00 | 11 (rotated row-1 courtyards reach the SIG lane) | 0 | 0 |
| cols-alt | 12.75 x 11.00 | 5 | 0 | 0 |
| all-180 | 72.50 x 6.25 | 13 | 0 | 0 |
| row0-only | 72.50 x 6.25 | 0 | 0 | 0 |
| row2-only | 63.25 x 6.25 | 2 | 0 | 0 |

Systematic enumeration over per-row families (none/all/edge-pair/centre-pair,
64 combos), lane-filtered first: **0 of 64 lane-clean patterns contain a
>= 7.8 x 8.3 mm free rect.**  (The east/west keep-out asymmetry of the
stepped outline is included; tiling checks used v=(4P,0), w=(-1.5P,3R) with
all six neighbours' pads+pads+courtyard bboxes - zero cross-tile overlaps in
every accepted pattern.)

### Verdict

* Socket rotation is mechanically legal but **cannot fit the GAL on the
  minimum tile AND keep the fixed 19-contact lanes clear.**  Both boards are
  therefore emitted in the baseline orientation.
* Relaxed-pitch path (if B2 is ever mandatory): the obstacle scan
  (`pitch_scan` in the same tool) finds the first pitch with an 8.3 mm deep
  island at **P' = 18.91 mm (+0.55 mm, +3.0%)**, R' = P' sin60 = 16.38 mm;
  at that pitch the same-tile and six-neighbour collision checks stay
  zero (verified by the same engine).  Lane positions/board outline at a
  relaxed pitch belong to the connectors workers' rebudget - this study only
  quantifies the tile-side pitch requirement.

## Layer count

Both boards stay 2-layer placement prototypes (no routing claimed).
No 6-layer option is proposed; if routing is ever attempted, the rev-C
family context says 4 layers is the realistic target - recorded here as a
note, not as a claim.
