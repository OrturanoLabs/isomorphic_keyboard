# FPGA layer decision review — stay 2L or move to 4L

Independent engineering review, 2026-10-16. Reviewer: Kimi-K3 subagent.
Owned file: this note only. **No board edits, no routes, no tool installs,
no vendor runs.** Ordered register preserved: **FPGA-01 IN PROGRESS**
(quote NOT OBTAINED; B1/B1b/B2/B3 hardware-gated), FPGA-02..04 PENDING.
This note informs the FPGA-02 task-2 layer comparison; it closes no gate.

## 1. Verified baseline facts (canonical board)

- Canonical pcb `out/kicad/tile_gw1nz.kicad_pcb` (sha256[:12]
  `c7d5b66fa1db`) enables **exactly 2 copper layers**:
  `(layers (0 "F.Cu" signal) (2 "B.Cu" signal))` — kicad_pcb:5,7-9
  (thickness 1.6 mm). No stackup/dielectric block; `(setup
  (pad_to_mask_clearance 0.05))`. `.kicad_pro` design rules: track/clr
  0.2/0.2, via 0.6/0.3, hole-hole 0.25, copper-edge 0.3.
- Board state: **0 tracks, 99 unconnected items, 0 DRC errors** (107
  silk-class warnings) — fpga02_handoff.md:9; fresh DRC rerun fpga-01.md
  session 7 (`kicad-cli pcb drc` 22:07, both variants). No `(segment`
  blocks in the pcb. 65 parts / 45 nets / 210 pads / ERC 0.
- All SMD copper (QFN FPGA, 12 socket pads, passives, LDO) is on **B.Cu**;
  F.Cu carries only NPTH switch holes. GND=21 pads, VCC=27, VCC1V2=7
  (single island behind FB1 bead), VCC1V2_RAW ~31 mm feed
  (route_arms.json pins_per_net; routing_plan.md:24-30).

## 2. What the scratch "4L" arms actually measured (and why they must not
be read as "4L is bad")

- **four_l_planes 17/79** and **four_l_attach_vias 30/79** were run on a
  **different denominator**: DSN `(plane ...)` declarations silently
  **absorbed 20 of 21 GND items from the routing list (99→79) and
  emitted NO inner-layer copper** — SES layers {F.Cu,B.Cu} only; VCC1V2
  plane ignored outright (route_arms.json:462,467,605; trap T4,
  fpga02_handoff.md:96-98). This is exclude-not-attach, not an
  implemented 4L PDN: zero plane geometry, GND left unconnected-but-hidden.
- The attach-via arm failed by **tool semantics, not physics**: all 17
  injected stub+via sites were **ripped** (`(type route)` is rippable);
  the router placed its own 53 plane vias but the pre-seeded 0.5 mm
  stubs/ring created clearance debt → **19 unresolved violations** vs 0 in
  every other arm (route_arms.json:610; T11 handoff). No pcbnew-side
  attached 4L variant — the proven LEDGER shape — was ever run on this
  tile.
- Width violations: only the 4L arms carried **sub-rule 0.15 mm** widths
  scored "0 violations" (K5; L_clk/L_clk_DRV) — widen pass is confirmed
  mechanical+conflict-free (docs/widen_report.json; handoff T3).
- The 2L stub arm (28/99) landed its 52 stubs on **F.Cu while pads are
  B.Cu** (T12, fpga02_handoff.md:121-126) — wrong-side stubs; the honest
  conclusion is "dead-end fixed pre-routes hurt", not "fanout impossible".
- Conclusion: **no unlike-denominator ratio (17/79, 30/79) vs the 2L
  46/99 baseline proves anything about 4L inferiority.** The only
  apples-to-apples fact: the router's SMD-fanout stage escapes
  115/144 pins (79.9%) on 2L and 114/144 (79.2%) on the 4L input —
  identical bottleneck, escape-geometry-bound, not plane-bound
  (route_arms.json:329,474).

## 3. Field facts that drive the decision

- **0.4 mm QFN escape** (B-side): pad gap 0.2 mm → zero inter-pad tracks
  at 0.2/0.2; escape is radial (routing_plan.md:42-45). 4L does not
  change pad geometry; it frees surface by removing GND/VCC from it.
- **Measured congestion**: in-row socket corridors 2.883 mm = 6 tracks
  min; **U1-north/SW6-tooling-hole pinch 0.375 mm = 0 tracks** — the
  binding site (routing_plan.md:112,119; routing_geo.json). Router open
  items localize exactly there + socket VCC chain (fpga-01.md session 13).
- **Returns at 20 MHz**: the fundamental is benign; the **LVCMOS33
  edges** rule — any threshold re-crossing on clock/strobe nets is a
  spurious shift/latch (termination.md items 1-2). Edge-critical class
  demands "adjacent continuous GND return, no plane splits under the run"
  (netclasses.json rule note); longest leg L_latch 51.1 mm, chassis run
  ≤0.25 m asserted-not-derived (A1, termination.md:68-71); closure gate
  is bench B2 (termination.md:129-138). On 2L a B-side trace's return
  crosses ~1.6 mm to F-side pour; on 4L prepreg 0.2104 mm (discrete
  stackup) coupling is ~8× closer.
