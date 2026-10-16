# Resource guard — checkpoint

Owner: resource worker. Files owned: `tools/resource_guard.py`, this checkpoint.
No edits outside this file pair; no jobs past 2026-10-15 10:00 Europe/Rome.

## Recovery sweep — 2026-10-14 (read-only; nothing killed or touched)

- Repo processes: only interactive shells/editor (`zsh`, `opencode`, `nvim`,
  `xdg-open`). No surviving heavy job with cwd in this repo.
- `~/Projects/antani` (inspect metadata only): one `claude` session
  (pid 3927138, RSS ~340 MiB), two sleeping `kimi-worker wait` + `tail` pairs
  (other active sessions — left untouched), and six sleeping `oss-cad-suite`
  `ld-linux-x86-64` loader stubs (pids 1765578, 204967, 212049, 3452221,
  3704753, 3705498; RSS 12-76 kB each; cwd in `/tmp/*antani*/**prove` dirs,
  two `(deleted)`). All state S, negligible memory; left untouched.
- Rust: no `rustc`/`cargo`/`sccache`/`nextest`/`rust-analyzer` processes
  anywhere at sweep time.
- Containers: none running. `allpix-squared` exited 6 months ago;
  `pensive_brown` in Created state since 2026-09-24 (mem limit 0 = unlimited,
  cpus 0). No container resource limits to preserve or contend with.
- Host pressure at sweep: 22,832 MiB total, ~6,861 MiB available (was ~8,289),
  swap 11,416/11,416 MiB used (0 free), PSI memory avg10=0.00,
  16 CPUs, `/tmp` tmpfs 70% full (7.8 GiB used).
- systemd: user manager reachable (`degraded` but working);
  `systemd-run --user --scope -p MemoryMax=2G -- /bin/true` succeeded, so
  scoped hard caps are the primary mode. systemd version check pending.

## Design decisions

- Admission: flock single-job serialization, then gated start requiring
  MemAvailable >= 6,144 MiB, PSI memory some avg10 < 25, and no active Rust
  toolchain processes (reported, postpone). Bounded wait, then refuse
  (exit 2). Never kills or signals anything it did not start.
- Caps: systemd user scope `MemoryMax`, `MemorySwapMax=0`, `CPUQuota`,
  bounded `TasksMax` (dropped with warning if unsupported); fallback
  `setrlimit` (`RLIMIT_AS`, `RLIMIT_NPROC`, `RLIMIT_CPU`) with honest
  limitations documented. Command timeout; timeout exit 124.
- Deadline: `--deadline` / `RESOURCE_GUARD_DEADLINE` (ISO 8601); refuse to
  start jobs past it (exit 4). Orchestrator deadline:
  2026-10-15T10:00:00+02:00.
- Stdlib only Python 3; light bounded self-tests via `--self-test`
  (no files written, transient memory <= 256 MiB).

## Status

Done and tested on this host, including remediation of the independent
review findings in `fpga-resource-review.md` (re-tested below).
Orchestrated runs should go through this wrapper; no monitoring daemon is
installed or needed. No jobs past 2026-10-15 10:00 Europe/Rome.

## Review remediation — 2026-10-14 (review: `fpga-resource-review.md`)

- **P1 rust run/link phase evaded gate** — fixed: `/proc/<pid>/exe`
  read-only readlink after the comm fast-path. Toolchain paths
  (`/.cargo/`, `/.rustup/`, `/rustup/toolchains/`) matched globally --
  earlier marker bug found: `~/.rustup` has a leading dot, so
  `/rustup/toolchains/` alone would never match it. Test-executable paths
  (`/target/{debug,release}/deps/`) matched ONLY under declared project
  roots (default `~/Projects/antani`; extend with `--rust-target-root DIR`
  / `RESOURCE_GUARD_RUST_TARGET_ROOTS`). Generic Python/C builds elsewhere
  are not flagged. Labels: `target-test-exe:*`, `toolchain-exe:*`.
- **P2 fallback RLIMIT_NPROC** — dropped entirely (per-uid budget; ~201
  live uid processes measured, headroom ~55 forks caused spurious EAGAIN
  risk). Task bounds exist only via systemd TasksMax; logged honestly.
