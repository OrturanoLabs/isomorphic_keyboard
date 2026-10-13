# Checkpoint: fpga-board worker (simple-tile)

Started: 2026-10-12 (session start). Status: IN PROGRESS.
RECOVERY 2 (2026-10-13, same day): independent review found a REAL
electrical defect in what was previously recorded as PASS: the three
GND_DET_* presence pads were emitted as single-pad ISOLATED nets
(whitelisted in netcheck N8 + documented as "intentional"). Wrong for
rev-A presence semantics: ON THE REMOVABLE TILE each JP_GND_DET_T/B/R
pad must be BONDED to tile GND (closed ground contact when inserted,
open when removed); the backplane keeps its separate traces (owned by
connector-next - untouched). Fix plan (owned files only, pure PCB net
fix, NO PnR repeat): board_gen chassis-pad net binding bonds
name.startswith("GND") -> net "GND" keeping refs/roles JP_GND_DET_*;
netcheck drops the PRESENCE whitelist, N6 expects JP nets = 14 signals
+ VCC + GND, N9 asserts each presence pad shares GND with FPGA/LDO
grounds, N8 singles must be EMPTY on gw1nz (up5k: U1-facing only);
new negative control: rebinding one presence pad to an isolated net
MUST fail; regen r4 (~10 min) + real DRC + netcheck; docs rewritten
(readiness claim withdrawn).

RECOVERED 2026-10-13 after power interruption + a failed resume turn
("Failed to execute statement", no progress made by that turn). Recovery
check: no active containers/jobs; docs/ and README.md confirmed MISSING on
disk; DRC jsons of 2026-10-12T20:52 exist.
Scope: ONLY `hardware/experiments/simple-tile/fpga/board/**` + this checkpoint.
No commits, no installs, no orders. Sibling workstreams (fpga synth/sim,
system, controller, discrete baseline) own their files; never edit theirs.

## RECOVERY FINDINGS (2026-10-13, analysis only - no files changed yet)

- Existing out/kicad/tile_*.drc.json (both variants) are NOT clean despite
  GK1-GK7 PASS: gw1nz = 209 violations (10 clearance, 13 edge, 27 courtyard
  overlaps, 13 shorting, 19 mask bridge) + 84 unconnected; up5k = 118
  violations + 81 unconnected. Unconnected counts are EXPECTED (unrouted
  placement prototype); hard violations are NOT.
- ROOT CAUSE identified, evidence on disk: board/kicad/board_gen.py
  instantiate() inserts the board-level `(at x y)` line BEFORE
  mirror_footprint_text() negates every x (GEOM_XY regex) for bottom parts ->
  every B-side part is emitted mirrored through the y axis relative to the
  position the Placer checked. Emitted U1 at (-7.8597, 5.4) vs checked/planned
  (+7.86, 5.4); same for all caps/straps/TPs -> real overlaps in the file.
  GK4 passed because pl.parts used the same wrong assumption consistently.
- Cosmetic: the 12 Kailh sockets keep reference "REF**" (set_prop regex does
  not match the vendored legacy footprint format).
- Checkpoint progress text said "U1 placed (17.61,5.90)" but
  board_checks.json GK7 says fpga_at=(7.86, 5.4) - stale text; regenerated
  numbers below will be authoritative.
- DECISION (fix, in my scope only): mirror local footprint geometry FIRST,
  THEN attach the board-level at; harden set_prop for legacy fp_text.
  Plan: fix -> rerun board_gen (GK gates) -> rerun kicad-cli DRC both
  variants -> vendor-land-pattern footprint verification doc/assert ->
  board netlist/power-pin checker with negative control -> constrained
  Gowin synth+PnR with board .cst IF tools exist (oss container; none
  running now - probe first) -> README + docs/{candidate,power_reg,
  readiness}.md (honest gaps; NOT fab-ready; unrouted).

## Task scope (orchestrator brief)

1. Choose the exact tiny-FPGA hardware candidate for the single-PCB tile:
   primary GW1NZ-LV1QN48 (open bitstream fit exists, 26 tile IO; rails/JTAG/
   startup previously UNVERIFIED), fallback iCE40UP5K-SG48 (needs external
   flash + regulator), LP8K-CM81 packaging not preferred.
2. Retrieve authoritative or mirrored datasheet + pinout (web tools); VERIFY
   actual package pin identities, power rails, configuration storage and
   boot-pin pulls. Do NOT infer power pins from chipdb-missing IO pads.
3. Pin-constraint checker: reserves JTAG/strap pins, checks the 26 tile IO
   against actual package pads, flags anything whose primary source is
   unknown.
