# FPGA-01 — independent adversarial review (2026-10-14)

Reviewer: independent (CERN Kimi-K3, second instance). Scope: read-only review of the
FPGA-01 electrical-design artifacts; own ONLY this file. No edits to
`fpga/board/**`, `checkpoints/fpga-01.md`, or the plan. No
purchases/hardware/commits; no container or regeneration runs. One light
existing checker re-run (tools/schematic_check.py, self-guarded via
tools/resource_guard.py) was executed to test reproducibility.

## Evidence actually inspected (not summaries)

- `docs/FPGA_PLAN.md`, `checkpoints/fpga-01.md` (all sessions), prior ledger files.
- Changed `fpga/board/**` files via `git diff HEAD`: production cst,
  board_gen.py (C8/C9 + TLV75512PDBVR), board_net_check.py, run_board_pnr.sh,
  all out/ artifacts.
- `docs/{termination,power_reg,bom,candidate,readiness}.md` + `bom.json`.
- Generated artifacts parsed directly: `tile_gw1nz.kicad_sch`, symbol lib
  `out/kicad/lib/fpga_tile.kicad_sym`, `tile_gw1nz.erc.json`, `tile_gw1nz.net`
  (46 nets), `tile_{gw1nz,up5k}.drc.json`, `board_checks.json`,
  `netcheck_report.{md,json}`, `sch_summary.json`, `out/pnr/summary.txt`,
  `out/pnr/tmp/ab_{A,B}.fs`.
- Independent re-derivations: A/B bitstream identity by sha256 (both
  3918ac9c… — verified byte-identical); netlist spot-memberships
  (`/VCC1V2_RAW` = {C8.1, FB1.1, U2.5} exactly); TP census from the pcb
  (11); U1 symbol pin-type census (49 pins exactly: 12 bidir keys,
  16 input, 8 output, 8 power_in, 5 no_connect = pins 6/9/14/15/29); symbol TLV755P_DBV = 1IN/2GND/3EN/4NC/5OUT
  with OUT power_out; DRC jsons recounted (gw1nz: 92 warnings + 94
  unconnected_items; up5k: 90 + 88).
- Reproducibility probe: `python3 tools/schematic_check.py` re-run at
  ~22:35–22:42 (regenerated `tile_gw1nz.erc.json` 22:42:50 + `.net`) →
  **PASS S1–S7** (fresh ERC 0 violations, 46 nets, 134==134 pads, 3/3
  controls). The PASS is genuinely reproducible by a third party today.
- Web spot-checks (light): TI TLV755P product page (option 1.2 V exists,
  COUT ≥ 1 µF, accuracy 1 % @85 °C, UVLO/foldback/soft-start monotonic —
  all as claimed); DBV 5-pin pinout 1=IN 2=GND 3=EN 4=NC 5=OUT confirmed by
  independent sources; **LCSC C5799569 fetched live today** = GOWIN
  GW1NZ-LV1QN48C6/I5, stock 850, price breaks $6.6772/5.6426/5.012/4.4832
  exactly as recorded in bom.json; Gowin cst keyword check (see P2).

## Verdict (corrected 2026-10-14 ~23:10, supersedes the first wording)

**Partial progress verified; FPGA-01 acceptance NOT closed.** The machine
evidence below (schematic/ERC/reconciliation/BOM sourcing) is strong and
reproducible, but two ordered task requirements are unmet and cannot be
papered over:

1. **Ordered item 5 (assembly quote) is a recorded BLOCKED gate.** No
   apparatus exists here to obtain it (account + file upload), and
   relabeling does not waive the requirement. Sub-gate 5 as ordered is
   therefore NOT DONE at the evidence level; only the plan owner may
   formally re-scope it.
2. **The physical termination topology is UNRESOLVED.** Once the invalid
   rationale (P1) is removed, "keep 19 contacts" stands only as an
   engineering *hypothesis* whose remaining support is the B2 physical
   measurement — not an evidence-level resolution. Sub-gate 4 is a
   recorded decision, not a resolved question.

