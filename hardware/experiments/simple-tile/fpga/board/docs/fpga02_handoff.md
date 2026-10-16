# FPGA-02 preparation handoff index

Audience: whoever picks up FPGA-02 (routing the GW1NZ tile) after the
2026-10-15/16 overnight preparation campaign (batches 001-012,
checkpoint fpga-01.md sessions 2-16). Every row below was produced
WITHOUT touching the design artifacts: pcb sha256[:12] stayed
`c7d5b66fa1db` (validator snapshot) all night; pcb pad census 210
(U1 49 + SW 12x7 + JP 19 + TP 11 + C 18 + R 22 + FB 2 + U2 5);
65 parts / 45 nets / ERC 0 / DRC 0-error (107 gw1nz silk and 99
unconnected warnings are the recorded baseline corpus, not new
defects). All router runs were dry-run-only; no copper, no import,
no adoption.

## 1. Preparation artifacts (fpga/board/docs/)

| Artifact | Tool | Status in one line |
|---|---|---|
| power_reg.md | (batch 1 analysis) | Decoupling table + EP thermal closure: no thermal vias at ~50-60 mW; EP pad 49 soldered to GND with multi-window paste; via-in-EP skipped; optional outside-EP 0.6/0.3 via ring deferred here. Design-phase closed; bench B1/B1b/B2/B3 still hardware-blocked. |
| netclasses.json | netclass_prep.py | 6 classes / 45 nets exact partition (N1-N5 verified); class rules: 0.2/0.2 everywhere except power 0.5 track; power={GND,VCC,VCC1V2,VCC1V2_RAW}. Canonical class source of truth. |
| routing_geo.json | routing_geo.py | 23 socket corridors: min in-row obstacle_gap 2.883 mm = 6 tracks (SW1-SW2); U1-SW6 tooling-hole pinch 0.37 mm (0 tracks). Corridor capacity is measured, not assumed. |
| routing_plan.md | (living doc) | Full plan: capacity table, DSN/SES I/O contract, EP analysis, fanout order, and the recorded 3-arm autorouter conclusion (section at the bottom). |
| fanout_prep.json | fanout_prep.py | 58 power pads = 6 anchors (EP+JP) + 52 planned stubs, via-free 2L, 0 conflicts/collisions, deterministic (sha256[:16] 0dc19412c6f8ff5c); 46/52 via-feasible; 6 fourL blockers listed (U1-2/26/37, C4-2, C5-2, C8-2). |
| length_budget.json | length_budget.py | Per-net pin-centre Manhattan MST lower bounds; edge-critical rank: L_latch 51.09 mm worst; DRV stubs 5-11 mm (R7-R11 mapped); contact legs 19-51 mm. |
| route_arms.json | route_report.py | Audited 3-arm autorouter census (see section 3), with provenance blocks and canon invariants; tool FAILS if invariants break. |
| widen_report.json | widen_check.py | Per-path fix-style widen lists per SES arm (7/63/9/12 below-class paths) + sub-rule paths (K5 @ 150 um; 4l_attach L_clk/L_clk_DRV @ 150 um) + routed-length vs MST-budget audit (worst overage 1.132). |
| quote/ (README, bom_neutral.csv, cpl_gw1nz_provisional.csv) | quote_prep.py | Assembly quote package READY TO UPLOAD; blocked on account + Gerber/BOM/CPL upload (needs login). |
| readiness.md | (batch 1 analysis) | SCH0->45-net readiness register; open gates cross-referenced here. |

## 2. Router I/O chain (fpga/board/tools/ + out/route/)

Baseline guards (pre-overnight, still green at batch 2 re-check):
board_net_check.py, pincon_check.py (parse_cst repaired, batch 2),
footprint_verify.py, schematic_check.py; regen_batch.sh is the
sanctioned heavy-invocation pattern; drive_attr_ab.sh the pin-attr A/B.

Night-built route tooling (all run via resource_guard):
- export_dsn.py — flatpak pcbnew Specctra export, argv-parametrized:
  `(export_dsn.py <pcb> <out.dsn>)`.
- dsn_check.py — D1-D4 DSN-vs-pcb gate (nets/pins/via/boundary).
- dsn_class_split.py — text-level class injection into a DSN
  (`kicad_default` -> 6 classes, power 500/200 um), byte-exact inverse;
  argv-parametrized (src/out/report).
- ses_import_check.py — S1-S7 SES import gate; subset mode and
  `--full` (complete-route) mode; characterized on the in-tree
  discrete fixture (46/52 nets) plus all three of our arms.
- fanout_prep.py / fanout_apply_probe.py — plan generator and the
  pcbnew-COPY stub applier (52 stubs, 0 vias; saved a probe pcb only).
- dsn_4l_probe.py — 4-layer plane splice with inverse identity
  (GND->In1, VCC1V2->In2, via padstack [0-3]).
