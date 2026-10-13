# scan20 — actual results (no claims beyond these numbers)

Dates: 2026-10-12 baseline recon, 2026-10-13 implementation+runs.
Wireguard remote environment for the record:

- container `localhost/oss-cad-suite:2026-09-26`:
  Yosys 0.69+154, Nextpnr nextpnr-0.11.1-33-g1aea87ab, GHDL 7.0.0-dev,
  python 3.11.6 (py3bin), Linux 7.2.8-arch1-2 x86_64
- host fallback `~/.local/share/oss-cad-suite`:
  Yosys 0.63+89, nextpnr-ice40 0.9-102, GHDL 7.0.0-dev, python 3.14.7

All functional sims and the PnR numbers below were run in the CONTAINER
and cross-checked on the host; both agree (host f60: nextpnr 62.61/63.60
MHz PASS, icetime 16.63 ns = 60.14 MHz PASS).

## Simulation: 24/24 expectations PASS (exit 0)

`bash firmware/ice40/scan20/sim/run_sims.sh` — logs in `sim/build/logs/`.

Positive grids, each at BOTH exact configs (f60: 3 ticks/bit 2h+1l;
f120: 6 ticks/bit 4h+2l — same 33.33/16.67 ns phases, 20.000 MHz shift):

| grid | tiles/frames | episodes | clean | errf | errt |
|------|--------------|----------|-------|------|------|
| n1x1          | 1x1   / 1  | 2 | 2 | 0 | 0 |
| col2          | 1x2   / 2  | 2 | 2 | 0 | 0 |
| col16 (deep)  | 1x16  / 16 | 2 | 2 | 0 | 0 |
| g4x4          | 4x4   / 16 | 2 | 2 | 0 | 0 |
| mix34 (mixed height: 3 cols of 4/2/1) | 3x4 / 7 | 2 | 2 | 0 | 0 |
| inj_col2 / inj_4x4 (marker bits 3,2 forced 0 in one frame of episode 1) | / 2,16 | 3 | 2 | 1 | 0 |
| tmo (watchdog < natural episode)       | 1x2 / - | 2 | 0 | 0 | 2 |

Checks per run: every sampled bit vs the docs-derived stream; every frame's
data+coords+(0-based index) vs the walk; exactly 16 launches == 16 samples
== 16 BOARD_CLK rising edges per frame (no extra/missing pulse, incl. the
16th completing before frame work); exact tick-level duty (high ==
TICKS_HIGH, glitch/runt async monitor in the time domain); latch width ==
LATCH_TICKS; latch-fall->first-launch == GUARD_TICKS; sample->launch lead
== SAMPLE_LEAD_TICKS +/-0; latch-reload: two clean episodes bit-identical;
marker-error injection: aborted episode accounted (16*(INJ+1) edges/
samples), quiet recovery, auto-retry, following episodes clean; watchdog
mode: bites, quiet, retries, never a scan_done.

Negative configs caught by REAL assertions (4/4): THI=1 breaks the armed-
fall config assert; GUARD=2 breaks the lead-fits assert (both also below
the chain/model floors); LEAD=4@f120 breaks the tb sample-lead window
(>28 ns); LATCH=1@f120 breaks the armed-exit latch assert.

DUT mutants caught by runtime assertions (4/4): sample moved to the launch
tick -> "sample->launch lead is 0 ticks"; broken 16th-pulse condition ->
bound check / pairing failure; fall arm one tick late -> exact-duty
assert; row-walk broken -> coordinate mismatch.

## UP5K (sg48) synthesis / place+route / STA — explicit per-config --freq

`bash firmware/ice40/scan20/synth/run_synth.sh` — artifacts in
`synth/build/<cfg>/` incl. JSON/asc/bin, PLL bitstream params verified
against icepll for every config (fail-hard on mismatch).

| config | sysclk (bitstream-verified) | nextpnr interior Fmax | icetime interior | verdict |
|--------|--------------------|-----------------------|------------------|---------|
| **f60**    | 60.000 MHz exact (DIVF=79 DIVQ=4) | **61.44 / 66.01 MHz PASS at 60.00** | **16.42 ns = 60.91 MHz; 16.67 ns constraint PASSED** | **CLOSED — chosen** |
| f120   | 120.000 MHz exact (DIVF=79 DIVQ=3) | max 66.05 / 68.57 MHz | — | does NOT close at 120 |
| f100p5 | 100.500 MHz (100.0 infeasible)  | max 62.50 / 69.19 MHz | — | does NOT close at 100.5 (and would be 20.100 MHz, +0.5%) |

f60 device utilisation: 190/5280 ICESTORM_LC (3%), 1/1 PLL, 9/39 SB_IO,
1/8 SB_GB. f60 cross-corner spread observed across seeds/tools on the
host: 60.14-66.01 MHz interior.

Auxiliary paths reported by nextpnr for f60: `<async> -> sysclk` max
11.07/12.57 ns (RESET_N release; asynchronous by design, synchronous
deassert pipe), `sysclk -> <async>` max 8.09/8.17 ns (LED/pad outputs).

## External gaps (explicit, unchanged by any number above)

- The STA above is the FPGA fabric only. The external chain — BOARD_CLK /
  BOARD_LATCH / BOARD_DATA pads, board traces/cables, connectors, the
  SN74LVC165A-class tile electronics and their setup/hold/recovery — is
  NOT in this STA. No physical-signoff statement is made or implied.
- The adopted guard/lead/duty floors (guard >= 50 ns for a 16-deep column,
  lead 1..30 ns, high >= 22 ns) come from the fpga-system SYNTHETIC
  corners exploration (machine.json), itself explicitly not sign-off.
- f60's interior margin over 60 MHz is thin (60.91 MHz by icetime;
  61.44-66.01 MHz by nextpnr corners/seeds). It is a routed-netlist
  estimate at tool-default corners; there is no added PVT margin, and the
  bitstream has never been flashed or measured on hardware.
- scan20 is a test fixture: no MIDI synthesis, no UART; PACKAGE_MIDI is
  parked at the golden idle level only.

## Reproduce

```sh
bash firmware/ice40/scan20/sim/run_sims.sh    # 24/24 PASS, exit 0
bash firmware/ice40/scan20/synth/run_synth.sh # f60 CLOSED summary, exit 0
```
