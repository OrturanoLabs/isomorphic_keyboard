# Single-board tile: implementation and timing follow-up

Baseline commit: `6572e0f` — Single-board tile: self-checking logic and drop-in
connector experiments. This follow-up advances all four logic families plus
connection and validation work. No candidate is a fabrication release or a
20 MHz / 16-tile hardware sign-off.

## Current candidate comparison

| Candidate | Implemented evidence | Remaining gate |
|---|---|---|
| Discrete LVC + LV161A + two LVC165s | Pin-level circuits, key mapping, behavioral checks, fully placed nine-IC prototype | Complete routing, corrected tiled-outline integration and electrical validation |
| Four-IC ATF22LV10C-10 SPLD | Generated JEDEC decoded and compared with equations; pin-level simulation; partial placement | Exact-part programming and GAL package placement; minimum-pitch fixed-lane layout does not fit |
| One-logic-chip ATF1502ASV CPLD | Verilog comparison, 44-pin capability plan, deterministic device-shaped EDIF | Actual fitter/macrocell allocation, STA, programming and board placement |
| One-logic-chip tiny FPGA | Behavioral comparison, synthesis and routed bitstreams through open tools on three device families | Latch-to-clock timing, exact rails/configuration/pin verification, power and board placement |

"One logic chip" is not a total BOM claim. Regulators, configuration storage,
passives and programming access depend on the exact FPGA part. No prices were
verified, so no cheapest-finished-design ranking is claimed.

The tiny FPGA is explicitly retained. It currently has the most complete
open *implementation* flow among the programmable candidates, while discrete
logic remains the no-programmer reference. The CPLD path's proprietary fitting
dependency is recorded rather than concealed.

## Functional and implementation evidence

### FPGA

`fpga/` contains two implementations of the parallel-load snapshot:

- **fall**: captures on the merged latch falling edge; supplies the first bit
  before any shift clock and uses a special first shift. This is the current
  default. The latch is an extra clock domain requiring explicit timing work.
- **track**: the previous oscillator-sampled approximation. A phase-sweep test
  demonstrates stale samples in nine of nine selected last-sample-to-latch-fall
  windows. This is characterization, not equivalence for unrestricted inputs.

Independent rerun: **35/35 checks**, including four caught mutations. Real
open-flow synthesis, place/route and packing reproduced **six bitstreams**:
two modes on GW1NZ-LV1QN48, iCE40UP5K-SG48 and iCE40LP8K-CM81. The last part is
the TinyFPGA BX device, not a proposed whole development module per tile.

Tool-reported interior timing does not cover external links or prove the
asynchronous latch/shift relationship. GW1NZ exact rail and programming-pad
verification remains open. iCE40 parts are SRAM-configured; external flash or
an independently verified NVCM programming path must be accounted for.

### Discrete / SPLD

The full worker suite passed **33 configurations**. Independent review reran
key mapping and the **18-case quick suite**. The corrected SPLD JEDEC is now
decoded: checksums and twenty Boolean-function comparisons match for both the
original and corrected maps. This advances beyond source-equation simulation.

The nine-IC discrete implementation is a tested partition, **not a minimum
proof**. Surveyed count-neutral substitutions do not establish a global bound.

The regenerated discrete placement has all parts placed; the SPLD prototype
still lacks a placed GAL at minimum pitch. Both report zero error-severity DRC
violations but retain **175 / 129 unconnected items**, respectively: they are
unrouted placement prototypes, not DRC-complete tiles.

With the fixed aggregate contact lanes, the studied 180-degree socket rotations
did not rescue GAL placement. A relaxed-pitch study reports a possible
**approximately 18.91 mm** placement with same-tile and six-neighbor checks;
that case requires connector rebudgeting and full layout validation. These
placement boards have not yet been integrated with every subsequent corrected
outline/assembly constraint.

### CPLD

Independent simulation and pin-checker reruns passed. The candidate testbench
reports **1,180 comparisons**, with synchronous-load and flag-swap mutations
caught. Synthesis reproduces deterministic EDIF and explicitly stops before
device fitting. A user-provided licensed-fitter wrapper exists; no fitter or
Wine was installed and no device-fit or STA success is asserted.