These must be repaired/explicitly adjudicated before FPGA-01 is marked
complete in the plan, and the invalid claims must NOT be carried into
FPGA-02/03 as closure evidence. None of the findings alters the
keep-19-contacts decision itself.

## Review baseline and scope

Evidence taken against artifacts as of **2026-10-14 ~22:42–23:05 CEST**,
including key counts at that instant: gw1nz DRC 92 warnings / 94
unconnected_items (up5k 90 / 88); schematic_check S1–S7 PASS re-run
22:42:50; netlist 46 nets, 134==134 pads, 11 TPs; A/B .fs sha256
3918ac9c… for both; board r5 = 60 parts. **The original worker is now
remediating `board/**`; this review is frozen at the baseline above and
does not track those evolving artifacts. The checker re-run listed above
(22:42:50) is the only one this review performed, done before the freeze;
no checkers will be re-run after the baseline (the checker also writes
report artifacts outside this review's ownership).**

## Findings (priority order)

### P1-CRITICAL — termination.md's closure rationale is invalid physics (as written)

`fpga/board/docs/termination.md` lines 20–25: "the run lengths (<=0.25 m …)
keep the worst-case reflection settling time far inside a 50 ns bit cell;
the receiving ends are high-impedance CMOS inputs, twice terminated by
snap-flop sampling in the destination tile. The fpga workstream already
closes 20 MHz system timing on this topology (board PnR Fmax 234-342 MHz,
board/tools/run_board_pnr.sh logs)."

1. **"twice terminated by snap-flop sampling" is not a termination.** A
   high-Z CMOS input reflects with Γ≈+1; sampling the waveform twice in
   destination flip-flops provides zero line termination and zero damping.
   There is no physical termination equivalence anywhere in the interface —
   the honest description is "unterminated, full far-end reflection; margin
   rests on edge-rate/run-length ratio and is bench-gated (B2)".
2. **"Settles inside the 50 ns bit cell" does not make the CLOCK-class nets
   safe.** On T_clk/L_clk (shift clock) and L_latch (latch strobe), any
   reflection that re-crosses the input threshold window — even if it
   settles well before the cell ends — produces a spurious shift/latch
   event (double-clocking). Settle-then-sample reasoning is valid only for
   the level nets (B_data, and B_W if static). The doc's own B2 acceptance
   (no non-monotonicity in the threshold window, lines 60–62) is the
   correct criterion and contradicts the rationale: settling is necessary,
   not sufficient.
3. **"Fmax 234-342 MHz … already closes 20 MHz system timing on this
   topology" is a category error.** The quoted numbers are nextpnr
   interior-fabric STA for one clock (`u_tile.b_clk`) on an unrouted
   chip — the driver script itself states it "does NOT close board-level
   20 MHz system timing" (run_board_pnr.sh lines 13–14). Board/chassis
   interconnect, spring contacts, return paths and controller timing are
   exactly what PnR cannot see. Also "234-342" mixes two unrelated runs
   (fall 342.35/234.25, track 336.47/213.68) into a range.
4. The "≤0.25 m" worst-case run is asserted with no derivation, no line
   impedance/return-path/load-capacitance model and no simulation; at that
   length (~1.5–2 ns one-way) far-end doubling into a 3.3 V LVCMOS input is
   physically plausible, so B2 is correctly mandatory.

Consequence: the *decision* (keep certified 19 contacts; bench-gate before
scaling; OSS drive-softening unavailable) is sound and conservatively
recorded, but the *rationale* argues safety from false premises. Repair:
rewrite lines 16–25 to state the true reason (certified-geometry cost vs an
unquantified but bench-gated SI risk) and drop claims 1–3. Bounded effort:
doc-only.

### P2-HIGH — "honored by the vendor flow" is unverified, and the slew keyword conflicts with Gowin documentation

- termination.md lines 39–47 ("Verified 2026-10-14 that these are **honored
  only by the vendor flow**") and cst comment (constraints/
  tile_gw1nz_board.cst lines 67–77: "honored by Gowin EDA gw_sh/pnr from
  UG842 pad attributes"). The only evidence is the OSS A/B (byte-identical
  .fs — I re-verified the sha256 pair) plus `strings`. That proves
  nextpnr-himbaechel silently ignores the attributes; it says nothing about
  the vendor flow. No vendor-tool run exists. "Verified" is over-claimed.
- Worse: Gowin's own documentation (SUG935-1.3E Physical Constraints User
  Guide, §4.1; Gowin SystemIO User Guide §7.1.9) writes the attribute
  **`SLEW_RATE`** ("IO_PORT "xxx" SLEW_RATE=SLOW"), while the production
  cst writes **`SLEWRATE`** (lines 78–82). Third-party material exists with
  both spellings, so this is unresolved — but the keyword the docs cite as
  "valid Gowin cst … free insurance" is not the keyword in the official
  guide. `DRIVE=2` does match the documented `DRIVE=` form.
