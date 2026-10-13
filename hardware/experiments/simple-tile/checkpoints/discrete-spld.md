# Checkpoint: discrete-spld (pin-level circuits + candidate boards)

Worker scope: `hardware/experiments/simple-tile/discrete-spld/**` and this checkpoint
file only. No edits elsewhere; no git commits; existing files read-only.
Started 2026-10-12 (restart of an interrupted prior attempt; no prior checkpoint
or edits existed for this scope).

## Task (as delegated)

Acceptance frame: 20 MHz shift clock, 16 tiles, 12 MX hot-swap keys per tile on the
18.36 mm equilateral lattice, drop-in chassis, no tile-side MCU/LED/Hall, strong
open-hardware/open-flow preference, cheap.

1. Advance **variant A** (all-LVC glue + SN74LV161A counter + two SN74LVC165A) and
   **variant B2** (ATF22LV10C-10 glue + two SN74LVC165A + SN74LVC1G04, true-Z T_clk)
   on the simple-tile frame.
2. Read existing logic models (`logic/equivalence`, `logic/pld`), the timing JSON
   (`logic/timing/timing.json`) and the rev-A circuit/keymap
   (`hardware/kicad/tile/`, `docs/architecture/protocol.md`).
3. Build faithful **machine-readable pin-level circuits** + a **BOM checker against
   rev A**. Investigate fewer discrete ICs using actual mux/consolidation parts
   only if behavior is proven.
4. Generate **KiCad candidate placement boards** for both variants with actual
   footprints/holes, SMD hot-swap sockets, decoupling, source resistors, test
   points (pcbnew via flatpak). Collision-check courtyards of all packages; report
   routing/unconnected honestly. No fabrication-readiness claim without
   schematic/DRC. If schematic/netlist generation is viable, produce authoritative
   connectivity; else stay at an explicit circuit-prototype stage.
5. Close the **JEDEC-vs-equations gap** (5892-fuse parse or supported open jedutil
   model): decode the corrected true-Z design's counter/flag/OE-feedback from the
   actual fuse map, crosscheck, self-tests. If only "model the actual fuses" is
   achievable, say so; do not invent JEDEC provenance.
6. Inspect upstream **Afterburner** and **minipro** sources for the exact
   ATF22LV10C programmer gap; write a bench plan incl. publicly available
   programming pin conditions. Do NOT program hardware, patch a programmer, or
   guess VPP.
7. Costs: actual sources or "unknown".
8. Run all checks; preserve existing files read-only; no orders, no commits.

## Baseline observed (before my first edit)

- Repo HEAD = `6572e0f` on branch `rev-c` (baseline given by caller).
- `git status --short` before my edits: `?? hardware/experiments/simple-tile/checkpoints/cpld-fit.md`
  (pre-existing untracked file, NOT mine; left untouched).
- Owned dirs `discrete-spld/` + this checkpoint did not exist before start.
- Reference inputs (read-only): `hardware/gal/tile_glue.{pld,jed,pin}`,
  `logic/pld/tile_glue_truez.pld` + `logic/pld/results/tile_glue_truez.jed` (B2),
  `logic/equivalence/*.vhdl`, `logic/timing/timing.json` + `calc_timing.py`,
  `hardware/kicad/tile/*.kicad_sch` (rev-A keymap/netlist),
  `connectors/out/placement.json` (tile outline, 12-key lattice, 28-pad chassis
  contact plan), `docs/architecture/{protocol,electrical,mechanical}.md`.
- Tools: KiCad flatpak 10.0.6 (`tools/kicad-cli.sh`), flatpak pcbnew python,
  `localhost/galette` (crates.io galette, github simon-frankau/galette),
  `localhost/oss-cad-suite:2026-09-26` (GHDL 7.0.0-dev, yosys; `tools/oss.sh`),
  host python 3.14.7. jedutil/minipro NOT installed (sources cloned to /tmp for
  read-only inspection only). Network: available (github reachable).

## Recovered state at restart (2026-10-12, second resume)

