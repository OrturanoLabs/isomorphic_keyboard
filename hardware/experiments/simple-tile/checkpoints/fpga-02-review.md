# FPGA-02 four-layer trial — independent review

Date: 2026-10-16. Reviewer: Kimi-K3 subagent (read-only, host-light analysis;
no tool reruns, no pcbnew, no containers). Owned file: this note only.
Register unchanged: **FPGA-01 IN PROGRESS** (quote not obtained), FPGA-02
acceptance **NOT** met (73 opens), FPGA-03 hardware validation unwaived.

Sources read: FPGA_PLAN.md, current-development.md, checkpoints fpga-02.md,
fpga-layer-decision-review.md, fpga-vendor-stackup-review.md,
docs/fpga02_handoff.md, and the four-layer/** artifacts directly.

## Verified facts (artifact-level, exact paths/values)

1. Canonical 2L board intact: `fpga/board/out/kicad/tile_gw1nz.kicad_pcb`
   sha256[:12] = `c7d5b66fa1db` (re-measured today).
2. `four-layer/out/tile_gw1nz_4l_repaired.kicad_pcb` is a true 4L board:
   layers (lines 10-13) F.Cu/In1.Cu/In2.Cu/B.Cu; stackup block present:
   0.035/0.2104 prepreg/0.0152/1.065 core/0.0152/0.2104/0.035, `(thickness
   1.6)`. Four GND zones, all with filled polygons: F.Cu 1, B.Cu **2**,
   In1.Cu 1, In2.Cu 1.
3. Interface preserved (re-ran parser read-only): 210/210 (ref,pad,net,pos)
   identical to canonical; 19/19 JP contacts (incl. JP_GND_DET_T/B/R
   presence) identical coords+nets; 60 NPTH. 45 nets, supplies
   GND/VCC/VCC1V2/VCC1V2_RAW all present (21/27/7/3 pads variant == canon).
4. Final KiCad DRC `four-layer/out/tile_gw1nz_4l_repaired.drc.json`:
   153 warnings (silk 76+29+2, track_dangling 27, via_dangling 17,
   **connection_width 2**) / 73 unconnected pairs / 0 error-severity.
   Counts independently re-tallied from the JSON.

## Decisive findings (regressions vs checkpoint narrative)

F1. **All 52 fanout stub+via attaches are ABSENT from the final board.**
    `dsn_fix_types.json` (52/52 fixed, 0 type-route) proves they entered
    the router; the SES holds 27 nets, 29 vias, **0 power-net vias**
    (`_4l_widened.ses`, network_out census). The "(type fix)" wiring did
    not survive the freerouting round-trip/SES import: final 45 vias =
    29 SES signal vias + 17 GND stitch − 1 router via-in-chassis-pad
    removed (finish stage recorded 46; router log lines 23-33 shows its
    own fanout stage ran anyway, escaping 93/144). The trial's core 4L
    mechanism (plane attach) is therefore **not present in the measured
    artifact**; the checkpoint never states this. Fanout vias surviving
    on power pads: zero.

F2. **EP (U1-49) is grounded to a floating island, not to board GND.**
    B.Cu GND pour's second filled polygon (252 pts, x 5.42..10.30,
    y 3.11..7.69, inside the QFN ring) contains all 4 EP corners and the
    pad centre (no hole loop) → pour copper physically reaches under/over
    the EP land, but no via, pad-attach or stitch exists inside its bbox;
    it is disjoint from the main pour (separate filled_polygon) despite
    the zone declaring connect_pads=thru_hole_only. The DRC "zone-zone"
    unconnected pair (F.Cu zone ↔ B.Cu zone, uuids at the shared outline
    corner) is this island. Checkpoint "EP grounding resolves through the
    B.Cu GND pour" is **contradicted by the artifact**.

F3. **The 3 GND opens are real continuity holes (distinguished):**
    (a) U1-2 and U1-26 pads dangle vs F.Cu GND router fragments (3.7/4.5 mm
    gaps; their dogbone vias lost per F1); (b) the F.Cu↔B.Cu zone-zone pair
    = the F2 island; plus **TP_GND fully dangling** (no stub/via; router
    fragment starts 0.9 mm short; appears in 7 cross-net pairs — reporter
    proximity heuristic, not seven faults). "Continuous returns" is not
    just unmeasured — for these pads/island it is measuredly FALSE.

F4. **The 2 connection_width warnings are genuine fab-rule violations**,
    not maskable: B.Cu GND pour neck 0.1879 mm < 0.2 mm setup minimum
    (`_4l_repaired.drc.json`, zone uuid 45170f53, reported pos
    (63.7591,7.45)). 4L-introduced — new artifact of the B.Cu fill against
    pre-existing corner geometry; canonical's last DRC (107 warnings,
    zoneless) has no such item. "0 errors" framing must not hide these;
    the neck escapes I8 (segments-only check).

## Non-vacuity assessment

- variant_check I1/I4 re-verified independently (0 diffs; parser handles
  both writers). I5 shallow (presence-only; stackup values verified
  manually here); I6 axis-aligned rects only (rotated-pad edge cases
  possible, none flagged by KiCad DRC either); I7 does not gate "filled"
  for the final board (fills verified manually here: 4/4); I8 covers
  segments only (194×0.2 mm; 45 vias all 0.6/0.3 — verified separately).
- Schematic/board parity: canonical-side gates `out/netcheck_report.json`
  ok=true (negative_control 3), `out/board_checks.json` 2/2 ok,
  `out/kicad/tile_gw1nz_checks.json` 7 checks ok; repaired-board DRC json
  `schematic_parity: []`; variant↔canonical pad-net parity per point 3.
- manual_repair.py collides(): conservative pad disks, 0.2 edge gap,
  same-net skip, endpoint guarding; 6 candidates rejected on clearance —
  checker bites. One latent hazard: line 242-244 layer choice permits
  In1/In2 bridges in principle (none taken; 9/9 repairs B.Cu VCC, straight,
  ≤4.433 mm — matches `manual_repair_report.json`). Zone fill excluded
  from obstacle set but refill-after-repair + final DRC 0 clearance errors
  bound it.
- ses_widen: 2 sub-rule 0.15 mm router paths (B.Cu, nets K5 and L_clk —
  the recurring T3 offenders incl. an edge-critical clock) raised to 0.2
  pre-import; widen report confirms non-width bytes identical.
- SES `--full` gate correctly FAILS (27/45 nets); `--full` not claimed.

## Comparison honesty (2L vs 4L)

Router-internal metrics on the same 99-item denominator: 2L bare 46/99,
violations 0 (unverified metric, never KiCad-confirmed); true-4L log:
autoroute end "61 unrouted and 44 violations" (optimizer start shows 64 —
log line ambiguity, either way ~35-38 closed), freerouting violations 44
vs 0 on 2L. KiCad truth exists only for 4L: 99→81→73 opens. These are
**not comparable**; the trial demonstrates
partial closure progress (73<99) under strict 0.2/0.2 + 0.6/0.3 rules, but
**no evidence 4L improved router closure** — the fanout that was its lever
never reached the board (F1). The layer-review's "4L raises closure odds
MEDIUM-HIGH" remains unproven.

## Process (hardcap) honesty

Checkpoint honestly records: ~4 unguarded flatpak-pcbnew repair iterations
(<60 s, serial, lock free) under deadline pressure — a logged policy
deviation, not concealed; final DRC guarded (wall 2.7 s); router podman
2g/2g/1cpu/256pids (log: wall 849.7 s, exit 0). One transient flatpak
segfault recorded with probe evidence (not reproducible on identical bytes).

## Risk list (for the next bounded step)

- R1 (F2): EP island — fab EP solders to floating copper; must tie island
  to plane (via(s) inside it or outside-EP ring) before any fab claim.
- R2 (F1): power pads lack plane attach; 29 power opens (VCC 19, VCC1V2 7,
  VCC1V2_RAW 3) cannot close on surfaces alone at 0.2/0.2 — restore fanout
  AFTER SES import (discrete recipe order) or make router keep fixed vias.
- R3 (F4): 0.1879 mm B.Cu neck at (63.76,7.45) — fix zone corner/outline.
- R4 (F3): TP_GND/U1-2/U1-26 attach; zone-zone tie under U1.
- R5: 27+17 dangling tracks/vias are partial-route breadcrumbs; repair-by-
  patching is bounded out (35/74 pairs >6 mm apart).
- R6: inner-layer-signal assertion and adjacent_gnd_plane:true in
  finish_report are structural (not measured continuity); do not quote as
  return-path evidence.

## Recommended next step (bounded, no more bench docs)

Fix the finish-stage attachment loss: re-place the verified 52-pad fanout
(plus EP-ring or in-island via) **after** SES import in
`finish_4l_variant.py` — reusing the proven `build_4l_variant.py` site list
and collision checks — then iterate guarded freerouting rounds (import-safe
fanout) or close the 29 power opens with the bounded repair loop
(MAXDIST raised, only after R1/R3 fixed). Re-DRC; target: 0 opens, 0
connection_width, EP island tied. FPGA-03 hardware waiver: none.
