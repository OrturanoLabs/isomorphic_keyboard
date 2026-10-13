# Checkpoint: discrete-layout (variant-A 4-layer routing attempt)

Worker scope (owned, R/W):
- `hardware/experiments/simple-tile/discrete-spld/layout/**` (new)
- `hardware/experiments/simple-tile/discrete-spld/tools/board_gen.py` (existing)
- `hardware/experiments/simple-tile/discrete-spld/boards/variant_a/**` (existing)
- this checkpoint file only.

Everything else is READ-ONLY reference. B2/CPLD/SPLD are retired; not developed here.
No git commits, no orders. The removed `isomorphic_keyboard-revc` worktree is NOT
recreated anywhere.

## Task (as delegated)

Discrete parallel baseline/contender: no MCU, no Hall, no LED, single PCB,
12 MX hot-swap keys, 18.36 mm equilateral lattice, 20 MHz shift clock, 16 tiles,
strong open-flow preference.

1. Build current variant A (9 ICs: all-LVC glue + SN74LV161A + 2x SN74LVC165A)
   on the corrected connector-next interface (old connectors tile overlapped its
   neighbour): full NPTH/pads/ICs/19-contacts interface, carried 33R series Rs,
   test points, power caps.
2. variant_a circuit is proven (33/33 protocol suite) but boards/variant_a is an
   UNROUTED placement prototype (175 unconnected pads / 52 nets). Attempt actual
   routing: 4 layers with proper GND reference, using the existing containers
   Freerouting (localhost/freerouting:2.4.1) and KRT (localhost/krt) per repo
   scripts. Do NOT silently relax fab design rules; do NOT hide opens; do NOT
   force 6 layers.
3. Plane SMD fan-out BEFORE the autorouter (ledger lesson: freerouting does not
   connect SMD pads to plane layers). Per-outbound 33R source placement correct.
4. Authoritative nets: schematic/ERC if a generator is available in this
   consolidated tree, else an explicit circuit-JSON -> KiCad net-binding checker
   gate.
5. Evidence: before/after DRC counts, remaining unconnected, via-in-pad
   clearance check, courtyard 6-neighbour tiling check.
6. Conditional 20 MHz target from timing-chain assertions (30/20 duty model);
   report actual routed lengths; write MY OWN readiness JSON under layout/
   (system worker reads it as reference; I do not edit theirs).
7. If routing fails: preserve best partial board + logs + job IDs here;
   no false "complete".

## Baseline observed (before my first edit, 2026-10-12)

- Repo: consolidated `/home/marco/Documents/OrturanoLabs/isomorphic_keyboard`,
  branch `rev-c` @ 6572e0f. `git status --short` shows PRE-EXISTING baseline
  changes (not mine, left untouched):
  - `D` deletions of the revc-mcu-tile tracked files (board/scripts/docs/media),
  - `M hardware/experiments/simple-tile/README.md`, `M .../RESULTS.md`,
  - untracked: `hardware/experiments/consolidation/`, `simple-tile/{connector-next,
    cpld-fit,discrete-spld,fpga,timing-chain}/`, `simple-tile/FOLLOWUP_RESULTS.md`,
    checkpoints for other workers.
- Existing state (from checkpoints/discrete-spld.md, verified on disk):
  - `discrete-spld/boards/variant_a/` holds the round-2 placement board built in
    the OLD -revc worktree (placement_report.txt references the removed path).
    DRC 0 errors, 175 unconnected items on 52 nets (unrouted by design).
  - `discrete-spld/circuits/variant_a.json`: 88 components, 74 nets (52 named +
    22 NC), 9 ICs; connector-next 19-contact interface; 5x 33R outbound series
    (7->5 after T_latch/R_data fold).
  - `results/boards_drc.md` (round-2 digests): vA 0 errors, 218 warnings
    (silk cosmetics), 175 unconnected / 52 nets.
- Timing-chain worker (read-only ref): 16/16 PASS; 20 MHz conditionally OK at
  max corner with >=28 ns clock-high (30/20 duty model), min corner fine at 50%.
  SI burst at 20 MHz: far-clock-tree fails for every Rs at typ corner
  (documented finding, NOT a 20 MHz hardware pass).