- Verified on disk: `discrete-spld/` contains only step-1 partial output:
  - `circuits/reva_kicad_export.xml` (145,904 B; kicad-cli netlist export of rev-A,
    3407 lines), `circuits/reva_reference.json` (83 components, 75 nets; interface
    mapping still empty `{}`), `tools/kicad_xml_to_json.py` (74 lines, stdlib).
- JSON parses OK (python3 json.load). No simulator/circuits/boards/JEDEC tools yet.
- Git status: only expected untracked paths (mine + other workers' fpga/,
  connector-next/, checkpoints/). No modifications to tracked files.
- No running jobs, no containers started by me (checked earlier: none recorded).
- Working tree commands run so far this session: `git status --short`,
  `git log --oneline -5`, `python3 json.load` sanity probe. All read-only.

## Next steps (updated after resume)

1. [partial: export + JSON conversion done; interface + keymap check still open]
   Export rev-A netlist (kicad-cli, into own dir) → JSON pin model + keymap check.
2. Write variant A + variant B2 JSON circuits; netlist simulator (zero-delay,
   pin-level IC models) with frame-level crosscheck vs rev-A behavior.
3. BOM checker vs rev A; fewer-IC investigation (only proven consolidations).
4. JEDEC 5892-fuse parser for GAL22V10: decode truez + golden .jed, crosscheck
   vs source equations, selftests; simulate decoded fuses.
5. KiCad board generation (both variants) + courtyard collision check + DRC
   report with honest unconnected counts; attempt schematic/netlist authoring.
6. Afterburner/minipro source inspection → programmer gap report + bench plan.
7. Costs table (sourced or unknown); README + results.

## Commands/jobs log

### 2026-10-12 resume 2 (progress)

1. `python3 json.load` on circuits/reva_reference.json → parses, 83 comps/75 nets
   (interface still empty); full rev-A pin/net map recovered from
   reva_kicad_export.xml pinfunctions. Key facts extracted:
   - U109 (161): CK=2, /MR=1, ENT=10/ENP=7 tied to /rst, P0-3=GND, /PE=9=VCC,
     Tc=15 → U102 (AND to flag). Q0-3 unconnected at pins (Tc used). 
   - LVC 2G gate pinout interleaved: 1Y=6, 2Y=3 for 2G125/2G126; gates
     2G08/2G32: 1Y=7, 2Y=3 (confirmed vs nets: W=T_W·B_first at U102.3 → OEs).
   - Per-key: SW→100R series→'165 D pin; 10k pull-down at switch node; switch
     other pin = VCC_T; interface pull-ups/downs 9×10k exactly as protocol.md;
     series 33R ×7 on T_clk/T_latch/L_clk/L_latch/B_data/R_data/B_W.
   - Debug headers J105–J108 bridge SW side to logic side 1:1 (LSB: J106↔J108,
     MSB: J105↔J107) incl. VCC↔VCC_T, GND↔GND_T. Variants will document the
     jumper-through (= direct connection) as an explicit simplification.
2. Cloned galette (github simon-frankau/galette @HEAD, depth 1) to
   /tmp/opencode/galette (read-only reference); fetched MAME jedutil.cpp to
   /tmp/opencode/jedutil.cpp.
3. Wrote tools/jeddec.py: full JEDEC/GAL22V10 decoder (geometry from galette
   src + jedutil tables, cross-validated by self-test incl. row/col maps and
   S0/S1 addresses 5808..5827, *C checksum recompute).
   - `python3 tools/jeddec.py --names ... ../logic/pld/results/tile_glue_truez.jed`
     → decode + checksum OK (declared==computed 0x92a4). 
     RESULT: Q0..Q3 + HX have OE=FALSE (fully blown OE rows → pins Hi-Z;
     Q0..Q3 internal-only by design, HX is the helper macrocell — benign but
     real: those pads must be treated as NC/floating in the board design).
   - same for hardware/gal/tile_glue.jed → checksum OK (0x9790); TCLK
     driven-low compromise confirmed in fuses (SOP=BCLK*/TW+BCLK*/BFIRST,
     OE always on); NPL present; Q0..Q3 OE blown as in truez.
   - models written: results/truez_from_jed.json, results/golden_from_jed.json
