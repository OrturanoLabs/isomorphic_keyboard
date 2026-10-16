#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# run_freerouting_4l.sh -- guarded freerouting run for the FPGA-02 4L arm.
# Exact recipe proven in prep batches 9/20, with the task's explicit caps:
# resource_guard outside (admission + 2 GiB scope + CPUQuota 100% +
# deadline), podman container-side --memory 2g --memory-swap 2g --cpus 1
# --pids-limit 256 (never --ignore-rust). Serial: one router run at a time
# via the guard's flock.
#   args: IN.dsn OUT.ses LOG
set -euo pipefail
IN="$1"; OUT="$2"; LOG="$3"
ST="$(cd "$(dirname "$0")/../../../.." && pwd)"  # simple-tile
GUARD="python3 $ST/tools/resource_guard.py"
mkdir -p "$(dirname "$OUT")" "$(dirname "$LOG")"
$GUARD --timeout 3000 --mem-mib 2048 -- \
  podman run --rm -i --userns=keep-id \
    --memory 2g --memory-swap 2g --cpus 1 --pids-limit 256 \
    -v "$PWD":/work:Z -w /work \
    localhost/freerouting:2.4.1 \
    -de "$IN" -do "$OUT" -mp 40 --gui.enabled=false 2>&1 | tee "$LOG"