- Tools present: flatpak KiCad 10.0.6 (`tools/kicad-cli.sh`, pcbnew python via
  `flatpak run --command=python3 org.kicad.KiCad`), podman with
  `localhost/freerouting:2.4.1`, `localhost/krt`, `localhost/ngspice`,
  `localhost/oss-cad-suite:2026-09-26`; host python3 3.14.7. `java` NOT on host
  (freerouting runs containerised). Kailh footprints read from
  `hardware/kicad/lib/Switch_Keyboard_Hotswap_Kailh.pretty`, other footprints from
  the flatpak library via `flatpak run --command=cat`.
- Schematic generator: the revc_mcu schematic generator was removed with the
  rev-c worktree (deleted tracked files). No in-tree schematic generator for the
  discrete variants -> explicit FALLBACK GATE: circuit-JSON -> KiCad net-binding
  checker (to be written under layout/); NO ERC claim will be made.

## Plan (next steps)

1. Re-run full sim suite (33 configs, ~3.5 min) in background to confirm the
   variant_a circuit baseline in this consolidated tree.
2. Regenerate boards/variant_a in this tree (board_gen.py) → fresh in-tree
   placement baseline + kicad-cli DRC (expect 0 errors / 175 unconnected).
3. layout/: net-binding checker (circuit JSON vs emitted .kicad_pcb pads).
4. layout/: 4-layer stack conversion (F.Cu sig, In1.Cu GND plane, In2.Cu VCC
   plane, B.Cu sig) + scripted SMD power fan-out (via per power pad, >= pad
   edge + 0.65 mm clearance per ledger via-in-pad rule) BEFORE routing.
5. Export DSN, run localhost/freerouting:2.4.1 capped (memory 2500m,
   -Xmx1500m, --gui.enabled=false), import SES; fallback/second opinion KRT
   with strict options (--escalation board, --same-net-pad-clearance 0.3,
   --hole-to-hole-clearance 0.25, .kicad_pro next to board).
6. Before/after DRC (kicad-cli json), unconnected counts, via-in-pad check
   (tools/scripts/check_via_in_pad.py, kicad flatpak python), courtyard
   6-neighbour tiling check.
7. Routed-length report per key net (pcbnew), readiness JSON under layout/,
   honest verdict vs the conditional 20 MHz target.

## Commands/jobs log

### 2026-10-12 round 1

1. Sim baseline re-validation (background job, host PID 1730605):
   `python3 tools/sim_tile.py` (full suite, no selector) →
   **ALL PASS (33 configs)** in this consolidated tree
   (log: discrete-spld/layout/logs/sim_full_run1.log).
2. `python3 tools/board_gen.py` initial regen in this tree: ran OK, both
   variants rewritten deterministically (b2 regenerate = tool default side
   effect, same input→same placement; B2 not otherwise developed).
   NOTE: round-2 board text referenced the removed -revc path; the in-tree
   regen removed that stale reference.
3. kicad-cli 10.0.6 DRC of the regen'd boards/variant_a → **0 errors,
   218 warnings (silk_*), 175 unconnected / 52 nets** — matches the round-2
   digests byte-for-byte in substance.
4. DEFECT FOUND + FIXED in my owned `tools/board_gen.py` (routing-relevant):
   bottom-side parts were "flipped" by layer-string swap only; pad/geometry X
   was never mirrored.  pcbnew probe of the round-2 board showed TSSOP-16
   pad1 at library-local (-2.8625,-2.275) instead of mirrored (+2.8625,...)
   i.e. as fabricated the round-2 prototypes would have put every IC's pins
   on mirrored copper.  Fix: `mirror_footprint_text()` applied to the LIBRARY
   text before placement injection (first attempt mirrored the injected
   `(at)` placement line too -> parts landed on mirrored board positions with
   43 DRC errors; caught by DRC, fixed by reordering, re-verified).
5. DEFECT FIXED #2: footprint Reference/Value stamping only matched the old
   `(fp_text reference "...")` quoted form; all KiCad-10 property-style
   footprints kept "REF**" (and JP/TP gen pads were all "JP"/"TP").
   Now: property-style + unquoted fp_text forms handled; ChassisPad/TestPad
   emit the real refs (JP_<net>, TP_<net>).  `grep -c 'REF**'` = 0.
