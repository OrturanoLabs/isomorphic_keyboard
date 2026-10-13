# FPGA-tile chain: timing-aware system validation (fpga/system)

Timing-aware validation of the **FPGA-tile chain at 20 MHz**: a W x H grid
of timed FPGA tiles ([`tile_sys`](vhdl/tile_sys.vhdl), a wrapper adding pad /
TBUF / output / assertion timing around the UNMODIFIED golden core
[`../rtl/tile_fpga.vhdl`](../rtl/tile_fpga.vhdl), `SNAP_MODE="fall"` lead) on
the rev-A scan protocol, driven by a controller model with configurable
latch guard, 20 MHz clock duty and sample lead.

**This is synthetic-corner EXPLORATION, not hardware sign-off.** Interior
delays anchor to fitted nextpnr/icetime post-route max-analysis numbers
(verbatim extraction, [`tools/extract_delays.py`](tools/extract_delays.py) →
[`results/interior_delays.json`](results/interior_delays.json)); pad input/
output delays, TBUF en/dis, the per-hop interconnect, and the FF recovery
windows are SYNTHETIC or UNKNOWN by default ([`cfg/corners.json`](
cfg/corners.json) records the provenance of every value).

## Layout

- `tools/extract_delays.py` — fitted-anchor extraction from the existing
  `../synth/results/` logs/JSON (per-value source file + sha256).
- `cfg/corners.json` — explicit synthetic corner triplets + fixed 20 MHz
  controller numbers. `cfg/sources.json` — pinned sha256 of every read-only
  reference (golden RTL, golden frames, protocol doc, synth logs, cst).
- `vhdl/system_timing_pkg.vhdl` — the delay/requirement constants
  (transcribed from corners.json; drift guard enforces equality).
- `vhdl/tile_sys.vhdl` — timed tile wrapper + leaf assertions: SNAP-XDOM
  (fall-capture → first-shift cross-domain recovery budget, anchor 4.9 ns),
  SNAP-WINDOW (pd stability window at the local latch fall), CLK-PULSE.
- `vhdl/chain_sys_tb.vhdl` — W x H chain TB + 20 MHz controller. Checks:
  golden-frame stream (2 passes, bit-exact, first bit before first clock),
  B_W windows, true-Z clock selection (MUXSEL), per-tile resolved-clock
  exact edge counts (SPURIOUS-CLK), latch-OR fall counts (LATCH-GLITCH),
  W-switch phase hazards (RELEASE-HIGH / ENABLE-HIGH / W-LOWPHASE, plus
  TMARK WPHASE mid-high/low exposure), DS-VALID, CONTENSION, DATA-SETTLE
  (returning-data settle at the sample point) + arrival TMARKs.
- `vhdl/latch_or_tb.vhdl` — latch-OR source unit: B-only / R-only / skewed
  both (positives), glitch (falls twice) and snapshot-window negatives.
- `vhdl/track_cdc_tb.vhdl` — `SNAP_MODE="track"` sysclk-domain recovery
  contract sweep (>= 1 TSYS offsets asserted; < TSYS dead zone
  characterised) + short-latch negative.
- `run_system.sh` — full runner (container via `tools/oss.sh` falling back
  to host ghdl): drift guard, positive matrix (N=1/2/16x4, 1x16, 4x4 ×
  syn_min/fit/syn_max + route variants), negatives (each MUST fail on its
  named assertion token, not on infrastructure), guard/lead/duty/scale
  sweeps, then `results/make_report.py` → `results/machine.json` +
  `results/report.md`.

## Reproduce (from this directory)

```sh
python3 tools/extract_delays.py        # fitted anchors (verbatim)
python3 results/check_system_sync.py   # SYNC-PASS drift guard
bash run_system.sh                     # full matrix (see results/summary.txt)
bash run_system.sh quick               # 3-run smoke
python3 results/make_report.py         # machine.json + report.md
```

Results convention: a config passes iff GHDL exits 0 AND the log carries
`SYSPASS <name>`; negatives pass iff they fail with the expected
`TIMING-FAIL:<TOKEN>` and no SYSPASS. See
[`results/report.md`](results/report.md) for the measured limits and
[`results/machine.json`](results/machine.json) for the machine-readable
results/assumptions (incl. the 26-pin plan consistency).
