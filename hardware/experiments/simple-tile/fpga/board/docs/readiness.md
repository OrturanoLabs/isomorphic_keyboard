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
| KiCad DRC (kicad-cli 10.0.6) | out/kicad/*.drc.json | **0 errors**, 87 warnings (63 silk_over_copper, 22 silk_overlap, 2 silk_edge) | **0 errors**, 88 warnings (62/24/2 same classes) |
| unconnected pairs (DRC) | same | 90 -- all expected: unrouted nets, 0 tracks by design (the 3 GND_DET pads joined the unrouted GND island, +3 vs the isolated-pads state) | 84 -- same + NOFIT board |
| emitted-board netlist/power checks N1..N9 + 3 negative controls | tools/board_net_check.py | PASS (49/49 pad nets exact; rails VCC={1,25,36} VCC1V2={12,37} GND={2,26,49}; unused pads exactly {6,9,14,15,29}; presence pads bonded to GND; zero single-pad nets) | PASS (U1 absent by design) |
| real synth+PnR vs production maps | tools/run_board_pnr.sh | PASS (bitstreams 351954 B; IOB 24/48; Fmax 213-342 MHz @20 MHz target) | PASS (104090 B; SB_IO 26/39; 62-69 MHz) |
| cst-really-applied control (BEL diff vs old empirical map) | out/pnr/logs/ctl_emp_* | 25/26 IO cells moved -- cst honoured | n/a |

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
- **LDO part TBD**: SOT-23-5 pin convention assumed (1=IN,2=GND,5=OUT);
  exact part + quiescent current + thermal not selected; VCC1V2 load
  current unmeasured (est. mA scale, TBD vs DS841 tables + bench).
- **UP5K land = LAND-TBD**: package dims vendor-verified; land geometry is
  KiCad stock practice, no vendor recommended-land captured. Also the SG48
  body does not fit the tile (NOFIT) -- fallback needs the concession
  analysis in docs/candidate.md before any use.
- **21-contact rev-B**: board implements the certified 19-contact
  interface; rev-B (+2 nets, R-data split) has no certified pad
  coordinates yet -- needs a connector-next run first.
- **GND_DET_* presence contacts**: the three pads are bonded to tile GND
  (checker N9); the HOST-side detect interpretation (backplane traces stay
  graph-separate, owned by connector-next) needs sign-off from the
  system/controller workstream that this matches their detect scheme.
- **No fab review**: no gerber/drill export, no stencil review, no
  assembly probe plan; EP thermal via field for the QFN EPAD is not
  designed (currently SMD pad only -- decide after thermal estimate).

## Interface + outlines (19 pads, recertified every regen)

GK1/GK2 re-assert: outline == revc TileTiling (6-neighbour min gap =
rib_gap 1.0 mm), 19 chassis pads == connector-next certified coords,
worst slack incl. 0.35 mm chassis tolerance = +1.395 mm. Pad ROLES:
14 tile signals + VCC + GND + 3 GND_DET_* presence -- on the tile the
presence pads are net GND (bonded); role labels are kept for the
backplane graph only. Sockets at the 18.3597/15.9 lattice centres; 3 of
12 use the EdgeTrim pad variant.