6. PLACEMENT IMPROVEMENT (owned tool): anchored placement pass —
   outbound 33R series resistors are placed first, ring-search anchored at
   the resolved driver output pin (driver table per TI pinouts, resolved
   from the circuit JSON), then 100n caps anchored at their IC's VCC pin.
   Resolution result: ROTCK@UA7.6, ROLCK@UA6... see board report; measured
   on the saved board with pcbnew (authoritative):
   ROTCK 2.28 mm, ROLCK 2.28 mm, ROLLA 2.93 mm, ROBW 1.64 mm (driver-pin to
   nearest R pad) — all within the rev-B 1.9-2.9 mm habit; ROBDA 7.06 mm
   (nearest free spot around UA4.9; recorded, not hidden).
8. Net-binding gate (the ERC substitute; no schematic generator in tree):
   `layout/net_binding_check.py` — two-way exact match, circuit JSON <->
   board pads.  Baseline board: **NET-BINDING PASS** (261 pads, 52 nets ==
   52 circuit nets, 22 NC pins net-less, TP bindings ok).  Negative test
   (one pad rebound nRST->GND): FAILS with both missing/extra diagnostics —
   gate is non-vacuous.

9. MAJOR UPSTREAM FINDING (G1, fabrication-blocking, NOT fixed by me — out
   of my file scope): `circuits/variant_a.json` / `tools/gen_circuits.py`
   author the power-rail pins of 7 of 9 ICs as NC_* single-pin nets:
   UA1/UA2/UA6/UA7 (2G SSOP-8) miss 8->VCC and 4->GND; UA8 (2G74) misses
   8->VCC, 4->GND (7->VCC present); UA5 (1G04) misses 5->VCC, 3->GND;
   UA9 (LV161A) misses 16->VCC, 8->GND (9->VCC=/PE present).
   Cross-verified against the FABRICATED rev-A export
   (circuits/reva_reference.json: U101/U102/U106/U107 4=GND,8=VCC;
   U108 4=GND,7=8=VCC; U105 3=GND,5=VCC; U109 8=GND,16=VCC) and against the
   per-device `'power'` pin tables encoded in gen_circuits.py itself, which
   are NEVER consumed by any code path.  Sim is logical-only (33/33 PASS is
   unaffected by rails); 2-layer boards passed DRC because NC pins are not
   "unconnected".  As authored, a circuit-faithful board would have 7 of 9
   ICs unpowered.
   Decision (recorded, reviewable): continue the routing workstream with an
   explicit errata overlay (`layout/errata_rails.json`, 12 pins) applied at
   the 4-layer build; the net-binding gate runs in `--errata` mode and
   checks board == circuit+errata EXACTLY.  The overlay is deleted when the
   owner fixes gen_circuits.py.  boards/variant_a stays circuit-faithful.

### Next

- regen baseline with corrected cap anchoring (physical VCC pin per package),
  DRC + net-binding on it; then 4-layer+fanout build with the G1 overlay,
  autoroute in localhost/freerouting:2.4.1 (memory-capped, logged, job id),
  import, finish; before/after DRC + via-in-pad + 6-neighbour courtyard
  tiling + routed-length report + readiness JSON.

### Continue (log 10-11)