- **P3 delegation escapes caps** — argv-detection of `docker`, `podman`,
  `flatpak`, `systemd-run`, `systemctl` as cmd[0]. podman/docker without
  container-side limits REFUSED (rc 64) listing tested flags
  `--memory --memory-swap --cpus --pids-limit` (verified present in this
  host's `podman run --help`); with all four flags present, runs with a
  loud DELEGATION warning. `flatpak` (needed for KiCad) always runs but
  logs loud accurate warning: app relocates into its own app-*.scope,
  flatpak has no per-run memory/cpu flags, so caps do not apply inside.
  Nested systemd-run/systemctl refused unless `--allow-delegation`.
  Scripts hiding delegators cannot be detected (documented limitation).
- **P4 systemd cleanup** — clustered ladder on own unit only: stop
  (TimeoutExpired + rc!=0 safe) -> bounded 60 s wait -> own-unit
  `systemctl --user kill --signal=KILL` -> bounded 30 s wait -> log and
  leave scope to `--collect` GC (never kills systemd-run). Stop-escalation
  state now logged (`stop_escalation=...`); reduced prop sets note the
  ~90 s default. Unit names carry random hex suffix vs stale collisions.
- **P5 signal-exit docs** — normalized to shell convention 128+N
  (`247 -> 137` now; verified live by the memory-cap test showing
  `rc=137`). Docstring updated; 256-N only if APIs bypass `main()`.
- **Minor** — bad ISO `--deadline` now rc 64 (was ValueError rc 1);
  unit stale-scope collision handled by random suffix.

## Remediation test evidence (2026-10-14 19:25-19:28 CEST, bounded, RC=0)

`python3 tools/resource_guard.py --self-test` -- 12/12 PASS:

- Previous 7 tests all still PASS (memory cap now reports rc=137).
- `rust gate: exe-path detection (root+toolchain)`: fake binaries (real
  copies of /bin/sleep, self-started and self-killed) under a mock root's
  `target/debug/deps/` and a mock `.rustup/toolchains/` -> wrapper
  denied with rc 2 + `RUST ACTIVE`, labels
  `['target-test-exe:fakecrate-...', 'toolchain-exe:fake-ld.lld']`.
- `cleanup ladder: mocked failures bounded`: mocked timeouts/rc!=0 ->
  stop tolerated, SIGKILL escalation on own unit recorded, fully-stuck
  mock left to GC with bounded return. No real units touched.
- `delegation detect/warn/refuse/opt-in`: fake delegators (symlinks to
  /bin/true) -> podman no-flags rc 64 listing `--memory`/`--pids-limit`;
  podman all-flags rc 0 + DELEGATION warning; flatpak rc 0 + loud
  app-scope warning; fake systemd-run rc 64, rc 0 with
  `--allow-delegation`.
- `podman caps flags verified against help`: all four flags present.
- `deadline: past -> rc 4, bad ISO -> rc 64`.

One edit-time defect found and fixed during remediation: a duplicated
`start/proc = ...` block from a partial edit made the ulimit path pass a
stale 3-arg `_apply_ulimits` (TypeError in preexec, rc 1); removed, tests
re-run green.

## Implementation evidence

Host: systemd 262, cgroup v2 (controllers memory,pids,cpu present), 16 CPUs.
`systemd-run --user --scope` accepts `MemoryMax`, `MemorySwapMax=0`,
`CPUQuota`, `TasksMax`, `TimeoutStopSec`; `--wait` is rejected with `--scope`
(removed after empirical failure; scopes block in foreground and forward
exit codes). Direct evidence:
`MemoryMax=128M` scope vs 200 MiB allocation -> cgroup OOM kill, rc 137
raw (`systemd-run` scope mode encodes signal death as 256-sig = 247 at the
wrapper; document both, treat any nonzero as "did not survive").

## Test evidence (all bounded, light; executed 2026-10-14 ~19:00 CEST)

`python3 .../tools/resource_guard.py --self-test` (7 tests, < 60 s total):

- PASS meminfo/psi/rust scan (read-only; reported avail/psi/rust count)
- PASS flock contention (second fd on held lock -> errno 11 EAGAIN)
- PASS capped trivial run rc=0 `mode=systemd`
- PASS memory cap enforced: 200 MiB inside 128 MiB cap, no "survived", rc 247
- PASS timeout: `--timeout 2` vs `sleep 30` child -> rc 124 in 2.2 s;
  scope child received SIGTERM (observed exit -15), bounded escalation
  SIGKILL after `TimeoutStopSec=5` if it had ignored it
- PASS admission denial one-shot with absurd requirement -> rc 2
- PASS ulimit fallback (`--no-systemd`) enforced `RLIMIT_AS` cap -> rc 1

Manual checks (same host):

- Rust gate: fake `rustc` (symlink to sleep, run by us, killed after) ->
  wrapper reported `RUST ACTIVE: 1 proc(s): rustc(pid ...)` and denied
  with rc 2 after bounded `--wait 3`; `--ignore-rust` admitted and ran
  under full caps `MemoryMax=2048M,MemorySwapMax=0,CPUQuota=100%,TasksMax=256`.
  No real Rust processes existed on this host at test time.
- Deadline: `--deadline 2026-10-14T00:00:00+02:00` -> rc 4, refused to start.
- Lock contention: external flock on the default lock -> rc 3 in 2.2 s,
  message names the holder condition (lock-timeout), nothing killed.

## Usage

Heavy commands (yosys/nextpnr/verification sweeps) run through one shot:

    RESOURCE_GUARD_DEADLINE=2026-10-15T10:00:00+02:00 \
    python3 hardware/experiments/simple-tile/tools/resource_guard.py \
      --timeout 1800 --mem-mib 2048 -- \
      yosys -s build.ys

Key flags: `--min-avail-mib` (default 6144), `--psi-max-avg10` (25),
`--wait/--no-wait`, `--ignore-rust`, `--rust-target-root DIR` (repeatable),
`--allow-delegation`, `--lock`/`--lock-timeout`,
`--timeout` (0=none, clamped to deadline if one is set), `--mem-mib`
(2048), `--cpu-percent` (100), `--tasks-max` (256), `--no-systemd`,
`--deadline` (or env). Exit codes: child code (signal deaths 128+N);
2 admission denied; 3 lock timeout; 4 deadline; 64 usage error incl.
delegation refusal; 124 timeout-kill.

## Limitations (honest)

- `ru_maxrss_of_direct_children` on the systemd path measures the
  systemd-run wrapper's tree only, not cgroup peak (scope is `--collect`ed
  before MemoryPeak can be read). Use cgroup tooling if exact peak matters.
