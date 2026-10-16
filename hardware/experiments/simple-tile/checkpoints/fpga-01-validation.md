# FPGA-01 — independent validation checkpoint (2026-10-15 afternoon, CERN Kimi validator)

Scope: validate the actual current state of the FPGA-01 electrical artifacts after
the session-5b batch. Owns ONLY this file. No design/generator/checker/doc source
was modified; no canonical artifacts were edited; no board regen, synthesis or
heavy job was run. Read-only inspections plus in-memory negative-control probes
using the shipped checker functions. Fresh canonical re-runs were attempted four
times through `tools/resource_guard.py` and were **admission-blocked** (recorded
below); the canonical reports therefore carry the 2026-10-15 10:55-10:56 session-5b
timestamps, and their contents were re-verified directly against sources here.

User authorization for this validation supersedes the expired 12:10 batch
deadline; this session was bounded (~12:27-13:05, no overnight job). Guard
deadlines used: `RESOURCE_GUARD_DEADLINE=2026-10-15T13:00/13:05/13:08+02:00`,
min-avail default **6144 MiB**, caps MemoryMax=2048M / CPUQuota=100% (guard defaults).

## 1. Recovery / provenance verdict (the orchestrator's 12:26 concern)

`/tmp/opencode/fpga01-regen-r6.log` (mtime 10:55:33) ends at step 3/5 with
`SCH0 self-check: FAIL` (stale expected census 40 vs real 45) — that log alone
reads as a failed batch. **It is stale.** The follow-up
`/tmp/opencode/fpga01-regen-r6b.log` (mtime 10:56:47), started after the SCH0 fix,
completed all remaining steps with exit 0 everywhere:

- `SCH0 self-check: PASS` (census 45 nets incl. the five `*_DRV` stubs);
- `SCHEMATIC_CHECK: PASS (S1-S7)` — S1 ERC 0 violations fresh, S3 45/45,
  S4 144==144 pads, S5 26/26, S6 MATCH, S7 3/3 controls fired;
- DRC gw1nz: "Found 107 violations, 99 unconnected items" (all warnings, §4);
- DRC up5k: 90 / 88 (untouched-variant control);
- final line `R6-B BATTERY DONE`.

Artifact mtimes form one coherent session-5b chain: pcb 10:47:06 (r6 step 1),
netcheck_report 10:55:32 (r6 step 2), sch/sym/sch_summary 10:56:34 (r6b step 3),
erc 10:56:37 + net 10:56:38 (r6b step 4), drc.json 10:56:43 (r6b step 5).
No other writer touched the tree afterwards (hashes in §6 taken 12:30-12:50 match
the 10:56 artifacts; `git status` shows only the documented 5b diff set).
A/B drive evidence also re-verified at 12:38: `out/pnr/tmp/ab_A.fs == ab_B.fs ==
rtl_ab/fs_A.fs == 3918ac9c77dec30f…737fe`; `rtl_ab/fs_B.fs = 2f43b717911e…` —
exactly as checkpointed.

## 2. Independent re-derivation against raw artifacts (validator's own parses)

All performed read-only at 12:31-12:47 against the actual text of the canonical
files (not via the contained reports):

- **Five series split nodes exact** (`.kicad_pcb` parse): for each of
  T_clk/L_clk/L_latch/B_data/B_W: `U1.<35/19/31/30/27>=<net>_DRV`,
  `R<n>.1=<net>_DRV`, `R<n>.2=<net>`, `JP_<net>.1=<net>` — all five match N10's
  table literally.
- **Resistor placement/values**: R7..R11 all `Value=0R`, all on **B.Cu**, at
  (-0.09,3.10)/(12.41,14.10)/(-0.09,4.45)/(-0.09,5.85)/(0.91,10.80) — matches the
  r6 log. U1 GW1NZ-LV1QN48C6/I5 on B.Cu; U2 TLV75512PDBVR on B.Cu.
- **Supply pins**: U1.1/25/36=VCC, U1.12/37=VCC1V2, U1.2/26/49=GND (49=EPAD).
  Verified against `data/pins_gw1nz_qn48.json` roles (1=VCCIO0, 25=VCCIO1,
  36=VCCX3V3 power; 12/37=VCC1V2; 2/26/EPAD ground; 42/43 strap GND).
- **Presence**: JP_GND_DET_T/B/R all bonded to tile **GND**; U2.2 on GND;
  U2.5=VCC1V2_RAW; FB1.1=VCC1V2_RAW, FB1.2=VCC1V2; C8.1=VCC1V2_RAW — matches N5's
  `[C8.1, FB1.1, U2.5]` requirement.