10. Placement corridor work (owned tools, in layout pipeline):
   - board_gen corridor-aware placement: placed copper model (pad boxes +
     NPTH holes + chassis discs); for every part with rail pads the first
     corridor-capable candidate is chosen (stub 0.25 + via 0.6/0.3 + clr
     0.2, all-foreign conservative), fallback marked [NO FANOUT CORRIDOR].
     Regen: 9/9 ICs, caps 3-6 mm from their IC VCC pins, series Rs
     1.6-2.9 mm from drivers (ROBDA 7.1), 0 courtyard collisions,
     DRC 0 errors / 176 silk warnings / 175 unconnected (unchanged class).
   - build_4layer.py (pcbnew): 4 layers (F, In1=GND plane LT_POWER,
     In2=VCC plane LT_POWER, B), applies errata overlay (14 rail pins,
     printed), full-outline GND/VCC zones (unfilled pre-route), explicit
     generic 1.6 mm 4-layer stackup text (ENIG; 0.21 mm prepreg).
     SMD power fan-out BEFORE routing: worst-first ordering + retry ladders
     to 8 mm -> 85/88 rail pads get stub+via (0.6/0.3).
     OPEN TRADEOFF (recorded): 3 rail pads have no legal stub+via corridor
     (UA1.4 GND, UA2.4 GND, RPTW.2 VCC after final placement): they join
     GND/VCC as ordinary routed connections by the autorouter onto existing
     fanout stubs/vias; the DRC unconnected==0 + via-in-pad==0 gates will
     show whether that held.  NOT via-in-pad, no rule relaxation.
   - layout/tile_variant_a_4l.dsn: 4 layers exported.

11. ROUTING JOB RUNNING: `podman run --rm --userns=keep-id
    --name fr_va_run1 --memory 2500m -e JAVA_TOOL_OPTIONS=-Xmx1500m
    -e HOME=/tmp -v <layout>:/work:Z -w /work localhost/freerouting:2.4.1
    -de tile_variant_a_4l.dsn -do tile_variant_a_4l.ses -mp 40
    --gui.enabled=false` — host wrapper PID 2123121, container fr_va_run1,
    log layout/logs/freerouting_run1.log.
    (Optimizer left at freerouting defaults; judged by post-import KiCad DRC.)

##### Continue (log 12-13)

12. CRITICAL FINDING + FIX: the board outline came from the OLD connectors
    study (`connectors/out/placement.json` tiles.stepped) — the one whose
    vertical margin P/2 overlaps the up/down neighbour outlines by 1.46 mm
    (measured by connector-next CT0; my own 6-offset interior test
    reproduced 4/6 offending neighbours before any fix).  The CORRECTED
    TileTiling (revc-exact, vertical margin R/2) tiles with exactly the
    1.0 mm rib gap.  board_gen now builds on `corrected_outline()` — it
    imports connector-next/study.py's TileTiling itself when importable and
    cross-checks against a local formula copy.  layout/tiling_check.py
    (new) shows: outline x 6 neighbours: 0 overlaps (was 4-6/6);
    socket/pad cross-collisions 0; 105/105 anchors inside outline.
    KILLED fr_va_run1 (mid-route on the obsolete outline; ~7 min CPU in)
    and regenerated everything.
13. Corrected-outline chain (actual numbers):
    cell corridor-aware regen (log layout/logs/board_gen_run4.log):
    9/9 ICs, caps 3.5-7.5 mm, series Rs anchored, 0 courtyard collisions,
    0 off-board; DRC **0 errors / 175 unconnected**; NET-BINDING PASS.
    4L build: errata 14 pins; worst-first SMD fanout **87/88** rail pads
    (only UA2.4 GND has no corridor -> router joins it as an ordinary
    connection; recorded tradeoff).  DSN carries width 200 um / clearance
    200 um (50 um smd-smd) / via 0.6x0.3 — defaults, NOT relaxed.
    NET-BINDING PASS on the 4L board with --errata.
    ROUTE JOB: fr_va_run2 (podman, --memory 2500m, -Xmx1500m) started
    17:05Z, log layout/logs/freerouting_run2.log -> wait for SES.

14. ROUTE RUN 2 OUTCOME (fr_va_run2, 47 min autorouting): plateaued -
    passes 9..16 oscillate 39-42 unrouted + 90 freerouting-side violations
    (stuck since pass 1; freerouting "violations" are its own soft count,
    not KiCad DRC).  Example open: T_clk_drv ROTCK-1 <-> UA7-6 (2.3 mm!).
    Dense 4-hole-per-key field + fanout via forest + only 2 effective
    signal layers (inner are power planes, F is perforated by NPTH).
    Optimizer stage started unbounded (rev-C lesson: killing it loses the
    SES) -> KILLED deliberately at 17:53Z after archiving the pass log;
    no board artifact lost (SES is written only at normal end).
