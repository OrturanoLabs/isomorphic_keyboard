# FPGA implementation plan — persistent task register

Updated: 2026-10-13. Implementation baseline: `b19aa80`.

**Next task: FPGA-01.** All four tasks below are pending. Work through them in
order; a task is completed only when its acceptance gate has recorded evidence.

## Objective and fixed scope

Produce a buildable single-PCB **GW1NZ-LV1QN48** tile, then validate it on
hardware at a **20 MHz shift clock**, ultimately with **up to 16 tiles**.
Preserve rev A's frame/topology contract, SMD MX-style hot-swap switches,
practical equilateral pitch and chassis-supported drop-in contacts.
No tile-side MCU, LEDs or Hall sensors. Prefer open hardware and an end-to-end
open build/programming toolchain; compare actual finished cost.

FPGA is the lead implementation. Discrete logic is a bounded reference effort;
SPLD/CPLD artifacts are retained findings, not active development tasks.

## Ordered register

- [ ] **FPGA-01 — Complete the electrical design** — pending; no dependency.
- [ ] **FPGA-02 — Route the FPGA tile** — pending; depends on FPGA-01.
- [ ] **FPGA-03 — Validate the complete digital system** — pending; depends on FPGA-02.
- [ ] **FPGA-04 — Build and validate a small hardware set** — pending; depends on FPGA-03.

### FPGA-01 — Complete the electrical design

1. Select the exact core regulator and verify its pinout, startup, decoupling,
   load capacity and thermal budget. The existing board has a placeholder LDO.
2. Create an authoritative KiCad schematic for FPGA rails, boot straps,
   programming access, key inputs and chassis contacts.
3. Reconcile schematic, circuit data, production pin constraints and board
   connectivity. Explicitly check every supply pin and the three dedicated
   presence contacts: bonded to GND on the tile, isolated as traces on the chassis.
4. Resolve the shared-versus-separate outbound termination/contact scheme
   before layout. The certified 19-contact geometry is the current baseline;
   any changed contact set needs renewed mechanical and detection checks.
5. Obtain a sourced BOM and assembly quote, distinguishing one logic IC from
   the total regulator/passive/programming cost.

**Acceptance gate:** complete schematic, clean ERC, selected purchasable BOM,
and passing schematic-to-board/pin/power/presence checks.

Starting point: `hardware/experiments/simple-tile/fpga/board/`.
Checkpoint: `hardware/experiments/simple-tile/checkpoints/fpga-01.md`.

### FPGA-02 — Route the FPGA tile

1. Route clock, returning data and latch paths with continuous ground returns
   and deliberate source termination, using the approved contact interface.
2. Compare two and four layers on routing feasibility, electrical quality and
   finished cost. Do not silently relax fabrication rules to finish routing.
3. Finish power distribution, decoupling, FPGA exposed-pad treatment,
   programming/test access and receiver-side measurement points.
4. Recheck socket/component/contact clearances and all six neighboring tiles
   using the corrected `TileTiling` construction.
5. Record routed lengths/loading assumptions, stack-up, DRC and netlist checks.

**Acceptance gate:** zero unconnected items, clean DRC, matching approved
connectivity, and reviewed power/return paths and assembly clearances.

Starting point: the FPGA placement prototype currently has 90 unconnected pairs.
Checkpoint: `hardware/experiments/simple-tile/checkpoints/fpga-02.md`.

### FPGA-03 — Validate the complete digital system

1. Connect the actual `scan20` controller RTL to the timing-aware FPGA tile-chain
   model, rather than relying only on separate controller/tile tests.
2. Update delay/loading inputs from the routed board and its production pin-map
   implementation. Keep unmeasured inputs explicit; synthetic corners are not
   hardware sign-off.
3. Cover sixteen-high columns, 4x4 arrays and supported unequal-height layouts:
   first-bit capture, latch recovery, snapshot/shift clock-domain timing,
   column switching, clock-output enables and controller sample/hold timing.
4. Exercise power-up/boot, malformed frames and rescan recovery. Retain meaningful
   negative controls proving that timing and protocol failures are detected.
5. Document achieved constraints and margins, model limitations and the
   measurement plan needed to close remaining assumptions.

**Acceptance gate:** documented margins for the implemented design, passing
integrated assertions and negative controls, and an explicit list of remaining
physical assumptions to measure.

Starting points: `firmware/ice40/scan20/` and
`hardware/experiments/simple-tile/fpga/system/`. The selected controller uses
an exact 60 MHz PLL, three ticks per bit and a 66.7 ns latch guard; its current
tool timing margin is thin and applies to interior fabric only.
Checkpoint: `hardware/experiments/simple-tile/checkpoints/fpga-03.md`.

### FPGA-04 — Build and validate a small hardware set

1. Build three identical tiles and a chassis-contact coupon. Arrange the tiles
   as a row, a column and an L shape to exercise both directions and column switching.
2. Verify power rails, programming, persistent flash boot and current consumption.
3. Check frame/key/topology correctness at a low clock, then sweep through 20 MHz.
4. Measure receiver waveforms and sampling/recovery margins with equipment and
   probing appropriate for the actual edge speeds. Validate contact fit,
   resistance/compression, insertion/removal and error recovery.
5. After the small set passes, expand to the sixteen-tile acceptance test and
   record the measured limits and any required design revision.

**Acceptance gate:** reproducible bench records establishing the required
function and electrical/mechanical behavior at 20 MHz, including the final
sixteen-tile test. Prototype failures are recorded results, not task completion.

Checkpoint: `hardware/experiments/simple-tile/checkpoints/fpga-04.md`.

## Session recovery procedure

1. Use the sole checkout `isomorphic_keyboard/`; do not recreate the removed
   `isomorphic_keyboard-revc/` directory.
2. Read this register, [current development](architecture/current-development.md),
   and the next task's checkpoint if it exists. Inspect `git status` and saved
   results before editing or rerunning jobs.
3. Mark the started task **in progress** here; keep later tasks pending. Record
   blockers and next steps rather than checking a task off on intent.
4. Delegate self-contained work to CERN/Flatiron Kimi K3 where feasible. In
   OpenCode, use native `cern-worker` tasks. Give workers disjoint file ownership
   and an early durable checkpoint, updated after each coherent change/test.
5. Check for surviving jobs after interruption. Preserve partial boards/logs;
   do not launch duplicate writers or repeat completed expensive jobs.
6. On completion, record actual commands, results, artifact paths and remaining
   assumptions in the checkpoint; update this register's status and **Next task**.

The tested rev A fabrication and golden controller firmware remain the reference.
Existing checks and results are indexed in
[current development](architecture/current-development.md) and the workstream READMEs.