- **RTL/cst table check**: `rtl/top_gw1nz.vhdl` entity has exactly the 26 ports
  schematic_check's PORT2NET and pincon's B1 assume (12 keys + 9 inputs + 5
  outputs); `constraints/tile_gw1nz_board.cst` carries `DRIVE=2 SLEW_RATE=SLOW`
  on exactly the five outputs with the documented UNVERIFIED-hint comment.
- **sch_summary.json** (10:56): `ok:true, problems:[], nets:45` including the
  five `_DRV` stubs — SCH0 expectation is derived from SERIES_DRV_NETS, not the
  stale literal (fix verified in `kicad/sch_gen.py:608`).

## 3. Canonical report contents re-verified (contents, not just existence)

- `out/netcheck_report.json` (10:55:32): `ok:true`; gw1nz 10/10 and up5k 10/10
  checks ok; negative controls a/b/c all `failed_as_expected:true` (corrupted
  expectation → N1; SW1.2 K2 → N6; JP_GND_DET_B on isolated net → N8+N9).
- `out/kicad/tile_gw1nz.erc.json` (10:56:37): `kicad_version 10.0.6`,
  severities error+warning+exclusion included, `violations: []`. S1 in
  `tools/schematic_check.py:189` **regenerates** this file via
  `kicad-cli sch erc --severity-all -o … <sch>` through the guard on every run —
  it is a fresh-tool product, not a mutable hand-authored report. **No project
  ERC exclusions**: `tile_gw1nz.kicad_prl` contains no `erc_exclusions`;
  `tile_gw1nz.kicad_pro` has no `schematic.erc` settings at all; the S1 command
  takes no exclusion flags. The four `ignored_checks` entries
  (single_global_label, four_way_junction, simulation_model_issue,
  footprint_filter) are KiCad's stock default-ignored *check classes* echo, and
  no violation exists at any included severity to hide behind them; connectivity
  substance is additionally covered by S3/S4/S6.
- `out/sch_summary.json`: ok, 45 nets (above).

## 4. DRC reading — clean errors ≠ fab-ready

`out/kicad/tile_gw1nz.drc.json` (10:56:43, source tile_gw1nz.kicad_pcb):
**0 error-severity violations**; 107 **warnings** = 76 silk_over_copper +
29 silk_overlap + 2 silk_edge_clearance (cosmetic silkscreen classes only, +15
vs r5 = the five new resistor reference labels); **99 unconnected_items** (+5 vs
r5, the intended split of five {U1,JP} pairs into {U1,R}+{R,JP} pairs). The board
is an **unrouted placement prototype: NOT fab-ready** (acceptance requires zero
unconnected; FPGA-02 owns routing). up5k control: 90 warnings / 88 unconnected.

## 5. NEW negative controls (validator-added, this session)

Script `/tmp/opencode/fpga01-validate-controls.py` (runs the SHIPPED functions
`board_net_check.load_pcb/expected_fpga/run_checks` and
`schematic_check.parse_netlist/parse_pcb/compare` on in-memory deep copies of
the real parsed artifacts; writes nothing; exit 0):

- **baseline**: real board through run_checks = N1..N10 all ok (checker not vacuous).
- **(d) resistor bypass** (R7 shorted; U1.35 on T_clk): fired — N10
  `T_clk_DRV=['R7.1']`, `T_clk=['JP_T_clk.1','R7.2','U1.35']`; N8 also fired
  (single-pad drv stub, a genuine defect class).
- **(e) resistor wrong pin** (R7.2 on L_clk): fired — N10 both sides
  (`T_clk=['JP_T_clk.1']`, `L_clk=[…,'R7.2','R8.2']`); N8 tripped on the
  now-singleton T_clk (correct behavior, not over-fire).
- **(f) schematic-side bypass** (exported-netlist T_clk_DRV folded into T_clk):
  fired via the real S4 compare (`nets only in first: ['T_clk_DRV']`).
- **parity sanity**: real netlist vs real pcb through shipped compare = MATCH.

Result: `VALIDATION CONTROLS: all fire as required … parity clean`. Combined with
the canonical a/b/c (netcheck) and S7 3/3 (schematic) controls, bypass and
wrong-pin faults on all five series positions are provably caught on both the
board and schematic sides.

## 6. Source hashes (validator snapshots 12:30-12:50)

