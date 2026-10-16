# FPGA-01 — electrical design checkpoint

## Recovery — 2026-10-14

Status: in progress; acceptance gate not met.

- Read `docs/FPGA_PLAN.md`, `docs/architecture/current-development.md`,
  prior `fpga-board.md`, and board readiness ledger before editing.
- Initial `git status --short` clean. No previous numbered FPGA-01 checkpoint.
- Baseline is the certified 19-contact placement prototype, not fab-ready:
  90 unconnected pairs, placeholder core LDO, no authoritative schematic.
- CERN model discovered as `cern/Kimi-K3-FLATIRON`. Named `cern-worker`
  is not exposed in this session; use coding workers with that exact model.
- Disjoint worker ownership: electrical worker owns `fpga/board/**` and this
  checkpoint; resource worker owns `tools/resource_guard.py` and
  `checkpoints/fpga-resource.md`. Orchestrator owns the plan/status review.
- Initial memory: 8,289 MiB available; all 11,416 MiB swap occupied. Heavy
  jobs must be serial, bounded, memory-capped and admitted after checking
  memory and competing Rust activity. Do not modify unrelated jobs.
- User authorized unattended progress until 2026-10-15 10:00 local time;
  session persistence is not guaranteed. No purchases or hardware claims.

## Session 2 recovery — 2026-10-14 ~19:00 CEST (Kimi-K3 electrical worker)

- Read FPGA_PLAN.md, current-development.md, fpga-board.md (full history),
  fpga-01.md, board README/docs/{candidate,power_reg,readiness}.md,
  connector-next budget.py header, fpga/docs/pin_budget.md, my production cst.
- `git status --short`: only orchestrator's plan edit + this checkpoint
  untracked-modified — checkout is clean for my scope. No board jobs running
  (r4 finished 2026-10-13); no containers active. MemAvailable 6.5 GiB, swap
  full (11.4 GiB); no rustc/cargo activity. junit OK to proceed serially.
- INHERITED STATE (fpga-board worker, machine-checked): boards = unrouted
  placement prototypes (0 DRC errors, r4 nets gw1nz=40 with GND_DET bonded to
  GND); production cst/pcf PASS B1..B6/H1/S1; real PnR 4/4 PASS; netlist
  N1..N9 PASS + 3 negative controls; footprint verify PASS. LDO = placeholder
  class only ("TLV75512-class, pin conv. TBD"), banks unpowered class fixed,
  but **LDO OUT node (VCC1V2_RAW) carries NO capacitor** — violates every
  candidate LDO's stability requirement (C6 4u7 sits AFTER FB1). Exact part
  selection must fix this (add C8 at LDO OUT). Also cst outputs carry no
  DRIVE/SLEW attributes (termination not pinned down).

### [19:05-19:35] Regulator selected + C8/C9 fix spun into regen r5 (PASS)

- **DS841E re-fetch reproduces the recorded sha256** (a19cdd7a...; CDN
  needs a browser UA). Numbers extracted: VCC LV 1.07-1.26 V; ramps VCC
  0.6-6/VCCX 0.6-10/VCCIO 0.1-10 mV/us monotonic (Table 3-3); POR trips
  VCC 0.8/VCCX 1.5/VCCIO 0.9 V (T3-5); LV static ICC=3 mA typ, ICCX/ICCIO
  0.5 mA typ (T3-9).
- **REGULATOR DECIDED: TI TLV75512PDBVR** (SBVS320D, fixed 1.2 V, 500 mA,
  SOT-23-5 DBV). Verified from PDF text: DBV pinout 1=IN 2=GND 3=EN 4=NC
  5=OUT == board's existing U2 binding; CIN/COUT >= 1 uF min (drives C8/C9
  additions); UVLO 1.44 V max << 3.3 V; EN->IN sanctioned; accuracy
  +/-1% (<=85C: 1.188-1.212 V, inside 1.07-1.26 V); R_thJA 231 K/W JEDEC
  (at 50 mA worst-case P=105 mW -> +24 K at TA 85 -> TJ ~109 < 125);
  soft-start monotonic rise; Fig 5-11 startup ~0.5 ms for 3.3 V out ->
  est 0.2-0.55 ms for 1.2 V (2.2-6 mV/us: at/inside Gowin's 0.6-6 window,
  recorded as bench-verify item B1). Foldback current-limit + constant-
  current-load startup caveat noted (FPGA core ≈ resistive-ish, 3 mA
  static typ; fine).
- board_gen parts: U2 value TLV75512PDBVR + verified-note; +C8 1u
  (VCC1V2_RAW-GND, LDO COUT before the bead -- the missing-cap defect),
  +C9 1u (VCC-GND LDO CIN); up5k U2 likewise + C11/C12 same reasoning.
- board_net_check N5 updated: VCC1V2_RAW == {C8.1,FB1.1,U2.5}; 1u census.
- **regen r5 DONE (serial, pre-guard): GATE PASS both variants** (log
  out/logs/board_gen_r5.log): gw1nz 60 parts/40 nets, GK1-7 PASS; up5k 72
  parts/36 nets, NOFIT documented as before. Nets unchanged (40/36): cap
  additions joined existing nets, parts +2 each variant.

### [18:59-20:10] Schematic format spike (KiCad 10 / 20260306)

- Format template = repo rev-A schematics (KiCad-10.0-written, version
  20260306): header, lib_symbols with `(power global)` power symbols
  whose VALUE names the net, wires, labels, no_connect, junction,
  sheet_instances. Spike ERC runs via flatpak kicad-cli 10.0.6 **through
  resource_guard.py** (flock serial; MemAvail gate; 2 GiB scope).
- TWO environmental findings recorded: (1) Gowin CDN serves HTML to
  non-browser UA (re-fetch needs UA; hash then matches); (2) **flatpak
  /tmp is private -- kicad-cli cannot see /tmp files; kicad-cli.sh
  supports KICAD_EXTRA_FS=/tmp/opencode** (or work in HOME paths).
- ERC mechanics learned from real violations: power symbols provide net
  NAMES but not DRIVE -> chassis pads JP_VCC/JP_GND get pin type
  power_out (truthful: power enters Via the spring contact), U2 pin5 OUT
  gets power_out; symbol-lib Y axis is screen-UP (sheet Y is DOWN) --
  label/pin placement must flip lib-y; labels sit exactly on pin tips;
  NC pins: type no_connect, no X needed (X on NC-typed pin =
  no_connect_connected violation); external lib needs a sym-lib-table in
  the project dir or lib_symbol_issues warnings appear.
- Programming-review requirements cross-checked: TCK/TMS/TDI/TDO/GND/VCC
  test pads exist (N4), MODE straps 00, RECONFIG_N pull-up + TP, 3.3 V
  JTAG bank powered -- ALREADY satisfied; JTAG pins not consumed by cst.

## Session 3 — 2026-10-14 ~20:30-22:00 CEST (Kimi-K3 electrical worker)

Schematic generator finished + true ERC + reconciliation gate. All heavy
jobs serial via resource_guard (guard report: MemAvail ~8.8 GiB admitted).

### Built/green
- **`kicad/sch_gen.py` -> `out/kicad/tile_gw1nz.kicad_sch`** (+ project-local
  `lib/fpga_tile.kicad_sym`, `sym-lib-table`, `fp-lib-table`,
  `out/sch_summary.json`). Single A3 sheet, everything on the 1.27 mm
  connection grid; U1 GW1NZ-QN48 (49 pins incl NC X on 6/9/14/15/29),
  U2 TLV75512PDBVR (1=IN 2=GND 3=EN 4=NC 5=OUT), C1-9/FB1/R1-6 net-for-net
  identical to the board, 12 key sockets, 19 chassis pads, 11 TPs, notes.
  SCH0 self-check (all 49 U1 pins connected, net census == board 40).
- **ERC: `kicad-cli sch erc --format json --severity-all` = 0 violations**
  with NO exclusion file (out/kicad/tile_gw1nz.erc.json).
- **`tools/schematic_check.py` = PASS (S1-S7)**: S1 fresh ERC 0; S2 netlist
  parses, no empty/`<NO NET>` nets; S3 census 40/40 vs canonical; S4
  schematic-vs-PCB pad parity **134==134 every net** (pcode ref/pin ==
  pcb ref/pad); S5 cst parity 26/26 ports == U1 pins (map derived from
  rtl/top_gw1nz.vhdl entity); S6 power/strap/NC coverage vs pins db
  (NC exactly 6/9/14/15/29); S7 negative controls 3/3 fired. Netlist =
  46 nets (40 + 6 expected unconnected-NC). Exporter's `annotation errors`
  warning is the semantic-ref style (JP_B_clk/TP_TCK... same refs as the
  PCB on purpose); documented in the checker, ERC stays the gate.

### Root-caused format defects (for future KiCad writers)
1. `(kicad_sym_lib ...)` typo -> library "not found" (silent whole-lib
   rejection, cascaded 100+ phantom violations).
2. **`.kicad_sym` header version must be lib-era (20230121)**; the
   schematic-era 20260306 string is REJECTED by kicad-cli 10.0.6 sym
   loader ("unable to load library"; verified by A/B probe).
3. Power-symbol Instances need an **instance Value property** -- KiCad
   names power nets from it; omitting it leaves rails nameless ('').
4. f-string ref bug `JP_PAD_...` -> instances asked for `JP_PAD_PAD`.
5. TP grid `divmod(i,2)` unpacking swap stacked 8 TPs on 4 points ->
   cross-net mergers (this was the phantom JTAG<->CFG short).
6. JP feed pads (power_out pins) need the rail's PWR symbol at the pad
   tip or the rail is a driverless island; DET pads tie to GND the same
   way (matches board GND_DET*-on-GND fact = truthfully documented).
7. Bead-filtered rail (VCC1V2 after FB1) can't be seen through the
   passive bead -> added documented PWR_FLAG (fpga_tile:PWR_FLAG, text
   says exactly why; NOT an exclusion file).
8. every connection endpoint must sit on the 1.27 mm grid
   (endpoint_off_grid warnings otherwise); uuids via uuid5 over a
   project namespace string (stable across regens).

### Parity hunt outcome
schematic_check's S4 initially reported U1/U2/SW pin mismatches; ALL were
parser bugs in MY pcb probe (netless NC pads swallowed the next pad's
net; SW uses bare pad names). Board pin map == cst == db == schematic:
NO board defect existed on those pins. Parser fixed; controls in S7
guard against such vacuity.

## Session 4 — 2026-10-14 ~22:00-23:00 CEST (Kimi-K3 electrical worker)

Termination doc, BOM evidence, doc alignment, cleanup. One guarded
kicad-cli run (SVG render smoke test, serial; MemAvail ~8.1 GiB), no
design-affecting re-runs.

### Built/done
- **`docs/termination.md` — RESOLVED: keep certified 19 contacts.**
  Records the drive-strength finding honestly: cst carries
  `DRIVE=2 SLEWRATE=SLOW` on the 5 merged outputs as **vendor-tool intent
  only** — A/B nextpnr-himbaechel bitstreams are byte-identical
  (out/pnr/tmp/ab_A.fs == ab_B.fs, 351954 B; `SLEWRATE` absent from the
  libexec binary strings), so with the OSS flow pads run at
  silicon-default drive. Bench gate **B2** (scope T_clk/B_data edges at
  the far contact) owns the go/no-go for the gated 21-contact series-R
  rev-B fallback. The .fs pair is kept as durable evidence; A/B jsons +
  probe cst deleted.