15. ROUTE RUN 3 (fr_va_run3): same DSN, `-mp 14
    --router.optimizer.enabled=false` -> guaranteed SES of the best
    autorouted (partial) state.  Log layout/logs/freerouting_run3.log.
    After: finish_4layer import -> DRC/open count -> KRT repair passes on
    the open nets (production revc flow) -> final gates + readiness JSON.

### 2026-10-13 resume (post power interruption), worker relaunched

RECOVERY STATE AS FOUND (~08:55 CEST):
- Checkpoint's "fr_run3" note was stale. Actual sequence since: fr_va_run3
  COMPLETED normally (37m58s, log layout/logs/freerouting_run3.log): final
  autoroute state **34 unrouted + 90 freerouting-internal violations**,
  SES written (73277 B). finish_4layer imported it ->
  layout/tile_variant_a_routed.kicad_pcb; kicad-cli DRC:
  reports_drc_routed.json = 195 viol (11 track_width leftovers, 2
  copper_edge_clearance GND vias, 20 via_dangling, silk 162) / 34 unconn.
  fix_routed.py then widened sub-0.2 mm tracks to 0.2 and DELETED the 2
  edge-clearance GND vias (opens GND by design, for the repair pass) ->
  reports_drc_fix1.json = 192 viol (9 clearance, 20 via_dangling, 1
  isolated_copper, silk 162) / **36 unconnected**.
- KRT repair job adopted, RUNNING, NOT restarted by me:
  container 81d289b860c9 (name hungry_mahavira, image localhost/krt:latest),
  started 2026-10-12 20:37:24 CEST, still Up.
  CMD (from podman inspect): `python /opt/krt/py_router/route.py
  pass_in.kicad_pcb pass_out.kicad_pcb --nets <30 nets> --rip-existing-nets
  <same 30> --clearance 0.2 --track-width 0.2 --layers F.Cu B.Cu
  --layer-costs 1.0 1.0 --via-size 0.6 --via-drill 0.3 --escalation board
  --same-net-pad-clearance 0.3 --hole-to-hole-clearance 0.25
  --board-edge-clearance 0.5 --grid-step 0.05`
  Mount: layout/krt_attempt -> /work. pass_in.kicad_pcb == copy of the
  fix1 board (same 1666681 B). Log: layout/logs/krt_pass1.log (active).
- KRT pass 1 finished inside the container ~08:5x after ~12 h (rescue leg
  dominated): JSON_SUMMARY in log: 20/29 nets ok; open pad-pair groups:
  SWN1 0/2, SWN3 1/2, T_endcol 1/2, W 3/5, flag_and 0/1, flag_d 0/1,
  latch_drv 1/3 (7 groups). **RULE ESCALATION RECORDED BY KRT** (not
  silent): 18 nets contain "net rescue" tracks at **0.0889 mm** and many
  clamped vias 0.25-0.45 mm vs requested 0.6/0.3 (escalation policy
  "board"). These violate strict 0.2/0.2 rules -> final DRC must show them
  as real errors; candidate remediation = scripted widen-to-rule pass like
  fix_routed.py + report residual clearance errors honestly (no hiding).
  Its plane finalize joined GND regions, repaired pad UA8.4, then EXCLUDED
  the VCC zones (VCC outside --nets scope; pads own stub+via copper from
  build_4layer). Current activity: "Final reconciliation" pass reloading
  its own pass_out, retrying 12 nets with rip authority; T_clk_drv
  succeeded, SWN1/flag_d/latch_drv taps still failing at ~09:0x.
  pass_out.kicad_pcb on disk (1945626 B, written 08:51) = pass-1+finalize
  state = current best partial board artifact. On-disk file is consistent.
- Budget decision recorded: let reconciliation run while I do the G1
  canonical fix (authorized: tools/gen_circuits.py + circuits/variant_a.json
  + variant_a2.json), then re-assess with hard stop criteria below.

### 2026-10-13 resume - continued (~09:15)

