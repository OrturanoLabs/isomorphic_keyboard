# Single-board tile: first experiment results

Historical first-round snapshot (`6572e0f`). The subsequent experiments and
review corrections are summarized in [FOLLOWUP_RESULTS.md](FOLLOWUP_RESULTS.md).

## Decision status

No candidate has 20 MHz system timing sign-off or hardware validation yet.

The leading reduced-part-count experiment is **ATF22LV10C-10 + two
SN74LVC165A + SN74LVC1G04 (four ICs)**. It restores the original tri-state
clock behavior, unlike the previous three-IC GAL design. Its equation model
passes functional comparison and its PLD assembles with open-source Galette.
Programming the exact low-voltage part remains unverified; equation simulation
does not independently verify the generated JEDEC fuse map.

Keep the discrete implementation with a **SN74LV161A counter** as the
no-programmer reference. This experiment does not prove nine ICs is the minimum
possible discrete implementation, nor establish a cheapest finished BOM.

The **ATF1502ASV one-chip candidate** passes behavioral comparison, including
transparent parallel load and the first bit before the first shift edge.
Generic synthesis is a structure proxy only. Device fitting, asynchronous
set/reset realization, pin assignment and fitted timing remain unverified;
the practical fitter dependency is proprietary.

## Independently rerun checks

| Experiment | Result | What it establishes |
|---|---|---|
| Original tile-model topology regression | 19/19 checks; includes four caught mutations | Frame order, presence flags, routing and reset in zero-delay simulation |
| Glue/candidate comparison | 344 frames, 261,716 samples, zero unexplained mismatches | Equation/RTL behavior; three-IC GAL's 3,630 Z-versus-low differences are counted explicitly |
| Clock-selection hazard probe | Reference/three-IC/corrected top-clock edges: 2/3/2 | Characterizes a difference; not an insertion or timing safety proof |
| Connector study | 64/64 checks | Assumption-bound 2D clearances, interface inventory, cap geometry and passive detection graph |
| Three connector concept coupons | Each: zero DRC errors, zero unconnected items | PCB-rule/connectivity checks of the coupons, not complete tile routing or manufacturing readiness |

Functional simulation uses the unchanged `hardware/simulation/` models. A
20 MHz stimulus in these models does **not** establish 20 MHz hardware operation.

The supported examples include 16-high columns, 16-wide rows, 4x4 tiles and
unequal column heights. Gap experiments show that tiles above a column gap can
be silently omitted; a missing bottom tile can instead produce a malformed
frame. Do not promise arbitrary placement or perfect error detection.

## Timing findings

`logic/timing/timing.json` records datasheet values and explicitly unknown
system inputs. `calc_timing.py` distinguishes component-only constraints,
provisional CPLD estimates and populated system bounds.

- The original HC161 has no 3.3 V timing column in the audited datasheet;
  LV161A supplies a characterized alternative for the discrete experiment.
- ATF22LV10C **-10** deserves priority over **-15**. In a synthetic example
  adding 1.5 ns each for clock/data interconnect, the -15 hop becomes negative;
  this is sensitivity analysis, not measured interconnect data.
- Controller launch and return delays matter: the component-only half-period
  return budget is tight after including the FPGA clock-output delay.
- Default system setup, latch propagation/recovery and other missing-input
  checks remain UNKNOWN. Generic CPLD sums are not fitted STA.

Still required: actual controller phase/STA constraints, min/max interconnect
and loading, output-enable hazards across topologies, first-bit settling,
latch timing for a 16-tile chain, power/SI and independent bench measurements.
The present controller's storage, coordinates and cadence do not implement the
new 16-tile/20 MHz acceptance target.

## Drop-in connection findings

The corrected study carries the full rev A directional interface: **28
directional contact positions**, with shared nets and removable-neighbor
presence straps represented explicitly. Underside contact pads fit in the
studied lattice, using custom hexagonal caps; ordinary square caps of width
pitch-minus-gap overlap the adjacent rows.

Neither evaluated spring is selected: S1941-42R fails body packing and
S1971-46R fails the conservative height budget. Find a part meeting both, or
revise chassis geometry. Ground pads at rail ends do not guarantee ground-first
mating; contact-height sequencing remains open. The STEP height is a bound,
not a verified assembled 3D clearance.

Only the measured mezzanine examples were evaluated. The tested 30-position
DF12 alternative needs a board extension and socket relief; it is a geometry
reference, not a purchasing recommendation (series lifecycle concern).

Coupon files are in `connectors/out/coupons/`. They lack schematic/ERC and
complete assembly verification, so are **concepts, not fabrication releases**.

## Reproduce from the repository root

```sh
bash hardware/experiments/simple-tile/regression/run_regression.sh
tools/oss.sh make -C hardware/experiments/simple-tile/logic/equivalence equiv hazard
python3 hardware/experiments/simple-tile/logic/timing/calc_timing.py --selftest
python3 hardware/experiments/simple-tile/logic/timing/calc_timing.py
bash hardware/experiments/simple-tile/connectors/run.sh
```

GHDL/Yosys use the existing `localhost/oss-cad-suite:2026-09-26` image; the
verified image ID is recorded in the regression results. Connector generation
uses the installed KiCad Flatpak (10.0.6 in the verified run); its version is
recorded in `connectors/out/versions.txt`. Flatpak is not version-pinned by this
experiment. Galette assembly commands/results are recorded under
`logic/pld/results/galette_log.md`; toolchain and vendor-document provenance
are recorded in the worker checkpoints and timing database.

No new SPICE sign-off, assembled prototype, price comparison or full-tile
DRC result is claimed here. The next gates are exact-part programming,
connector selection/3D fit, timing-aware chain tests and electrical validation.