4. Wrote tools/galcheck.py: parses .pld source equations (subset grammar),
   decodes .jed via jeddec.py, compares boolean functions exhaustively over
   the full support (13 vars = 8192 rows per expression) using silicon
   feedback law (registered '+' tab = /Q; comb feedback = pin).
   - truez: 20/20 MATCH (Q0..Q3 next-state+OE, BW next-state+OE, TCLK/LCLK/
     LATCH/HX/DS comb+OE, AR) — results/galcheck_truez.txt
   - golden: 20/20 MATCH — results/galcheck_golden.txt
   JEDEC counter/flag/OE are now PROVEN against source equations (not assumed).

5. Completed rev-A reference: `tools/keymap_check.py` runs 30+ assertions
   (key order, marker/flag pins, chain order, pulls, series Rs, W routing);
   ALL PASS; wrote the interface block into reva_reference.json;
   results/keymap_check.txt. Verified every logic pinout against TI/LVC
   datasheets (fetched to /tmp/opencode/dspld/): 2G74 SM8 is a SINGLE FF
   (pinout matches the rev-A symbol exactly: 1=CLK,2=D,3=/Q,5=Q,6=/CLR,
   7=/PRE,8=VCC) - no rev-A BOM error there; 2G125/2G126/2G08/2G32
   interleaved SM8 pinouts confirmed vs rev-A nets (1Y=6/7, 2Y=3); LVC165A,
   LV161A, 1G04 confirmed.
6. `tools/gen_circuits.py` authors circuits/variant_a.json (105 comps: 9 ICs)
   + circuits/variant_b2.json (95 comps: 4 ICs). Both keep rev-A passives
   (9 interface 10k pulls, 12x 100R key series + 12x 10k pd, 7x 33R series,
   100n/IC + 4u7 bulk). Only structural simplification vs rev A documented:
   debug headers J105..J108 removed (VCC_T/GND_T merged, keys wired direct).
   NC pins materialised as NC_* nets.
7. `tools/pinmodel.py` zero-delay pin-level engine (union-find domains through
   series Rs, rails, pulls, X-conflict + oscillation detection, synchronous
   per-round state updates). `tools/sim_tile.py`: window-level ABSTRACT
   protocol reference (frames/flags/W/spine clocking) vs pin-level grid sim.
   Early checker mistakes fixed during bring-up (documented in the session
   trail): L_endrow polarity in expected frames, domain value write-back,
   flag distance rule, W-flip timing for grids - all checker-side fixes;
   the circuit descriptions themselves never changed after authoring.
8. FULL SUITE PASS: 22/22 configs (6 shapes incl. grid4x4=16 tiles x
   pressed/released/distinctive) x 2 variants, 2 scans each: bit-exact frames,
   window-exact flags + mux, first-bit discipline, idle tail, zero X/settle
   failures. B2 runs the DECODED JEDEC model. results/sim_suite.txt.

9. BOM: `tools/bom_check.py` (results/bom_check.txt) — glue census revA=7,
   varA=7, varB2=2 ICs (9/9/4 total). fewer-IC investigation
   (results/fewer_ics.md): 7-IC floor proven by function-inventory; 5
   candidates examined incl. PROVEN count-neutral swap: variant_a2
   (2x SN74LVC2G241 for 2G125+2G126, same SM8 pinout) — variant_a2 PASSES
   the full 33-config protocol suite. Verdict: real consolidation only via
   the SPLD route (B2 = 4 ICs).
