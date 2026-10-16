# Resource guard — independent review

Owner of this file: reviewer (Kimi K3). Reviews `tools/resource_guard.py` +
`checkpoints/fpga-resource.md`. Read-only against all other paths; only this
file written. Tests: bounded light runs (≤ ~128 MiB scoped caps), self-started
processes only, killed only own artifacts. Host at review: 22,832 MiB RAM,
~7,950 MiB available, swap 11,416/11,416 used (0 free), 201 uid processes,
systemd 262.

## Verdict

Sound core: no path kills unrelated processes (`killpg` only on own `setsid`
group; `systemctl stop` only on own `rg-<pid>` unit; `/proc` scans read-only).
Highest risks below, in priority order.

## P1 — Rust gate misses test-executable phase (verified live)

`RUST_COMMS` matches `/proc/*/comm` exactly. `cargo test` runs compiled
binaries `target/{debug,release}/deps/<crate>-<hash>` (comm = crate name),
so the run phase of competing `~/Projects/antani` cargo tests evades the gate.
Verified: ran a fake `antani-3f9a2c1d` process (symlink to sleep); guard
printed `admitted:` and executed the payload with no rust warning. Linkers
(`ld`/`lld` via `cc`) evade identically. Only the compile phase is caught.
Repair: keep the comm fast-path, then `os.readlink(f"/proc/{pid}/exe")`
(try/except OSError → skip) and flag if path contains `/target/debug/deps/`,
`/target/release/deps/`, or `/.cargo/`/`/rustup/toolchains/`. Read-only,
same cost class. Until then the checkpoint's "rust gate" line must be read as
compile-phase-only; real protection vs antani tests is MemAvailable+PSI.

## P2 — Fallback `RLIMIT_NPROC=256` is a shared per-uid budget

Measured 201 live processes for this uid. Check counts the whole uid across
all sessions, so any browser/editor/agent burst pushes the guarded child's
forks to EAGAIN spuriously; headroom today is ~55 forks.
Repair: in `run_ulimit` compute current per-uid count (stat `/proc/*/`
uid match) and set `(cur + tasks_max)`; or drop NPROC to a large value and
either way.

## P3 — Caps bind only the direct tree; daemon/scope delegation escapes

`MemoryMax` on `rg-<pid>.scope` covers only processes staying in that cgroup.
A wrapped makefile invoking `docker` (daemon slice), rootless `podman` (own
cgroup), `flatpak run` (moved to its own app scope), or nested
`systemd-run --user` (sibling scope) silently escapes every cap. Same for the
ulimit path (rlimits don't cross into a daemon's exec).
Repair: in `run_capped`, if `basename(cmd[0])` ∈ {docker, podman, flatpak,
systemd-run, systemctl} log a loud "caps not transitive through daemon/
scope delegation" warning (or require `--allow-delegation`); document in
checkpoint Limitations.

## P4 — Timeout-cleanup edges on the systemd path

a) `systemctl stop` uses `timeout=30` but `subprocess.TimeoutExpired` is not
caught → traceback, exit 1, scope (and child) keeps running uncapped-in-time.
Repair: wrap both stop calls in `try/except subprocess.TimeoutExpired`, log
and continue (the stop job is usually already queued in PID 1).
b) After stop, `_finalize` runs `proc.wait()` with no timeout; a stuck
systemd-run hangs the wrapper holding the single-job lock. Reduced prop sets
also drop `TimeoutStopSec` (escalation falls back to ~90 s, not 5).
Repair: `proc.wait(timeout=60)` in a try; on expiry log and return (never
kill systemd-run to "help" — the scope is independent; `--collect` GCs it).
Note in log when the active prop set lacks `TimeoutStopSec`.

## P5 — Docstring exit-code claim wrong (verified)

Header says child signal death = `128+N`. Measured (ulimit mode, child
self-SIGKILL): shell rc = 247 = 256−9 (Popen returncode −9, `sys.exit`
truncates). Checkpoint documents 247 for scopes but the module docstring
still misleads shell consumers expecting 137.
Repair: docstring → "signal deaths surface as 256−N (e.g. 247 for SIGKILL)",
or normalize: `rc = 128 - rc if rc < 0 else rc` in `main`.

## Minor

- Bad ISO `--deadline`/env → ValueError rc 1, not usage 64 (catch in `main`).
- Unit `rg-<pid>` collides with a stale scope from a crashed run; rare.
- `check_once` deny order: rust deny masks memory/psi deny; cosmetic.

## Defaults question: 6144 MiB gate + 2048 MiB command — sensible?

Yes, with caveats. Ratio gate ≈ mem-mib + ~4 GiB preserves the desktop plus
the concurrent antani/claude sessions on a 22.8 GiB host whose swap is
permanently full (so MemAvailable is honest and the guard correctly does
NOT gate on SwapFree — gating there would deadlock). Frictions observed:
available RAM swings 6.8→8.1 GiB, so a 6144 gate flaps near threshold; the
120 s default wait is short against multi-minute cargo test runs (expect
rc 2 denials; that is the design working, but tune `--wait` to competitor
length in orchestration). The 2 GiB command cap with `MemorySwapMax=0` is a
good hard bound — cgroup OOM kills the child before the host thrashes, and
PSI avg10 ≤ 25 is the correct dynamic backstop while P1 is unfixed. Keep
6144/2048 for interactive hosts; for unattended batch `--min-avail-mib
4096` is defensible since PSI+MemoryMax carry the real protection.

## Tests performed by reviewer (all light, own processes only)

- Evasion demo P1 (fake test-binary comm → admitted; cleaned up).
- Signal-death rc: 247 (P5). `--no-systemd` 200 MiB in 128 MiB `RLIMIT_AS` → rc 1.
- `--no-systemd --timeout 2` vs `sleep 30` → rc 124 (killpg own group only).
- Host facts: uid process count 201; swap 0 free; systemd 262.