16. KRT CONTAINER EXITED ~08:57-09:0x (found gone at 09:07; `podman ps -a`
    no longer lists 81d289b860c9 - it was started with --rm, so a clean
    remove-on-exit).  Last log write 08:57:10, last pass_out write 08:51
    (1945626 B) = pass-1 + plane-finalize state.  The "Final reconciliation"
    pass (12 nets, started after 08:51) had completed T_clk_drv [1/12] and
    W [3/12] and was stuck in retry loops on the SWN1 17.26 mm tap edge
    (blocked by SWN5/KEY8/T_clk_drv/SWN3 copper) when the log stops.  No
    final write -> reconciliation's ripped-but-unrestored in-memory state is
    LOST, disk state is self-consistent.  Host memory at the time:
    22/22 GB used, swap 11/11 GB FULL -> probable OOM-kill of the python
    router.  DECISION (finite budget): do NOT restart KRT; adopt
    krt_attempt/pass_out.kicad_pcb as the best partial board.
17. G1 CANONICAL FIX DONE (newly authorized scope: tools/gen_circuits.py +
    circuits/variant_a.json + circuits/variant_a2.json):
    - gen_circuits.Builder.finish() now consumes DEVICES[*]['power']
      (VCC/GND pin per device): binds rail pins, tolerates same-rail
      explicit pins, raises on a conflicting owner net.  Docstring records
      the fix.  variant_b2() intentionally NOT regenerated
      (variant_b2.json is outside my owned scope; full __main__ rerun by
      the owner will also bind UB4.5->VCC / UB4.3->GND - same G1 class).
    - Regenerated variant_a.json + variant_a2.json only, via selective
      driver (no __main__, no B2 touch).  Both: 88 comp, 74->60 nets.
      Diff vs pre-fix copies (/tmp/opencode/g1_variant_*_prefix.json):
      ONLY 14 NC_* nets removed each; GND/VCC gained exactly the 14 rail
      pins (A: UA1/2/6/7 8->VCC&4->GND, UA8 8->VCC/4->GND, UA5 5->VCC/3->GND,
      UA9 16->VCC/8->GND; A2 same for UA2/5/6/8/9 + UV1/UV2 8/4).  All
      other nets and ALL other JSON sections byte-identical.
    - EXACT-EQUIVALENCE PROOF: old circuit + layout/errata_rails.json
      (checker transformation) == new circuit net-for-net; NC set 22->8.
      Remaining 8 NC pins are genuinely unused (165 /QH x2, 1G04 pin1,
      2G74 /Q, LV161 QD..QA).  => cached routing built from old+errata
      stays valid; per the removal condition, errata_rails.json will be
      deleted once the FINAL board also passes net-binding vs the new
      canonical (already PASS on the fix1 board - see below).
    - boards/variant_a regenerated via selective build('variant_a') call
      (no B2): 105 footprints, 52 nets, NC pads 22->8.  Placement
      byte-identical (57/57 ref layer+xy+rot unchanged; raw diff = 28
      lines, rail bindings + 5 paren-spacing shifts only).  Net-binding
      PASS vs new canonical WITHOUT --errata (261 pads, 52==52 nets).
    - Net-binding vs NEW canonical, NO --errata, on the pre-KRT routed
      board (layout/tile_variant_a_routed.kicad_pcb fix1 state) AND on the
      adopted pass_out board:
      **PASS** (261 pads, 52 nets == 52, 8 NC pins net-less, TPs ok) -
      this is the removal-condition gate for the overlay.
    - Sim: logical nets unchanged (rail pins only) => full 33-suite repeat
      not mandated ("no expensive full repeat unless changed logic");
      running anyway a REDUCED suite --circuits variant_a,variant_a2 as a
      loader/behaviour smoke (bg pid 3262056, log
      layout/logs/sim_g1fix_run1.log) - result recorded when done.
18. NEXT: adopt pass_out -> tile_variant_a_routed.kicad_pcb (backup fix1
    board first), refill zones (KRT: "press B to refill"), final gates
    (strict DRC incl. KRT's recorded 0.0889 mm rescue tracks + 0.25-0.45 mm
    vias as REPORTED violations, unconnected, via-in-pad, 6-neighbour
    tiling, source-R distances, net-binding + negative control), bounded
    manual repair attempt on the 7 open pad-pair groups (no new
    autorouter runs), readiness JSON, overlay deletion + build_4layer
    skip-if-absent patch.