- **`docs/bom.md` + `docs/bom.json` — component sourcing COMPLETE**
  (all evidence fetched 2026-10-14, URLs + stock + price breaks):
  U1 GW1NZ-LV1QN48C6/I5 LCSC C5799569 (stock 888-924, US$6.6772@1);
  U2 TLV75512PDBVR DigiKey 296-TLV75512PDBVR (stock 8.3k+, US$0.30@1);
  SW1-12 Kailh CPG151101S11 kailhswitch.net US$0.21 ea (NOT in PCBA
  libraries -> hand-solder/consigned); FB1 Murata BLM18PG121SN1D LCSC
  C14709 (stock 1.29M, US$0.0147@50); passives commodity-spec'd.
  Roll-up ~US$9.6/tile components at qty 1.
- **PCBA quote = BLOCKED GATE recorded, NOT invented**: JLCPCB formal
  quote needs account + Gerber/BOM/CPL upload. Public structure captured
  (jlcpcb.com/pcb-assembly: no-setup-fee coupons, 680k+ parts, fine-pitch
  >=0.35 mm covers QFN48 0.4 mm; GOWIN x JLCPCB coop 2026-04-30).
- **Docs aligned**: readiness.md (3 new ledger rows: sch_gen/ERC,
  schematic_check; 2026-10-14 defects section incl. the C8-before-bead
  find; LDO/termination/BOM gap text replaced), power_reg.md (TLV75512
  verified section + B1 + BOM pointer), candidate.md (LDO line),
  README.md (sch_gen/schematic_check/termination/bom entries, regen
  list, status 2026-10-14). power_reg N5 wording verified == checker
  ({U2.5, FB1.1, C8.1}).
- **Schematic render smoke test**: `kicad-cli sch export svg` plots the
  full sheet -> `out/kicad/tile_gw1nz.preview.svg` (2.49 MB); content
  spot-checked (U1/U2 values, JP_B_clk, VCC1V2, SW12 all present) --
  the emitted .kicad_sch is a real editable schematic, ERC-clean AND
  renderer-clean.
- **Cleanup**: probing residue removed from out/kicad (t_notext,
  t_nolabel, abs.erc.json, p1/p2/S_*) and out/pnr/tmp (A/B jsons, probe
  cst). No stray generated files remain in the owned tree.