- Consequence: with the current spelling, a future vendor pass may warn,
  ignore, or error — i.e. the "insurance" may be fictional. Bounded repair:
  (a) reword all three texts to "UNVERIFIED — vendor flow never run here";
  (b) fix spelling to the SUG935 form `SLEW_RATE=SLOW` (costless, and
  nextpnr demonstrably ignores either spelling); (c) optionally validate in
  one Gowin EDA run when a vendor flow is ever admitted.

### P3-MEDIUM — GPIO drive: no working path proven; the actionable bounded repairs are recorded nowhere

Current state (verified): cst DRIVE/SLEW attrs are no-ops in the OSS flow
(byte-identical .fs). Pads therefore run at silicon-default drive. The A/B
only covered the **cst** path. Open alternative paths nobody tested or
ruled out: (a) RTL port attributes (e.g. `attribute DRIVE/SLEWRATE` via
yosys json → nextpnr → gowin_pack) — a second A/B of identical cost
(2 nextpnr runs, guard-bounded like the first) would close the question
exhaustively; the strings probe ("DRIVE" constid exists once, "SLEWRATE"
absent) suggests SLEW is dead but DRIVE might still wire through, so the
test is worthwhile rather than pre-judged; (b) check Apicula's chipdb/fuzz
state for GW1NZ IOB drive bits — if the fuse bits are not mapped upstream,
the OSS flow *cannot* set drive regardless of attribute path, which
converts the question permanently. Physical mitigation is a **review proposal, not an
approved structural design**: reserve DNP 0402 series-R positions in-line
on the 5 outputs **on the tile**, between U1 pin and the existing JP pad.
**Whether per-leg or in-tile resistors actually fit within the certified
19-contact geometry (routing, courtyard, clearance, any recertification)
is undetermined and must be established independently — this review does
not assert that they fit.** The doc's rev-B-only framing (21 contacts +
recertification) describes per-leg drive-end termination; the in-tile
single-R option above is an alternative to *evaluate*, pending that
independent determination.

### P4-MEDIUM — Cross-document numeric drift (post-r5 roll-ups not propagated)

- `docs/power_reg.md:83–84`: "1 ferrite, **7 capacitors**, 6 strap
  resistors, 11 test points = **58 parts**" and "**27 non-key parts**" —
  stale. Actual emitted r5 board: 9 capacitors (C8/C9 added), **60 parts**
  (board_checks.json GK7), 29 non-key parts. The LDO section of the same
  file *does* document C8/C9 — the roll-up line was missed.
- `docs/bom.md:9–10`: "**10 test points**" — actual 11 TPs (pcb census:
  TP_{DONE,GND,JTAGSEL,READY,RECFG,TCK,TDI,TDO,TMS,VCC,VCC1V2}; netcheck N4
  agrees).
- `checkpoints/fpga-01.md:103`: "**14 TPs**" — actual 11.
- `docs/readiness.md:14–15`: gw1nz "87 warnings … unconnected **90**",
  up5k "88 warnings … **84**" — the r5 DRC artifacts read **92/90 warnings**
  and **94/88 unconnected_items** (C8/C9/C11/C12 each add pads; the +4/+4
  delta is exactly consistent, so the artifacts are fine — the ledger rows
  are the pre-r5 numbers). The "0 errors" wording is accurate (all 92/90
  violations are warnings; unconnected pairs live in a separate
  `unconnected_items` list, expected on a 0-track prototype).

