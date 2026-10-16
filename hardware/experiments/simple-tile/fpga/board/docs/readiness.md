# Board readiness ledger -- what is proven, what is still open

Verdict up front: **placement-prototype clean, NOT fab-ready.** Both
variants are unrouted (0 tracks by design). Do not order PCBs from this
state.

## Gate ledger (all machine re-runnable; outputs in out/)

| gate | tool | gw1nz | up5k |
|---|---|---|---|
| pin constraints vs vendor tables (B1..B6, H1, S1) | tools/pincon_check.py | PASS | PASS |
| footprint land pattern vs vendor dims + negative control | tools/footprint_verify.py | PASS (vendor-recommended layout) | PASS (package dims; land = LAND-TBD flag) |
| placement gates GK1..GK7 (TileTiling outline + 6-neighbour 1.0 mm gap, certified 19 pads, sockets, courtyard matrix, NPTH, net census, counts) | kicad/board_gen.py | PASS (U1 at 7.86,5.40) | PASS (U1 NOFIT documented) |
| KiCad DRC (kicad-cli 10.0.6, r6 board) | out/kicad/*.drc.json | **0 errors**, 107 warnings (76 silk_over_copper, 29 silk_overlap, 2 silk_edge_clearance; +15 vs r5 = the 5 new series refs' silkscreen labels, same cosmetic classes) | **0 errors**, 90 warnings (64/24/2) -- unchanged vs r5 (untouched-variant control) |
| unconnected items (DRC) | same | 99 -- all expected: unrouted nets, 0 tracks by design (each series split turns one {U1,JP} pair into two {U1,R}+{R,JP} pairs: +5 vs r5) | 88 -- same + NOFIT board |
| emitted-board netlist/power checks N1..N10 + 3 negative controls | tools/board_net_check.py | PASS (49/49 pad nets exact; rails VCC={1,25,36} VCC1V2={12,37} GND={2,26,49}; unused pads exactly {6,9,14,15,29}; presence pads bonded to GND; zero single-pad nets; **N10** series-R split R7..R11 exact: U1--Rn.1 on <net>_DRV, Rn.2--JP on <net>) | PASS (U1 absent by design; N10 n/a) |
| series-termination placement GK1..GK7 incl. GK4 courtyard + GK5 clearances | kicad/board_gen.py (r6) | PASS (65 parts, unplaced=[]; 19 JP coords byte-identical to cert; GK4 53 rects no overlaps) | PASS (unchanged) |
| real synth+PnR vs production maps | tools/run_board_pnr.sh | PASS (bitstreams 351954 B; IOB 24/48; Fmax 213-342 MHz @20 MHz target; re-run 2026-10-14 with termination attributes: IOB 24/48, Fmax 342/234 MHz) | PASS (104090 B; SB_IO 26/39; 62-69 MHz) |
| cst-really-applied control (BEL diff vs old empirical map) | out/pnr/logs/ctl_emp_* | 25/26 IO cells moved -- cst honoured | n/a |
| authoritative schematic generation + self-check SCH0 | kicad/sch_gen.py | PASS (49/49 U1 pads touched; 45-net census == board, derived from SERIES_DRV_NETS after the session-5b fix) | n/a (gw1nz scope) |
| TRUE KiCad ERC, severity-all, zero exclusions | kicad-cli sch erc -> out/kicad/tile_gw1nz.erc.json | **0 violations** (exclusion file: none) | n/a |
| schematic<->board<->cst reconciliation S1..S7 + 3 negative controls | tools/schematic_check.py | PASS (sch<->PCB pad parity **144==144** (+10 series pads); 26/26 cst port<->net<->pin incl. _DRV alias; S6 straps + series node sets exact; controls fire) | n/a |

## Fixed serious defects found in the 2026-10-14 electrical pass

1. **LDO output capacitor on the wrong side of the bead**: the TLV755P
   required COUT (>=1 uF at the OUT pin, TI SBVS320D) was missing --
   FB1 would have isolated every bypass capacitor from the LDO control
   loop. Fixed: C8 on VCC1V2_RAW (before FB1), C9 on VCC (CIN); up5k
   got C11/C12. Board r5 netcheck N1..N9 + negative controls re-PASS.
2. **LDO part was "TBD"**: TI TLV75512PDBVR selected, pinout verified
   vs SBVS320D Table 4-1 (1=IN 2=GND 3=EN 4=NC 5=OUT == U2 binding).
3. **Eight KiCad-format defects in the first schematic generator**
   (lib header version, power-instance Value naming, f-string ref bug,
   TP grid unpacking, off-grid endpoints, ...) -- root-caused until
   TRUE ERC runs at zero without any exclusion. Full list: checkpoint
   fpga-01 session 3.

## Fixed serious defects found in this pass (2026-10-13)

1. **Bottom-side mirror bug** in the board emitter: every B-side part was
   written at x = -(checked x). Pre-fix KiCad DRC had 209 (gw1nz) / 118
   (up5k) violations incl. courtyard overlaps, shorts, edge-clearance
   errors (out/logs/drc_before_mirrorfix.json).
2. **Test-point courtyard bug**: fp_circle treated as two bbox corners ->
   degenerate rect -> TPs packed overlapping the FPGA.
3. **Unpowered IO banks**: FPGA power pads held vendor rail names
   (VCCIO0/VCCIO1/VCCX3V3...) as single-pad nets -- invisible to DRC
   unconnected-pairs; caught by net census (now checker N8 guards it).
4. **Dangling core-rail ferrite**: FB1 output net had one pad; now
   LDO -> FB1 -> VCC1V2 (core pins + bulk cap) with exact N5 topology.
5. **Floating presence pads** (caught by independent review): the three
   GND_DET_T/B/R chassis pads were emitted as isolated single-pad nets on
   the tile -- electrically wrong for rev-A presence semantics. Fixed:
   the pads keep their connector-next refs/roles (the backplane keeps
   separate traces, untouched) but are bonded to tile **GND** -- an
   inserted tile presents hard ground on those three contacts, an absent
   tile presents open. Checker N9 pins this, N8 allows ZERO single-pad
   nets on gw1nz, and negative control (c) reproduces the old defect.

## Open gaps before any fab order (true pad/power/boot gaps)

- **Routing**: zero tracks/vias/zones; unconnected counts above are the
  honest remainder. 2-layer escape for 0.4 mm QFN + return paths for the
  20 MHz shift chain across 16 tiles is real layout work, not a formality.
- **Silkscreen**: 60+ silk warnings per board (refs/courtesy overlaps) --
  cosmetic but must be cleaned for assembly.
- **System timing NOT closed**: interior Fmax passes with 10x margin, but
  inter-tile drive/return, cable model, and controller timing for the
  16-tile 20 MHz chain are unverified (fpga workstream owns the system sim).
- **LDO bench items open**: TI TLV75512PDBVR selected and pinout-verified
  (docs/power_reg.md); **B1** = scope the soft-start ramp vs the DS841
  AUTO-BOOT config window on the first tile; VCC1V2 load current still
  unmeasured (est. mA scale vs DS841 tables + bench).
- **UP5K land = LAND-TBD**: package dims vendor-verified; land geometry is
  KiCad stock practice, no vendor recommended-land captured. Also the SG48
  body does not fit the tile (NOFIT) -- fallback needs the concession
  analysis in docs/candidate.md before any use.
- **Termination DECISION-RECORDED, bench-gated -- NOT evidence-closed**
  (docs/termination.md, rewritten 2026-10-15 after review P1): 19-contact
  frame kept. Structural mitigation SHIPPED in r6: R7..R11 (0402, **0R
  populated** = conservative configurable placeholder, reproduces today's
  circuit exactly; NOT proven damping) in-line on the 5 forward outputs,
  placement verified (GK1..GK7, N10, S6) but **routing feasibility not
  proven (0 tracks; escape is FPGA-02 scope)**. Free edge-rate knob =
  RTL DRIVE attribute (OSS-proven to reach the bitstream,
  tools/drive_attr_ab.sh) -- recommended to the fpga workstream. cst
  keeps SUG935-spelled `SLEW_RATE=SLOW` + `DRIVE=2` as UNVERIFIED vendor
  hints (OSS flow provably ignores cst attrs; no vendor run exists).
  **B2** = scope T_clk/L_latch/B_data at the far contact (overshoot AND
  undershoot bounds; no non-monotonicity). 21-contact rev-B = gated
  fallback needing connector-next recertification -- NOT fabricated
  preemptively.
- **GND_DET_* presence contacts**: the three pads are bonded to tile GND
  (checker N9); the HOST-side detect interpretation (backplane traces stay
  graph-separate, owned by connector-next) needs sign-off from the
  system/controller workstream that this matches their detect scheme.
- **No fab review**: no gerber/drill export, no stencil review, no
  assembly probe plan; EP thermal via field for the QFN EPAD is not
  designed (currently SMD pad only -- decide after thermal estimate).
- **BOM/quote state**: component sourcing evidence complete (docs/bom.md,
  fetched 2026-10-14, +5x0R 0402 series positions at r6; ~US$9.6/tile
  components at qty 1); **assembly quote NOT OBTAINED** -- still required
  by ordered FPGA-01/5 (JLCPCB formal quote needs account + Gerber/BOM/CPL
  upload; no apparatus here, no waiver recorded). Kailh sockets are not
  in PCBA libraries -> hand-solder/consigned.

## Interface + outlines (19 pads, recertified every regen)

GK1/GK2 re-assert: outline == revc TileTiling (6-neighbour min gap =
rib_gap 1.0 mm), 19 chassis pads == connector-next certified coords,
worst slack incl. 0.35 mm chassis tolerance = +1.395 mm. Pad ROLES:
14 tile signals + VCC + GND + 3 GND_DET_* presence -- on the tile the
presence pads are net GND (bonded); role labels are kept for the
backplane graph only. Sockets at the 18.3597/15.9 lattice centres; 3 of
12 use the EdgeTrim pad variant.

## Overnight 2026-10-15/16 evidence deltas (preparation-only, batches
001-017; checkpoint fpga-01.md sessions 2-21; trust anchor:
tools/integrity_check.py PASS 14/14; pcb stayed c7d5b66fa1db)

What the night's evidence SHIFTS inside the open-gaps list above:
- **Routing gap (still open)**: now QUANTIFIED, not just asserted.
  Corridors measured (routing_geo.json: min in-row 2.883 mm = 6
  tracks; U1-SW6 pinch 0.37 mm = the binding site). Router census
  deterministic (byte-identical replicate): 46/99 items routed at
  strict 0.2/0.2 + class table, 0 violations; internal SMD fanout
  escapes only 115/144 (79.9%); dead-end pre-stubs measured WORSE
  (28/99); DSN plane declarations absorb without attaching (17/79).
  Width trait: off-class incl. sub-rule 150 um scored 0 violations --
  a widen pass is a recorded adoption prerequisite and is proven
  mechanical+conflict-free on two arms (widen_report/apply). The gap
  itself (0 tracks) is untouched; the 2L/4L decision now has data
  (routing_plan.md bottom, docs/fpga02_handoff.md section 3).
- **EP thermal via field**: the pending "thermal estimate" now EXISTS
  (power_reg.md batch-1/batch-4 analysis: ~50-60 mW load -> no
  thermal vias; EP pad soldered to GND with multi-window paste;
  via-in-EP skipped; optional outside-EP 0.6/0.3 via ring deferred
  to FPGA-02). Analysis only; the design decision stays with the
  plan owner.
- **Assembly quote**: package prepared (docs/quote/: neutral BOM CSV,
  provisional CPL, README). The account+upload blocker itself is
  UNTOUCHED.
- **JP-band pad-to-edge**: 1.3 mm to the BBOX recorded info-only
  (routing plan); TRUE stepped-edge distance remains a GK recheck
  item -- untouched.

Explicitly UNTOUCHED by the night (no new evidence, no waiver):
bench B1/B1b/B2/B3 (hardware), termination decision-recorded status
(pending B2), Gowin vendor flow (never run), system timing closure,
GND_DET_* host-side sign-off, silkscreen corpus, UP5K LAND-TBD,
assembly quote account/upload.