19. GATES ON THE ADOPTED BOARD (layout/tile_variant_a_routed.kicad_pcb =
    krt_attempt pass_out state, zones refilled via layout/finish_krt.py):
    - NET-BINDING PASS vs NEW canonical circuits/variant_a.json, NO --errata
      (261 pads, 52==52 nets, 8 NC pins net-less, TPs ok).
    - NEGATIVE CONTROL (gate non-vacuous): one pad rebound UA9.1 nRST->GND
      in a scratch copy -> FAIL with missing+extra diagnostics, exit 1.
    - POWER GATE (explicit): all 14 ex-G1 pins bound exactly (UA1/2/6/7/8:
      8=VCC 4=GND; UA5: 5=VCC 3=GND; UA9: 16=VCC 8=GND - correct per TI
      pinouts; an early ad-hoc wants-table bug in my probe said FAIL, the
      authoritative per-device table says PASS).
    - VIA-IN-PAD (repo gate tools/scripts/check_via_in_pad.py, gap 0.2):
      **0 bad vias** (KRT's "via-in-pad clamp" log entries are sub-rule via
      SIZES placed next to pads, not in/pad geometry).
    - TILING (layout/tiling_check.py): 0/231 outline overlaps over 6
      neighbours, 0 socket cross-collisions, 105/105 anchors inside -> PASS
      (unchanged outline; NPTH included in model).
    - SERIES-R SOURCE PLACEMENT (pcbnew on final board, R pad1 centre to
      driver pin centre): ROTCK 4.38, ROLCK 4.38, ROLLA 4.75, ROBW 4.08,
      ROBDA 1.87 mm.  (Corrected-outline placement; measured pad-centre to
      pin-centre; ROBDA improved 7.06 -> 1.87 vs the round-1 board.)
    - STRICT DRC (kicad-cli json, ALL rules, reports_drc_krt1.json):
      errors 1090, unconnected 12 items (6 net groups + 1 GND pour island):
      clearance 499, track_width 199, hole_clearance 199, via_diameter 69,
      drill_out_of_range 69, annular_width 55; warnings 178 (silk 162 as
      before, via_dangling 14, track_dangling 2).
      Compare fix1 (pre-KRT): 9 errors (clearance), 36 unconnected.
      => the KRT pass-1 board is the connectivity-maximal artifact but is
      NOT strict-fab clean; the narrowed copper (1445 segments @0.0889 mm,
      55 vias @0.25-0.45/0.15-0.2 drill, 10x 2.0 mm plane-join straps) is
      KRT's recorded escalation, reported here, not adopted as a rule.
    - Opens inventory (DRC coordinates): SWN1 3 islands
      (RK1.1+stub / SW2.2 / RS1.1), SWN3 (main <-> SW4.2 pad), latch_drv 3
      islands (main / TP_latch_drv / UA5.2), W 4 islands (main / UA1 pair /
      TP_W side / lone via 11.636,0.374), T_endcol 2 islands (RPTEC stub
      <-> UA3+JP island), flag_and 2 bare pads, flag_d 2 islands, GND B.Cu
      pour island(s) - B.Cu GND fill has 40 islands, DRC flags 1 pair.
    - REDUCED sim suite (--circuits variant_a,variant_a2) on the fixed
      canonical circuits: **ALL PASS (22 configs)** (log
      layout/logs/sim_g1fix_run1.log).  Full 33-repeat not run: logic nets
      proven byte-identical by JSON diff (only rail bindings changed).
20. OVERLAY RETIREMENT (condition met: board == new canonical exactly):
    errata_rails.json DELETED; build_4layer.py apply_errata() now no-ops
    when the file is absent.  Net-binding gate remains the proof.