### P5-MEDIUM — PCBA quote: recorded honest, but the gate row hides an unmet ordered requirement

Plan item FPGA-01/5 asks for "a sourced BOM **and assembly quote**". The
quote is a recorded BLOCKED gate (needs account + file upload) — correctly
*recorded* (bom.md:42–57, bom.json, readiness.md:94–98) and the ~$9.6/tile
component roll-up is real. But the checkpoint gate table
(`checkpoints/fpga-01.md:201`) marks sub-gate 5 flatly "DONE", and line 204
declares the whole task "complete at the evidence level". The plan's
acceptance sentence only requires a "selected purchasable BOM" (satisfied —
LCSC line re-verified live today), but the ordered item-5 text also names
the quote. **BLOCKED ≠ DONE: the quote stands unobtained, the requirement
is unmet, and nothing in this task's authority silently waives it or
re-books it as a later task's prerequisite.** Row 5 must read "BOM DONE;
assembly quote NOT OBTAINED (blocked: needs account + upload)" and the
acceptance verdict must remain open; whether the ordered requirement is
re-scoped is the plan owner's call, not a labeling fix.

### P6-LOW — schematic_check.py mostly non-vacuous, with two dead/vacuous fragments and one docstring overclaim

Reproduced today: S1–S7 PASS, all three S7 negative controls genuinely fire
(the corruptions are applied to the *used* comparison machinery). The good
parts outweigh the bad; still, for the record:
- S5 docstring promises "cst pins == db io pin set"; the code computes
  `io_pins` (line 244) and never uses it — the db legality half of S5 is
  not executed here (it IS covered elsewhere: pincon_check B1–B6/S1 PASS).
- S6 strap block (lines 264–269) is vacuous by construction (`pass`
  regardless); the `tp` variable (264–265) is unused. Strap values are in
  fact cross-covered by board_net_check N3 + S4 parity, so no coverage hole
  — but the code should not pretend to check what it doesn't.
- S1 reads only `sheets[0]` (single-sheet design; fine today, brittle if a
  second sheet ever appears).
Recommendation: delete the dead fragments or implement them; update the
docstring. Bounded, low priority.

### P7-LOW — B2 bench-gate parameter nits

- Acceptance bounds overshoot (<0.6 V over 3.3 V) but not **undershoot**;
  unterminated far-end reflections ring both ways. Suggest adding e.g.
  undershoot > −0.4 V.
- B2 scopes T_clk and B_data only; add **L_latch** (same clock-class
  hazard) when equipment is on the bench anyway.
- 0.6 V over 3.3 V = 3.9 V ≈ typical LVCMOS33 abs-max (VCCIO+0.5); as a
  *gate* this is fine, but it is a screen at the absolute limit, not a
  margin target — worth one sentence.

### P8-INFO — provenance/process notes (no action required)

- out/pnr/summary.txt records only the 2 gw1nz re-runs after the cst edit,
  yet the footer (run_board_pnr.sh:129) hardcodes "BOARD-PNR PASS (4
  runs…)", and the `nextpnr:` version line is empty. The A/B .fs pair is
  the durable evidence (verified identical); the summary's run-count claim
  is cosmetic noise. up5k was intentionally skipped (RUN_VARIANTS gw1nz) —
  acceptable, but the banner lies a little.
- DRC JSON `schematic_parity: 0` is vacuous (board is python-generated, no
  linked kicad project); schematic↔PCB parity is enforced by S4 instead —
  fine, just don't read the DRC field as evidence.
- TLV755P RθJA: checkpoint uses "231 K/W JEDEC"; TI's current parametric
  page lists 60.3/100.8 °C/W (package-dependent, DYD thermal-pad vs standard).
  The exact DBV number should be traced to SBVS320D Table 6-4; **the
  conclusion is insensitive** (105 mW worst case → +11 to +25 K either
  way). Low-severity provenance nit only.