## Dense-layout drop-in connection

`connector-next/` replaces the earlier extra detection straps with rev A's
existing passive presence signals. The dedicated scheme uses **19 contacts**;
the separate per-leg termination scheme uses **21**. These are scheme budgets,
not universal minimum claims: a donor-fan-out study also found an electrically
working 18-contact option, with a different single-fault coupling tradeoff.

Every slot in the 16-slot graph is removed in turn to check that neighboring
presence inputs become absent without a permanent ground path.

The supported dense-layout branch is **compact spring contacts on tiered
chassis rails**, using studied Harwin S1971-46R / S1961-46R geometry. Land-pattern
dimension extraction is recorded; drawing confirmation, contact alignment,
compression, durability and assembled fit remain physical gates. Ground-first
mating is not guaranteed by the studied tolerance/tilt envelope.

Review found and corrected two important geometry errors:

1. The first-round stepped outline overlapped its vertical neighbor. The new
   study uses the rev-C construction with vertical margin R/2 and checks six
   neighboring board outlines.
2. A connector tab that fits an isolated tile can collide with its neighbors.
   Widening the outline inset separates polygons but can remove PCB material
   under switch holes. Rechecking those holes rejects all tested tab remedies
   at the fixed minimum-pitch geometry. **No tested mezzanine-tab solution is
   currently qualified for the dense array.**

The in-production DF40 candidate retains useful STEP-derived footprint evidence
but needs a non-tab placement and complete receptacle verification. DF12's
lifecycle concern and the measured Gecko parts' through-board tails are recorded.

Three next-round connector coupons pass zero-error/zero-unconnected DRC, but
lack complete schematic/ERC and assembly verification. The mezzanine coupon
is isolated concept geometry, not evidence it tiles.

## Timed chain and SPICE findings

Independent full timed-chain rerun: **16/16 checks**, including five deliberately
failing timing cases caught with their expected assertions. The drift guard
matches **34/34 constants** to the datasheet timing database. The tested paths
include a 16-high column and larger stress configurations.

At the modeled max corner with a synthetic 1.5 ns route delay, the 50% clock
duty case fails the column-switch timing assertion. The successful modeled
case requires approximately **28 ns high time in a 50 ns period**. This is
scenario evidence, not a universal duty-cycle specification: output-enable
minimum delays, some recovery cells and real interconnect behavior are missing.

The 20 MHz ngspice burst sweep reports **9 case-checks meeting the selected
budgets and 15 failing**. The attempted independent rerun exceeded the terminal
tool's 300-second limit, but its container continued; the worker recovered the
completed output from journald and verified agreement with the previous and
hardened runs. Per-case progress and time limits now preserve expensive work.

None of the swept resistors satisfied the selected clock-far-node budgets in
the tested rev-B geometry. This is a reason to revise and validate the clock
tree/return path, not proof hardware cannot run at 20 MHz. The model remains
typical-corner IBIS-lite with assumed budgets and lossless interconnects.

## Reproduction entry points

From the repository root:

```sh
bash hardware/experiments/simple-tile/fpga/sim/run_sims.sh
bash hardware/experiments/simple-tile/fpga/synth/run_synth.sh
bash hardware/experiments/simple-tile/cpld-fit/sim/run_sims.sh
bash hardware/experiments/simple-tile/cpld-fit/synth/run_synth.sh
python3 hardware/experiments/simple-tile/cpld-fit/constraints/check_pins.py
bash hardware/experiments/simple-tile/timing-chain/run_timing_chain.sh
bash hardware/experiments/simple-tile/timing-chain/si/run_si.sh
bash hardware/experiments/simple-tile/connector-next/run.sh
```

For the pin-level circuit suite, run `python3 tools/sim_tile.py --quick` from
`discrete-spld/`; the full suite takes several minutes. Exact tool versions,
commands and recovery provenance are saved in the workstream results and
checkpoints. Hardware measurement, current BOM quotes and final tile routing
are still required before choosing a production design.
