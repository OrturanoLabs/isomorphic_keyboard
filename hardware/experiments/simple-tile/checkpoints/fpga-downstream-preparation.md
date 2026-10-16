# Checkpoint: fpga downstream preparation reconnaissance (FPGA-02/03/04)

Updated: 2026-10-14. Read-only survey; **no task activated, no task completed.**
FPGA-01 remains in progress (board/** owner, untouched here). Ordered tasks
FPGA-02..04 stay PENDING. Owned file: this note only. Evidence below is quoted
from actual code/logs, not from the plan.

## Scope verified by reading code (paths)

- Controller: `firmware/ice40/scan20/{src,sim,synth,README.md,RESULTS.md}`
  — 24/24 sim; f60 bitstream closes interior STA (icetime 60.91 MHz, thin);
  pcf pins BOARD_CLK=31/ DATA=34/ LATCH=38 (golden-identical pico-ice wiring).
- Tile chain model: `hardware/experiments/simple-tile/fpga/system/`
  (`vhdl/chain_sys_tb.vhdl`, `vhdl/tile_sys.vhdl`, `cfg/corners.json`,
  `results/machine.json`, `results/report.md`, `run_system.sh`) — 33/33 PASS,
  synthetic corners, explicitly not sign-off.
- Tile core port contract: `fpga/rtl/tile_fpga.vhdl` (4 edges, TBUF T_clk/L_clk,
  latch-OR, merged dout); 26-IO pin plan `fpga/docs/pin_budget.md` +
  `fpga/synth/tile_gw1nz.cst`.
- Golden protocol: `docs/architecture/protocol.md`, `firmware/ice40/src/top.vhd`
  (16 clocks/frame, no tail, sticky error).

## Interfaces / topologies actually supported

- W x H grid of tile_sys, controller at bottom of right-most column 1
  (protocol walk: columns right->left, tiles bottom->up — chain_sys_tb +
  tile_reg_pkg). Verified grids in fpga/system: N=1/2/16xH4, 1x16, 4x4;
  scan20 sim additionally: 1x1, 1x2, 3-col mixed 4/2/1 (mix34), marker-inject,
  watchdog timeout.
- Presence straps: T_first/B_endcol/R_endrow hard GND on tile PCB
  (tile_fpga.vhdl:142-144); Gowin pads carry UP+DOWN pulls, zero-BOM
  (pin_budget.md); three dedicated presence contacts share tile GND, chassis
  traces isolated (FPGA-01's scheme; not re-inspected here).
- Chassis variant: 19-contact aggregate spring-pad scheme (checkpoints/
  connector-next.md: S1971-46R/S1961-46R, tiered rails, agg19 coupon DRC
  0/0); mezzanine branch placement-rejected. Physical fit NOT validated.

## Concrete integration gap (FPGA-03 task 1) — what is and isn't done

- chain_sys_tb drives the grid with its OWN behavioral driver/sampler
  (latch->guard->`nbits=nfr*16+TAIL` pulses, TAIL=32 default) — NOT the
  scan20 RTL. scan20's own tb drives UNTIMED tile cores. Neither covers the
  actual-controller x timed-chain combination: first-bit capture at the real
  66.7 ns guard, 33.33/16.67 duty with W-switch hazards, 16.67 ns lead at
  the real DATA-SETTLE point, per-frame ST_FRAME/ST_ACT/ST_GAP gaps (~83 ns).
- scan20 emits EXACTLY 16 clocks/frame (ST_BIT bit_cnt<=16; ST_GAP relaunch),
  no tail. exp_clk_loc in chain_sys_tb bakes nbits incl. TAIL into bottom-tile
  counts — integrated TB must pass TAIL=0-equivalent expectations; upper tiles
  (`16*(hc-1)`) are tail-independent already.
- Zero-new-code preliminary check runnable TODAY in the existing harness
  (scan20 timing tuple as TB generics):
  ```sh
  cd hardware/experiments/simple-tile/fpga/system
  ../../../../tools/oss.sh bash -c '
    ghdl -a --std=08 -fsynopsys --workdir=results/build \
      ../../regression/tile_reg_pkg.vhdl vhdl/system_timing_pkg.vhdl \
      ../rtl/tile_fpga.vhdl vhdl/tile_sys.vhdl vhdl/chain_sys_tb.vhdl &&
    ghdl elab-run --std=08 -fsynopsys --workdir=results/build chain_sys_tb \
      -gNAME=pos_n1x16_scan20duty_max -gW=1 -gH=16 -gCORNER=2 -gTAIL=0 \
      -gCLK_HIGH_100PS=333 -gCLK_LOW_100PS=167 -gLEAD_100PS=167 \
      -gGUARD_100PS=667 -gLWIDTH_100PS=10000 --stop-time=60ms'
  # expect SYSPASS; sweep W/H/corner (fit/min/max, W=2/16 H=4, 4x4)
  ```
  (guard 66.7 > 50 ns deep-col bound; high 33.3 > 30 ns r30 finding;
  lead 16.7 inside 1..30 ns window — current machine.json numbers.)

## Likely timing/protocol deficiencies to probe first

- **Asymmetric duty never run**: all chain positives 50/50 or 60/40; f60's
  2h+1l = 33.33/16.67 untested against RELEASE-HIGH/ENABLE-HIGH/W-LOWPHASE
  (TMARK WPHASE ~6 ns fit/~13 ns max after rise; slack to fall ~20 ns — ok in
  principle, unrecorded).
- **BOARD_DATA has no synchroniser** (scan20_core.vhdl:66): valid only if the
  chain return settles 16.67 ns before the next launch; synthetic arrival
  9–14 ns (report.md) leaves ~19 ns settle margin — unmeasured on hardware.
- **thin interior margin**: f60 icetime 60.91 MHz vs 60.00 (RESULTS.md); no
  PVT guard band; SDC marks latch/sysclk crossings async (fpga synth note).
- **f60 fixed floors depend on synthetic values**: t_padin/out, TBUF en/dis,
  route_hop, recovery — all "unknown:true" in machine.json; must be re-based
  from the ROUTED board + production pin map (FPGA-03 task 2 needs
  extract-style numbers from FPGA-02 artifacts, currently nonexistent).
- Error path on hardware: sim-only marker inject; bench recovery behaviour
  (partial contact during scan) is uncharacterised.

## Tools for strict 2/4-layer routing (FPGA-02 prep, all in-tree)

- Freerouting 2.4.1 container: `tools/containers/freerouting` (Java 25; run
  `-de x.dsn -do x.ses -mp 40 --gui.enabled=false`; cap `--memory 2500m` +
  `JAVA_TOOL_OPTIONS=-Xmx1500m`). Traps recorded in docs/LEDGER.md: no SMD-to
  -plane connection (scripted fan-out first), optimiser overrun (kill), own
  violation count != KiCad DRC — always gate with `tools/kicad-cli.sh` DRC.
- KRT container: `tools/containers/kicad-routing-tools`; rev-B comparison
  done, pipeline default ROUTER=freerouting (docs/LEDGER.md 2026-09-27).
- Strict-geometry prober patterns reusable: `discrete-spld/layout/
  {repair_opens.py,tools/probe_*.py,drc_digest.py,fix_routed.py,
  build_4layer.py,finish_4layer.py,tiling_check.py}` — rules 0.2/0.2 mm,
  via 0.6/0.3, snpc 0.3, hole-hole 0.25, edge 0.6 (readiness.json);
  `tools/scripts/check_via_in_pad.py`, `check_invariants.py`.

## Realistic FPGA-04 bench acceptance (draft, hardware-gated)

1. Program: pico-ice scan20 f60 via dfu-util (Makefile flow, USB 1209:b1c0);
   each GW1NZ tile .fs via JTAG — openFPGALoader support for GW1NZ-LV1QN48
   SRAM AND internal flash must be verified (`openFPGALoader --detect`);
   fallback vendor tool would break the open-toolchain preference.
2. Tile bring-up: rails/core current per tile x3; persistent-flash boot by
   power-cycle, chain responds unassisted.
3. Low-clock functional first (needs a slow scan20 config variant — decision
   below), then f60 20 MHz; arrangements: row, column, L on the chassis
   coupon; frame/key/topology vs tile_reg_pkg expectations.
4. Waveforms at receiver measurement points (FPGA-02 must place them):
   BOARD_CLK return at controller pin vs launch (33.3 ns bit cell), edges,
   overshoot; margin sweep by re-synthed LEAD/GUARD config variants.
5. Error recovery: disturbed contact mid-scan -> red LED + auto-retry clean.
6. Contact mechanics: compression/resistance/insertion cycles.
7. 16-tile acceptance after 3-tile pass (needs 16 fabricated tiles).

## Design decisions needing review before FPGA-02/03/04 execution

1. Integrated TB shape: instantiate scan20_core in a chain_sys_tb derivative
   reusing all passive monitors, vs extend scan20_tb with timed tiles;
   TAIL/edge-count rebasing (item above) either way.
2. Bench observability: scan20 exposes LEDs only; frames not externalised.
   Option A: RP2040 UART bridge top variant; option B: logic-analyser decode
   of BOARD_*+dbg. Acceptance evidence depends on this choice.
3. Low-rate bring-up build for FPGA-04 step 3 (slow config via the existing
   cfg_f*.vhdl mechanism) vs direct 20 MHz.
4. GW1NZ programming ownership: which host tool is authoritative at bench.

## Blockers only physical tools/fabrication can close

- Oscilloscope/probing adequate for ~1-2 ns edges; logic analyser or bridge.
- Spring-contact parts + chassis-coupon/tile fabrication and assembly;
  contact force/resistance fixture; 16-tile set.
- Real pad/TBUF/hop numbers measured off the routed board (feeds
  machine.json; today they are declared unknown).