- Resource/admission hygiene confirmed: my only run went through the
  in-script resource_guard path; no containers, no regen, no heavy jobs;
  everything else read-only. Deadline 2026-10-15T10:00+02:00 respected.

## What passes robustly (recorded so the rebuttal is bounded)

1. Real schematic authority exists: generated .kicad_sch + project-local
   symbol lib, single sheet, 49-pin U1 with truthful pin types (NC only
   6/9/14/15/29), TLV755P_DBV with verified pinout and power_out OUT,
   power symbols typed power global, JP feed pads power_out, one
   documented PWR_FLAG on VCC1V2 (not an exclusion file).
2. TRUE ERC: severity-all, 0 violations, no project exclusion file
   (`included_severities` includes `exclusion`; the 4 `ignored_checks` are
   KiCad built-in defaults). Reproduced by this reviewer (fresh run 22:42).
3. Schematic↔PCB↔cst reconciliation S1–S7 PASS reproduced; 134==134
   pad/pin parity per net; 26/26 cst ports; netlist VCC1V2_RAW exactly the
   documented N5 set; presence pads bonded to GND (N9).
4. C8-before-FB1 fix is real and correct (the r4 board had the LDO output
   node with no local cap; that was a genuine defect, now fixed in both
   variants with checker updates).
5. Non-vacuous negative controls across the stack: N-family (3 controls,
   incl. reproduction of the pre-fix GND_DET defect class), S7 (3 firing),
   footprint_verify control; pcb probe bug found by parity hunt was
   root-caused, not papered over.
6. LM BOM sourcing: LCSC C5799569 identity/price breaks verified live
   today; TLV755P pinout and headline params match TI's site; commodity
   passives honestly spec'd; Kailh socket assembly note (consigned) honest.
7. Pins DB is sha256-pinned to DS841E (a19cdd7a2 …) — provenance solid.
8. PnR driver resource/fit limits are real and generous (IOB 24/48,
   LUT4 34/1152) and interior Fmax (213–342 MHz) is honestly labeled as
   interior-only everywhere except termination.md's one sentence.

## Required repairs before FPGA-01 can be adjudicated (bounded, doc-only)

1. **Rewrite termination.md decision rationale (P1)**: delete "twice
   terminated by snap-flop sampling", delete the settle-inside-cell
   safety argument for T_clk/L_clk/L_latch (keep it for data nets),
   delete the Fmax-closes-system-timing sentence; state the true basis
   (certified frame + B2 bench gate, unmodelled-risk acknowledged) and
   reclassify sub-gate 4 as a recorded decision pending B2 physical
   evidence, not a resolved topology.
2. **Downgrade the vendor-flow claim (P2)**: cst comment + termination.md +
   README → "UNVERIFIED (no vendor run here); keyword per SUG935 is
   SLEW_RATE"; fix spelling to `SLEW_RATE=SLOW`.
3. **Fix stale roll-ups (P4)**: power_reg.md:83–84 (9 caps/60/29 parts),
   bom.md:9–10 (11 TPs), fpga-01.md:103 (11 TPs), readiness.md:14–15
   (92/90 warnings, 94/88 unconnected).
4. **Correct gate row 5 (P5)** to "BOM DONE; assembly quote NOT OBTAINED".

## Recommended (optional, bounded) — review proposals, not approved design

5. RTL-attribute A/B for DRIVE (P3a) + Apicula drive-bit check (P3b) to
   close the GPIO-drive question exhaustively; evaluate the DNP
   series-R-in-tile proposal (P3c) — **feasibility within the certified
   contact geometry undetermined; must be established independently
   (routing/clearance/certification) before any adoption.**
6. schematic_check.py cleanup (P6 dead/vacuous fragments + docstring).
7. B2 parameter additions (P7: undershoot bound, include L_latch).

Repairs 1–4 make the ledger honest but do **not** by themselves close
FPGA-01 acceptance: the assembly quote remains an unmet ordered requirement
pending plan-owner adjudication, and the termination topology remains
physically unresolved pending B2 bench evidence. Until then the task
status is "partial progress verified", not complete.