- **Ownership check**: `git status` confirms this worker's diff touches
  ONLY `fpga/board/**` + `checkpoints/fpga-01.md` (FPGA_PLAN.md,
  fpga-resource*.md, fpga-downstream*.md are other writers' files).

### FPGA-01 gate status (end of session 4, CORRECTED by session-5 review)

| sub-gate | status |
|---|---|
| 1 regulator (TLV75512PDBVR, pinout + caps verified vs SBVS320D) | DONE |
| 2 authoritative schematic + TRUE ERC 0, no exclusions | DONE |
| 3 schematic<->board<->cst reconciliation S1-S7 | DONE |
| 4 termination | **DECISION RECORDED, NOT RESOLVED** — keep-19-contacts is an engineering hypothesis resting on bench gate B2 after the independent review removed the invalid closure rationale; structural mitigation options compared in session 5 (docs/termination.md) |
| 5 BOM | **BOM DONE; assembly quote NOT OBTAINED** — still required by ordered FPGA-01/5 (needs account + Gerber/BOM/CPL upload: no apparatus here; no waiver recorded). Item 5 NOT DONE. |
| 6 docs + README alignment | DONE (re-aligned 2026-10-14/15 to fpga-01-review findings P1–P7) |

FPGA-01 task status: **IN PROGRESS** (per fpga-01-review verdict: sub-gates
4 and 5 are not evidence-closed; the task is marked complete only when the
assembly quote is actually obtained (or the plan owner formally re-scopes
it) and the termination decision earns its bench evidence). What remains: physical/bench (B1 LDO ramp, B2 edge
scope, B3 flash-free AUTO-BOOT blink), adjudication items (PCBA quote,
termination closure), and out-of-scope-here work (routing, silk cleanup,
EP thermal vias) listed in docs/readiness.md.

## Session 5 — 2026-10-15 ~00:00 CEST (Kimi-K3 electrical worker, remediation pass)

Early checkpoint BEFORE any heavy runs, per orchestrator instruction after
the independent review (`checkpoints/fpga-01-review.md`, frozen baseline
2026-10-14 22:42-23:05). Task status: **IN PROGRESS** (NOT complete;
sub-gates 4 and 5 are decision-recorded / evidence-missing, not closed).

### Repairs landed (doc-only, cheap — no regenerations yet)

- **P1 (doc-physics)**: termination.md rewrite staged; the invalid
  rationale ("twice terminated by snap-flop sampling", settle-inside-cell
  safety for clock-class nets, interior-Fmax = system closure) is being
  removed; assumption-vs-evidence split made explicit.
- **P2 (vendor claim)**: cst comment rewritten — attrs are UNVERIFIED
  vendor hints (no Gowin-EDA run exists here); spelling fixed to the
  documented SUG935-1.3E A.2 form **`SLEW_RATE=SLOW`** (document verified
  via published SUG935 copies: gowinsemi.com.cn 1.6.1E + Sipeed mirror
  1.3E; both show `SLEW_RATE = FAST` in Example 2). OSS-flow ignores
  either spelling (A/B evidence unchanged).
- **P4 (stale counts, all re-verified from artifacts, not the review)**:
  DRC gw1nz = 92 warnings (66 silk_over_copper/24 silk_overlap/2
  silk_edge_clearance), unconnected_items 94; up5k = 90 warnings
  (64/24/2), 88 unconnected — readiness.md rows fixed. Parts r5 =
  60 total (GK7), 9 caps, 29 non-key — power_reg.md fixed. TPs = 11
  (verified list: TP_DONE/GND/JTAGSEL/READY/RECFG/TCK/TDI/TDO/TMS/VCC/
  VCC1V2) — bom.md + session-3 note fixed.
- **P5 (gate relabel)**: session-4 gate table corrected above: row 4 =
  DECISION RECORDED NOT RESOLVED; row 5 = BOM DONE, assembly quote NOT
  OBTAINED (still ordered, no waiver); closing sentence replaced by
  IN-PROGRESS statement. (2026-10-15 batch: the interim "carried-open to
  FPGA-02" wording was UNAUTHORIZED — removed everywhere in owned docs.)

### Investigation model (evidence-grounded, for the termination comparison)

Contact/branch facts read from the actual sources (rtl/top_gw1nz.vhdl
header, connectors/out/report.md adjacency PASS lines, board jp census):

| net (FPGA port) | class | topology (from sources) |
|---|---|---|
| T_clk (out) | clock (edge-critical) | point-to-point link to the tile-above's merged clk_net; that net carries one other TBUF driver (the above tile's right neighbour) — 1 active driver at a time |
| L_clk (out) | clock | same, toward the left tile |
| L_latch/latcho (out) | latch strobe (edge-critical) | **2 branches** (T_latch + L_latch merged on the chassis): up + left receivers |
| B_data/dout (out) | data level | **2 branches** (B_data + R_data chassis merge): down + right receivers |
| B_W (out) | write level | point-to-point |

RTL budget (read, not assumed): 20 MHz shift chain, 50 ns bit cell,
source-synchronous per hop ( neighbour T_clk launches, neighbour's clk_pin
captures; tile_fpga snap flops). Clock/strobe-class nets fail on ANY
mid-cell threshold re-crossing (double shift/latch); level nets only need
settling before the capture edge. No channel model (impedance, return
path, loads, spring-contact parasitics) exists anywhere — the ≤0.25 m run
length is an ASSERTION (no derivation found); both are recorded as
assumptions A1/A2 in the rewritten doc.

### Planned (bounded; expensive items serial + guarded)

1. termination.md full rewrite (physics repair + options comparison
   A=direct / B=in-tile series-R footprints (0R default, DNP-selectable
   values; frame-neutral: 19 coords untouched) / C=backplane per-leg DNP
   positions (connector-next owned, zero new contacts) / D=rev-B
   21-contact per-leg (gated, likely unnecessary if B/C viable)) with
   branching connectivity, part/net/power-count deltas, and an honest
   routing-feasibility paragraph (placement-level only; no tracks exist).
2. OSS drive-path closure: apicula/chipdb probe for GW1NZ IOB DRIVE/SLEW
   fuse mapping (P3b) + ONE guarded container run doing RTL-attribute A/B
   (P3a: VHDL port attrs via yosys ghdl → nextpnr; two pnr runs, .fs
   sha256 compare) and the gw1nz re-PnR required by the cst text change.
3. schematic_check.py P6 cleanup (dead io_pins leg + vacuous S6 block +
   docstring) and re-verify.
4. IF the comparison verdict is safe+clear AND the placement lattice
   accepts 5x 0402 positions near U1's output pins: implement option B
   (board_gen parts/net-split, checker updates, sch_gen, ONE guarded
   regen + DRC + netcheck + schematic_check/ERC). Otherwise the doc
   carries the decision deferral with the evidence.
5. Final checkpoint with exact recounts from regenerated artifacts.

Started ~00:00; deadline 2026-10-15T10:00+02:00 respected; heavy jobs
serial through resource_guard (2 GiB outer scope, CPU1).

## Session 5b — 2026-10-15 10:39 CEST (Kimi-K3, bounded current-session batch)

Resumed after provider disconnect (00:04). Batch rules: deadline
RESOURCE_GUARD_DEADLINE=2026-10-15T12:10:00+02:00 (90-min window; the old
overnight cutoff is expired and NOT reused), MinAvailable 6144 MiB, 2 GiB
memory / CPU1, heavy jobs serial, top-level podman with EXPLICIT caps
(--memory 2g --memory-swap 2g --cpus 1 --pids-limit 256) via the new
fpga/board/tools/oss_capped.sh (tools/oss.sh is outside ownership and
cap-less — left untouched). Ownership: board/** + this checkpoint only.

### State inspection before any job (all read-only)

- No live jobs of mine; no active containers (one stale podman name from
  months ago, not mine — left as-is). Guard lock free.
- Overnight partials PERSISTED and were NOT duplicated: cst SLEW_RATE
  respell + re-PnR PASS (342/234 MHz modes, 351954 B); drive_attr_ab.sh
  evidence (fs_A == production 3918ac9c…, fs_B differs; 10 config rows =
  5 ports × 2; pnr json shows DRIVE=24 on exactly the 5 OBUF/TBUF cells);
  option-C code edits in board_gen.py + board_net_check.py (R0402,
  SERIES_DRV_GW1NZ, N10). NOT yet done at interrupt: sch_gen.py +
  schematic_check.py series updates, termination.md rewrite, regen.
- Correction applied first: "carried-open to FPGA-02 fab prep" was
  UNAUTHORIZED — removed from all owned docs; quote is simply NOT
  OBTAINED and still ordered by FPGA-01/5. Historical "TERMINATION DONE
  (session 4)" mark superseded.

### Batch plan (serial)

1. Finish option-C edits: sch_gen.py (5 series symbols + _DRV labels +
   note) and schematic_check.py (census 45, S5 DRV alias, S6 series node
   sets).
2. termination.md full rewrite (P1 physics repair, options comparison
   A/B/C/D with the implemented option C, assumption-vs-evidence tables,
   B2 extended per review P7).
3. ONE guarded regen battery (explicit caps): board_gen regen →
   board_net_check → sch_gen → schematic_check (fresh ERC) → DRC both
   variants → recount everything from the new artifacts.
4. Docs + counts (readiness/power_reg/README/bom) to the r6 numbers;
   final checkpoint with persisted-vs-planned and exact remaining
   blockers.

FPGA-01 stays IN PROGRESS either way (ordered item 5's quote is missing;
ordered item 4 is decision-recorded pending B2).

### Session 5b -- batch results (COMPLETED 2026-10-15 ~11:15 CEST)

All four batch items done. One generator defect found and repaired
(SCH0's own expected-census still listed 40 nets; sch_gen.py now derives
it from SERIES_DRV_NETS -- the emitted schematic was right all along,
the self-check expectation was stale). Exact commands (serial, guard
admission at every heavy step, scope caps MemoryMax=2048M CPUQuota=100%,
top-level podman caps 2g/2g/--cpus 1/--pids-limit 256 via
fpga/board/tools/oss_capped.sh):

1. `bash fpga/board/tools/regen_batch.sh` (10:42; durable log
   /tmp/opencode/fpga01-regen-r6.log): board_gen r6 **PASS**,
   board_net_check **PASS**; sch_gen **FAIL** on SCH0 (above) -> aborted
   remaining steps, no duplicate reruns of passed steps.
2. SCH0 fix + rerun of ONLY steps 3-5 (absolute-path launcher; log
   /tmp/opencode/fpga01-regen-r6b.log): sch_gen, schematic_check, both
   DRC runs -- **all PASS**.

Results at r6 (recounted from artifacts, not predicted):
- board_gen: GK1..GK7 all OK; **65 parts, unplaced=[] -- all 5 series
  resistors placed (B side)**: R7(-0.09,3.10) R8(12.41,14.10)
  R9(-0.09,4.45) R10(-0.09,5.85) R11(0.91,10.80); 45 nets, 0 tracks;
  GK2: 19 JP coords byte-identical to the certified geometry.
- netcheck: N1 49/49 exact; **N10 series split exact** (U1--Rn.1 on
  <net>_DRV, Rn.2--JP on <net>); negative controls 3/3 fired; up5k N1
  absent-by-design, N10 n/a. Overall PASS.
- schematic_check: **S1 ERC = 0 violations (severity-all, no
  exclusions)**; S2 netlist 51 nets (45 + 6 NC), no bad names; **S3
  census 45/45**; **S4 pad parity 144==144** (+10 series pads);
  S5 26/26 cst ports (DRV alias); **S6 straps + series node sets
  exact**; S7 3/3 controls fired.
- DRC kicad-cli 10.0.6: gw1nz **0 errors, 107 warnings**
  (76 silk_over_copper / 29 silk_overlap / 2 silk_edge_clearance; +15 vs
  r5 = the five new refs' silkscreen labels, same cosmetic classes),
  **99 unconnected_items** (+5 vs r5: each split turns one {U1,JP}
  unrouted pair into two {U1,R}+{R,JP} pairs); up5k **unchanged**
  90 warnings (64/24/2) / 88 unconnected -- untouched-variant control.
- A/B evidence (persisted from overnight, not re-run):
  ab_A.fs == ab_B.fs == rtl_ab/fs_A.fs ==
  3918ac9c77dec30f7c5c6aa4121190c9362676a81151131aefc975c786c737fe
  (cst attrs dead + no-attr RTL re-anchors the production hash);
  rtl_ab/fs_B.fs = 2f43b717911e... (RTL DRIVE=24 on exactly the five
  OBUF/TBUF cells -> RTL attr path proven).

Persisted vs planned:
- PLANNED-AND-DONE: cst respell P2; count fixes P4; gate relabel P5;
  P6 real STRAPS checks; SCH0 fix; P1 termination rewrite; P3 RTL-attr
  A/B; option C implemented end-to-end (gen 4x + checks + regen +
  recounts + docs); carried-open purge; readiness/power_reg/README/bom
  r6 alignment.
- PLANNED-NOT-DONE (beyond batch scope): any vendor-flow run (no
  vendor access); RTL DRIVE edit itself (fpga workstream's file --
  recorded as evidence-backed recommendation in docs/termination.md);
  routing (FPGA-02 scope by ordering).
- BLOCKERS, unchanged and honest: assembly quote **NOT OBTAINED**
  (ordered FPGA-01/5, no waiver); bench items B1/B2(inc. L_latch probe +
  undershoot bound)/B3 unexecuted (no hardware access); series
  resistors are placement-proven configurable placeholders (0R
  populated), NOT proven damping and NOT routing proof.

Task status: **FPGA-01 IN PROGRESS**. 2026-10-15 batch deadline met
(all heavy work finished ~11:15, before 12:10).

## Session 7 — overnight batch 002 (2026-10-15 22:02-22:14 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

Continuation of batch 001 (READY). Recovery checks: checkpoint tail is as
batch 001 left it; `git status --porcelain` identical to batch-001 end (my
files present, no foreign writes in owned paths); no STOP file; no foreign
process references this session id. Executed the recorded next step.

### Canonical report refresh — validator §7 now FULLY closed (all serial, each through resource_guard with --mem-mib 2048 + deadline 2026-10-16T11:00+02:00)

Admission granted on every call (MemAvail 6251-6310 MiB, PSI ~0, no Rust):

- `board_net_check.py` — **PASS** N1..N10 both variants + neg controls
  a/b/c (netcheck_report.{json,md} refreshed 22:03).
- `pincon_check.py` — **REAL LATENT DEFECT FOUND FIRST**: exit 1,
  `unparsed residue: 'IO_PORT "t_clk_pin" IO_TYPE=LVCMOS33 DRIVE=2
  SLEW_RATE=SLOW;'`. Root cause: session-5b respelled the cst's five
  output lines to the SUG935 form SLEW_RATE + attr body; the r6
  regen-battery runs did NOT include pincon_check, and the validator's
  refresh attempts were admission-blocked — so the checker had not seen
  the new statement form since. Repaired `parse_cst` (general IO_PORT
  attribute body; strict ATTR_KEYS = {IO_TYPE, DRIVE, SLEW_RATE,
  SLEWRATE, PULL_MODE}; unknown keys/values still fail = F1 hygiene
  preserved). Inline parser self-test before the real run: production
  cst parses exactly (26 nets, pulls correct) + 4 controls behave
  (unknown attr rejected, legacy SLEWRATE accepted, bare token rejected,
  synth-style shared-line pull parsed; tempfiles deleted). Real run:
  **PASS** B1a/B1b..B6/H1/S1 both variants (pincon_report refreshed
  22:06). The cst itself was correct; the checker lagged it.
- `footprint_verify.py` — **PASS** both variants + 4 wrong-expectation
  controls (footprint_verify.json refreshed 22:07).
- `kicad-cli pcb drc` gw1nz — **107 violations / 99 unconnected** (fresh
  file 22:07:16; all 107 are warnings: 76 silk_over_copper, 29
  silk_overlap, 2 silk_edge_clearance; **0 error-severity**), exact r6
  reproduction.
- `kicad-cli pcb drc` up5k — **90 / 88** (fresh file 22:07:28; 64/24/2,
  0 errors), unchanged-variant control.
- Together with batch-001's fresh schematic_check (S1-S7 at 21:58),
  EVERY canonical report now carries a tonight's-timestamp verified
  regeneration. pcb itself untouched (sha256[:12] c7d5b66fa1db).
- First batch-001 mistake corrected: pure-python checkers that spawn no
  heavy tool were run via resource_guard individually (board_net_check,
  pincon_check, footprint_verify); only schematic_check self-guards.

### FPGA-02 prep (recorded-next continuation)

- New `tools/netclass_prep.py` + emitted `docs/netclasses.json`:
  machine-checked net-class assignment of all 45 r6 nets —
  edge_critical 6 (T_clk/L_clk/L_latch + _DRV), level_out 4
  (B_data/B_W + _DRV), channel_in 9, keys 12, power 4, config 10 —
  with the strict reference rule set and per-class return-path/bench
  (B1/B2/B3) notes. Self-checks N1-N5: exact partition (pcb-derived, not
  hand census), series topology re-read off the pcb (U1.35/19/31/30/27
  -> R7..R11 -> JP), power set exact, JP/presence coverage, and a real
  vacuity control (dropping T_clk provably fails partition). Converts
  straight into KiCad net classes at FPGA-02 time.
- `docs/routing_plan.md` + README.md updated to reference it.

### Status

**FPGA-01 IN PROGRESS**, blockers unchanged (quote NOT OBTAINED —
account+upload needed; B1/B1b/B2/B3 bench; vendor flow never run; board
unrouted). Modified this batch: tools/pincon_check.py (parser repair),
new tools/netclass_prep.py + docs/netclasses.json, README.md,
docs/routing_plan.md; refreshed out/netcheck_report.*,
out/pincon_report.*, out/footprint_verify.json, out/kicad/*.drc.json.

## Session 6 — overnight batch 001 (2026-10-15 21:43-22:05 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

Window 21:43→ next-day 11:00 CEST; batch-1 scope: owned `fpga/board/**` only
+ this checkpoint. Bootstrap done: AGENTS.md, FPGA_PLAN.md,
current-development.md, all seven checkpoints; `git status/--porcelain`
(prior r5-r6 session work preserved exactly — verified again at 22:20 that
`hardware/experiments/simple-tile/tools/*` mtimes predate the batch);
`pgrep -af opencode` (only this batch's own process references the session
id; nothing else writes fpga/board/**). No STOP file.

### Done (four small verified steps + one formal refresh)

1. **Fresh canonical rerun (closes fpga-01-validation §7's outstanding
   formal refresh)**: admission granted at 21:58 (MemAvail ~6.0-6.2 GiB,
   PSI 0, no Rust). `python3 tools/schematic_check.py` (self-guarding its
   kicad-cli steps; correct mode — see mistake note below):
   **PASS S1-S7** — S1 FRESH ERC 0 violations (severity-all, kicad-cli
   10.0.6, no exclusions; regenerated `tile_gw1nz.erc.json` 21:58:44),
   S2 51 nets, S3 45/45, S4 pad parity 144==144, S5 26/26, S6 MATCH,
   S7 3/3 controls. New erc/net bytes differ from the morning snapshots
   only by the embedded `date` metadata field (violation/net substance
   identical; pcb sha256[:12] c7d5b66fa1db unchanged == validator file).
2. **Consistency repair**: readiness.md SCH0 ledger row said "40-net
   census" (r5-era) — fixed to the r6 truth (45 nets, census derived
   from SERIES_DRV_NETS post-5b). Grep audit found no other stale r5
   roll-ups in owned docs.
3. **Regulator/decoupling closure (paper-stage)**: power_reg.md gained a
   measured r6 decoupling-placement table (cap->pin distances: bypass
   2.26-4.10 mm; C8 5.18 mm to U2.5 pre-bead; C9 5.42 mm to U2.1; bead
   load-side 4.59 mm to U1.12; coherent VCC-entry cluster at JP_VCC) +
   load/thermal budget closure: est. load ≪50 mA vs 500 mA rating;
   TJ<=125 ceiling ~82 mA at the recorded JEDEC 231 K/W (TA=85),
   >=190 mA at TI's parametric 60.3/100.8 K/W figures (review P8 folded
   in as provenance range) — conclusion insensitive at real load.
   **Load capacity + thermal VERIFIED ON PAPER**; true current = bench
   B1b (now named: rails scope + ammeter at 20 MHz, first tile).
4. **Distributor-agnostic quote preparation**: new `tools/quote_prep.py`
   (self-checks S1-S4: pcb census 65; bom.json refs == pcb BOM-bearing
   35 refs; CSV re-parse parity; board Value drift check) emits
   `docs/quote/bom_neutral.csv` (10 line items, JLC/LCSC/DigiKey-neutral
   columns) + `docs/quote/cpl_gw1nz_provisional.csv` (35 refs, r6
   placements, honestly labelled provisional-of-unrouted-prototype) +
   `docs/quote/README.md` checklist. **Quote itself still NOT OBTAINED**
   (needs account+upload on the routed board; no waiver).
5. **FPGA-02 preparation**: `docs/routing_plan.md` — r6 routing census
   (45 nets, classes), measured geometry (QFN 0.4-pitch pads leave 0.2 mm
   gaps => no inter-pad pass at 0.2/0.2 rules, radial escape; JP contact
   band x -9.0..36.5 y 21.7..36.7; longest on-tile segments 25-35 mm
   class), strict rule-set candidates from the discrete reference,
   2L-vs-4L comparison procedure with the recorded freerouting traps and
   criteria table, TP/B1/B2 measurement-point preservation list.
   Preparation only — FPGA-02 stays PENDING.

### Mistake + recovery (recorded)

I first wrapped `schematic_check.py` in an OUTER resource_guard call;
the checker's inner kicad-cli guard then refused on the held flock
(wall 0.2 s, S1/S2 "failed", cascaded FAIL). No artifacts were damaged
(pre-rerun hashes == validator snapshots; kicad-cli never ran inside the
refused scope). Root cause understood, reran correctly (checker
self-guards). Do NOT nest the guard around self-guarding tools.

### Status

**FPGA-01 IN PROGRESS**, blockers unchanged: assembly quote NOT OBTAINED
(ordered 5, needs account+upload); B1/B1b/B2/B3 bench items unexecuted
(no hardware); vendor flow never run; board unrouted (99 unconnected,
FPGA-02). New owned files this batch: tools/quote_prep.py, docs/quote/
(README + 2 CSVs), docs/routing_plan.md; edits: README.md,
docs/readiness.md, docs/power_reg.md; refreshed: out/kicad/
tile_gw1nz.erc.json + tile_gw1nz.net (21:58, check-identical substance).

## Session 2 plan (FPGA-01 sub-gates)

1. REGULATOR: select exact SOT-23-5 1.2 V LDO vs DS841 ramp (VCC 0.6–6 mV/µs,
   POR/flash-init), load (DS841 static/dynamic) and thermal maths; fetch TI
   datasheet; fix C8 (LDO OUT cap, 1 µF 0603) + C9 (LDO IN cap close) in
   board_gen; update N5 expectations; single regen. **DONE (session 2).**
2. SCHEMATIC: new `kicad/sch_gen.py` emits local symbol lib
   `lib/fpga_tile.kicad_sym` + `out/kicad/tile_gw1nz.kicad_sch`; true ERC via
   flatpak kicad-cli 10.0.6 `sch erc` (no blanket exclusions; zero violation
   target with NC flags + power symbols). **DONE (session 3): 0 violations.**
3. RECONCILE: new `tools/schematic_check.py` — exported schematic netlist vs
   board .kicad_pcb vs board_gen circuit vs production cst: refs, per-pin
   nets, rails, straps, 26 constraint pads, 3 presence pads on GND (tile),
   isolated-on-chassis note; ≥3 negative controls. **DONE (session 3):
   S1–S7 PASS, 134 pads == 134 pins.**
4. TERMINATION: resolve shared-vs-separate outbound WITHIN certified 19
   contacts (keep merged dout/latcho; add DRIVE=2/SLEW=SLOW to production
   cst + re-PnR gw1nz-only bounded; rev-B 21-contact per-leg series R
   recorded as gated fallback needing connector-next recertification).
   **~~DONE (session 4)~~ SUPERSEDED by the 2026-10-14 independent review +
   session 5: decision-recorded, NOT resolved (structural options compared
   in docs/termination.md; closure needs bench item B2).**
5. BOM: dated URLs/prices/stock for FPGA, LDO, sockets, FB, passives;
   public assembly price evidence; blocked gates recorded, never invented.
   **BOM DONE (session 4): docs/bom.md+bom.json; assembly quote NOT
   OBTAINED — item 5 NOT DONE (review P5).**
6. Update docs/{power_reg,candidate,readiness}.md + README; board value
   strings (U2 exact part) batched into the same single regen + DRC +
   netcheck re-run. **DONE (regen in session 2; docs aligned session 4).**

## Next

Electrical worker to select sourced regulator, create and reconcile schematic,
run ERC and electrical checks, resolve termination within certified contacts,
and record actual BOM evidence and quote limitations. Later ordered gates
remain pending until prerequisites pass; fabrication and bench work require
physical access and cannot be inferred from tool results.

## Session 8 — overnight batch 003+004 (2026-10-15 22:13-23:00 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

**Recovery note:** batch 003 was interrupted after its tooling/artifacts
landed but before its protocol close (no checkpoint append, no outcome
file). Batch 004 recovered the state read-only (pgrep: no foreign
processes; no STOP file; pcb sha256[:12]=c7d5b66fa1db == validator
snapshot; git status shows only prior uncommitted work plus own files),
re-verified every batch-003 artifact deterministically, completed the
remaining analysis, and closed the protocol. The retroactive
batches/003/outcome.env records the absorption.

**Recorded-next-step item executed (FPGA-02 prep continuation: freerouting/
fanout plan detail) — all three sub-items done:**

1. **DSN export feasibility — PROVEN on this host.** The in-tree proven
   path is the pcbnew Python API inside the KiCad 10.0.6 flatpak (same
   recipe as discrete layout/build_4layer.py and rev-B/C scripts;
   kicad-cli has no DSN subcommand). New `tools/export_dsn.py` ran via
   resource_guard (admission MemAvailable 7307 MiB, PSI 0.01, 2048 MiB
   cap; flatpak DELEGATION warning logged = expected per design):
   `EXPORT_DSN_OK pcb_nets=45 footprints=65 pads=210 tracks=0
   out/route/tile_gw1nz.dsn bytes=37680` (wall 0.8 s). Pad census
   independently reconciled: 210 = U1 49 + SW 12x7 (2 SMD + 5 NPTH) +
   JP 19 + TP 11 + C 18 + R 22 + FB 2 + U2 5.
   New `tools/dsn_check.py` PASS (first run caught my own pins/net
   close-paren regex bug; fixed and re-verified): D1 45 DSN nets ==
   45 pcb nets; D2 per-net pin parity (144 pins == the S4 pad-parity
   number); D3 boundary path present, exactly F.Cu/B.Cu, default rule
   200/200 um + smd_smd 50 um (KiCad defaults — the reference 0.2/0.3
   set must be written into pcb setup BEFORE export = fanout phase A),
   via Via[0-1]_600:300_um; D4 vacuity control fires. Report:
   out/route/dsn_check.json. This exports nothing routed: preparation
   evidence only.

2. **EP thermal-via decision analysis** recorded in docs/routing_plan.md
   ("QFN EP (pad 49) thermal-via decision analysis"): FPGA consumes
   ~50-60 mW (power_reg.md batch-1 numbers; the 2.1 V drop heat is the
   LDO's) -> thermal vias NOT needed by ~2 orders of magnitude; EP is
   on net GND (pins 2/26/49) and MUST be soldered (multi-window paste,
   no fab vias); via-in-EP array SKIP proposal (filling/plugging cost +
   void risk, zero thermal need); open sub-item = 2L GND stitching with
   an optional outside-EP via ring (measured EP-to-row corridor
   1.175 mm fits one 0.6/0.3 ring) deferred to the FPGA-02 fanout phase.
   No geometry change, no gate claim.

3. **Socket-corridor width measurement** — new `tools/routing_geo.py` →
   `docs/routing_geo.json` (deterministic vs the r6 pcb; rect-to-rect
   euclidean min over pad/hole AABBs, NPTH drill +0.15 annulus, rot==0
   asserted, vacuity control). Results: 23 adjacent socket corridors;
   in-row (18.36 pitch) bottleneck 2.883 mm = SW1 K1 hotswap pad to SW2
   edge-trimmed VCC pad corner (0.04 mm y-offset) -> 6 tracks at
   0.2/0.2; diagonals up to 9.02 mm -> 22 tracks. LEDGER trap
   quantified: courtyard-only model says 7.56 mm, true obstacle gap
   2.88 mm (hotswap pads stick ~2 mm out of courtyards). U1 escape
   pinch points: SW6 3.05 mm NPTH tooling hole vs north pad-toe row =
   0.375 mm (x~10.0 line must jog); C1-C6/FB1/R2 at 0.52-0.6 mm by
   design; R7-R11 deliberately in the south corridor. JP band: min
   pad-box to outline-BBOX edge 1.3 mm (info only; true stepped-edge
   distance stays a GK recheck matter).

4. docs/routing_plan.md gained four sections: channel-capacity
   measurements, router I/O path (DSN/SES feasibility), EP decision
   analysis, fanout order of operations (phase A rule-set-first,
   phase B 2L/4L fanout sequence incl. the SMD-to-plane LEDGER trap,
   phase C closure checks incl. dsn_check re-run on the routed board).

Board, schematic, cst, netlist untouched this session (hash evidence
above). Bench items (B1/B1b/B2/B3), the assembly quote (account+upload),
and vendor-EDA closure remain plan-owner/hardware-gated, not
worker-closable.

**Next session seed:** draft `tools/netclass_apply.py` (FPGA-02 phase-A
dry run): apply docs/netclasses.json class assignments + the 0.2/0.3
reference rule set to a COPY of the pcb (never the design artifact),
plus a verifier proving the copy diff is exactly the setup/netclass
block; then re-export DSN from the copy and confirm dsn_check still
PASSes with the real rule values.

## Session 9 — overnight batch 005 (2026-10-15 22:43-23:35 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

**Recorded-next-step item executed: FPGA-02 phase-A (classed router rule
set delivery) — completed with an empirical course-correction recorded
in full.** All runs guarded via resource_guard (2048 MiB, deadline
2026-10-16T11:00; admissions MemAvailable ~7.3 GiB, PSI 0.00-0.01).

1. NEGATIVE RESULT (valuable; bisected): a hand-written pcb net-class
   text format SEGFAULTS the KiCad 10.0.6 flatpak `ExportSpecctraDSN`.
   Initial `tools/netclass_apply.py` inserted `(net_class ...)` blocks +
   class-padded `(net N "NAME" "CLASS")` decls into a copy (inverse-diff
   byte-identity proven textually); export → exit 139 inside
   pcbnew.py:9919 ExportSpecctraDSN (faulthandler trace recorded).
   Controlled bisection (blocks-only variant, decl-padding-only variant,
   then blocks+legacy `(net "X")` member lists): ALL crash. Demos inside
   the flatpak contain zero net_class pcb examples. The hand-written
   tool + its copies were DELETED (hazard class: files that crash the
   toolchain must not sit in the tree).

2. Native probe (tools/netclass_apply_pcbnew.py, API-discovered via
   guarded dir() probes): pcbnew.NETCLASS objects built (guard caught
   that SynchronizeNetsAndNetClasses requires aResetTrackAndViaSizes —
   passed False), board.GetNetClasses() map insertion, 45/45 nets
   assigned via NETINFO_ITEM.SetNetClass, SaveBoard →
   out/route/tile_gw1nz_rules.kicad_pcb + .kicad_pro; in-memory census
   printed: Default/0.2/0.2, 5 signal classes 0.2/0.2, power 0.5/0.2,
   via 0.6/0.3 everywhere. ExportSpecctraDSN in-process SUCCEEDS (no
   segfault with real objects).

3. Format archaeology (the answer to "where do classes live in KiCad
   10"): the KiCad-written pcb contains ZERO net_class blocks (pads
   reference nets name-only `(net "VCC")`); the companion
   tile_gw1nz_rules.kicad_pro carries `net_settings.classes` — but
   SaveBoard persisted ONLY the Default class (my 6 in-memory classes
   did not reach the project settings), and the exported DSN still
   lists all 45 nets under `(class kicad_default ...)` at 200/200 um.
   CONCLUSION: per-class rules do not surface into the DSN from KiCad
   state in this build.

4. Resolution = DSN-level injection: NEW `tools/dsn_class_split.py`
   rewrites the single kicad_default block of the pristine-board
   tile_gw1nz.dsn into the 6 Specctra class blocks (power=500/200 um,
   others 200/200, use_via preserved) → out/route/
   tile_gw1nz_classes.dsn. Runs PASS with: inverse-diff byte-identity
   (only the class-block span changes), class-net union == 45 network
   nets, rule inventory check, vacuity control. →
   out/route/dsn_class_split.json.

5. Verifier hardening: dsn_check.py gained (a) optional pcb/dsn/report
   path args (defaults unchanged), (b) a DSN class-block inventory
   (parse (class NAME nets (circuit)(rule ...))), (c) pcb pad net-refs
   accepting both numbered and name-only forms. Re-runs (guarded):
   canonical copy DSN PASS (kicad_default 45/200/200); the split
   classes.dsn PASS vs the pristine pcb: 45==45 nets, 144 pins,
   boundary, 6 classes with exact memberships (edge_critical 6,
   level_out 4, channel_in 9, keys 12, power 4, config 10). →
   out/route/{dsn_check_rules,dsn_check_classes}.json.

6. docs/routing_plan.md updated: "Router I/O path" bullet now records
   the full negative-result chain + the splitter approach; the fanout
   order phase-A points at the empirical chain; leftover open item for
   the container run: confirm freerouting honours DSN class rule
   sections. Design artifact pcb untouched (sha256[:12] c7d5b66fa1db
   verified post-run); bench/quote/vendor gates unchanged (hardware/
   account gated).

**Next session seed:** draft the SMD-fanout dry-run skeleton (FPGA-02
phase-B prereq): tools/fanout_prep.py computing per-power-net stub/via
positions OFF the measured geometry (power pads U1/U2/C1-C9/FB1 + socket
VCC pads), emitting a machine-checked stub list (docs/fanout_prep.json)
with clearance self-checks against the routing_geo obstacle model — no
copper written.

## Session 10 — overnight batch 006 (2026-10-15 22:55-23:30 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

**Recorded-next-step item executed: tools/fanout_prep.py (FPGA-02
phase-B dry-run fanout plan) → docs/fanout_prep.json. No copper
written.**

- Model: 4 orthogonal candidates per SMD power pad × {via ring 0.5,
  via ring 0.9, 0.6 mm surface stub}, envelope = stub+via AABB,
  obstacles = pads/holes (NPTH +0.15 annulus) from the routing_geo
  parse, greedy cross-net-aware placement (placed fans become
  obstacles), 0.2 clearance, edge rule 0.6 measured via-corner to the
  TRUE stepped Edge.Cuts polygon (12 gr_lines chained; 13-pt closed
  polygon, bbox matches the board dims; signed-area sanity consistent
  with the rib cutouts), inside-outline probes. Greedy development
  history kept honest: first run found a REAL QFN-0.4-pitch via clash
  (U1-36/U1-37 sister vias, -0.388) which motivated adding the
  surface-stub + ring-stagger candidate set.
- Result on r6: 58 power pads, 6 anchors (QFN EP pad 49 per the batch-4
  decision, JP contact pads), 52 pads planned, 0 conflicts, 0 cross-net
  collisions; chosen plan is via-free (surface stubs suffice at
  0.2/0.2), via feasibility ALSO recorded per pad: 46/52 have a
  feasible direct-via candidate; the 6 fourL via-attach blockers are
  U1-2, U1-26 (GND), U1-37 (VCC1V2), C4-2, C5-2 (VCC1V2), C8-2 (GND) —
  exactly the pads near the batch-4 pinch zones (SW6 tooling hole,
  U2/FB1 cluster, QFN west corner). Worst compliant margins recorded
  (several pads at exactly 0.2: tight but rule-compliant).
- Self-checks: plan-vs-plan pairwise fan-envelope check; vacuity
  control (corrupted fan box strictly reduces clearance) passes;
  determinism proven (two reruns byte-identical, sha256[:16]
  0dc19412c6f8ff5c); all runs guarded (fanout_prep via resource_guard,
  2048 MiB); design pcb untouched (sha256[:12] c7d5b66fa1db).
- docs/routing_plan.md phase-B text updated to consume the JSON.

**Next session seed:** pre-routing length/loading budget
(FPGA-01 evidence for FPGA-02 termination scoping): machine-derive
per-net Manhattan/span length estimates from placements for the 45
nets (endpoint bbox spans + netclass), emit docs/length_budget.json
cross-checked against the DSN pin census — feeds the B2 edge-class
(T_clk/L_latch/B_data) route-length discipline before any copper.

## Session 11 — overnight batch 007 (2026-10-15 23:03-23:20 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

**Recorded-next-step item executed: tools/length_budget.py →
docs/length_budget.json (pre-routing length/loading budget; no copper).**

- Per-net metrics (r6 pcb): Manhattan MST over pin centres (routing
  lower bound), bbox span/HPWL, pin-pair Manhattan diameter, net class,
  series-resistor id for the R7-R11 boundary twins (*-DRV + plain twin
  share the R ref by construction). Independent cross-checks: DSN pin
  census parity vs out/route/tile_gw1nz.dsn (45 nets, pins) PASS; class
  coverage PASS; vacuity control PASS (K1 MST moves under a +5 mm pad
  perturbation).
- Decisive numbers: DRV-side stubs 5-11 mm (R7 T_clk / R8 L_clk /
  R9 L_latch / R10 B_data / R11 B_W); contact-band legs: T_clk 23.8,
  L_clk 19.2, L_latch 51.1 (longest edge-critical; the routing_plan
  geometry section's "25-35 mm" estimate was light -- L_latch's JP pad
  sits at the band far end), B_W 30.7, B_data 26.9. Per-class mst_max:
  edge_critical 51.1 / channel_in 48.5 (R_latch) / keys 64.3 (K4) /
  config 34.3 / level_out 30.7 / power 229.7 (feed net).
- Guarded run PASS (one RUST-ACTIVE admission hold (~2 min, cargo
  observed) before admission: the guard behaved as designed; an earlier
  same-minute orchestration hiccup (piped output loss, missing report
  read-back) was re-run cleanly and verified on disk).
- docs/routing_plan.md gained a "Length/loading budget" section folding
  these numbers into the fanout discipline. Design pcb untouched
  (sha256[:12] c7d5b66fa1db).

**Next session seed:** draft tools/ses_import_check.py (FPGA-02 phase-C
prereq): a pcbnew-free pure-Python SES-file parser+verifier for the
freerouting output contract (parse (routes ...) of the discrete project's
existing *.ses fixture offline, assert what fields the re-import path
must see: net names == DSN netnames, via names resolvable, resolution
identity), so the eventual ImportSpecctraSES step has an independent
sanity gate before touching pcbnew.

## Session 12 — overnight batch 008 (2026-10-15 23:10-23:35 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

**Recorded-next-step item executed: tools/ses_import_check.py
(pcbnew-free SES return-path gate) characterized on the in-tree
discrete fixture pair (tile_variant_a_4l.dsn + .ses).**

- Development caught REAL round-trip contract traps (the point of the
  fixture-first approach):
  1. Router-returned net names are QUOTED and can be CASE-FOLDED
     ("B_W_drv" vs DSN B_W_DRV) — net-name drift recorded per-net
     (name_drift_report_only), import-time repair flagged, since KiCad
     net names are case-sensitive;
  2. multiline (path ...) point lists (parser fix);
  3. ROUND-TRIP FRAME: freerouting SES numbers are 0.1-um resolution
     integers while the KiCad DSN boundary reads raw um — coordinates
     divide by the declared resolution before boundary containment;
  4. boundary parity gotcha: (path pcb CLEAR pairs ...) leading
     clearance scalar shifts naive even/odd coordinate slicing (swapped
     the bbox axes in the first parser).
- Final gate checks S1-S7 PASS on the fixture pair (resolution
  declarations; subset-of-DSN routed nets with drift reporting; via
  padstack resolution vs the DSN via table; layer subset F.Cu/B.Cu;
  width inventory 1500/2000/2500 -> 0.15/0.2/0.25 mm; boundary
  containment over 1390 points; S2f --full mode PROVEN to fire on the
  fixture's incomplete 46/52 routes; vacuity control). Reports:
  out/route/ses_fixture_check[_full].json. All runs guarded (2048 MiB).
- Note recorded for our own future run: under --full the eventual tile
  SES must show 45/45 complete routes before pcbnew.ImportSpecctraSES
  is invoked (LEDGER pitfalls list applies to the import script).
  routing_plan.md "Router I/O path" updated with the gate + contract.
- Operator-honesty footgun recorded: shell pipelines `... | tail; echo
  $rc?` masked the checker's exit code earlier (kept $? of tail) —
  this batch's commands were re-run unpiped for the record; pcb
  untouched (sha256[:12] c7d5b66fa1db).

**Next session seed:** freerouting availability sweep (read-only: java
-version, freerouting jar/container presence per downstream-preparation
notes) and, IF present, a PREPARATION-ONLY headless dry run on the
batch-5 classes.dsn producing out/route/tile_gw1nz.ses gated by
ses_import_check --full (45/45) — evidence of whether 2L closes at
0.2/0.2, explicitly not an import/adoption step; if freerouting is
absent, record the exact blockage.

## Session 13 — overnight batch 009 (2026-10-15 23:15-23:35 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

**Recorded-next-step item executed: freerouting availability sweep +
preparation-only headless dry run. Sweep: host java NOT installed;
localhost/freerouting:2.4.1 container image PRESENT (podman+docker
lists; built per tools/containers/freerouting/Containerfile, which I
read-only reviewed); LEDGER documents the prod invocation line
(production/panel revb_pipeline.sh: podman --userns=keep-id, -de/-do,
-mp 40, --gui.enabled=false). NOT an import or adoption step: no
copper, no pcb mutation, design artifact c7d5b66fa1db verified.**

- The resource_guard correctly REQUIRED container-side limits for
  delegation (first attempt refused with guidance) — rerun with
  --memory 2g --memory-swap 2g --cpus 2 --pids-limit 256, under a
  rg-*.scope too, deadline-capped. Log evidence: router completed in
  519.22 s, peak heap 249.8 MB, state COMPLETED; wrote
  out/route/tile_gw1nz.ses (22,333 bytes).
- DRY-RUN RESULT (2L, strict 0.2/0.2 + 6 class blocks from batch-5
  classes.dsn): 99 connection items total; AUTOROUTER DONE with 0
  violations but 53 items unconnected after optimization stopped
  (improvement < 1% threshold). Net level: 25/45 nets carry wire;
  widths {2000,3750,5000}/res10 = {0.2,0.375,0.5} mm — the power class
  ran at 0.5 mm, proving the batch-5 class blocks were honored.
- ses_import_check (batch-8 gate) against the same classes.dsn: subset
  PASS (out/route/ses_tile_check.json); --full FAILS as designed
  (out/route/ses_tile_check_full.json) with the open-net list:
  B_W_DRV B_data_DRV B_first B_latch JTAGSEL_N JTAG_TDI JTAG_TDO
  JTAG_TMS K2 K3 K6 K10 L_latch_DRV MODE0 MODE1 R_latch T_W T_clk_DRV
  T_data T_endcol. Router-reported open items include VCC1V2
  U1-12→C4-1, U1-37→C5-1 and SW10-1→SW11-1 — the exact corridors
  predicted tight by routing_geo (batch 4) and fanout_prep (batch 6).
- FEASIBILITY FINDING (prep evidence, not a routing decision): 2L does
  not close by router alone under the strict rules; the phase-B manual
  SMD/power fanout (stubs+pours, fanout_prep.json) is a material
  prerequisite before a closing attempt; 4L stays the comparison arm.
  routing_plan.md records the numbers + the artifact pointers.

**Next session seed:** draft tools/fanout_apply_probe.py — apply
fanout_prep.json's stub/via plan onto a COPY pcb via pcbnew
(SaveBoard), then re-export DSN from the copy and rerun the dry run to
measure the delta (items routed with deterministic fanout vs without).
Preparation-only; nothing enters the design artifact.

## Session 14 — overnight batch 010 (2026-10-15 23:27-23:50 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

**Recorded-next-step item executed: tools/fanout_apply_probe.py drafted and
run; two-arm router comparison measured. Preparation-only throughout:
design artifact c7d5b66fa1db verified unchanged at batch start and end;
all probe outputs confined to fpga/board/out/route/.**

- tools/fanout_apply_probe.py (new): flatpak pcbnew loads the r6 pcb
  READ-ONLY, applies all 52 planned batch-6 fanout pads as 0.2 mm copper
  stubs on their pad layer (via-free 2L plan => 52 tracks, 0 vias), net
  codes resolved via NetsByName, BuildConnectivity, SaveBoard to
  out/route/tile_gw1nz_fanout_probe.kicad_pcb (COPY only).
  FANOUT_APPLY OK: tracks=52 vias=0.
- export_dsn.py parametrized earlier (argv) exported the probe copy
  (EXPORT_DSN_OK: 45 nets, 65 footprints, 210 pads, 52 tracks, 41649
  bytes); dsn_class_split.py parametrized this batch (optional argv
  src/out/report, defaults unchanged) -> tile_gw1nz_fanout_classes.dsn,
  6-class table identical, union==45 nets, inverse diff identity True.
- ROUTER ARM 2 (guard-capped, container limits as batch 9, -mp 40
  headless): freerouting COMPLETED in 926.4 s wall; 71 unrouted
  connection items, 0 violations; net level 28/45 nets carry wire;
  widths {2000,3000,3750,5000}/res10. ses_import_check subset PASS,
  --full FAILS as designed (open list first 5: B_W, B_W_DRV, B_clk,
  B_data, B_data_DRV).
- MEASURED COMPARISON (strict 0.2/0.2 + 6 class blocks, same router,
  same flags): bare classes.dsn arm = 46/99 items, 25/45 nets (batch
  9); dead-end-stub arm = 28/99 items, 28/45 nets. DEAD-END 2L STUBS
  HURT: the router honors pre-routes as fixed, so stubs that terminate
  mid-air pre-block escape directions instead of helping. This
  refines, not contradicts, the batch-9 finding: copper helpers fed to
  the router must be COMPLETE attachments (stub+via into a plane/pour,
  i.e. the LEDGER-proven 4L SMD-to-plane via attach as on the discrete
  build); on 2L the router phase should run stub-free with any helper
  copper added as manual finishing afterwards. routing_plan.md
  conclusion rewritten to record both arms and the consequence.
- Guard behavior: all heavy steps (pcbnew apply, dsn export, class
  split, router, gates) serialized through resource_guard with
  deadline caps; container delegation accepted only with
  --memory/--memory-swap/--cpus/--pids-limit. No leftover container or
  java processes at batch end (pgrep checks).

**Next session seed:** light task — write tools/route_report.py that
parses a freerouting stdout log (kept via tee in future runs) plus the
SES into docs/route_arms.json summarizing wall time, items routed,
per-net open lists, and width inventory for both recorded arms
(bare vs dead-end-stub), so later arms (manual-finish, 4L) drop into
one comparison table; optionally: generate a 4L rules DSN probe input
(stack 4-layer with GND/VCC planes declared in the DSN structure
section) for a hypothetical arm-3 measurement, still preparation-only.

## Session 15 — overnight batch 011 (2026-10-15 23:46 - 2026-10-16 00:20 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

**Recorded-next-step item executed: tools/route_report.py built +
docs/route_arms.json now holds one auditable three-arm comparison; the
OPTIONAL arm-3 probe (4L planes) was also executed end-to-end with a
teed log. All preparation-only; pcb artifact stayed c7d5b66fa1db.**

- tools/route_report.py (new, regression-guard style): recomputes from
  artifacts on disk (DSN pins->items, SES wires/widths/layers, sha256),
  keeps unpersisted-log numbers (wall s, items routed/unrouted) in an
  explicitly-sourced provenance block, and FAILS if invariants break
  (items conservation incl. plane-absorbed items, canonical arm
  census). Caught one real defect in its own comparison labels during
  bring-up (gained/lost swap) — fixed and canon-pinned.
- docs/route_arms.json (three arms, all 99 items, 45 nets):
  bare 46/99 25n | dead_end_stubs 28/99 28n | four_l_planes 17/79 34n
  (+20 items silently absorbed by the GND plane). Deltas vs baseline:
  stubs -18 items (+7/-4 nets), four_l -29 items (+10/-1 nets).
- tools/dsn_4l_probe.py (new): exact 5-point text surgery on
  classes.dsn -> tile_gw1nz_4l.dsn (In1.Cu/In2.Cu power layers, GND
  plane polygon In1, VCC1V2 In2, via padstack Via[0-3]_600:300_um +
  6 class use_via refs). Inverse-undo identity True, nets 45, classes
  6. Mirrors the discrete fixture tile_variant_a_4l.dsn pattern.
- ARM-3 RUN (guard + container caps, -mp 40 headless, LOG TEED to
  out/route/freerouting_4l.log — first persisted router log):
  COMPLETED in 398.0 s wall, 62 unrouted of 79, 0 violations,
  ses_import_check subset PASS / --full fires as designed.
- MEASURED PLANE SEMANTICS (arm-independent router trait): freerouting
  2.4.1 treats DSN (plane ...) as 'exclude net from routing': GND 20
  items absorbed, ZERO inner-layer wires in the SES (layers {F.Cu,
  B.Cu} only), VCC1V2 plane ignored (6 items stayed). No congestion
  relief -> the discrete build's 4L benefit came from pcbnew-side
  PRE-PLACED pad->plane vias, not plane declarations. A real 4L arm
  needs attach vias as fixed pre-routes terminating on plane layers.
- WIDTH AUDIT finding (now per-arm in route_arms.json): router emits
  off-class widths in every SES (bare {3750}, stubs {3000,3750},
  four_l {1500,3000,3750}); 1500 (0.15 mm) is BELOW the strict 0.2 mm
  rule yet scored 0 violations -> any SES adoption needs a widening
  pass (LEDGER fix_routed.py precedent: same freerouting trait on the
  discrete project). Recorded in routing_plan.md.
- Guard behavior nominal all batch (admissions at MemAvailable
  7313-7338 MiB vs the 6144 gate, PSI some avg10 0.00); no leftover
  java/freerouting/podman processes at wrap; STOP file absent.

**Next session seed:** build tools/widen_check.py — a DSN/SES width
fix-audit: enumerate every routed path width per net, map to the
class-table minimum, and emit the widen-list (target >= 0.2 mm) a
fix_routed-style pass would need for each SES arm; optionally quantify
length_budget.json arm data against the actual SES routed-path lengths
for the wired nets (how close routed lengths run to the stub/leg
budgets). Both are pure text analysis on owned artifacts.

## Session 16 — overnight batch 012 (2026-10-16 00:02-00:35 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

**Recorded-next-step item executed: tools/widen_check.py built -> SES
per-path width audit against class minimums + routed-length vs
length_budget comparison. Two bring-up defects of my own found+fixed
(path regex trailing-whitespace before ')', budget key mst_manhattan_mm);
final run clean on all three arms. Pure text audit; pcb untouched
(c7d5b66fa1db).**

- tools/widen_check.py -> docs/widen_report.json: per arm, per net,
  per path: (layer, width, required class width, start, n_points,
  length) for every path below its class rule; absolute 0.2 mm floor
  checked separately; per-net routed length so far vs
  length_budget.json mst_manhattan_mm; LEDGER fix_routed.py precedent
  cited in the report header as the adopting-pass counterpart.
- AUDIT RESULT (widen items): bare 7 (all router's own: power nets
  VCC/GND at 375 vs class 500); dead_end_stubs 63 (55 = MY pre-placed
  200 um stubs on power nets -- knowingly placed at escape width in
  fanout_apply_probe.py, now formally flagged as class violations the
  adopting pass must widen or get excepted; 8 = router's at 375);
  four_l_planes 9 (router's at 375/300) + 1 SUB-RULE path: K5 B.Cu at
  150 um vs 200 required -- router narrowed a key net 25% under the
  strict factory rule yet scored 0 violations. NET: no SES arm is
  import-clean under our class table; a widening/repair pass is a
  recorded prerequisite for any SES adoption, exactly the LEDGER
  discrete precedent.
- LENGTH AUDIT (partial routes vs Manhattan MST lower bounds):
  worst ratio over budget: bare CFG_RECONFIG 1.096 (27.0 vs 24.7 mm),
  B_W 1.045; stubs arm CFG_RECONFIG 1.096, T_clk 1.076 (edge-critical
  clock, incomplete and already ~8% over budget); 4L arm T_clk 1.028,
  L_latch 0.955. Takeaway: router path-efficiency stays within ~10%
  of the MST lower bound so far, but the edge-critical clock class is
  precisely where the overage lands; the 0.955 on L_latch shows big
  legs are not always the meandering ones.
- Guard admissions nominal (MemAvailable 7328-7334 MiB vs 6144 gate,
  PSI 0); tool wall 0.1 s; no leftover processes; STOP absent.

**Next session seed:** collect the preparation outputs into one
FPGA-02 handoff index -- docs/fpga02_handoff.md: one table pointing at
every preparation artifact + tool produced since batch 002
(netclasses.json, fanout_prep.json, length_budget.json,
routing_geo.json, route_arms.json, widen_report.json, power_reg.md,
readiness.md, quote/) with its acceptance-relevant one-line status;
plus a short 'known traps' section distilled from the checkpoint
(SES width trait, plane semantics, dead-end stub trap, class-table
persistence path, quoted/case-folded net names). Documentation-only;
no new measurements.

## Session 17 — overnight batch 013 (2026-10-16 00:06-00:45 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

**Recorded-next-step item executed: docs/fpga02_handoff.md written and
cross-verified against its data sources. Documentation-only batch; no
measurements rerun, pcb c7d5b66fa1db untouched.**

- docs/fpga02_handoff.md (new): five sections — (1) preparation
  artifact index w/ one-line statuses (power_reg, netclasses,
  routing_geo, routing_plan, fanout_prep, length_budget, route_arms,
  widen_report, quote/, readiness); (2) router I/O chain: guard
  baselines + night-built tools with role lines + derived out/route/
  artifact map; (3) 3-arm autorouter measurement table + open
  decisions (manual finish after bare arm + widen pass / 4L arm with
  pre-placed attach vias pending 6 fourL blockers / fully interactive
  with measured data); (4) ten distilled known traps T1-T10
  (class persistence path, pcbnew class-text segfault hazard,
  off-class/sub-rule width trait, plane=exclude semantics, dead-end
  stub trap, SES round-trip frame quirks, guard delegation flags,
  shell footguns x2, courtyard over-estimate, post-adoption
  attach+widen+DRC order); (5) non-worker blockers recorded AS
  blockers (quote upload login; B1/B1b/B2/B3 bench; Gowin vendor
  flow; termination decision pending B2; JP-band 1.3 mm info-only /
  true stepped-edge distance = GK recheck).
- Verification of every number cited in the doc against the JSON
  sources (route_arms.json arms/deltas, widen_report 7/63/9 + 1
  sub-rule, routing_geo fields): matched except routing_geo's U1-SW6
  pinch which the JSON stores as obstacle_gap=0.37 mm (not 0.375 as my
  earlier session summaries rounded) — doc records 0.37 mm.
- No guard-needed work this batch (pure doc); STOP absent; no leftover
  processes.

**Next session seed:** two candidate light items, pick either:
(a) close the widen-loop evidence by drafting tools/widen_apply_probe.py /
     or extend widen_check.py into an APPLY-side plan — a pcbnew-COPY
     pass that widens the widen_report paths to class minima and
     re-checks, still artifact COPY only; (b) consolidate FPGA-01
     electrical sticky items into docs/readiness.md deltas annotation:
     verify which recorded FPGA-01 open items the night evidence
     actually shifts (EP decision analysis, decoupling closure,
     JP-band recheck info) and mark the rest explicitly untouched.

## Session 18 — overnight batch 014 (2026-10-16 00:10-00:40 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

**Recorded-next-step item executed (option a, adapted to the actual
fact that SES paths exist in no pcb yet): tools/widen_apply_probe.py —
TEXT-LEVEL SES repair candidate + geometry conflict check. Widen loop
now closed end-to-end: audit (b12) -> repair (b14) -> re-audit clean
(b14), all on copies; pcb c7d5b66fa1db untouched.**

- Why text-level: a pcbnew-side widen needs the SES imported first
  (import is an adoption step, out of scope); fix_routed.py philosophy
  applied at SES frame instead. dead_end_stubs arm deliberately
  SKIPPED: 55 of its widen items are OUR OWN 0.2 mm escape stubs
  (documented decision in fanout_apply_probe.py), not router defects.
- tools/widen_apply_probe.py -> docs/widen_apply_report.json +
  out/route/tile_gw1nz_widened.ses + tile_gw1nz_4l_widened.ses:
  bare 7 widths raised (GND 2, VCC 5; 375->500 um); four_l 9 raised
  (GND 4, VCC 4, K5 150->200). Offset-scoped inverse identity PASS
  (undo reproduces source bytes; only width tokens edited).
- GEOMETRY SELF-CHECK (same-layer cross-net segment distances vs
  (w1+w2)/2+0.2 mm): 0 conflicts on BOTH widened arms; checker proven
  non-vacuous by margin census: tightest positive slack bare 0.053 mm
  (GND vs VCC1V2_RAW, B.Cu, gap 0.753 vs need 0.700), 4L 0.063 mm
  (VCC vs VCC1V2_RAW, F.Cu). Limits recorded: pad/via keepouts not
  modeled (near-pad false positives possible), not a DRC substitute.
- RE-AUDIT of widened files: ses_import_check subset PASS both
  (unchanged coverage 25/45, 34/45); width inventories are now EXACTLY
  the class table {2000, 5000}; widen_check-core recount 0 below-class
  paths both. The freerouting width trait is repairable in-place for
  these two arms, cheaply — strengthens the feasibility of the
  'manual finish around bare arm' option in fpga02_handoff.md §3.
- Guard admissions nominal (MemAvailable 7613 MiB); wall 0.3 s; no
  leftover processes; STOP absent.

**Next session seed:** tools/integrity_check.py — one-command trust
anchor: rerun/assert every derived-evidence invariant of the campaign
in a single report (pcb sha c7d5b66fa1db; dsn_class_split inverse
identity on both splits; dsn_4l_probe inverse identity; route_arms
canon triplets; widen_report sub-rule census; widen_apply inverse
identities + widened SES re-audit zero-below-class; fixture SES gate
still 46/52 with --full firing) -> docs/overnight_integrity.json;
pure orchestration of existing tools, no new measurements.

## Session 19 — overnight batch 015 (2026-10-16 00:14-00:25 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

**Recorded-next-step item executed: tools/integrity_check.py — the
campaign's one-command trust anchor. INTEGRITY PASS 14/14
(docs/overnight_integrity.json). Two own bring-up defects found+fixed
(subprocess cwd vs tools/-relative cmd paths; REPO depth 3->5; session
threshold 17->18). pcb c7d5b66fa1db untouched.**

- Checks (all OK): pcb hash anchor; route_arms.json artifact hashes vs
  files; six deterministic reruns byte-identical (route_report,
  widen_check, widen_apply_probe + its two widened SES outputs,
  dsn_4l_probe, dsn_class_split default AND fanout invocations) —
  catches both nondeterminism and silent input drift; SES gate
  behavior: bare/bare_widened/4l_widened subset PASS x3, discrete
  fixture subset PASS at 46/52, fixture --full FAILS as designed
  (rc=1); checkpoint completeness (>=18 session headers).
- Wall 0.6 s for the whole anchor; guard admissions nominal
  (MemAvailable 7563-7568 MiB, PSI 0); no leftover processes.

**Next session seed:** router-variance replicate — a second bare-arm
guarded run (tile_gw1nz_classes.dsn -> tile_gw1nz_rep2.ses, LOG TEED
to freerouting_rep2.log), then register arm bare_rep2 in
route_report.py (canon tolerance: report actual; assert items
conservation + 0 violations only) and record items-routed delta vs
46/99. Rationale: the 46/99 feasibility number currently rests on a
single router run; freerouting pass trajectories re-randomize (board
hashes differed between passes), so a replicate shows whether 46/99
is tight or a spread. If variance is large, the 2L/4L decision
weight on these arms drops accordingly — recorded, not waived.

## Session 20 — overnight batch 016 (2026-10-16 00:17-00:42 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

**Recorded-next-step item executed: router-variance replicate.
RESULT: ZERO VARIANCE — freerouting 2.4.1 is byte-deterministic for
this input/flags. Registered as arm bare_rep2; route_arms.json now
4 arms; integrity anchor re-PASSes 14/14. pcb c7d5b66fa1db.**

- Guarded rerun (same classes.dsn, -mp 40 headless, container caps,
  LOG TEED to out/route/freerouting_rep2.log): COMPLETED, wall 608.7 s,
  identical score trajectory (autoroute final 464.64 / 53 unrouted /
  0 violations; optimizer 454.54 / 54). OUTPUT SES sha256 ==
  fa54ef9b0920.. == the batch-9 bare output BYTE-IDENTICAL.
  Consequence: the 46/99 feasibility number is EXACT for this
  router/input, not an RNG sample; remaining uncertainty is input and
  flag sensitivity. ses_import_check subset PASS on rep2 (25/45, as
  expected from identical bytes).
- NEW sharp datum mined from the teed logs: freerouting's own FANOUT
  STAGE escaped only 115/144 SMD pins (79.9%) on the 2L bare input —
  and 114/144 (79.2%) on the 4L input: the SMD attach bottleneck is
  internal, quantified, and NOT relieved by the 4L plane arm. This is
  the crispest single number for the 2L feasibility story.
- route_report.py: arm bare_rep2 registered (canon (99,25,20)),
  finding records determinism + fanout-escape stats; one own edit
  defect during registration (stray desc line) repaired in-file.
  ROUTE_REPORT OK arms=4, invariants hold; fpga02_handoff.md arm table
  updated with determinism + escape facts.
- Guard note: ~85 s of admission PENDING mid-batch while host
  MemAvailable sagged 7.6->4.4 GiB (foreign spike), guard held and
  admitted at 6542 MiB when it recovered — no denial, no retry-spin on
  my side (the pending loop is the guard's own, within policy).
- Integrity anchor rerun AFTER the arm registration: INTEGRITY PASS
  14/14, docs/overnight_integrity.json refreshed.

**Next session seed:** close the loop on the fanout-escape datum:
parse both teed router logs into a per-stage table (fanout escapes,
autoroute trajectory, optimizer stop) inside route_arms.json
provenance (log files now exist for arms 4L + rep2; arms 1-2 keep
checkpoint-transcribed provenance) — i.e. make route_report.py parse
log files automatically when a provenance['log'] path is present,
guarded by asserting parsed numbers match the transcribed constants
for rep2/4L. Light tool work, no new measurements.

## Session 21 — overnight batch 017 (2026-10-16 00:31-00:50 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

**Recorded-next-step item executed: route_report.py now parses teed
router logs (provenance.log) into a per-stage table with consistency
assertions. First assertion version FAILED loudly and taught us
something real. pcb c7d5b66fa1db untouched.**

- Stages parsed per logged arm (fanout / autoroute start-line +
  completed-line / optimizer / job elapsed+state / peak heap).
  bare_rep2: fanout 115/144 (79.9%), autoroute 99->53, optimizer
  54->54, job COMPLETED 605.44 s; four_l: fanout 114/144 (79.2%),
  autoroute RECOUNT 101->60, optimizer 62->62, job 394.53 s.
- ROUTER RECOUNT NOISE discovered by the failed strict assertions:
  freerouting's own stage counters disagree with each other (4L
  start-line 79 vs completed-line recount 101; autoroute-final 60 vs
  optimizer-final 62; bare autoroute 53 vs optimizer 54). The SES
  remains ground truth; the transcribed provenance stays the census
  anchor (it alone passes items-conservation). Consistency assertions
  finalized to: within +/-2 of provenance on both stage finals,
  violations==0 everywhere, job state==COMPLETED, fanout SMD total
  ==144; per-arm recount_noise_items recorded in the table (1 and 2).
- ROUTE_REPORT OK arms=4 with stages; integrity anchor refreshed:
  INTEGRITY PASS 14/14.

**Next session seed:** annotate docs/readiness.md (queued from batch
13): mark which recorded FPGA-01 open items the night's evidence
actually shifts (EP decision analysis supports the no-thermal-via
placement as-routed; corridor pinch numbers support U1-north escape
being the binding constraint; JP-band stays info-only pending GK
stepped-edge recheck) and explicitly mark everything untouched by the
night (bench/quote/vendor). Documentation-only, no new measurements.

## Session 22 — overnight batch 018 (2026-10-16 00:35-00:48 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

**Recorded-next-step item executed: docs/readiness.md annotated with a
scoped 'Overnight evidence deltas' section appended after the ledger
(no existing entries edited). Documentation-only; pcb c7d5b66fa1db.**

- SHIFTS recorded with evidence pointers: routing gap now quantified
  (corridors 2.883/0.37 mm; deterministic 46/99 + 0 viol; fanout
  escape 79.9%; stub arm worse; plane-declaration trap; widen-pass
  prerequisite proven) while the 0-tracks state itself stands;
  EP thermal ESTIMATE now exists (power_reg.md: no via-in-EP at
  ~50-60 mW, ring deferred to FPGA-02); quote package prepared while
  account/upload blocker stands; JP-band info-only vs GK stepped-edge
  recheck.
- Explicitly-untouched list recorded in-file: bench B1/B1b/B2/B3,
  termination-decision status, Gowin vendor flow, system timing,
  presence host-side sign-off, silkscreen corpus, UP5K LAND-TBD,
  quote account/upload. No silent waivers anywhere in the section.

**Next session seed:** compile a one-page EVENING-MORNING synthesis
into the checkpoint tail itself (session 23): an executive summary
block 'CAMPAIGN RESULT' pinned at 10-12 lines — the ordered-register
status line per FPGA-01..04, the single number per major finding
(46/99 exact; 79.9% escape; 0 conflicts widen; 17/79 plane trap;
byte-identical variance), and the three unblocked follow-ons
(readiness/fabrication-facing: quote upload, bench plan, 4L attach
attempt owner decision) — so the plan owner reads ONE block, not 21
sessions. Documentation-only.

## Session 23 — overnight batch 019: CAMPAIGN RESULT (executive block; plandetails sessions 2-22 + docs/fpga02_handoff.md; trust anchor integrity_check.py PASS 14/14)

**REGISTER**: FPGA-01 IN PROGRESS (placement-prototype gate-clean,
unrouted by design; pcb c7d5b66fa1db all night, 65 parts/45 nets).
FPGA-02 PENDING and de-risked by this campaign's measured preparation.
FPGA-03, FPGA-04 PENDING, untouched tonight (no evidence produced).

**FEASIBILITY NUMBER**: freerouting 2.4.1 closes 46/99 connection
items on the strict-2L 6-class table, 0 violations — EXACT, not a
sample: byte-identical SES on a variance replicate (deterministic).
**BOTTLENECK NUMBER**: the router's own SMD fanout escapes only
115/144 pins (79.9%); the attach problem is internal, not rule-driven.
**TRAP NUMBERS**: dead-end pre-stubs drop routability to 28/99; DSN
plane declarations silently absorb GND and attach nothing (17/79);
off-class widths emitted incl. sub-rule 0.15 mm scored 0-violations
(never adopt raw SES).
**REPAIR NUMBER**: text-level widen of both router arms to class
minima is conflict-free (min slack 0.053 mm): adoption path =
import + widen + re-DRC, proven mechanical on copies.
**CORRIDOR NUMBERS**: min in-row 2.883 mm (6 tracks); U1-SW6 pinch
0.37 mm — U1-north escape is the binding constraint.

**FPGA-02 OPEN DECISION (owner)**: (a) manual finish around the bare
arm + widen list; (b) 4L arm with pre-placed attach vias (6
blockers listed in fanout_prep.json); (c) fully interactive routing
on measured data. Inputs ready: netclasses, fanout_prep,
length_budget, routing_geo, route_arms, widen_report, handoff doc.

**UNBLOCKED FOLLOW-ONS (owner-level)**: 1) quote upload (docs/quote/
ready; needs account) ; 2) bench provisioning B1/B1b/B2/B3 (hardware);
3) FPGA-02 kickoff choosing (a)/(b)/(c) — all inputs measured.
**BLOCKERS STANDING (not waived)**: bench hardware, Gowin vendor flow
never run, quote account login, termination decision pending B2,
system timing closure.

## Session 24 — overnight batch 020: 4L ATTACH-VIA probe arm (decisive final measurement) (2026-10-16 00:39-01:20 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015)

Batch-20 executed the recorded next step: the LEDGER-shape 4L arm —
stub+via attach sites terminating into the declared inner planes,
injected at DSN text level into the batch-11 4L splice, plus a guarded
router run. Result: NEGATIVE for adoption, and decisive.

**Tool** `tools/dsn_attach_probe.py` (new, text-level, no pcb access):
reads `out/route/tile_gw1nz_4l.dsn` + `docs/fanout_prep.json`, selects
pads with net in {GND, VCC1V2} and `via_alternative.feasible==True`
(17/23 power pads; the 6 fourL blockers U1-2/U1-26/U1-37/C4-2/C5-2/
C8-2 correctly excluded), recomputes via centers with the SAME
fan_box math as fanout_prep (pad edge + ring {0.5,0.9} along escape
dir), emits per site: B.Cu stub at power-class width 500 um pad-center
-> via-center + `(via "Via[0-3]_600:300_um" x y (net N)(type route))` —
grammar cribbed from the in-tree discrete 4L fixture
(tile_variant_a_4l.dsn lines 1142+). Wrote
`out/route/tile_gw1nz_4l_attach.dsn` + `dsn_4l_attach_report.json`
(ATTACH OK: sites=17 GND=11 VCC1V2=6, nets=45 conserved; 0.2 s,
guard scope rg-749876).

**TWO DISCOVERIES made while building the probe (recorded as handoff
traps T11/T12)**:
1. DSN frame is (x, -y) x1000 of pcb mm (KiCad y-down vs Specctra
   y-up). Measured per-pad against the batch-10 probe DSN stub starts
   (U1-12 mid (10809.7,7600) -> stub (10809.7,-7600) etc). The tool
   asserts the frame per site (tol 0.5 um-units) before writing.
2. The batch-10 probe pcb's 52 stubs landed on F.Cu — pcbnew
   `pad.GetLayer()` reports F_Cu for these B-side SMD pads — so they
   never touched their B.Cu pads. The stub-arm MEASUREMENT stands
   (they were fixed obstacles either way; the 28/99 conclusion is
   about dead-end pre-routes blocking escapes), but they were not the
   intended attached stubs. Any future pcbnew-side fanout placement
   must take the layer from the pad's layer set, not GetLayer().

**Guarded router run** (podman localhost/freerouting:2.4.1, container
caps 2g/2cpu/256pids, `-de tile_gw1nz_4l_attach.dsn -do
tile_gw1nz_4l_attach.ses -mp 40 --gui.enabled=false`, teed log
`out/route/freerouting_4l_attach.log`): COMPLETED in 565.18 s job
(guard wall 570.8 s). Stages: fanout active here —
"144 of 150 SMD pins needing fanout", passes inserted +65/+11/+2/+0/
+2/+0 extra vias; autoroute start line 66 unrouted items (fanout
stage settled ~13 incl. attach items); final 49 unrouted
**19 VIOLATIONS — the ONLY arm with any violations**, held constant
from autoroute pass #1 through optimizer end
(score 477.22, optimizer stopped on <1% threshold).

**Attach fate (measured in the SES)**: 0/17 injected vias survive —
freerouting rips `(type route)` wiring that conflicts with its plans.
The router instead placed 53 of its OWN vias into the planes. SES
gates: ses_import_check subset PASS (29/45 nets wired, 16 open,
layers {F.Cu,B.Cu} as in every arm, widths incl. off-class 1500/3000/
3750 and sub-rule 1500 — same widen-before-adoption rule applies).

**Reading**: more items closed (50/99 vs bare 46/99, and the fanout
escape datum 115/144 = 79.9% matches bare) but the board is strictly
worse for adoption: 19 unresolvable-by-optimizer clearance violations
carried around the injected wide stubs/via ring vs 0 in every other
arm. Conclusion pinned in route_arms.json findings + handoff T11:
DSN-text-level attach injection is counter-productive; attach
sovereignty belongs to the router's own fanout when planes are
declared, or to PCB-side pre-placed vias with fix semantics (the
discrete build's recipe) — never to DSN text.

**Registration**: route_report.py gained arm `four_l_attach_vias`
(canon (99,29,16); items conservation 30r+49u+20a=99; recount noise
+/-2 documented; violation pins made RELATIVE (ar==prov && op==prov)
since this is the first nonzero arm) -> `docs/route_arms.json` arms=5
all-ok. Handoff doc: arm table row added, traps T11/T12 appended; no
existing entries edited. pcb untouched (sha256[:12] c7d5b66fa1db).

**Guard note**: the post-registration integrity_check.py re-run was
admission-DENIED (foreign cargo pid 753500 active; policy-compliant
bounded wait, rc>0) and deferred, not retried in a spin. overnight_
integrity.json therefore remains the 14/14 anchor for the 4-arm state
at its batch-15 run; route_arms.json has since advanced to 5 arms —
re-run integrity_check.py on a quiet machine to refresh the anchor
(first light task of the next batch).

**Register after batch 20**: FPGA-01 IN PROGRESS (electrical design
evidence complete pending owner decision a/b/c from session 23 — the
(b)-arm 4L attach option is now MEASURED NEGATIVE, narrowing the real
choice to (a) manual finish + widen list vs (c) interactive). All
acceptance gates still require bench/quote/vendor evidence. No local
unblocked DSN/SES arm remains with positive expected value: bare 46/99
deterministic is the adoption base; stubs/4L/attach all measured worse.

## Session 25 — overnight batch 021: integrity anchor refresh + widen coverage for arm four_l_attach_vias (2026-10-16 01:16-01:19 CEST, Kimi-K3 worker, ses_fpga_overnight_20261015; short batch: recorded next-step tasks were entirely text-level)

Executed the recorded batch-20 NEXT items. All guard admissions clean
this batch (no Rust contention; MemAvailable ~7.3-7.4 GiB throughout).

**STEP 1 — integrity anchor refresh (was admission-denied in batch
20)**: `tools/integrity_check.py` PASS 14/14 (scope rg-780917, 0.6 s —
the suite is text-level tools + sha256 only, no KiCad CLI). Confirms
on the 5-arm state: pcb hash c7d5b66fa1db unchanged; arm artifact
hashes tie; `rerun_route_report identical=True` (the 5-arm
route_arms.json is byte-stable/deterministic); all gates incl.
fixture expected-fail fire as designed. overnight_integrity.json now
describes the current state again; the batch-20 staleness caveat is
closed.

**STEP 2 — widen coverage extended to arm four_l_attach_vias**
(widen_check.py + widen_apply_probe.py ARMS lists; the integrity
suite itself deliberately left untouched so "14/14" keeps one frozen
meaning; the new arm's results are recorded here and in docs):
- widen_check: 115 wire paths audited; **12 below-class widen items
  (worst arm)** — GND 4 + VCC 6 router-made power stubs down at
  375/300 um vs 500 class minimum; L_clk 1 + L_clk_DRV 1 at
  **150 um sub-rule** (2nd arm carrying sub-rule widths after K5);
  routed-length/MST budget worst overage **1.132** (all-night worst;
  bare 1.096). -> docs/widen_report.json now 4 arms.
- widen_apply (text-level raises to class minima on a copy):
  **raised=12, geometry conflicts=0** -> new artifact
  out/route/tile_gw1nz_4l_attach_widened.ses +
  widen_apply_report.json 3 arms.
- Gate of the widened SES (ses_import_check subset vs
  tile_gw1nz_4l_attach.dsn): **SES_IMPORT_CHECK OK** — 29/45 nets,
  layers {B.Cu,F.Cu}, 382 points, **widths inventory now clean
  [2000, 5000]** (off-class 375/300/150 all repaired).
  NOTE: this repairs WIDTHS only; the arm's 19 clearance
  violations from the router are untouched and remain the arm's
  disqualifier vs adoption (batch-20 conclusion stands).

**STEP 3 — anchor re-verified after the tool edits**: second
integrity_check run PASS 14/14 (scope rg-782026; all rerun-identical
checks byte-stable, incl. widen_check/widen_apply on their new 4/3-arm
outputs). Handoff artifact-table row for widen_report.json updated
(7/63/9 -> 7/63/9/12, sub-rule note, budget worst 1.096 -> 1.132); no
other handoff entries touched.

**Register after batch 21**: unchanged from session 24 — FPGA-01 IN
PROGRESS pending owner decision; 4L attach option measured negative;
adoption base = bare 46/99 + widen list (or interactive). The widen
mechanics are now proven conflict-free on ALL router outputs produced
tonight (3/3 arms repair clean), which hardens the
import+widen+re-DRC adoption path as the campaign's closing
engineering datum. No new arm is worth running: the remaining open
items are owner/bench/quote/vendor, not DSN/SES experiments.
