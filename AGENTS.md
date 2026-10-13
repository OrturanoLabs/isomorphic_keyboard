# Session recovery

The active project is this single `isomorphic_keyboard` checkout.

Before FPGA development, read `docs/FPGA_PLAN.md` and
`docs/architecture/current-development.md`. Resume the next pending task in the
ordered FPGA-01 through FPGA-04 register and inspect its saved checkpoint and
working-tree changes before editing. Update task status and checkpoint evidence
as work proceeds; do not treat simulation/tool results as hardware validation.

Delegate self-contained work to CERN/Flatiron Kimi K3 where feasible. In OpenCode,
use native `cern-worker` tasks with disjoint ownership and durable checkpoints.
Recover surviving jobs/partial work before retrying; avoid duplicate writers.