4. Production-oriented .cst/.pcf in MY board folder only (never touch
   fpga/synth/*).
5. KiCad single-PCB placement/circuit prototype on the corrected
   connector-next TileTiling outline (NOT the old baseline connectors "Tile"
   outline, which overlaps vertical neighbours by 1.46 mm): full pairwise
   courtyard / NPTH / socket / 19-or-21-contact interface / 6-neighbour
   outline checks. pcbnew/kicad-cli DRC + readiness metrics. Do NOT call the
   unrouted board fab-ready.
6. Power-regulator requirements + BOM logic-count-vs-total with prices marked
   unknown (no invented quotes).
7. If the Gowin pinout cannot be verified: keep GW1NZ as a BLOCKED candidate
   and develop a VERIFIED UP5K fallback from the Lattice primary pin map,
   exact package footprint, bypass + SPI-flash programming test pads, so a
   legitimate physical prototype is possible.

## Baseline facts inherited (from checkpoints/fpga.md etc., read-only)

- User constraints: no tile MCU / LED / Hall; 20 MHz shift clock target;
  16-tile chain; strong open-hardware/open-flow preference.
- RTL/sim/synth done by fpga workstream: 26 user IO exact (pin_budget.md);
  synth/tile_gw1nz.cst and tile_up5k.pcf are PROPOSALS on empirical chipdb
  pad census only (DS861 fetch had failed: vendor site served marketing).
- connector-next: corrected outline = `TileTiling` (vertical margin R/2,
  horizontal P/2, rib_gap 1.0) — exactly 1.0 mm gap at all six neighbours.
  interface = 19 contact pads (budget.py), rev-B variant = 21 contacts.
  Branch A (vertical springs vs chassis) VIABLE; mezzanine tab branch is
  placement-REJECTED.
- Tools: host python3 (stdlib only); KiCad 10.0.6 via tools/kicad-cli.sh
  (flatpak org.kicad.KiCad — confirmed `version` prints 10.0.6); pcbnew
  python via flatpak `flatpak run --command=python3 org.kicad.KiCad`
  (connector-next make_coupons_next.py pattern); no kicad-cli/pcbnew on host
  PATH; synth tools only in the oss container (not needed for board here).
- git: consolidation in progress in the working tree (revc-mcu-tile deletions
  staged, untracked hardware/experiments/consolidation/) — not mine, do not
  touch/commit.

## Progress log

- [start] Recon done: read fpga/RESULTS.md, docs/{alternatives,pin_budget,
  power_bom}.md, checkpoints/fpga.md, connector-next README + checkpoint +
  study.py TileTiling construction, baseline connectors/study.py header
  (Params, CONTACTS), existing synth cst/pcf.
- [ds] Vendor documents retrieved via curl from vendor sites (mirrors listed):
  Gowin DS841-2.8E (CURRENT; NOTE: prior task referenced "DS861" - DS861 is
  the GW1NSR datasheet, GW1NZ is DS841), UG842-1.6.8E (GW1NZ-1 Pinout, the
  QN48 per-pad table), UG290-2.9.1E (config modes), UG293-1.3.4E (schematic
  manual), UG846-1.1E (automotive QN48 pkg/pins), Lattice FPGA-DS-02008-2.4
  (iCE40 UltraPlus DS), iCE40UP5K Pinout xlsx (doc 51971, primary pin map),
  FPGA-TN-02001-3.5 (config), FPGA-TN-02006-2.4 (hw checklist),
  FPGA-DS-02053-8.8 (package diagrams, SG48 section 31). All sha256-stamped
  in board/data/*.json. => GOWIN PINOUT IS NOT BLOCKED: verified from the
  vendor CDN. Automotive UG846 lists VCC on pin 9 where commercial UG842 has
  user IO IOR2A - order-code HAZARD, pin 9 excluded from assignment (pool is
  30 pads for 26 nets).
- [pincon] data/pins_{gw1nz_qn48,ice40up_sg48}.json (all 48 pins + EP,
  per-source provenance). constraints/tile_{gw1nz_board.cst,up5k_board.pcf}
  (production maps; JTAG/strap/config reserved, MODE pins strapped 00 = AUTO
  BOOT, 10K/4.7K strap practice per vendor manuals). tools/pincon_check.py:
  rules B1..B6, H1, S1 -> BOTH VARIANTS PASS (rc=0); Vendor power pad sets
  match the empirical chipdb censuses EXACTLY (B4) - nothing inferred from
  tool absence anymore.
- [board] kicad/board_gen.py + gen_footprints.py (custom QFN48s:
  GW1NZ 6x6 P0.4 EP2.7, UP5K SG48 7x7 P0.5 EP5.35; pad patterns = KiCad
  stock practice for the class, CCW numbering cross-checked vs stock
  QFN-48-6x6). GW1NZ board: U1 placed (17.61,5.90), 58 parts, 46 nets,
  GATE GK1-GK7 PASS. UP5K: SG48 FPGA does NOT FIT the bottom side (largest
  free square ~7.5 mm vs 7.6 courtyard) = NOFIT documented, board emitted
  as placement-review copy without U1 (keys+19 pads+flash/passives), gate
  records the NOFIT. Next: kicad-cli DRC both boards + cst pack-legality.

## Resume log (2026-10-13)

- [fix1] board_gen.py instantiate(): board-level `(at x y)` now inserted AFTER
  the bottom-side mirror (was before -> every B-side part was emitted at -x
  vs the +x position the Placer checked). Set_prop hardened for legacy
  unquoted fp_text tokens (vendored Kailh sockets kept REF** because of this).
  Evidence of the bug in the old file: U1 at (-7.8597,5.4) while the placer
  gate recorded (+7.86,5.4). Before-fix DRC category counts saved to
  board/out/logs/drc_before_mirrorfix.json.
- [regen1] board_gen.py rerun (9m57s): GK1-7 PASS both variants, U1 gw1nz
  checked+emitted at (7.86,5.40); kicad-cli DRC gw1nz rerun: STILL
  27 courtyard overlaps / 10 shorts / 8 clearance, all clustered on the TP_*
  test points stacked on/near U1 -> placer accepted overlapping TPs.
- [fix2] courtyard_bbox(): KiCad fp_circle was bboxed from its (center)+(end)
  points -> degenerate zero-height rect for the stock D1.0 test point
  ((-0,0,1,0)); now circle = center +/- radius. TP bbox now (-1,-1,1,1).
- [verify1] tools/footprint_verify.py written + PASS (rc=0): both custom
  QFN48 land patterns match the vendor-recorded dims in data/pins_*.json
  (GW1NZ: UG846 recommended PCB layout P=5.90/L=0.85/e=0.40/EP2.70 =
  VENDOR-RECOMMENDED; UP5K: DS-02053 sec.31 package dims verified, land
  geometry = KiCad stock practice and is labelled LAND-TBD in the report).
  Negative control (pitch+0.05, EP+0.1) FAILS as expected. Output:
  out/footprint_verify.json.
- [fix3] NET BUG found via emitted-board net census: fpga_nets_* bound FPGA
  power pads to the VENDOR rail names (VCCIO0/VCCIO1/VCCX3V3 on gw1nz;
  VCCIO/SPI_VCCIO1/VPP_2V5 on up5k) = single-pad nets -> IO banks silently
  unpowered (DRC cannot see this). Fix: RAIL_BOARD rollup maps those rails
  to board net "VCC" in both fpga_nets functions. ALSO fixed the gw1nz
  ferrite topology: U2(pin5) now drives VCC1V2_RAW -> FB1 -> VCC1V2 =
  FPGA core pads + C4/C5/C6 (was: FB output net dangling with 1 pad).
  Chassis-pad report text corrected: GND_DET_* are net-separate
  presence-detection nets, not merged into GND.
- [regen3] regen2 (pid 3414953) KILLED before completion: its placement
  geometry is unchanged by the net fixes, so one rerun with all fixes
  suffices. regen3 pid 3415953 (log out/logs/board_gen_r3.log) running.
- [pnr] Constrained synth+PnR vs the PRODUCTION pin maps, in the oss
  container (yosys 0.69 ghdl + nextpnr-himbaechel chipdb GW1NZ-1,
  nextpnr-ice40 up5k/sg48): ALL 4 RUNS PASS (board-PNR PASS) -
  gw1nz fall+track .fs 351954 B each, IOB 24/48, 26 tile IO bound,
  Fmax clk 213-342 MHz (PASS at 20 MHz SDC target);
  up5k fall+track .bin 104090 B each, SB_IO 26/39, Fmax 62-69 MHz.
  Output: board/out/pnr/{summary.txt,build/,logs/}; driver:
  board/tools/run_board_pnr.sh (uses ../rtl + ../synth READ-ONLY).
  Control run vs the OLD empirical synth cst started (pid 3417405,
  out/pnr/logs/ctl_emp_*) to PROVE the cst drove BEL placement
  (BEL diff expected, e.g. old map used excluded pin 9).
- [pnr-ctl] DONE (rc=0): board-cst vs empirical-cst BEL comparison:
  25/26 IO cells on DIFFERENT BELs -> the production cst genuinely drove
  the pin binding; nothing silently unconstrained. ctl artifacts in
  out/pnr/build/ctl_emp*.
- [regen3] DONE: GK1-7 PASS both variants (log out/logs/board_gen_r3.log),
  43 nets gw1nz / 39 nets up5k.
- [drc] kicad-cli pcb drc 10.0.6 on the regen3 boards: gw1nz 87 violations
  ALL warnings (63 silk_over_copper + 22 silk_overlap + 2 silk_edge) -
  ZERO hard errors; 87 unconnected pairs (expected, unrouted prototype,
  0 tracks by design). up5k: 88 warnings (same classes), 81 unconnected.
  Compare BEFORE fixes: 209/118 violations incl 64/24 hard errors
  (out/logs/drc_before_mirrorfix.json).
- [netcheck] tools/board_net_check.py PASS (rc=0) both variants:
  N1 49/49 FPGA pad nets exact vs pin DB + constraints; N2 rails
  {VCC:[1,25,36] VCC1V2:[12,37] GND:[2,26,49]}; N3 straps/FB topology;
  N4 11/9 TPs; N5 decoupling census + ferrite series exact
  (VCC1V2_RAW == [FB1.1,U2.5]); N6 sockets/JP; N7 unused pads exactly
  [6,9,14,15,29] gw1nz incl pin-9 hazard; N8 no unexpected single-pad
  nets (the singleton-power-rail bug class guard). Negative controls
  (corrupted expectation, corrupted board) FAIL as designed.
  Output: out/netcheck_report.{json,md}.
- [docs] WROTE: board/README.md (map+rerun recipes+status),
  docs/candidate.md (choice, pin-9 hazard, config/straps/JTAG table,
  land provenance, PnR, open items), docs/power_reg.md (rail tables,
  straps, decoupling, BOM counts, prices TBD), docs/readiness.md (gate
  ledger, 4 fixed defects, true open gaps, NOT fab-ready).
  Contact-count answer: boards implement the connector-next CERTIFIED
  19-contact interface (study.json tiers GND=4/SIG=15); 21-contact rev-B
  has no certified pad coords yet -> documented as blocked-upstream.
- [status 2026-10-13] ALL board-side gates done. No jobs running.
  NOT fab-ready: unrouted (0 tracks), silk warnings, system 20 MHz
  chain timing open, LDO part TBD, UP5K land TBD + NOFIT.
- [presence-fix] board_gen chassis pads: GND-class pads (GND + the three
  GND_DET_*) are now BONDED to net GND on the tile while keeping their
  refs/roles (JP_GND_DET_* stays; connector-next graph untouched).
  board_net_check: PRESENCE whitelist REMOVED; N6 expects JP nets =
  14 signals+VCC+GND and presence refs present; NEW N9 = presence pads on
  GND + required GND nodes (U1.2/26/49 + U2.2; up5k: U2.2+U3.4); N8
  singles = ZERO allowed on gw1nz (up5k: U1-facing only); NEW negative
  control (c) = presence pad rebound to isolated net must fail N8+N9.
  regen r4 pid 3422270 running (log out/logs/board_gen_r4.log); nets
  expected 43->40 (3 DET nets joined into GND).
- [presence-fix RESULTS] r4 DONE: nets 43->40 (gw1nz) / 39->36 (up5k),
  exactly -3 as expected; GK1-7 PASS both. DRC after fix: 0 errors both
  (warnings unchanged silk-only 87/88); unconnected pairs 90/84 (+3: the
  DET pads now sit on the unrouted GND island - expected). netcheck PASS
  rc=0: gw1nz N8 singles now EMPTY, N9 presence pads all on GND with
  U1.2/26/49 + U2.2 present; up5k N8 only U1-facing singles (NOFIT),
  N9 = U2.2/U3.4 on GND. Negative controls a/b/c ALL catch their defect
  class (a: N1, b: N6, c: rebound presence pad fails N8+N9). No PnR
  repeat (pure PCB net fix, cst/pins unchanged). docs/readiness.md
  rewritten: the "intentionally single-pad" claim WITHDRAWN, replaced by
  fixed-defect entry #5 + corrected open-gap wording.

## Running jobs

None (r4 finished).

## Job history (all finished 2026-10-13)

1. board_gen pid 3415953 (host python3, log out/logs/board_gen_r3.log) -
   finished rc OK; out/kicad/* + out/board_checks.json updated.
2. oss container BEL-control run pid 3417405 (out/pnr/build/ctl_emp*) -
   finished rc=0.
Earlier: regen pid 3414953 was killed before completion (superseded).

## Owned files (only these; everything else is read-only to this worker)

- hardware/experiments/simple-tile/fpga/board/README.md (done)
- .../board/data/pins_gw1nz_qn48.json + pins_ice40up_sg48.json (provenance DB)
- .../board/tools/pincon_check.py, board_net_check.py, footprint_verify.py,
  run_board_pnr.sh
- .../board/constraints/tile_gw1nz_board.cst, tile_up5k_board.pcf
- .../board/kicad/ (board_gen.py, gen_footprints.py, pin_con_parse.py,
  lib/fpga_board.pretty/*)
- .../board/docs/{candidate.md, power_reg.md, readiness.md} (done)
- .../board/out/ (json/md/logs/pnr/drc)
- hardware/experiments/simple-tile/checkpoints/fpga-board.md (this file)
