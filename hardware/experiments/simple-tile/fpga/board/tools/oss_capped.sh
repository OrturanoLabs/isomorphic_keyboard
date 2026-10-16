#!/usr/bin/env bash
# SPDX-License-Identifier: CERN-OHL-S-2.0
#
# oss_capped.sh -- resource-capped twin of <repo>/tools/oss.sh for the
# fpga-01 session-5b batch. tools/oss.sh is OUTSIDE this worker's
# ownership and ships no podman resource limits, so every top-level
# podman run for this batch goes through THIS launcher instead:
#   podman run --memory 2g --memory-swap 2g --cpus 1 --pids-limit 256
# Combined with tools/resource_guard.py on the outside (admission +
# 2 GiB / CPUQuota=100% systemd scope + deadline), the heavy job is
# capped at both layers. Usage mirrors oss.sh.
set -euo pipefail
IMAGE="${OSS_IMAGE:-localhost/oss-cad-suite:2026-09-26}"
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
REL="$(realpath --relative-to="$ROOT" "$PWD")"
exec podman run --rm -i --userns=keep-id -e HOME=/tmp \
  --memory 2g --memory-swap 2g --cpus 1 --pids-limit 256 \
  -v "$ROOT":/work:Z -w "/work/$REL" "$IMAGE" "$@"