- route_report.py / widen_check.py — arms census and width/length
  audits (both regenerate their docs/*.json).
- netclass_apply_pcbnew.py — pcbnew-native class assignment (45
  assigned). PROVEN but see trap T1: assignment does not persist to
  the pcb file.

Derived route artifacts (out/route/): tile_gw1nz.dsn (raw export),
tile_gw1nz_classes.dsn (classed, arm-1 input), tile_gw1nz_rules.*(batch-2 per-class attempt, see T1), tile_gw1nz_fanout_probe.kicad_pcb
(COPY with stubs), tile_gw1nz_fanout_probe.dsn + _fanout_classes.dsn
(arm-2 input), tile_gw1nz_4l.dsn (arm-3 input), three .ses outputs,
*_check[_full].json gate reports, freerouting_4l.log (arm-3 teed
log; arms 1-2 logs were piped only — recounts in fpga-01.md s13/s14).

## 3. Autorouter measurement summary (freerouting 2.4.1, localhost
container, -mp 40 headless, guard-capped 2g/2cpu; strict 0.2/0.2 +
6-class table)

| arm | input | items routed | nets with wire | wall | verdict |
|---|---|---|---|---|---|
| bare | classes.dsn | 46/99 | 25/45 | 519 s | Baseline. 0 violations. Byte-identical VARIANCE REPLICATE (bare_rep2, batch 16): router is deterministic, 46/99 is exact; internal SMD fanout escapes only 115/144 pins (79.9%). |
| dead_end_stubs | probe copy classes.dsn | 28/99 | 28/45 | 926 s | WORSE: fixed dead-end stubs block escapes (-18 items); gained 7 small nets, lost 4. |
| four_l_planes | 4l.dsn | 17/79 | 34/45 | 398 s | Plane declarations EXCLUDE nets from routing (20 GND items absorbed, zero inner-layer geometry; VCC1V2 plane ignored). No congestion relief. |
| four_l_attach_vias | 4l_attach.dsn | 30/79 | 29/45 | 571 s | WORSE for adoption: 19 UNRESOLVED clearance violations (all other arms 0). All 17 injected vias ripped ((type route) is rippable); router's own fanout placed 53 plane vias, but the pre-seeded wide stubs/via ring created clearance debt held from autoroute pass #1 to optimizer end. Items closed 50/99 vs bare 46/99 — more items, strictly worse board. |

Decision-relevant reading: on 2L the router alone does not close and
neither pre-copper variant helped as tried. The discrete project's
success shape was pcbnew-side pad->plane attach VIAS on a true 4L
board. Options actually open: (a) manual finishing around a bare-arm
router result with the widen list applied; (b) a 4L arm with
pre-placed attach vias (needs the 6 fourL blockers resolved);
(c) interactive routing entirely, using routing_geo/fanout_prep/
length_budget as guidance. No routing acceptance gate was closed or
waived.

## 4. Known traps (distilled, all personally stepped on or inherited)

T1. KiCad 10 class persistence: .kicad_pcb carries NO net-class text;
classes persist via .kicad_pro net_settings.classes; pcbnew
SaveBoard persists Default only. Keep the class table at DSN level
(dsn_class_split) for router handoff.
T2. Hand-written `(net_class ...)` inside .kicad_pcb SEGFAULTS
pcbnew 10.0.6 ExportSpecctraDSN (3 variants bisected, exit 139).
Never reintroduce.
T3. Freerouting 2.4.1 trait: emits off-class widths — including
BELOW the 0.2 mm floor (K5 @ 150 um) — while scoring 0 violations.
Any SES adoption requires the widen_report-driven widening pass
(same trait as discrete fix_routed.py).
T4. Freerouting reads DSN `(plane ...)` as exclude-net-from-routing
and emits NO attach geometry; one plane was ignored outright. 4L
attach must be explicit vias placed at pcb level.
T5. Freerouting honors DSN wiring as fixed pre-routes: dead-end
stubs make results WORSE (measured). Feed only terminated geometry.
T6. SES round-trip frame traps: net names quoted and possibly
case-folded (KiCad is case-sensitive — drift repair needed at
import); SES integer coords/widths are 0.1-um units (10x the DSN
raw-um frame). ses_import_check encodes both.
T7. resource_guard refuses podman delegation without explicit
--memory --memory-swap --cpus --pids-limit (by design). Never pass
--ignore-rust. rc 2/3/4 = defer to light tasks.
T8. Shell: `cmd | tail; echo $?` masks exit codes (re-run unpiped);
zsh expands a bare `===` (= expansion) — quote separators.
T9. Corridor capacity from courtyard-only geometry over-estimates
(socket pads stick ~2 mm out); use routing_geo.json measured values.
T10. After ANY SES adoption: verify SMD power-pad attach (discrete
freerouting left two GND attaches unconnected — LEDGER), then run
the widen pass (T3), THEN re-DRC against the class table.
T11. DSN text-level attach injection is counter-productive: freerouting
rips (type route) wiring that conflicts with its plans (0/17 survived
batch 20), places its own plane vias, and the injected geometry leaves
unresolvable clearance debt (19 violations). If attach vias must be
seeded, do it PCB-side with fix semantics (T4), never as DSN text.
T12. DSN coordinate frame is (x, -y) x1000 of pcb mm (KiCad y-down vs
Specctra y-up) — dsn_attach_probe asserts it per-pad against probe
wiring. Also: pcbnew pad.GetLayer() reports F_Cu for these B-side SMD
pads — the batch-10 probe stubs landed on F.Cu, disconnected from
their B.Cu pads (stub-arm conclusion stands: they were fixed obstacles
either way, but they never attached).

## 5. Open gates NOT in worker scope (recorded as blockers, not waived)

- Assembly quote: account + Gerber/BOM/CPL upload (login; quote/ ready).
- Bench B1/B1b (LDO ramp, rail current), B2 (edge scope:
  overshoot < 0.6 V, undershoot > -0.4 V), B3 (flash-free AUTO-BOOT):
  need hardware.
- Gowin EDA vendor flow never run (no install in worker scope);
  termination decision-recorded pending B2 (see termination.md).
- True stepped-edge pad distance recheck (GK): JP-band pad-to-BBOX
  1.3 mm is recorded info-only.

Ledger and plan references: docs/LEDGER.md (autorouter comparison,
SMD trap, guard design), checkpoints/fpga-01.md sessions 2-16
(evidence per batch), docs/FPGA_PLAN.md (register order).
