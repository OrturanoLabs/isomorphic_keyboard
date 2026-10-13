# FPGA worker recovery history (consolidated from the former root checkpoint)

Updated: 2026-10-12 — FINAL (rev.2, post-review fixes applied and re-verified).

## Review round 2: what changed (real edits + reruns)

1. `tile_fpga.vhdl`: added `SNAP_MODE` generic — "fall" (default; negedge
   latch-clocked shadow = rev-A capture instant exactly) and "track" (sysclk
   sample; approximation). First-bit-before-first-clock is now combinational
   (pd(15) while latch high, shadow(15) until first shift edge). No async
   parallel-data FF anywhere.
2. Sim S8 added (tile_unit_tb): directed phase sweep of key changes in the
   last sysclk period before latch fall — CHARACTERISATION (labeled, not
   pass-equivalence). Measured: track shows stale bit at ALL 9 in-window
   phases (ref='1' vs dut='0', control=0); fall matches rev A at every phase.
3. run_sims.sh doubled the matrix across both modes → 35/35 PASS (rc=0).
4. Tops got SNAP_MODE + merged B/R clock into one clk_pin (exact 26-pin
   board budget; json shows 26 pads, BUFG shares clk pad). Track variants
   are separate top files since the ghdl plugin rejects `-g` generic flags.
5. run_synth.sh reran ALL SIX variants (RTL changed, so rerun required):
   6/6 bitstreams. gw1nz fall 254.84 MHz / track 193.80 MHz (nextpnr,
   interior); up5k fall 40.19 / track 40.74 MHz; lp8k fall 69.17 / track
   68.48 MHz (icetime, interior). fall builds drop OSCZ/SB_HFOSC cells.
6. SDC attempt (gw1nz): create_clock ACCEPTED (rc=0, log
   synth/results/logs/gw1nz_sdc.log); set_clock_groups UNSUPPORTED (probe
   recorded) → async latch↔clk crossing declared in text, NOT STA-closed.
   Interior cross report: negedge latch→posedge clk = 2.98 ns max delay.
7. Docs corrected: pin_budget (26 exact), clock_domains (CDC/metastability
   contract, what was/wasn't timing-checked), power_bom (logic-IC vs total
   BOM; UP5K/LP8K = SRAM config, NOT embedded flash; NVCM open programming
   unverified), alternatives (per-row config-storage claims, stale Fmax
   figures replaced with the measured rev.2 ones).

## One more check of commands actually run (rev.2)

- `sim/run_sims.sh` → rc=0, "SIMS PASS", 35/35 (summary.txt; sweep evidence
  in unit_track.log/unit_fall.log S8 lines).
- `synth/run_synth.sh` → rc=0, "SYNTH PASS (6 variants)".
- SDC probe: rc=0 after set_clock_groups removal (initial `//` comment and
  set_clock_groups failures recorded honestly in the log).

## Remaining gates (unchanged, explicit)

DS861/Lattice datasheet fetch (rails/JTAG-pad identity/OSCZ base freq/
startup), FF recovery window STA on real silicon, bench power (no open
estimator), 16-tile/20 MHz bench or external-model STA (interior-only Fmax
here), pad-pull bench check, per-device layout of the cst proposal. UP5K
NVCM: open programming path unverified → external flash until proven.

## Environment baseline (measured)

- Host: NO yosys/nextpnr/apicula/ghdl/iverilog on host PATH (all MISSING).
- Container flow confirmed: `localhost/oss-cad-suite:2026-09-26` image id
  `58f58619c735...` (same image the regression used). Contains:
  - Yosys 0.69+154 (ghdl-yosys-plugin works: `yosys -m ghdl -p "ghdl ..."`)
  - nextpnr-himbaechel 0.11.1-33-g1aea87ab (gowin uarch; nextpnr-gowin is
    superseded by himbaechel; `nextpnr-gowin` binary ABSENT but irrelevant)
  - nextpnr-ice40, nextpnr-ecp5, icepack, icetime, ecppack present
  - apycula installed (gowin_pack/gowin_unpack work; python lacks numpy/
    msgspec -> perf warnings only)
  - chipdb present for GW1NZ-1 (exact target family), GW1N-1/4/9/9C,
    GW1NS-4, GW2A-18(..), GW5A*, gatemate.
