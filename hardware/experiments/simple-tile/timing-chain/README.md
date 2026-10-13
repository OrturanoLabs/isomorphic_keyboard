# Timing-aware rev-A tile chain experiment

A timing-aware VHDL model of the rev-A tile scan chain plus a 20 MHz burst
signal-integrity check of one tile-to-tile hop. It extends the zero-delay
behavioural regression (`../regression/`) from "the chain's function is right"
to "the documented 20 MHz timing actually closes, and if not, where".

**Scope statement (deliberate):** all interconnect delays are a fixed
*synthetic* 1.5 ns/hop (transport) or 0 (component-only). These runs are
**necessary-condition evidence, not hardware signoff**; nothing here claims a
20 MHz hardware pass.

## Layout

- `vhdl/chain_timing_pkg.vhdl` — datasheet min/max constants transcribed from
  `../../logic/timing/timing.json` (single source of truth; the drift guard
  below enforces it).
- `vhdl/logic74_timed.vhdl` — timed, self-checking models of the rev-A chip
  list: SN74LVC165A, SN74LV161A, SN74LVC2G08/2G32/1G04/2G125/2G126/2G74,
  with SER/flag setup+hold, SH/LD and ~CLR recovery, and clock pulse-width
  assertions. Outputs use transport delay so glitches propagate.
- `vhdl/tile_timed.vhdl` — rev-A tile wiring per `docs/architecture/protocol.md`
  (two '165s, '161 counter + RCO, W=T_W·B_first gate, flag AND/OR + '74
  sticky B_W, '125/'126 tri-state clock forward and data mux).
- `vhdl/chain_tb.vhdl` — W×H grid + controller (latch width/guard, clock duty,
  sample-lead configurable), checks against the unchanged golden frames
  (`../regression/tile_reg_pkg.vhdl`), per-net spurious-edge counters with
  exact expected counts, W-release/enable high-phase hazard monitors, DS-mux
  validity at every sampled edge, persistent-X contention monitors, and TMARK
  instrumentation (local edge actual times, latch forward arrivals, controller
  data arrival, release/enable margins).
- `run_timing_chain.sh` — matrix: positives (N=1/2/16×4 rows + 16-high column,
  min/max corners, route 0/1.5, cross-corners), intentional-failure cases
  (must fail with a TIMING-FAIL token and no TCREGPASS; a vacuous fail is a
  harness error), and guard/lead/duty sweeps vs N in both corners.
- `results/` — logs, `summary.txt`, `sweeps.txt`, `check_timing_sync.py`
  (drift guard), `make_report.py`, generated `report.md`.
- `si/` — 20 MHz burst SI extension of `hardware/si/tile_hop_ibis.py`
  (20 MHz clock burst + data pattern + W-release float), series R 0/22/33/47,
  per-edge threshold-crossing/dwell/overshoot checks, degenerate-deck
  selftest. Requires the vendor IBIS models in `si/models/` (fetched with
  `hardware/si/models/fetch.sh`; recorded in `si/models/` here) and the
  `localhost/ngspice` image.

## Reproduce

```sh
# from the repository root; GHDL inside localhost/oss-cad-suite:2026-09-26
bash hardware/experiments/simple-tile/timing-chain/run_timing_chain.sh         # everything
bash hardware/experiments/simple-tile/timing-chain/run_timing_chain.sh quick   # smoke test
python3 hardware/experiments/simple-tile/timing-chain/results/check_timing_sync.py
bash hardware/experiments/simple-tile/timing-chain/si/run_si.sh
python3 hardware/experiments/simple-tile/timing-chain/results/make_report.py   # regen report.md
```

Pass criteria of the TB: exit 0 **and** `TCREGPASS <name>` in the log; the
stop time is only a backstop (compilation/elab failures on negative runs are
harness errors, not catches).

## Method notes / known model limits

- Delays per path: corner-selected per path group (clk/latch/data) so
  anti-tracking cross-corners can run; SCALE_*_PCT inject synthetic stress.
- ten/tdis of '125/'126 have no datasheet MIN: min corner uses a documented
  0 ns lower bound; margins affected by that side are unsigned.
- '74 ~CLR→Q delay is not a published cell: modelled as the CLK→Q delay
  (labelled proxy; only affects when B_W clears during the long latch).
- LV161A has no published ~MR recovery in timing.json: unchecked by design.
- Tile inputs' pull resistors are modelled as rail-strength steps (no RC
  float time); the analog consequence of a release-while-low is covered by
  the SI float case instead.
- mux/B_W per-edge windows are checked on column 1 only (deep columns lag by
  design); deep columns are covered by stream comparison, exact edge counts,
  hazard monitors and an end-of-pass aggregate flag check.
