#!/usr/bin/env bash
# Run a command inside the rootless OSS CAD Suite container, in the current directory.
# The repository root is mounted at /work so relative paths keep working.
#   usage (from any folder of the repo):  tools/oss.sh make
# Build the image first:
#   podman build -t localhost/oss-cad-suite:2026-09-26 tools/containers/oss-cad-suite
set -euo pipefail
IMAGE="${OSS_IMAGE:-localhost/oss-cad-suite:2026-09-26}"
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
REL="$(realpath --relative-to="$ROOT" "$PWD")"
exec podman run --rm -i --userns=keep-id -e HOME=/tmp -v "$ROOT":/work:Z -w "/work/$REL" "$IMAGE" "$@"