- KiCad flatpak 10.0.6 exists (not needed for this task).

## Probe RESULTS (real commands, container; /tmp/opencode/fpga-probe)

1. Exact device string `GW1NZ-LV1QN48C6/I5` ACCEPTED by nextpnr-himbaechel
   with chipdb-GW1NZ-1.bin -> open flow exists for the exact requested part.
2. VHDL->gowin: tiny tristate VHDL entity -> yosys synth_gowin maps to
   IBUF/LUT1/TBUF (true tristate supported) -> PnR+gowin_pack OK.
3. iCE40: same tristate -> synth_ice40 maps to SB_IO; UP5K (sg48) and
   LP8K (cm81 = TinyFPGA BX device) PnR+icepack OK. SB_HFOSC (UP5K 48MHz
   on-chip osc) full flow OK.
4. GW1NZ-1 on-chip oscillator: primitive OSCZ PnR OK; OSCH/OSCW/OSC have
   NO matching BEL on GW1NZ-1 ("no BELs remaining") -> use OSCZ (exact
   frequency per Gowin DS861, still unverified -> flagged in docs).
5. QN48 usable-IO probe (empirical, cst probe of pads 1..48):
   MISSING (power/etc): pins 1,2,12,25,26,36,37 -> 41 pads host IO bels.
   ~4 of those are JTAG-shared (gowin_pack --jtag_as_gpio flag exists;
   default pack did NOT error on all-41 design -> default-flag enforcement
   lenient; identify JTAG pad numbers against vendor pinout before layout).
6. gowin_pack produced 351954-byte .fs bitstream for the 41-pin probe,
   default flags, exit 0.

## Commands run so far (with real results)