- **PDN**: ~50-60 mW FPGA; 1.2 V island behind the bead is 7 pins;
  3.3 V is mA-class. Modest currents → routed-power-over-ground-planes
  is electrically comfortable (precedent: rev-C MCU "GND plane top, VCC
  tracks bottom", LEDGER.md:602-604).
- **Mechanical/contacts**: canonical 1.6 mm; spring S1971-46R (+1.49 mm)
  / S1961-46R (+1.34 mm) tiered rails, chassis land 2.25×3.70 mm
  (connector-next.md:45,48). The discrete-proven 1.6 mm 4L stackup
  (build_4layer.py:42-57) keeps the same total thickness — no contact or
  fit change.
- **EP**: pad 49 on GND, must be soldered (multi-window paste); ~50-60 mW
  → **no thermal vias, skip via-in-EP**; optional outside-EP 0.6/0.3 ring
  fits the measured 1.175 mm corridor (routing_plan.md:238-261). Feasible
  on both 2L and 4L; on 4L the ring drops to an adjacent plane.
- **Six 4L via-attach blockers** (pinch zones): U1-2, U1-26 (GND),
  U1-37 (VCC1V2), C4-2, C5-2 (VCC1V2), C8-2 (GND) (routing_plan.md:294-297;
  fanout_prep.json) — solvable with longer dog-bones; 46/52 power pads
  are via-feasible.
- **Fabrication rules unchanged** either way: 0.2/0.2, through via
  0.6/0.3 ([0-3] padstack on 4L), no microvias, edge 0.6/0.3.

## 4. If 4L: the RIGHT stackup (not blind Sig/GND/PWR/Sig)

Edge-critical traffic lives on the **bottom** layer. With the discrete
recipe's Sig/GND/VCC/Sig, bottom signals neighbor the **VCC** plane —
returns cross decoupling to reach GND (the trap this review was told to
avoid). Recommended primary:

- **F.Cu | In1 = GND | In2 = GND (+ small optional copper islands) |
  B.Cu** — both outer signal layers adjacent to solid GND across
  0.21 mm prepreg; GND stitching between In1/In2 at returns; 3.3 V and
  the 1.2 V island routed as traces/pours (current class trivial;
  precedent LEDGER.md:602-604). Tradeoff: VCC (27 pads incl. socket
  chain) still shares outer surface, so power corridors remain — but GND
  (21 pads incl. EP) leaves the surface, which is the true relief.
- Alternative B: **In2 = split fill** — mostly GND with a VCC island (+ a
  tiny VCC1V2 island); keeps a power plane but imposes seam-avoidance
  discipline from edge-critical corridors; acceptable secondary.
- Rejected: Sig/GND/PWR/Sig as-is (bottom clocks with no GND reference).

## 5. Cost (verifiable public structure only)

- Components ~**US$9.6/tile @ qty1** ($8.6 @10) (bom.md:42). JLCPCB
  public assembly structure captured 2026-10-14: monthly $6/$9/$10 SMT
  coupons, no setup fee, fine-pitch ≥0.35 mm covers QFN 0.4 (bom.md:50-52).
- PCBA line item is **TBD-quote**; order-of-magnitude US$30-100/tile at
  prototype qty is recorded as published-structure reasoning, **NOT a
  quote** (bom.md:57). Formal quote still blocked (account+Gerber/BOM/CPL).
- **No sourced 2L-vs-4L fab price differential exists in this repo** —
  none asserted here. Assembly (dominant cost class) is identical either
  way; the delta is fab-only and is scheduled to be captured at quote
  time (routing_plan.md criterion 5).

## 6. Recommendation

**Move to 4L** (stackup per §4 primary), with the 2L manual-finish path
(bare 46/99 deterministic base + widen list, or interactive routing on
the measured corridors) retained as the recorded fallback
(fpga02_handoff.md §3 options a/c). Rationale: the scratch 4L numbers
were unfair tests (§2); the true 4L lever — removing GND (and optionally
3.3/1.2 islands) from the two crowded outer surfaces plus legal
continuous returns for the 51.1 mm edge-critical legs — addresses the
measured bottleneck (SMD-fanout escape + surface congestion), while 2L
manual closure remains plausible but unproven and burns the same scarce
corridors for power.

**Confidence**: stackup correctness HIGH; "4L materially raises closure
odds" MEDIUM-HIGH (structural surface/return argument; 2L manual finish
never attempted; outer-layer 0.375 mm signal pinch exists regardless);
blind 4L adoption without the arm-6 check MEDIUM — bounded by unsourced
fab-cost delta. Decision is reversible at variant-copy level and cheap.

**Exact next design step if the user authorizes 4L** (bounded, no design
-artifact mutation): build a TRUE-4L variant COPY via pcbnew, mirroring
the proven discrete recipe (build_4layer.py): (a) enable In1/In2 as GND
(LT_POWER) + add the 1.6 mm stackup block; (b) pre-place stub+via attach
for the 46 via-feasible power pads and dog-bone the 6 blockers;
(c) optional EP outside-ring GND vias; (d) re-export DSN (gate: 45 nets /
144 pins / dsn_check PASS), class-split, and run ONE guarded bare
autorouter arm on the **same 99-item denominator** as arm 6. Compare
items-routed/violations against bare 46/99, fill the routing_plan.md
criteria table (incl. cost at quote time), and record into the FPGA-02
checkpoint when the owner opens that task. FPGA-01 stays in progress
(quote + B1/B1b/B2/B3 unchanged).
