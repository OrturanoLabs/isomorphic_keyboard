# Keyboard repository consolidation

The only active checkout is `isomorphic_keyboard/`. The separate
`isomorphic_keyboard-revc/` linked worktree has been removed with Git's
worktree command.

## Preservation and migration

- Rev B commit `d358953` was verified to be an ancestor of rev C `6572e0f`.
  The original checkout was fast-forwarded and now uses branch `rev-c`.
- Uncommitted latest source files, FPGA bitstreams/logs, timed simulations,
  vendor evidence and checkpoints were restored into this checkout.
- The original checkout's raw photos/recordings, SI captures/models, reference
  firmware builds and manufactured rev A files were preserved.
- The migration snapshot is reachable as
  `refs/archive/keyboard-consolidation-20261012`
  (`09068ea5ac38db771e60f5d72dcabfeb711b0121`). Its third parent records the
  newer worktree's then-untracked and ignored files; its main tree records
  tracked edits. It provides recovery without a duplicate working directory.
- The keymap checker now locates its circuit relative to its own script,
  instead of hardcoding the deleted directory.
- An identical duplicate connector checkpoint was removed. The distinct
  former root FPGA checkpoint was preserved as
  `hardware/experiments/simple-tile/checkpoints/fpga-recovery-history.md`.

## Removed superseded material

- MCU/LED tile project `hardware/kicad/revc-mcu-tile/`, its four generators,
  proposal and two images. The design remains recoverable from Git history
  (for example `9be96ae`).
- Duplicate original five-volt GAL outputs under `hardware/gal/`. Canonical
  comparison sources and fuse evidence remain under
  `hardware/experiments/simple-tile/logic/pld/`.
- Superseded first-round connector coupons and their generator/runner.
  Their geometry and detection assumptions were corrected by later studies;
  original files are recoverable from `6572e0f`.

The original connector geometry helper and placement inputs are retained
because current tools import them. They are reference/library inputs, not the
current tile outline or recommended coupon designs. The current construction
is `connector-next`'s corrected `TileTiling`.

Historical ledger entries and run logs can mention the removed checkout or
removed proposals. Those entries describe their original runs; they are not
instructions to recreate the duplicate checkout.

The previous experiment baseline is `6572e0f`. Consolidation, cleanup and the
subsequent verified experiments are recorded together in the following project
commit; the recovery snapshot remains separately reachable as noted above.

## Post-migration checks

- `git worktree list` reports only the consolidated checkout.
- The original rev A fabrication, simulation and controller sources show no
  changes against the preserved baseline.
- Raw photo/recording content hashes were recorded after migration.
- Controller simulations reran: 24/24 expectations pass. The selected exact
  60 MHz PLL/20 MHz scan configuration again meets its standalone tool constraint.
- FPGA board pin, footprint and net/power/presence checks pass, including
  their negative controls.
- FPGA system smoke tests pass (3/3), with source/hash drift checks passing.
- Discrete keymap checks and 12 quick A/A2 simulation cases pass. Both current
  board net-binding checks and six-neighbor tiling checks pass; routing DRC
  remains failed as documented in the current-development status.
