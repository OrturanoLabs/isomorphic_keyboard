# FPGA implementation plan — persistent task register

Updated: 2026-10-16. Implementation baseline: `b19aa80`.

**Next task: FPGA-01 (in progress).** Later tasks remain pending. Work through them in
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

- [ ] **FPGA-01 — Complete the electrical design** — in progress; no dependency.
- [ ] **FPGA-02 — Route the FPGA tile** — four-layer feasibility trial authorized 2026-10-16; acceptance still depends on FPGA-01.
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

**2026-10-16 user direction:** try four copper layers in the same single tile
PCB (no mezzanine). This authorizes a recoverable four-layer routing variant
while FPGA-01 remains open; it does not waive the quote or bench requirements
or close either gate. Proposed stack-up: F.Cu / GND / GND / B.Cu, with routed
power and continuous reference planes under edge-critical paths. Preserve the
certified 19 contacts, 1.6 mm total thickness and existing fabrication rules.
Keep the two-layer baseline unchanged until the variant is reviewed. Record
actual filled-zone connectivity and KiCad DRC, not router plane assumptions.

**Trial review (2026-10-16):** a real four-layer variant exists in
`fpga/board/four-layer/`; canonical two-layer baseline preserved. First repaired
variant has 73 unconnected items, 0 error-severity DRC violations and 153
warnings. Independent review found lost post-router power attachments, an
isolated EP ground pour, remaining ground opens and two sub-0.2 mm copper-neck
warnings. These are real blockers, not a clean DRC pass. Follow-up repair is
delegated; see `checkpoints/fpga-02.md` and `checkpoints/fpga-02-review.md`
under `hardware/experiments/simple-tile/`. No acceptance gate is closed.

**Work stopped (2026-10-16, 15:18 CEST, user request):** routing trial left
incomplete and committed as-is. Latest artifact
`fpga/board/four-layer/out/tile_gw1nz_4l_ground.kicad_pcb` + DRC JSON:
0 error-severity DRC violations, 150 warnings, 54 ground opens, 44/52
post-import power attachments, 3 legal EP vias placed, 2 sub-0.2 mm
copper-neck warnings still failing, 8 components unplaced. No acceptance
gate is closed; do not treat this as a routed board.

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

### Active unattended session — 2026-10-14

**Latest reviewed state (2026-10-15):** r6 follow-up completed successfully;
the earlier r6 log's SCH0 failure is superseded by
`/tmp/opencode/fpga01-regen-r6b.log`. Independent validation confirms ERC
0 violations, schematic/board parity and all five resistor-node splits;
GW1NZ DRC has 0 error-severity violations, 107 silkscreen warnings and
99 unconnected items. New resistor-bypass/wrong-pin negative controls pass.
Fresh canonical tool reruns were resource-admission blocked by low memory
and competing Rust builds; existing reports are from the completed follow-up.
See `hardware/experiments/simple-tile/checkpoints/fpga-01-validation.md`.
FPGA-01 remains in progress: assembly quote not obtained, termination bench
evidence outstanding. Zero-ohm resistor positions do not prove damping;
the board remains unrouted and not fabrication-ready.

- Electrical implementation is delegated to CERN Kimi K3; FPGA-01's checkpoint
  is authoritative for new artifacts and acceptance evidence.
- Review reproduced clean ERC and schematic/board parity. FPGA-01 remains
  **in progress**: the assembly quote is blocked, and termination rationale,
  GPIO-attribute claims and stale result counts require repair. See
  `hardware/experiments/simple-tile/checkpoints/fpga-01-review.md`.
  Evidence-level progress is not acceptance-gate completion.
- **Provider blocker (2026-10-15 ~00:05 Europe/Rome):** CERN/Flatiron Kimi
  endpoint `inference001.flatironinstitute.org:8000` refused connection on
  remediation and its same-session recovery attempt. Partial session-5 work
  is preserved in the FPGA-01 checkpoint. Resume worker session
  `ses_ec4abb8cdffepb5cQvRYDDVTDd` after service recovery; inspect surviving
  jobs first. No paid-provider fallback or duplicate writer was launched.
  The quote remains NOT OBTAINED; do not silently carry it into FPGA-02.
- **Restart requested (2026-10-15 10:39 Europe/Rome):** user reports Kimi
  restored. Same worker session resumed for a bounded remediation batch,
  with new-command cutoff **12:10 Europe/Rome today**, not an extension of
  overnight authorization. Recover partial work/jobs first; preserve resource
  admission and explicit container caps. Provider recovery is not yet verified
  by completed worker output. FPGA-01 remains in progress.
- Resource admission/caps and recovery evidence:
  `hardware/experiments/simple-tile/checkpoints/fpga-resource.md`.
  Use `hardware/experiments/simple-tile/tools/resource_guard.py` for heavy jobs;
  retain explicit container limits because delegators can escape scope caps.
- Preparatory findings (not later-task acceptance):
  `hardware/experiments/simple-tile/checkpoints/fpga-downstream-preparation.md`
  and `hardware/experiments/simple-tile/checkpoints/fpga-programming-review.md`.
- Stop new unattended jobs by **2026-10-15 10:00 Europe/Rome**. Preserve logs
  and partial results if resource admission prevents a run or this session ends.

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

### Overnight scheduling — 2026-10-15/16 (armed 2026-10-15 ~19:05 CEST)

An unattended overnight window was authorized for **2026-10-15 21:43 CEST to
2026-10-16 11:00 CEST** (fresh cutoff; the 12:10 remediation cutoff is
expired). A systemd-user-armed orchestrator
(`hardware/experiments/simple-tile/tools/fpga_overnight.py`, timers
`fpga-overnight-20261015.timer` + `-stop.timer`) runs bounded Kimi K3 batches
in the dedicated session `ses_fpga_overnight_20261015` with a 3 GiB cgroup
cap, guard-gated admission, 15/30/60 min provider-failure retry, and
READY/BLOCKED/COMPLETE outcome gating. Worker scope: `fpga/board/**` and
`checkpoints/fpga-01.md` evidence only; ordered FPGA-01..04 with no silent
waivers; no purchases/logins/submissions/hardware/commits/installs. Full
units, commands, memory limits, setup evidence, cancellation instructions
and per-batch results: `hardware/experiments/simple-tile/checkpoints/fpga-overnight.md`.