21. CLOSED: layout/repair_opens.py run #3 (strict-geometry prober) ->
    **0/11 signal links had any legal corridor** (straight on B/F +
    via-hop variants, all legality-checked) and **0 GND via sites** inside
    the floating B.Cu pour sliver.  Findings from the prober + probes:
    - Floating sliver = bbox x 7.05..9.21, y -6.95..-5.66.  It CONTAINS
      RPLDA.2 (L_data pull-down return) + its stub to the deleted-via
      site (7.391,-6.782 - deleted by fix_routed for the 0.5 mm edge rule).
      So the open is ELECTRICALLY REAL: RPLDA.2 floats -> column-0 L_data
      input floats when the left neighbour tri-states.  No legal repair:
      via sites fail edge/pad/rescue-KEY0 constraints; the south B.Cu
      channel is sealed between TP_B_clk/TP_B_W/RPTW+VCC pads + B_clk via
      + DS_net web at strict geometry (hand-traced in repair notes).
    - KRT's own frontier verdicts (boxed_in_static 1596-7909 iterations,
      sealed_by_snpc on UA3.11/ROBW.2/TP_L_clk.1) + 47 min freerouting
      plateau + 12 h KRT pass + my prober all agree: the residual opens
      are placement/congestion-bound, not engine-bound.
    - Board unchanged by the prober (0 additions): final kicad-cli DRC
      digest byte-identical before/after (1090 errors / 178 warnings /
      12 unconnected; reports_drc_krt_final.json).
22. DELIVERABLES (final):
    - layout/tile_variant_a_routed.kicad_pcb = BEST PARTIAL
      (connectivity-maximal: 12 opens; NOT fab-ready: 1090 strict-DRC
      errors dominated by inherited KRT rescue geometry 0.0889 mm /
      0.25-0.45 mm vias - reported, not adopted as rules).
    - layout/tile_variant_a_routed_fix1.kicad_pcb = strict-geometry
      reference (9 errors / 36 opens).
    - boards/variant_a + circuits/variant_a{,2}.json + tools/gen_circuits.py
      = fixed canonical (G1 closed; A==old+overlay proven; A2 same class;
      B2 untouched by scope).
    - layout/readiness.json = full verdict incl. "no-ERC" statement,
      substitute gates, blockers per open link, 20 MHz = unknown/
      baseline-conditional.  tools/kicad-cli.sh fla + pcbnew used for all
      checks; krt_attempt/{pass_in,pass_out}.kicad_pcb + logs kept raw.
    - No commits, no orders, no installs; no router was ever duplicated or
      restarted after exit.  No background jobs left running (sim done,
      repair done, KRT gone, podman ps empty).
23. RECOMMENDED OWNER ACTIONS (outside my scope):
    - Decide fab direction: (a) accept advanced-tier geometry for the
      rescued corridors (owner rule decision, NOT mine), or (b) change
      PLACEMENT to open the sealed channels (TP_B_clk/TP_B_W/VCC-fanout
      field near (6-10, -1..-7), key-street congestion) and re-run the
      pipeline with the fixed canonical circuit, or (c) accept the
      connectivity reference as analysis-only.
    - Re-generate circuits/variant_b2.json with the fixed gen_circuits.py
      (2-pin UB4 rail delta) when B2 is picked up.
    - The RPLDA.2 open is the single most consequential residual (floating
      L_data input) - prioritise it in any placement revision.

### Recovery pointers if the worker drops here (final state 2026-10-13)

- Canonical circuits are FIXED (G1): tools/gen_circuits.py consumes device
  power tables; circuits/variant_a.json + variant_a2.json regenerated
  (74->60 nets; NO other net/section change).  variant_b2.json untouched
  (scope).  Reduced sim 22/22 PASS on the new circuits.
- layout/errata_rails.json DELETED on purpose (proof: net-binding gate
  without --errata PASSes on both boards/variant_a and the routed board).
- Boards: layout/tile_variant_a_routed.kicad_pcb = KRT-adopted
  (connectivity-maximal; 1090 strict-DRC errors from KRT escalation);
  layout/tile_variant_a_routed_fix1.kicad_pcb = pre-KRT strict-geometry
  state (9 clearance errors, 36 unconnected).  DRC jsons next to them.
- Deterministic rebuild: `python3 tools/board_gen.py` +
  selective `board_gen.build('variant_a')` (full __main__ also rebuilds
  B2), then `flatpak run --command=python3 org.kicad.KiCad
  layout/build_4layer.py` (4L+fanout+DSN; errata no-op now).
- Repair state: layout/repair_opens.py run #2 in flight (log
  layout/logs/repair_run2.log); verify with
  tools/kicad-cli.sh pcb drc --format json --all-track-errors.
