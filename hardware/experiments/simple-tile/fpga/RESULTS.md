# FPGA tile experiment: results (rev. 2, post-review)

Status: behavioural equivalence demonstrated in zero-delay simulation for
TWO snapshot modes, with an explicit **characterised** approximation window
for the sysclk-tracked mode; real synthesis + place & route to bitstreams on
three device families for both modes (6 bitstreams). **No hardware built; no
20 MHz system sign-off; no full timing closure.** Zero-delay sims establish
behaviour only; tool Fmax is FPGA-interior only.

## Verdict (corrected wording)

A GW1NZ-LV1QN48 FPGA tile is **viable as a one-logic-IC design** with a fully
open build *and* production programming flow (yosys → nextpnr-himbaechel →
gowin_pack → openFPGALoader; GW1NZ-1 listed by idcode). It is NOT a
"one-part, free rails" device: the core LDO (+1 BOM) and the unverified QN48
rail/pin taxonomy vs Gowin DS861 remain open. The UP5K/LP8K alternatives are
SRAM-config parts — NOT embedded flash — so they carry a config-storage BOM
line (external SPI flash, or OTP NVCM whose open-flow programming is
unverified here). See docs/power_bom.md for the split.

## Snapshot semantics (the review-corrected core claim)

The 74x165 async parallel load has no FPGA equivalent. `tile_fpga` offers:

- `SNAP_MODE="fall"` (default): shadow clocked by the latch falling edge →
  snapshot at the exact rev-A instant; combinational pd(15) during latch →
  exact first-bit/transparency; small extra cost = 16 shadow FFs (negedge
  latch-clocked: DFFN/DFF-with-INVCLK appear in netlists). Requirement:
  parallel word stable through the fall (recovery window), documented, not
  STA-closed.
- `SNAP_MODE="track"`: shadow sampled on sysclk while latch high → snapshot
  = last sample before the fall, i.e. up to one sysclk stale. This is an
  APPROXIMATION, NOT an exact match for all rev-A admissible key changes.

Directed phase-sweep characterisation (`tile_unit_tb.vhdl` S8; NOT a
pass-equivalence test): for key changes inside the final sysclk period before
the latch fall, the track mode keeps the stale value (measured: 9/9 phases
show ref='1' vs dut='0'; control outside the window matches) while fall mode
matches the reference at every phase (0 mismatches). Quasi-static keys do not
waive the latch/sysclk metastability/recovery contract — see
docs/clock_domains.md.

## Self-checks (GHDL, container id 58f58619c735...)

`sim/run_sims.sh`: **35/35 PASS** (`sim/logs/summary.txt`).
Unit S1–S7 + S8 characterisation in both modes; 13 paired-grid topologies
(stream bit-exact vs docs-derived frames AND per-edge REF=DUT equality incl.
B_W timing and Z-clock mux) **per mode**; 4/4 DUT mutations caught; sanity
re-pass. Includes column16/grid4x4 (the 16-tile shapes) and ragged equality.

## Synthesis + place & route (real runs; results/logs/)

| device+mode | bitstream | IO cells | interior Fmax (tool) |
|---|---|---|---|
| GW1NZ-LV1QN48C6/I5 fall | gw1nz_fall.fs 351954 B | 26 pads (TBUF×2; BUFG shares clk pad) | 254.84 MHz (nextpnr) |
| GW1NZ-LV1QN48C6/I5 track | gw1nz_track.fs 351954 B | 26 + OSCZ used | 193.80 MHz (nextpnr) |
| iCE40UP5K-SG48 fall | up5k_fall.bin 104090 B | 26/39, 15 SB_DFFN, HFOSC 0 | 40.19 MHz (icetime) |
| iCE40UP5K-SG48 track | up5k_track.bin | 26/39, SB_HFOSC used | 40.74 MHz (icetime) |
| iCE40LP8K-CM81 fall (TinyFPGA BX dev) | lp8k_fall.bin 135100 B | 27/63 incl. sysclk pin | 69.17 MHz (icetime) |
| iCE40LP8K-CM81 track | lp8k_track.bin | 27/63 | 68.48 MHz (icetime) |

SDC attempt (gw1nz): `create_clock` on shift/latch pins ACCEPTED (pack-only
rc=0; results/logs/gw1nz_sdc.log); `set_clock_groups` UNSUPPORTED by this
nextpnr's SDC subset → the async latch↔clk crossing is declared in text and
deliberately NOT STA-closed (docs/clock_domains.md). Interior cross-domain
report latch→clk: 2.98 ns max delay (gw1nz fall log).

## Pin budget (corrected)

26 user IO exact (clk merged — the rev-A board itself shortens B_clk/R_clk);
+1 sysclk pin only for LP8K-track. Full table + empirical pad censuses:
docs/pin_budget.md.

## Open gates (remaining, explicit)

1. Gowin DS861 (QN48 rail/power-pin identity, JTAG-shared pads, OSCZ base
   frequency, power-on-to-user time) and Lattice NVCM/config specifics —
   vendor doc DB fetch failed (marketing pages only).
2. Latch-as-clock FF recovery / metastability window: needs real STA + bench;
   interior-only numbers here. Controller/latch cadence budget on a real
   16-tile chain: UNKNOWN (with ../../logic/timing).
3. Power: no estimator in the open flow; bench/vendor-calc needed.
4. Pad pull behaviour on hardware; cst is a legal proposal, not routed board.
5. UP5K NVCM: open programming path unverified → external flash until proven.
