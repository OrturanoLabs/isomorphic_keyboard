# discrete-spld — pin-level discrete-glue tile candidates

Two tile-logic candidates on the simple-tile frame (18.36 mm equilateral MX
lattice, drop-in chassis, no tile-side MCU/LED/Hall, 20 MHz shift clock,
16 tiles max), carried from machine-readable pin-level circuits to
protocol-level proofs to KiCad placement boards:

| variant | glue ICs | total ICs | functional proof | placement on the dense tile |
|---|---|---|---|---|
| A — all-LVC + SN74LV161A + 2x LVC165A | 7 | 9 | PASS (33-config suite) | full placement, 0 DRC errors |
| A2 — A with 2x LVC2G241 for the buffer pair | 7 | 9 | PASS (same suite) | (netlist-equivalent to A) |
| B2 — ATF22LV10C-10 (truez) + 2x LVC165A + 1G04 | 2 | 4 | PASS (suite on the DECODED fuse map) | all placed EXCEPT the GAL: TSSOP-24 fits no lane-clear free rect (see rotation study) |

Interface: the **connector-next aggregate 19-contact** plan (14 signals +
VCC + GND + 3 detect-GND pads, straps removed), used at its published
coordinates; `T_latch`/`R_data` legs of the old 28-pad plan are folded into
`L_latch`/`B_data` as the budget worker specifies (5 x 33R series now, not
7).

## Layout

* `circuits/` — the pin-level circuit JSONs (`schema.md` documents the
  format).  `reva_reference.json` is the rev-A export with the interface
  block completed + verified by `tools/keymap_check.py`.  `variant_a.json`,
  `variant_a2.json`, `variant_b2.json` are authored in
  `tools/gen_circuits.py` on rev-A's passive plan.
* `results/` — every check output (see below).
* `boards/` — generated KiCad boards (placement prototypes, unrouted by
  design) + placement/DRC reports.
* `tools/` — the toolchain (python stdlib only).

## Verification pipeline (all re-runnable)

```
python3 tools/keymap_check.py        # rev-A keymap+interface assertions
python3 tools/gen_circuits.py        # variant circuits
python3 tools/jeddec.py ...          # GAL22V10 fuse-map decoder (galette+jedutil cross-validated)
python3 tools/galcheck.py ...        # fuses vs source equations, exhaustive
python3 tools/sim_tile.py [--quick|--shapes ...|--circuits ...|--modes ...]
python3 tools/bom_check.py           # BOM census vs rev-A
python3 tools/rotation_study.py      # socket rotation / GAL-fit study
python3 tools/board_gen.py           # KiCad boards + placement + coll. checks
tools/kicad-cli.sh pcb drc boards/<v>/tile_<v>.kicad_pcb --format json --output boards/<v>/drc_raw.json
python3 tools/build_costs.py         # costs table (sourced-or-unknown)
```

Note: the full sim suite takes ~3.5 min; the earlier 120 s timeout was a
shell limit, not a failure — the complete run is recorded in
results/sim_suite.txt (33/33 PASS).  `--quick` finishes in seconds.

## Result index

| file | content |
|---|---|
| `results/keymap_check.txt` | rev-A keymap/pin map verification (all PASS) |
| `results/jeddec_{truez,golden}.txt` | fuse-map decode + checksums OK |
| `results/galcheck_{truez,golden}.txt` | 20/20 equation MATCH each |
| `results/sim_suite.txt` | 33/33 protocol configs PASS (3 variants) |
| `results/fewer_ics.md` | IC-count survey, corrected (no minimum claimed) |
| `results/bom_check.txt` | BOM census |
| `results/costs.{json,md}` | costs per tile (prices unknown — blocked fetches; MPNs datasheet-confirmed) |
| `results/programmer_gap.md` | ATF22LV10C programming gap report + bench plan |
| `results/rotation_study.{txt,md}` | socket-rotation feasibility + relaxed-pitch quantification |
| `results/boards_drc.md` | DRC digests (0 errors both boards) |
| `results/battery.log` | last full end-to-end battery output |

## Answers (current state)

1. **Faithful pin-level A and B2 circuits: done and simulation-proven**;
   B2's GAL behaviour comes from the decoded fuse map, not the source
   assumption.
2. **Fewer discrete parts:** 9-IC baseline (7 glue + 2 SR) is a working
   *partition*, not a proven minimum; surveyed swaps are count-neutral
   (`results/fewer_ics.md`).  The real consolidation is B2's SPLD route
   (4 ICs), blocked on geometry as quantified below.
3. **Boards:** both are placement prototypes with **0 DRC errors** under
   kicad-cli 10.0.6 (only cosmetic silk warnings; unconnected counts are
   the honest unrouted totals: vA 175 items / ~52+empty nets, vB2 129/48).
   Board copies normalize the vendored Kailh socket's courtyard to a closed
   B-side polygon (documented in board_gen.py) — the vendored lib is not
   touched.
4. **Socket rotation for the GAL** (tasked exploration): 180 deg rotation
   is mechanically legal here (documented), opens 63.25x11 mm undersides in
   some patterns, but every lane-clean pattern still misses the 7.7x8.3 mm
   GAL courtyard (0/64 structured candidates; the connector-next lanes are
   fixed).  Relaxed-pitch requirement quantified: P' >= 18.91 mm (+0.55,
   +3.0%) opens an 8.3 mm island, collision-free with all six neighbours at
   that pitch — chassis rebudget required; classified as the relaxed-pitch
   path, not pursued further here.
5. **Programmer gap** for ATF22LV10C: documented with upstream evidence
   (`results/programmer_gap.md`); no hardware touched.
6. **Layer count note:** 2-layer placement prototypes; no 6-layer option
   proposed anywhere (if routing ever happens, 4 layers is the family
   target — recorded as a note only).

## Integrity notes

* No fabrication or timing sign-off is claimed anywhere; these are
  placement prototypes + logic proofs.
* The boards are 2-layer, 1.6 mm, per the frame; all DRC classes are
  itemised in results/boards_drc.md with classifications.
* Prices are 'unknown' with recorded fetch evidence - no invented numbers.
* The rev-A BOM check found no symbol/silicon pinout errors (incl. the
  2G74 SM8 single-FF question, resolved per TI SCES203Q).