10. BOARDS: `tools/board_gen.py` emits boards/{variant_a,variant_b2}/
    tile_*.kicad_pcb (KiCad-10 format, embedded footprints incl. vendored
    Kailh sockets with arc-format conversion, all pads net-bound from the
    simulation-proven circuit JSONs; 12 keys on the 18.3597 lattice,
    stepped outline + 28 chassis pads + 6 strap pads at the study's exact
    coordinates). Package reality-found and applied: SOIC-16 does NOT fit
    the tile lanes -> 165/LV161A moved to TSSOP-16 (orderable PW).
    Placement: first-fit inside the connectors-study free-space islands
    (islands are already keep-out-inflated). variant_a: ALL 105 circuit
    parts + 17 TPs placed; zero same-side courtyard collisions among placed
    parts; min gap 0.002mm (kissing courtyards — legal, reported).
    variant_b2: all EXCEPT UB1 — the TSSOP-24 GAL (courtyard 7.7x8.3mm)
    fits NO free island (max 61.75x5.5 strips / 12.75x6.75 squares) — a hard
    geometric finding for the SPLD route, see boards/*/placement_report.txt.
    kicad-cli pcb drc (second opinion, both boards, json saved):
    vA: 1× shorting_items [VCC pad JP_J3p1 (-24.79,37.345) vs DET_L pad
    (-25.64,37.07): STUDY-DATA conflict, exact, also 1× clearance (0.075
    actual), 2× solder_mask_bridge, 4× courtyards_overlap — all traced to
    study pad-vs-strap coordinates; connectors worker notified via results],
    48× malformed_courtyard (vendored Kailh lib has OPEN B.CrtYd —
    pre-existing, also present in rev-A usage), 9× copper_edge_clearance
    (pads 0.32mm from edge vs KiCad default 0.5 rule — matches study's
    edge_clear=0.3 assumption, flagged for review), plus cosmetic silk_*
    warnings. Unconnected: vA 162 items / 53 nets, vB2 116/45 — everything
    unrouted BY DESIGN (placement prototypes), labelled so.

11. Costs: results/costs.{json,md} — every orderable MPN datasheet-confirmed;
    prices 'unknown' (distributor endpoints anti-bot-blocked from this host;
    recorded per-line evidence).
12. Programmer gap: results/programmer_gap.md — afterburner @7636cc724163 +
    minipro @3e2f4911fa86 cloned 2026-10-12, zero ATF22LV10C entries in both
    (grep evidence), ATF22V10C entries geometry-confirmed vs our decoder;
    voltages/VPP-pending LV params NOT printed in doc0780M (defers to Atmel
    appnote) — bench plan written with read-only-first protocol, no hw touched.
13. README.md written (layout, pipeline, headline answers). Full battery
    rerun 2026-10-12T14:02Z — results/battery.log: keymap 0 failures,
    galcheck truez+golden OVERALL MATCH, sim ALL PASS (33 configs), boards
    regen, DRC reruns, results/boards_drc.md with sha256-tagged digests.
14. Cleanup: stale sim_run1/2.txt + __pycache__ removed. git diff: zero
    tracked files touched; all new files inside discrete-spld/** + this
    checkpoint only. No commits anywhere.

### Next steps — task is COMPLETE; these are callers' follow-ups, not mine:

* connectors worker: fix VCC-pad vs DET_L strap physical conflict flagged by
  KiCad DRC (see results/boards_drc.md; both coordinate sets are study data).
* B2 route needs a tile-geometry decision (GAL package fits no free island)
  or a different orderable SPLD package; question handed back per findings.
* LV10C programming needs the upstream LV profile (results/programmer_gap.md);
  blocked until hardware + documented LV parameters exist.

## Final status (round 1)

COMPLETE per delegation scope.  SUPERSEDED by round 2 below.

## Round 2 (2026-10-12, review follow-up)

Scope: discrete-spld/** + this checkpoint only, again.  Reviewer findings and
my plan:

1. sim suite: add case selector (--quick/--shape/--circuit), run FULL suite
   with sufficient timeout (the 120 s truncation was a shell limit, NOT a sim
   failure - must be shown by a completing long run).
2. fewer_ics.md claim "7-IC floor" is INVALID (17-function counting + catalog
   survey cannot prove a global minimum).  Fix wording everywhere: 9-IC
   baseline = 7-IC glue partition; surveyed alternatives are count-neutral;
   no minimum claimed.  Attempt ONE genuine broader consolidation only with
   simulation proof (else document no-claim).
3. Interface: replace OLD connectors 28 pads + 6 DET straps with the
   connector-next corrected aggregate: 19 contacts (14 signals + VCC + GND +
   3 detect-GND), coordinates from connector-next/out/study.json (checks
   16/16 ok; budget 18/18).  Regenerate circuits + boards; DRC must reach
   ZERO geometric errors, with only the unrouted-prototype unconnected count
   remaining (labelled separately).
4. GAL 7.7x8.3 fit: examine 180 deg socket rotation legality from the REAL
   vendored footprint (MX pin/NPTH compatibility must hold); if legal,
   generate a rotated-socket layout for B2; 2D collision check vs full tile
   AND 6 tiled neighbours.  If still unfit: quantify minimal pitch increase
   with true equilateral tiling and classify as the relaxed-pitch path.
   Layer-count: keep the 2-layer placement prototype; record the 4-layer
   routing note (no 6-layer claim) per review.
5. Not mine: CPLD/FPGA package placement (other workers).  No orders, no
   commits.

Commands/results appended below as work proceeds.

### Round-2 command/results log (2026-10-12)

1. `python3 tools/sim_tile.py --quick` → ALL PASS (18 configs, seconds).
   `time python3 tools/sim_tile.py` → **ALL PASS (33 configs), 3m32s** —
   recorded full completion; the round-1 120 s truncation was a shell cap.
   Selector flags added (--quick/--shapes/--circuits/--modes).
2. `results/fewer_ics.md` REWRITTEN: floor claim retracted with reasons;
   baseline = 9-IC partition, surveyed swaps = count-neutral, no minimum
   claimed.  README.md updated to match.  No broader consolidation exists
   with proof; the sweep is documented per candidate.
3. Interface swap to connector-next 19-contact aggregate (proof: budget.py
   18/18, backplane graph unions read and mirrored 1:1 in the sim wiring):
   - gen_circuits: T_latch/R_data legs folded (33R series 7→5), 34→19 pads,
     DET straps removed.  Regenerated circuits: variant_a 105→88 comps
     (74 signal nets), variant_a2 88, variant_b2 95→78 comps (53 nets).
   - `python3 tools/sim_tile.py --quick` after swap → ALL PASS.
4. rotation study (NEW results/rotation_study.{txt,md}): rotation legal
   (whole-unit, documented pin/peg argument); built an obstacle engine from
   the vendored footprint (legacy arc parse per the study's own reader:
   fp_arc start=CENTER - caught and fixed against their study.py lines);
   discovered KiCad evaluates courtyards by bbox (board copies now emit a
   CLOSED fp_poly for the socket courtyard + place against bbox semantics);
   rows-alt would open 63x11 but hits the fixed SIG lane (11 pads);
   64-family enumeration: **0/64 lane-clean pattern holds a 7.8x8.3 rect.**
   Verdict: rotation cannot fit the GAL with fixed lanes; relaxed-pitch
   bound P'=18.91 mm (+0.55), R'=16.38, six-neighbour and same-tile
   collision checks = 0 at that pitch (verified by direct script run).
5. boards regenerated BOTH variants on theNEW interface, baseline key
   orientation (rotation rejected per #4):
   `kicad-cli pcb drc` → **0 error-severity violations BOTH boards**
   (only silk_* cosmetic warnings; 218/187 warnings), unconnected items
   175/129 = honest unrouted totals; digests in results/boards_drc.md.
   Placement internals: integral-image free grid on the vendored-geometry
   obstacle map, 0.25 mm quantisation bleed fixed, pad-to-edge >= 0.5 gate
   for my parts (socket pads' own 0.3-0.5 proximities are stepped-outline
   inherent).  variant_b2: 3/4 ICs placed; UB1 GAL unplaced with all-round
   evidence (rotation+enumeation+pitch all quantified).
6. boards_drc.md + bom_check text refreshed to 19C; costs unchanged
   (unknown prices); stale __pycache__ removed.

### Round-2 remaining follow-ups for callers (not mine)

* If B2 is wanted, it needs EITHER the relaxed-pitch rebudget (+0.55 mm;
  chassis lanes would have to be re-sited by the connectors worker) OR a
  different orderable SPLD package; no such package exists narrower than
  TSSOP-24 in the ATF22LV10C line.  Recommendation: variant A.