- tool survey loops above (MISSING/FOUND lists), all recorded.
- probes 1-6 as above; logs in /tmp/opencode/fpga-probe/*.log (throwaway).
- Read (READ-ONLY): hardware/simulation/tile.vhdl (rev-A tile model),
  docs/architecture/protocol.md, simple-tile RESULTS.md, README.md,
  regression README/results/run harness + tile_reg_pkg.vhdl +
  tile_grid_tb.vhdl, logic/equivalence/ref_glue.vhdl + Makefile,
  logic/cpld/tile_full.vhdl (ATF1502ASV whole-tile candidate = structural
  template for tile_fpga.vhdl; its async-transparent '165 /PL is exactly
  what FPGA fabric cannot do).

## Design facts locked from references

- Frame wire order (16 bits, first bit before first clock):
  buttons(11)..buttons(0), markers '1','1', L_endrow, T_endcol.
- latch = B_latch OR R_latch (async, level-active; clears cnt+bw);
  w = T_W AND B_first; tclk = bclk when w=0 else Z; lclk = bclk when
  w=1 else Z; dsin = w ? L_data : T_data; B_W sticky: sets at rising edge
  where cnt==15 AND own dout=='1'; cnt wraps 16 ('161/'161-model 4-bit).
- 74x165 /PL is LEVEL-transparent async load -> FPGA replaces it with:
  shadow reg sampled on free-running sysclk while latch=1, frozen at
  latch fall ("snapshot at latch falling edge"), first-bit = shadow(15)
  combinationally before first shift clock, "first shift special load":
  first shift edge loads shreg <= shadow(14..0) & dsin.

## Running jobs

None.

## Sim RESULTS (rev.2, run 2026-10-12 ~13:20Z, container ghdl)

`run_sims.sh`: **35/35 PASS** (rc=0, "SIMS PASS"), logs in fpga/sim/logs/.
Per-mode coverage: unit S1–S8 + 13 topology pairs × {track, fall}, mutations
4/4 caught, sanity. S8 characterisation evidence in unit_track.log /
unit_fall.log (9/9 stale in-window vs 0 in fall; control matches).

(Supersedes the rev.1 run of 20/20 which had track-only coverage and the
too-strong "snapshot at latch fall" claim; the over-claim and the hidden
stale window were the review knobs.)

## Synth+PnR RESULTS (rev.2)

6/6 variants → bitstreams (run_synth.sh, SYNTH PASS). Details in
fpga/RESULTS.md and synth/results/logs/summary.txt. Interior Fmax (tool-
level only): gw1nz fall 254.84 / track 193.80 MHz; up5k 40.19 / 40.74 MHz;
lp8k 69.17 / 68.48 MHz. SDC: create_clock accepted, set_clock_groups not
supported by this nextpnr subset (recorded).

## Next steps

(none — task delivered)

## Task scope (as delegated, terse form)

Baseline 6572e0f (`rev-c` branch). Goal: FPGA-based single-PCB tile,
12 Cherry MX SMD hot-swap keys per tile, 18.36 mm equilateral lattice,
drop-in chassis tiles, no tile-side MCU/LED/Hall, rev-A per-tile logic,
acceptance 20 MHz shift clock / up to 16 tiles, strong open-toolchain
preference. TinyFPGA must be included in the alternatives evaluation.

Work items (in order):

1. Read existing simple-tile experiments (logic/, regression/, RESULTS.md,
   docs/protocol.md, hardware/simulation models) as references — READ-ONLY.
2. Survey installed open toolchain: yosys, nextpnr-*, apicula, GHDL, icestorm;
   record versions/availability; record MISSING tools explicitly.
3. Evaluate FPGAs with on-chip config (embedded flash): exact Gowin
   GW1NZ-LV1QN48 (usable I/O, rails, config/startup) plus all viable
   alternatives incl. TinyFPGA family (iCE40), ECP5/etc. vs. requirements:
   20 MHz actual shift clock, 16 tiles, one-PCB SMD tile. Open-flow support
   (yosys/nextpnr/apicula) verified against INSTALLED binaries.
4. Build synthesizable RTL of the per-tile glue preserving:
   - first bit valid BEFORE first shift clock,
   - snapshot-while-shifting (parallel load at latch edge without corrupting
     ongoing frame),
   WITHOUT async parallel-load FF (unsupported on FPGA fabric). Design:
   latch-edge snapshot into shadow register, first-shift special load,
   true tri-state clock outputs (mirror rev-A tristate SCLK behaviour),
   document the extra clock domain and its timing.
5. Self-checking TB vs original rev-A tile-model frames: changing keys during
   latch, counter/flag behaviour, reset, top/bottom clock mux, 16-tile chain
   zero-delay equivalence.
6. Run synthesis (yosys) and real PnR (nextpnr/apicula) IF installed;
   otherwise provide credible build scripts + explicit missing-tool/
   missing-device blocker statement. No unsupported 20 MHz hardware pass
   claims — zero-delay sim only establishes behaviour.
7. Exact pin budget + power/BOM comparison table vs ATF22LV10C exper. baseline.
8. Preserve partial work; keep this checkpoint current after each step.

## Ownership

- WRITE: `hardware/experiments/simple-tile/fpga/**` only.
- This checkpoint: `checkpoints/fpga.md` (repo root) only.
- READ-ONLY: everything else (logic/, regression/, connectors/, docs/,
  hardware/simulation/). No git commits, no installs, no orders.

## Environment baseline (to be measured)

Pending; will record yosys/nextpnr/apicula/ghdl versions after tool survey.

## Commands run so far (with real results)

- `git log --oneline -5` in repo -> baseline 6572e0f confirmed
  ("Single-board tile: self-checking logic and drop-in connector experiments").
- `ls` of simple-tile/ and checkpoints/ -> fpga/ does not exist yet; creating.
- Read simple-tile/README.md, RESULTS.md, checkpoints/connector-next.md
  (reference study of prior worker scope/format).

## Running jobs

None.

## Next steps

1. Tool survey (yosys, nextpnr-ice40/-gowin/-himbaechel, apicula, gowin_pack,
   GHDL, iverilog) with versions.
2. Read rev-A tile model + prior RTL references under READ-ONLY scope.
3. Create fpga/ tree: `rtl/`, `sim/`, `synth/`, `docs/` (pinout/power/BOM),
   `results/`.