- Signal deaths are normalized to 128+N in `main`; code bypassing `main`
  still sees raw negative returncodes.
- ulimit fallback: `RLIMIT_AS` caps virtual address space (can over-trigger
  on mmap-heavy tools) and `RLIMIT_CPU` caps CPU time only; swap, CPUQuota
  and task bounds are NOT enforceable with ulimit (RLIMIT_NPROC dropped as
  a shared per-uid budget).
- Delegation: hard caps never descend into podman/docker containers,
  flatpak app scopes or nested systemd scopes. Detection is argv-basename
  based; a wrapped script/makefile that hides a delegator escapes unseen.
  podman/docker require explicit container-side caps flags or
  `--allow-delegation`; flatpak always runs (KiCad) with a loud warning
  because flatpak offers no per-run resource flags.
- PSI gate uses memory `some avg10` only; the host's permanent full-swap
  state is reported but tolerated (gating on SwapFree would deadlock).
- Rust detection: comm basenames plus `/proc/<pid>/exe` path markers;
  toolchain trees relocated outside `.cargo`/`.rustup`/`rustup/toolchains`
  and target dirs outside declared roots evade it. Postponement courtesy
  gate, not access control.
- Admission/lock are advisory (flock); tools not routed through this
  wrapper are unaffected by it, and this wrapper never touches them.
- Self-test writes only lock files under `/tmp/opencode/`; transient
  memory <= 256 MiB in capped scopes.

## Next

Tool is ready for the FPGA-01+ heavy commands. If host loses systemd user
scopes (e.g. degraded session), the tool falls back to ulimit automatically
and logs the fact; check `mode=ulimit` in stderr before trusting caps.
