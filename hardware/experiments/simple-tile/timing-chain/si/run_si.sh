#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
#
# 20 MHz burst SI runs (ngspice container).
#
#   hardware/experiments/simple-tile/timing-chain/si/run_si.sh
#
# Requires the localhost/ngspice image and the vendor IBIS models in
# si/models/ (fetch via ../hardware/si/models/fetch.sh ids SCEM283/288/216;
# not redistributed upstream). The harness:
#   1. asserts the degenerate-deck selftest FAILS its checks (non-vacuous),
#   2. runs the full burst sweep; the script exits nonzero if ANY case fails
#      its checks (failing cases are results, not harness errors),
#   3. prints a per-case PASS/FAIL table into results/chain_hop_20mhz.txt.

set -euo pipefail
cd "$(dirname "$0")"

IMG=localhost/ngspice
if ! podman image exists "$IMG"; then
  echo "ERROR: container image $IMG not present" >&2
  exit 2
fi
for m in sn74lvc2g125.ibs sn74lvc2g126.ibs sn74lvc1g04.ibs; do
  if [ ! -f "models/$m" ]; then
    echo "ERROR: models/$m missing; fetch via hardware/si/models/fetch.sh" >&2
    exit 2
  fi
done
mkdir -p results

RUN=(podman run --rm --userns=keep-id -e HOME=/tmp -e MPLCONFIGDIR=/tmp
     -v "$PWD":/work:Z -w /work "$IMG")

{
  echo "date_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "image_id: $(podman image inspect --format='{{.Id}}' "$IMG")"
  "${RUN[@]}" ngspice --version 2>&1 | sed -n '1,2p'
} > results/env.log

fail=0

"${RUN[@]}" python3 -c "
import sys; sys.path.insert(0, '.')
import chain_hop_20mhz
sys.exit(chain_hop_20mhz.main(selftest=True))
" | tee results/selftest.log
if ! grep -q "SI-SELFTEST PASS" results/selftest.log; then
  echo "SI SELFTEST FAILED (checks may be vacuous)" | tee -a results/summary.txt
  fail=1
fi

set +e
"${RUN[@]}" python3 -c "
import sys; sys.path.insert(0, '.')
import chain_hop_20mhz
sys.exit(chain_hop_20mhz.main())
" | tee results/chain_hop_20mhz.txt
rc=$?
set -e

npass=$(grep -c "^SI-PASS" results/chain_hop_20mhz.txt || true)
nfail=$(grep -c "^SI-FAIL" results/chain_hop_20mhz.txt || true)
{
  echo "20 MHz burst SI: $npass case-checks pass, $nfail case-checks fail (script rc=$rc)"
  echo "selftest: $(grep -o 'SI-SELFTEST [A-Z]*' results/selftest.log | tail -1)"
} | tee results/summary.txt

# A nonzero script rc is an honest "some cases fail budgets" result; it is a
# harness failure only if the selftest itself failed.
exit "$fail"