```
f728b1d6…7fd2  out/kicad/tile_gw1nz.kicad_sch        (10:56:34)
c7d5b66f…0a3a58 out/kicad/tile_gw1nz.kicad_pcb       (10:47:06)
17ba0274…05b396 out/kicad/tile_gw1nz.drc.json        (10:56:43)
74328928…dafc70 out/kicad/tile_gw1nz.erc.json        (10:56:37)
712bd5a2…c0cbc9d8 out/netcheck_report.json           (10:55:32)
d85ae0c7…64c659 out/sch_summary.json                 (10:56:34)
385bc986…8db486 out/kicad/tile_gw1nz.net             (10:56:38)
1461668e…7de37 out/kicad/lib/fpga_tile.kicad_sym     (10:56:34)
e1c31e47274752f4237c3d8da41ca5d268a56b67533a058be7d5a115c0b54a3a tools/schematic_check.py
6628d7145cfe3125c74969febbc3af192368a103a42d4c60bd95d704488cd94d tools/board_net_check.py
7168d334a724e1897a43f414df16e8041d73823b5babc352225fc05f5ef2069e kicad/sch_gen.py
e4ccd1febcb63f1d1d2a366e35803ccc4bd0f37c2c2a2bac8539d5201480d6eb kicad/board_gen.py
409fbae4f6e4214525d8061f2294bc46135f064afb4abe006f31235becaff5f4 constraints/tile_gw1nz_board.cst
```

## 7. Fresh re-run attempts — ADMISSION-BLOCKED (exact record)

Four guarded attempts to refresh the canonical reports today; all denied by the
6144 MiB MemAvailable gate (guard defaults honored, never lowered). Machine:
~16+ GiB used, swap 11.4/11.4 GiB occupied; competing jobs are the user's own
(antani cargo/rustc watch cycles respawning, a ~2 GiB julia test process,
firefox ~7 GiB). Observed MemAvailable 1.7→4.6 GiB over 12:33-13:00; peak single
sample 4572 MiB — never close to 6144.

1. 12:33 `--wait 120 -- python3 tools/board_net_check.py` → denied after bounded
   wait (rc 2), MemAvail 2444.
2. 12:37-12:52 `--wait 780` → denied after ~13 min polling (rc 2), MemAvail 3322.
3. 12:54 `--wait 150 -- bash -c 'board_net_check && pincon_check &&
   footprint_verify'` → denied (rc 2), MemAvail 3051.
4. 13:00 `--wait 20` (final one-shot) → denied (rc 2), MemAvail 4260, rust active.

Per `docs/FPGA_PLAN.md` recovery procedure ("preserve logs and partial results if
resource admission prevents a run"), the gate was respected rather than bypassed.
Consequence: `board_net_check`, `schematic_check` (fresh ERC+netlist),
`pincon_check`, `footprint_verify` and fresh kicad-cli DRC were **not re-run in
this session**; the statements in §2-§5 stand on direct artifact re-derivation
and the shipped functions, and the canonical reports' contents were individually
re-verified, but they carry 10:55-10:56 timestamps until a future admitted window
regenerates them. No UP5K rerun or placement search was attempted, by scope.

## 8. What was NOT tested / explicit gaps

- No fresh canonical checker run this session (§7); fresh ERC/DRC not regenerated
  after 10:56 — no indication of drift (hashes stable, single writer, coherent
  mtimes), but an admitted rerun remains the formal refresh step.
- No vendor-flow run exists (cst DRIVE/SLEW hints unverified; OSS-flow A/B says
  they are ignored by nextpnr-himbaechel).
- Bench items B1 (LDO ramp), B2 (edge scope incl. L_latch probe + undershoot
  bound), B3 (flash-free AUTO-BOOT) unexecuted — no hardware access.
- **Assembly quote NOT OBTAINED** (ordered FPGA-01/5; no waiver recorded).
- **Series resistors are placement-proven configurable placeholders (0R
  populated): NOT proven damping and NOT routing proof.**
- Board is unrouted (99 unconnected items) — **NOT fab-ready**; FPGA-02 owns
  routing and zero-unconnected acceptance.
- UP5K variant: NOFIT review artifact, untouched by design; not re-exercised.

## 9. Verdict

The orchestrator's 12:26 "failed log" reading is **stale**: session 5b completed
successfully at 10:56 (`R6-B BATTERY DONE`), and the current artifact set is
self-consistent, hash-stable and independently re-derivable clean:

schematic 45 nets / ERC 0 (fresh-tool, no exclusions) / S1-S7 pass · board 65
parts, five 0R series positions placed physically on B side, N1-N10 pass · five
split nodes exact · supply + presence pins exact · DRC 0 errors / 107 silk
warnings / 99 unconnected (placement prototype) · A/B drive evidence hash-verified ·
negative controls a/b/c + S7 + new d/e/f all fire · SCH0/S3 census 45/45
consistent.

**No regression found; no repair needed.** Remaining blockers for FPGA-01
(unchanged, not mine to close): assembly quote (item 5), termination closure via
bench B2 (item 4 DECISION-RECORDED, not resolved), and a future admitted window
for a formal fresh canonical rerun. Task status stays **IN PROGRESS**; nothing
here marks FPGA-01 complete and no later task has started.
