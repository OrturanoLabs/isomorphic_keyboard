# Checkpoint: connector-next worker (simple-tile)

Updated: 2026-10-12 — FINAL after mechanical review round. Hermetic
`bash run.sh` rc=0 across two consecutive runs: budget 21/21, step_axis 6/6,
df40_step 6/6, study 28/28, coupon DRC gate 0 errors / 0 unconnected on all
three coupons. `git diff` on tracked files: EMPTY. No commits/orders/installs.

## Mechanical review round 3 — resolutions (executed, not asserted)

Review point: widening the inset G SHRINKS the board (tiles stay at stations);
the earlier 'remedy verified' proof was outline-separation only. Resolved:

1. `evaluate_tab_remedy()` in study.py iterates the fixed point (inset G,
   re-certified tab via extended_fit at the widened inset), then re-measures
   on the final shrunk board: connector island slack, island edge slack,
   NPTH drill-to-edge, socket-pad-to-edge, cross-neighbour 15.6 mm switch
   body gap over ALL SIX lattice translations, and net added tab area.
   Verdicts (MZ6 checks, PASS = verified rejection):
   - df40_custom20: G=8.49, tab +7.49 (was +3.24): **NOFIT**
     (drill-edge -0.73 mm; island slack +0.52)
   - df12_pair20: G=13.0, tab +12 (was +6.04): **NOFIT** (drill-edge -1.385)
   - gecko_pair20_THT: G=13.0, tab +12 (was +5.75): **NOFIT** (drill-edge
     -1.385)
   => the south-tab mezzanine alley is placement-REJECTED for the minimal
   lattice, not merely colliding. Report/README/coupon text corrected (the
   old outline-only 'remedy verified' wording withdrawn; coupon_mezz20 text
   says concept geometry, isolated-tile certified tab only).
   Included analytical note: band corridor gap = G - ext (pitch-independent)
   -> key-pitch growth cannot rescue a tab either.
2. variant-A aggregate pads: all re-verified on the corrected TileTiling
   (revc-exact) outline each run (CN3/CN4 family: 19 pads, 2 tier lanes,
   worst slack after tolerance 1.395 mm, explicit pad-to-edge containment
   through tile.clearance + edge_slack; no fake class checks).
3. 18-contact fan-out: acknowledgement kept (B5 truth table correct in all
   17 states -> 19 = scheme bound, not universal floor), fault tradeoff
   kept (B6/B7: 36/48 inputs share cross-tile nodes; one-point fault
   falsifies up to 3 detections vs 1 with dedicated).
4. Coupon DRC: after coupon text update, all three coupons re-gated with a
   FRESH kicad-cli DRC run in the hermetic pipeline (not only changed ones,
   to stay honest): agg19 0/0, mezz20 0/0, backplane 0/0.

## Qualified viable branches (pitch/part requirements)

- **Branch A — vertical-spring pads on tiered rails: VIABLE (quantified).**
  S1971-46R (GND rail +1.49 mm) / S1961-46R (signal rail +1.34 mm), compact
  4.63x3.70 mm bodies pack (2 banks, 6-neighbour keep-outs), tile bottom
  5.44 mm >= conservative 4.94 mm bound (verified model depth 2.94 reported
  alongside). Chassis land: 2.25x3.70 mm per DRG-03072/03073. Spring tip
  anchoring + dia-2.5 target pads are documented relations, still awaiting
  a drawing-visual confirm before fabrication release. First-mate: guidance
  only (0.15 mm stagger, 0.24 deg envelope; NOT required by rev-A).
- **Branch B — mezzanine board-to-board: REJECTED at placement level** for
  every tested candidate (DF12-20 EOL; Gecko-20 through-board, not SMT;
  BM24 NRND; DF40 custom plug footprint STEP-derived but its tab remedy is
  NOFIT like the rest). DF40 remains a gated candidate ONLY IF a future
  non-tab placement variant is found (its 3.5 mm stack would clear the
  verified 2.94 mm bound without chassis relief pockets).

## Remaining hardware gates (report only)

1. DF40 receptacle STEP/land download (rate-limited here: HTTP 403) +
   drawing-visual confirm of the custom pad pattern; then a non-tab
   placement idea would be needed for branch B to reopen.
2. Visual confirm of the DRG-03072/03073 land-pattern association.
3. Full-tile KiCad schematic + ERC (coupons are concepts, no ERC).
4. 20 MHz / 16-tile SI review on the aggregated backplane routing.
5. Gecko mated stack height from the DRG section views (unknown here).

## Artifacts

connector-next/: budget.py, step_axis.py, df40_step.py, measure_next.py,
study.py, make_coupons_next.py, run.sh, README.md
out/: budget.json(+checks), step_axis.json, df40_plug.json(+checks),
study.json(+checks), vendor.json, mezz_next.json, report.md, plan.svg,
section.svg, field.svg, versions.txt, footprints/DF40C-20DP_connector-next.
kicad_mod, vendor_evi/ (DF40 STEP+2D, S1971R/S1961R, Gecko DRG-00182/168),
coupons_next/ (3 kicad_pcb + drc.json + drc_gate.json fresh).

## Running jobs

None.
