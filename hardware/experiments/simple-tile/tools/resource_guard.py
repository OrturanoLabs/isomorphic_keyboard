#!/usr/bin/env python3
"""resource_guard.py -- admission + hard-capped wrapper for heavy commands.

Single-job serialization via flock, conservative memory admission
(MemAvailable >= MIN_AVAIL_MIB), PSI pressure gate, Rust-toolchain activity
report/postpone, hard per-command caps via a systemd user scope when
available (MemoryMax / MemorySwapMax=0 / CPUQuota / bounded TasksMax) with an
explicit setrlimit fallback, and a command timeout. Stdlib only.

Never kills or signals processes it did not start: process scans are
read-only, and cleanup on timeout targets only the self-generated unit
(rg-<pid>-<random-hex>, no user-controlled scope-name parts) or the process
group it spawned. No daemon; one shot per invocation.

Exit codes:
    0..   child exit status; signal deaths are normalized to the shell
          convention 128+N (e.g. 137 = SIGKILL, including cgroup OOM kills)
    2     admission denied after bounded wait (memory / pressure / rust)
    3     could not acquire the single-job lock in time
    4     deadline reached (refuse to start new work)
    64    usage error (incl. delegating commands refused without opt-in)
    124   command killed by this wrapper because of --timeout

Usage:
    resource_guard.py [OPTIONS] -- CMD [ARGS...]
    resource_guard.py --self-test

Environment overrides:
    RESOURCE_GUARD_DEADLINE   ISO 8601 timestamp; refuse to start past it
    RESOURCE_GUARD_LOCK       flock path (default /tmp/opencode/isomorphic-resource-guard.lock)
    RESOURCE_GUARD_RUST_TARGET_ROOTS   os.pathsep-separated extra roots whose
                              target/{debug,release}/deps/ executables count
                              as Rust test/build activity (default root:
                              ~/Projects/antani)
"""

from __future__ import annotations

import argparse
import datetime as dt
import errno
import fcntl
import os
import shutil
import signal
import subprocess
import sys
import time

KIB = 1 << 10
MIB = 1 << 20

RUST_COMMS = {
    "rustc",
    "cargo",
    "rustup",
    "rust-analyzer",
    "sccache",
    "cargo-nextest",
}

# Executable-path markers for Rust toolchains; matched globally on
# /proc/<pid>/exe so cargo-instrumented linkers (rust-lld under
# .rustup/toolchains) and shims under ~/.cargo are also caught.
TOOLCHAIN_PATH_MARKERS = ("/.cargo/", "/.rustup/", "/rustup/toolchains/")

# Compiled test binaries run as target/{debug,release}/deps/<crate>-<hash>
# with the crate name as comm, so comm matching alone never sees them.
# Path gating for these is BOUNDED to declared project roots (default
# ~/Projects/antani) to avoid flagging unrelated trees.
TEST_DEPS_MARKERS = ("/target/debug/deps/", "/target/release/deps/")

DEFAULT_TARGET_ROOTS = (os.path.expanduser("~/Projects/antani"),)

DEFAULT_LOCK = os.environ.get(
    "RESOURCE_GUARD_LOCK", "/tmp/opencode/isomorphic-resource-guard.lock"
)


# ---------------------------------------------------------------------------
# Read-only host inspection
# ---------------------------------------------------------------------------


def _meminfo() -> dict[str, int]:
    """Parse /proc/meminfo into a dict of kiB values. Read-only."""
    info: dict[str, int] = {}
    with open("/proc/meminfo", encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) >= 2:
                info[parts[0].rstrip(":")] = int(parts[1])
    return info


def _psi_mem_some_avg10() -> float | None:
    """Return PSI memory 'some' avg10 percent (0-100), None if unavailable."""
    try:
        with open("/proc/pressure/memory", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("some "):
                    for tok in line.split():
                        if tok.startswith("avg10="):
                            return float(tok.split("=", 1)[1])
    except (OSError, ValueError):
        return None
    return None


def _rust_processes(
    target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS,
) -> list[tuple[int, str]]:
    """Read-only /proc scan for Rust-toolchain activity. Returns
    [(pid, label)]. Never signals anything; unreadable processes skipped.

    Detection: (1) comm fast-path for toolchain binaries; (2) executable
    path (/proc/<pid>/exe) under known toolchain dirs (global); (3)
    executable path under <root>/target/{debug,release}/deps/ for declared
    project roots only -- this catches `cargo test` run-phase binaries and
    cargo-spawned linkers without matching generic builds elsewhere."""
    roots = tuple(os.path.normpath(os.path.expanduser(r)) + os.sep
                  for r in target_roots)
    found: list[tuple[int, str]] = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/comm", encoding="utf-8") as fh:
                comm = fh.read().strip()
        except OSError:
            continue
        if comm in RUST_COMMS:
            found.append((int(name), comm))
            continue
        try:
            exe = os.readlink(f"/proc/{name}/exe")
        except OSError:
            continue
        label = os.path.basename(exe.removesuffix(" (deleted)"))
        if any(marker in exe for marker in TOOLCHAIN_PATH_MARKERS):
            found.append((int(name), f"toolchain-exe:{label}"))
        elif exe.startswith(roots) and any(
            marker in exe for marker in TEST_DEPS_MARKERS
        ):
            found.append((int(name), f"target-test-exe:{label}"))
    return found


def memory_snapshot(
    target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS,
) -> dict[str, object]:
    info = _meminfo()
    return {
        "mem_available_mib": info.get("MemAvailable", 0) / KIB,
        "swap_free_mib": info.get("SwapFree", 0) / KIB,
        "psi_some_avg10": _psi_mem_some_avg10(),
        "rust": _rust_processes(target_roots),
    }


# ---------------------------------------------------------------------------
# Deadline
# ---------------------------------------------------------------------------


def _parse_deadline(text: str | None) -> dt.datetime | None:
    if not text:
        return None
    parsed = dt.datetime.fromisoformat(text.strip())
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()  # interpret naive timestamp as local time
    return parsed


# ---------------------------------------------------------------------------
# Admission
# ---------------------------------------------------------------------------


class Admission:
    """Bounded-wait admission gate: memory, PSI pressure, Rust activity."""

    def __init__(
        self,
        min_avail_mib: float,
        psi_max_avg10: float,
        wait_s: float,
        poll_s: float,
        ignore_rust: bool,
        deadline: dt.datetime | None,
        target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS,
    ) -> None:
        self.min_avail_mib = min_avail_mib
        self.psi_max_avg10 = psi_max_avg10
        self.wait_s = wait_s
        self.poll_s = poll_s
        self.ignore_rust = ignore_rust
        self.deadline = deadline
        self.target_roots = target_roots

    def _deadline_remaining(self) -> float | None:
        if self.deadline is None:
            return None
        return (self.deadline - dt.datetime.now(dt.timezone.utc)).total_seconds()

    def check_once(self) -> tuple[bool, str]:
        snap = memory_snapshot(self.target_roots)
        avail = float(snap["mem_available_mib"])
        psi = snap["psi_some_avg10"]
        rust = snap["rust"]
        swap = float(snap["swap_free_mib"])
        note = (
            f"MemAvailable={avail:.0f} MiB (need >= {self.min_avail_mib:.0f}), "
            f"SwapFree={swap:.0f} MiB, "
            f"psi_some_avg10={'n/a' if psi is None else f'{psi:.2f}'}"
        )
        if rust:
            listed = ", ".join(f"{c}(pid {p})" for p, c in rust[:8])
            note += f"; RUST ACTIVE: {len(rust)} proc(s): {listed}"
            if not self.ignore_rust:
                return False, note
        if avail < self.min_avail_mib:
            return False, note
        if psi is not None and psi > self.psi_max_avg10:
            return False, note + f" (psi > {self.psi_max_avg10:g})"
        return True, note

    def wait(self) -> tuple[bool, str]:
        """Poll until admitted, wait budget exhausted, or deadline reached."""
        started = time.monotonic()
        last_note = ""
        while True:
            rem = self._deadline_remaining()
            if rem is not None and rem <= 0:
                return False, "deadline reached|" + last_note
            ok, note = self.check_once()
            last_note = note
            if ok:
                return True, note
            elapsed = time.monotonic() - started
            budget = self.wait_s
            if elapsed >= budget:
                return False, "admission denied after bounded wait|" + note
            sleep_for = min(self.poll_s, budget - elapsed)
            if rem is not None:
                sleep_for = min(sleep_for, max(rem, 1.0))
            _log(f"admission pending: {note}; retry in {sleep_for:.0f}s")
            time.sleep(sleep_for)


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------


def acquire_lock(path: str, timeout_s: float,
                 deadline: dt.datetime | None) -> object:
    """Acquire an exclusive advisory lock, releasing nothing early.
    Returns the open file object (kept alive by the caller)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fh = open(path, "a+b")  # noqa: SIM115 -- held for process lifetime
    started = time.monotonic()
    while True:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fh
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN):
                fh.close()
                raise
        if deadline is not None:
            if dt.datetime.now(dt.timezone.utc) >= deadline:
                fh.close()
                raise TimeoutError("deadline reached before lock acquire")
        if time.monotonic() - started >= timeout_s:
            fh.close()
            raise TimeoutError(
                f"lock {path} not free within {timeout_s:.0f}s "
                "(another resource_guard job holds it)"
            )
        time.sleep(1.0)


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------


def _log(msg: str) -> None:
    print(f"[resource_guard] {msg}", file=sys.stderr, flush=True)


def _systemd_available() -> bool:
    return shutil.which("systemd-run") is not None


def _systemd_prop_sets(mem_mib: int, cpu_percent: int,
                       tasks_max: int) -> list[list[str]]:
    """Candidate property sets, most complete first. Sets are dropped only
    after the previous one is empirically rejected."""
    full = [
        f"MemoryMax={mem_mib}M",
        "MemorySwapMax=0",
        f"CPUQuota={cpu_percent}%",
        f"TasksMax={tasks_max}",
        # Escalate to SIGKILL 5 s after a stop, so --timeout stays bounded.
        "TimeoutStopSec=5",
    ]
    return [
        full,
        [p for p in full
         if not p.startswith(("TasksMax=", "TimeoutStopSec="))],
        [p for p in full if not p.startswith(
            ("TasksMax=", "MemorySwapMax=", "TimeoutStopSec="))],
    ]


def _systemd_probe(props: list[str]) -> bool:
    """Empirically verify a property set with a /bin/true scope.
    Scopes block in the foreground and forward the exit code, so no
    --wait is allowed (it is rejected with --scope)."""
    argv = ["systemd-run", "--user", "--scope", "--quiet"]
    for p in props:
        argv += ["-p", p]
    argv += ["--", "/bin/true"]
    try:
        res = subprocess.run(argv, capture_output=True, timeout=15,
                             check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return res.returncode == 0


class RunResult:
    def __init__(self, returncode: int | None, wall_s: float,
                 timed_out: bool, mode: str) -> None:
        self.returncode = returncode
        self.wall_s = wall_s
        self.timed_out = timed_out
        self.mode = mode


def _finalize(proc: subprocess.Popen[bytes], returncode: int | None,
              wall_s: float, timed_out: bool, mode: str) -> RunResult:
    import resource

    rc = returncode
    if rc is None:
        try:
            rc = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            rc = proc.poll()  # may stay None: systemd-run outlived us
            if rc is None:
                _log("systemd-run outlived bounded waits; scope left to "
                     "systemd --collect GC; child exit code unknown")
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    _log(
        f"done mode={mode} exit={rc} wall={wall_s:.1f}s "
        f"ru_maxrss_of_direct_children={peak / KIB:.0f} MiB"
    )
    return RunResult(rc, wall_s, timed_out, mode)


def _systemctl(runner, action: list[str], timeout_s: float = 30.0) -> bool:
    """One bounded systemctl --user call; never propagates exceptions.
    `runner` is subprocess.run in production (self-tests inject mocks)."""
    try:
        res = runner(["systemctl", "--user"] + action,
                     capture_output=True, timeout=timeout_s, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        _log(f"systemctl {' '.join(action)} failed ({exc!r}); the request "
             "may still be queued in PID 1")
        return False
    if res.returncode != 0:
        raw = getattr(res, "stderr", b"") or b""
        text = (raw.decode(errors="replace")
                if isinstance(raw, (bytes, bytearray)) else str(raw))
        _log(f"systemctl {' '.join(action)} rc={res.returncode}: "
             f"{text.strip()}")
        return False
    return True


def _stop_scope(unit: str, wait_for_exit=None, runner=None,
                stop_timeout_s: float = 30.0, wait_timeout_s: float = 60.0,
                kill_wait_s: float = 30.0) -> bool:
    """Bounded cleanup ladder for OUR OWN unit only:

    1. systemctl --user stop <unit>.scope  (TimeoutExpired-safe)
    2. bounded wait for systemd-run to exit
    3. escalate: systemctl --user kill --signal=KILL <unit>.scope (own unit)
    4. bounded wait again; still stuck -> log and leave the scope to
       systemd (--collect garbage-collects it); the wrapper stops tracking
       but never kills systemd-run itself.
    """
    runner = runner or subprocess.run
    name = f"{unit}.scope"
    _log(f"stopping scope {name} (a unit started by this wrapper)")
    _systemctl(runner, ["stop", name], timeout_s=stop_timeout_s)
    if wait_for_exit is None:
        return True
    try:
        wait_for_exit(wait_timeout_s)
        return True
    except subprocess.TimeoutExpired:
        _log(f"scope {name} still present {wait_timeout_s:.0f}s after stop; "
             "escalating to SIGKILL on this own unit only")
    _systemctl(runner, ["kill", "--signal=KILL", name],
               timeout_s=stop_timeout_s)
    try:
        wait_for_exit(kill_wait_s)
        return True
    except subprocess.TimeoutExpired:
        _log(f"scope {name} outlived SIGKILL escalation; leaving it to "
             "systemd --collect GC")
        return False


def run_systemd_scope(cmd: list[str], props: list[str], timeout_s: float,
                      deadline: dt.datetime | None) -> RunResult:
    # Self-generated, sanitized unit name; random suffix avoids collision
    # with a stale scope left by a crashed earlier run.
    unit = f"rg-{os.getpid()}-{os.urandom(3).hex()}"
    argv = [
        "systemd-run", "--user", "--scope", "--quiet", "--collect",
        f"--unit={unit}",
    ]
    for p in props:
        argv += ["-p", p]
    argv += ["--"] + cmd
    stop_esc = ("5s" if any(p.startswith("TimeoutStopSec=") for p in props)
                else "systemd-default(~90s); escalation to SIGKILL may be "
                     "slow under the reduced property set")
    _log(f"systemd scope {unit}: caps={','.join(props)}; "
         f"stop_escalation={stop_esc}")
    start = time.monotonic()
    proc = subprocess.Popen(argv)
    try:
        proc.wait(timeout=timeout_s if timeout_s > 0 else None)
        return _finalize(proc, proc.returncode,
                         time.monotonic() - start, False, "systemd")
    except subprocess.TimeoutExpired:
        _log(f"timeout after {timeout_s:.0f}s; cleanup ladder on own scope")
        _stop_scope(unit, wait_for_exit=lambda t: proc.wait(timeout=t))
        return _finalize(proc, proc.poll(),
                         time.monotonic() - start, True, "systemd")
    except KeyboardInterrupt:
        _systemctl(subprocess.run, ["stop", f"{unit}.scope"], timeout_s=30)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            _log("systemd-run outlived stop on interrupt; scope left to "
                 "systemd GC")
        raise


def _apply_ulimits(mem_mib: int, timeout_s: float) -> None:
    """Child pre-exec limits. Honest limitations, printed by the parent:
    RLIMIT_AS caps virtual address space (can over-trigger on mmap-heavy
    tools) and RLIMIT_CPU caps CPU time (not wall-clock quota). No swap or
    CPUQuota enforcement is possible with ulimit. RLIMIT_NPROC is NOT set:
    it is a per-uid budget shared with every other session (~200 live
    processes on this host), so a value sized for one child causes
    spurious EAGAIN elsewhere -- the task bound exists only in the
    systemd path (TasksMax)."""
    import resource

    os.setsid()
    resource.setrlimit(resource.RLIMIT_AS, (mem_mib * MIB, mem_mib * MIB))
    if timeout_s > 0:
        secs = int(timeout_s) + 30
        resource.setrlimit(resource.RLIMIT_CPU, (secs, secs))


def run_ulimit(cmd: list[str], mem_mib: int, tasks_max: int,
               timeout_s: float, cpu_percent: int,
               deadline: dt.datetime | None) -> RunResult:
    _ = cpu_percent  # honest: CPUQuota is not enforceable with ulimit
    _log(
        "ulimit fallback: RLIMIT_AS(virtual,size-may-over-trigger) "
        f"{mem_mib} MiB"
        + (f", RLIMIT_CPU={int(timeout_s) + 30}s" if timeout_s > 0 else "")
        + "; swap, CPUQuota and task bounds are NOT enforceable with "
          "ulimit (RLIMIT_NPROC dropped: shared per-uid budget)"
        + f" [tasks_max={tasks_max} applies only in systemd mode]"
    )
    start = time.monotonic()
    proc = subprocess.Popen(cmd, preexec_fn=lambda: _apply_ulimits(
        mem_mib, timeout_s))
    try:
        proc.wait(timeout=timeout_s if timeout_s > 0 else None)
        return _finalize(proc, proc.returncode,
                         time.monotonic() - start, False, "ulimit")
    except subprocess.TimeoutExpired:
        _log(f"timeout after {timeout_s:.0f}s; terminating only our "
             f"process group {proc.pid}")
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return _finalize(proc, None, time.monotonic() - start, True,
                         "ulimit")
    except KeyboardInterrupt:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        raise


def run_capped(cmd: list[str], mem_mib: int, cpu_percent: int,
               tasks_max: int, timeout_s: float, no_systemd: bool,
               deadline: dt.datetime | None) -> RunResult:
    if not no_systemd and _systemd_available():
        for props in _systemd_prop_sets(mem_mib, cpu_percent, tasks_max):
            if _systemd_probe(props):
                return run_systemd_scope(cmd, props, timeout_s, deadline)
            _log(f"systemd scope rejected props {props}; trying reduced set")
        _log("systemd user scopes unavailable; falling back to ulimit")
    return run_ulimit(cmd, mem_mib, tasks_max, timeout_s, cpu_percent,
                      deadline)


# ---------------------------------------------------------------------------
# Delegation detection (argv inspection only; never probes daemons)
# ---------------------------------------------------------------------------

DELEGATORS = {"docker", "podman", "flatpak", "systemd-run", "systemctl"}

# Container-side caps that must be spelled out when wrapping podman/docker;
# verified against this host's `podman run --help` (see checkpoint).
CONTAINER_CAPS = ("--memory", "--memory-swap", "--cpus", "--pids-limit")


def check_delegation(cmd: list[str],
                     allow_delegation: bool) -> tuple[bool, str]:
    """Detect commands whose real work escapes this wrapper's cgroup/rlimits
    (daemon- or scope-delegated execution). Returns (ok_to_run, message).

    Hard caps are cgroup-scoped: a wrapped `podman`/`docker` client is
    capped, but the container runs in its own cgroup outside our unit;
    `flatpak run` relocates the app into its own app-*.scope (flatpak has
    NO per-run memory/cpu flags, and KiCad legitimately needs flatpak, so
    this is a loud allowed warning); nested systemd-run/systemctl spawn
    sibling scopes. Detection is argv-based; scripts that hide delegators
    cannot be seen here."""
    if not cmd:
        return True, ""
    base = os.path.basename(cmd[0])
    if base not in DELEGATORS:
        return True, ""
    if base in ("docker", "podman"):
        missing = [f for f in CONTAINER_CAPS
                   if not any(a == f or a.startswith(f + "=") for a in cmd)]
        gap = (f"DELEGATION: {base} containers run in their own cgroup, "
               "outside this wrapper's hard caps (only the client is "
               "capped).")
        if missing:
            if allow_delegation:
                return True, (f"WARNING {gap} --allow-delegation "
                              f"acknowledged; container-side flags still "
                              f"missing: {', '.join(missing)}.")
            return False, (
                f"{gap} Refusing to run without explicit container-side "
                f"limits; add tested flags: --memory --memory-swap --cpus "
                f"--pids-limit (missing: {', '.join(missing)}) or pass "
                "--allow-delegation to acknowledge the cap gap.")
        return True, (f"WARNING {gap} Container-side limits present "
                      f"({' '.join(CONTAINER_CAPS)}); relying on those.")
    if base == "flatpak":
        return True, (
            "WARNING DELEGATION: flatpak relocates the app into its own "
            "app-*.scope OUTSIDE this wrapper's hard caps; flatpak run has "
            "no per-run memory/cpu limit flags, so KiCad-via-flatpak runs "
            "capped only by the admission gates, not by cgroup limits.")
    gap = (f"DELEGATION: nested {base} spawns sibling scopes/daemon work; "
           "this wrapper's caps are not transitive.")
    if allow_delegation:
        return True, f"WARNING {gap} --allow-delegation acknowledged."
    return False, f"{gap} Refused; pass --allow-delegation to acknowledge."


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" in argv:
        idx = argv.index("--")
        return argv[:idx], argv[idx + 1:]
    return argv, []


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="resource_guard.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--min-avail-mib", type=float, default=6144,
                   help="admit only when MemAvailable >= this (default 6144)")
    p.add_argument("--psi-max-avg10", type=float, default=25.0,
                   help="postpone while PSI memory some avg10 exceeds this")
    p.add_argument("--wait", type=float, default=120,
                   help="max seconds to wait for admission (0 = one-shot)")
    p.add_argument("--no-wait", action="store_true",
                   help="alias for --wait 0")
    p.add_argument("--poll", type=float, default=5,
                   help="admission poll interval seconds")
    p.add_argument("--ignore-rust", action="store_true",
                   help="report but do not postpone on rust toolchain activity")
    p.add_argument("--rust-target-root", action="append", default=[],
                   metavar="DIR",
                   help="additional project root whose target/{debug,release}"
                        "/deps/ executables count as rust activity "
                        "(repeatable; default root ~/Projects/antani; env "
                        "RESOURCE_GUARD_RUST_TARGET_ROOTS os.pathsep list)")
    p.add_argument("--allow-delegation", action="store_true",
                   help="acknowledge and run delegating commands (podman/"
                        "docker without container-side limits, nested "
                        "systemd-run/systemctl) that escape wrapper caps")
    p.add_argument("--lock", default=DEFAULT_LOCK,
                   help="flock path (env RESOURCE_GUARD_LOCK)")
    p.add_argument("--lock-timeout", type=float, default=3600,
                   help="max seconds to wait for the single-job lock")
    p.add_argument("--timeout", type=float, default=7200,
                   help="command wall-clock timeout seconds (0 = none)")
    p.add_argument("--mem-mib", type=int, default=2048,
                   help="per-command memory cap MiB (default 2048)")
    p.add_argument("--cpu-percent", type=int, default=100,
                   help="CPUQuota percent (default 100 = one core)")
    p.add_argument("--tasks-max", type=int, default=256,
                   help="bounded task/pid count (default 256)")
    p.add_argument("--no-systemd", action="store_true",
                   help="force the setrlimit fallback")
    p.add_argument("--deadline",
                   default=os.environ.get("RESOURCE_GUARD_DEADLINE"),
                   help="ISO 8601; refuse to start past this")
    p.add_argument("--self-test", action="store_true",
                   help="run light bounded self-tests and exit")
    return p


def main(argv: list[str]) -> int:
    own_argv, cmd = _split_argv(argv)
    args = build_parser().parse_args(own_argv)
    if args.no_wait:
        args.wait = 0
    if args.self_test:
        return self_test(args)
    if not cmd:
        _log("usage error: no command after --")
        return 64
    ok_run, dmsg = check_delegation(cmd, args.allow_delegation)
    if dmsg:
        _log(dmsg)
    if not ok_run:
        return 64
    try:
        deadline = _parse_deadline(args.deadline)
    except ValueError:
        _log(f"usage error: unparseable --deadline {args.deadline!r}")
        return 64
    if deadline is not None and dt.datetime.now(dt.timezone.utc) >= deadline:
        _log(f"deadline {deadline.isoformat()} reached; refusing to start")
        return 4
    try:
        lock_fh = acquire_lock(args.lock, args.lock_timeout, deadline)
    except TimeoutError as exc:
        _log(f"lock: {exc}")
        return 4 if str(exc).startswith("deadline") else 3
    _log(f"single-job lock acquired: {args.lock}")
    env_roots = tuple(
        r for r in os.environ.get(
            "RESOURCE_GUARD_RUST_TARGET_ROOTS", "").split(os.pathsep) if r)
    roots = DEFAULT_TARGET_ROOTS + env_roots + tuple(args.rust_target_root)
    try:
        adm = Admission(args.min_avail_mib, args.psi_max_avg10, args.wait,
                        args.poll, args.ignore_rust, deadline, roots)
        ok, note = adm.wait()
        if not ok:
            reason, _, detail = note.partition("|")
            _log(f"{reason}" + (f": {detail}" if detail else ""))
            return 4 if "deadline" in reason else 2
        _log(f"admitted: {note}")
        if deadline is not None:
            rem = (deadline
                   - dt.datetime.now(dt.timezone.utc)).total_seconds()
            if rem <= 0:
                _log("deadline reached during admission; refusing to start")
                return 4
            if args.timeout > 0 and args.timeout > rem:
                _log(f"timeout clamped to deadline: {rem:.0f}s")
                args.timeout = rem
            elif args.timeout == 0:
                _log(f"no explicit timeout; clamping to deadline {rem:.0f}s")
                args.timeout = rem
        res = run_capped(cmd, args.mem_mib, args.cpu_percent,
                         args.tasks_max, args.timeout, args.no_systemd,
                         deadline)
        rc = res.returncode
        if rc is not None and rc < 0:
            # Normalize signal deaths to the shell convention 128+N
            # (e.g. -SIGKILL -> 137); sys.exit(-N) would surface as 256-N.
            rc = 128 - rc
        if res.timed_out:
            return 124
        return rc if rc is not None else 1
    finally:
        # flock released by process teardown; close explicitly for clarity.
        lock_fh.close()


# ---------------------------------------------------------------------------
# Self-tests: light, bounded (< ~120 s total; transient memory <= 256 MiB;
# mock payloads only -- no daemons, no installs, no unrelated processes)
# ---------------------------------------------------------------------------


def _self_run(script: str, extra: list[str], cmd: list[str],
              expect: set[int]) -> tuple[bool, str]:
    argv = [sys.executable, script] + extra + ["--"] + cmd
    res = subprocess.run(argv, capture_output=True, text=True, timeout=60,
                         check=False)
    ok = res.returncode in expect
    tail = (res.stderr or res.stdout).strip().splitlines()
    return ok, (f"rc={res.returncode} " + (tail[-1][:120] if tail else ""))


def self_test(args: argparse.Namespace) -> int:
    script = os.path.abspath(__file__)
    results: list[tuple[str, bool, str]] = []

    # T1: host inspection parses and reports (read-only).
    try:
        snap = memory_snapshot()
        ok = snap["mem_available_mib"] > 0 and snap["swap_free_mib"] >= 0
        results.append(("meminfo/psi/rust scan", ok,
                        f"avail={snap['mem_available_mib']:.0f} MiB "
                        f"psi={snap['psi_some_avg10']} "
                        f"rust={len(snap['rust'])}"))
    except Exception as exc:  # noqa: BLE001 -- self-test reports, not raises
        results.append(("meminfo/psi/rust scan", False, repr(exc)))

    # T2: flock contention: a second open of a held lock must not be
    # taken non-blocking; after release it must succeed.
    try:
        os.makedirs("/tmp/opencode", exist_ok=True)
        with open("/tmp/opencode/rg-selftest.lock", "a+b") as held, \
                open("/tmp/opencode/rg-selftest.lock", "a+b") as contender:
            fcntl.flock(held.fileno(), fcntl.LOCK_EX)
            try:
                fcntl.flock(contender.fileno(),
                            fcntl.LOCK_EX | fcntl.LOCK_NB)
                results.append(("flock contention", False,
                                "acquired a lock held by another fd"))
            except OSError as exc:
                results.append(("flock contention",
                                exc.errno in (errno.EACCES, errno.EAGAIN),
                                f"errno={exc.errno}"))
    except OSError as exc:
        results.append(("flock contention", False, repr(exc)))

    # T3: happy path, capped run of a trivial command (<=5 s). The
    # self-test uses its own lock with a short timeout so it can never
    # stall behind a real job.
    st_lock = "/tmp/opencode/rg-selftest-job.lock"
    base = ["--no-wait", "--lock", st_lock, "--lock-timeout", "10",
            "--timeout", "5", "--mem-mib", "256", "--min-avail-mib", "0"]
    ok, msg = _self_run(script, base,
                        [sys.executable, "-c", "print('ok')"], {0})
    results.append(("capped trivial run (auto systemd/ulimit)", ok, msg))

    # T4: memory cap enforcement: 200 MiB allocation inside a 128 MiB cap.
    t4_extra = ["--no-wait", "--lock", st_lock, "--lock-timeout", "10",
                "--timeout", "20", "--mem-mib", "128",
                "--min-avail-mib", "0", "--",
                sys.executable, "-c",
                "x = bytearray(200 * 1024 * 1024); x[-1] = 1; print('survived')"]
    res = subprocess.run([sys.executable, script] + t4_extra,
                         capture_output=True, text=True, timeout=90,
                         check=False)
    results.append(("memory cap enforced (no 'survived')",
                    res.returncode != 0 and "survived" not in res.stdout,
                    f"rc={res.returncode}"))

    # T5: timeout kills only our child: sleep 30 must end near ~2 s with 124.
    t0 = time.monotonic()
    ok_rc, msg = _self_run(script,
                           ["--no-wait", "--lock", st_lock,
                            "--lock-timeout", "10",
                            "--timeout", "2", "--min-avail-mib", "0"],
                           [sys.executable, "-c",
                            "import time; time.sleep(30)"], {124})
    elapsed = time.monotonic() - t0
    results.append(("timeout -> 124 in bounded time",
                    ok_rc and elapsed < 25, f"{msg} elapsed={elapsed:.1f}s"))

    # T6: admission denial one-shot with absurd memory requirement -> rc 2.
    ok, msg = _self_run(script,
                        ["--no-systemd", "--no-wait", "--lock", st_lock,
                         "--lock-timeout", "10",
                         "--min-avail-mib", "999999999"],
                        [sys.executable, "-c", "print('never')"], {2})
    results.append(("admission denial exit 2", ok, msg))

    # T7: ulimit fallback path works and enforces address-space cap.
    res7 = subprocess.run(
        [sys.executable, script, "--no-systemd", "--no-wait",
         "--lock", st_lock, "--lock-timeout", "10",
         "--timeout", "20", "--mem-mib", "128", "--min-avail-mib", "0",
         "--", sys.executable, "-c",
         "x = bytearray(200 * 1024 * 1024); x[-1] = 1; print('survived')"],
        capture_output=True, text=True, timeout=90, check=False)
    results.append(("ulimit fallback enforces cap",
                    res7.returncode != 0 and "survived" not in res7.stdout,
                    f"rc={res7.returncode}"))

    # T8: rust gate sees (a) compiled test binaries under a declared
    # project root's target dir and (b) executables under toolchain dirs,
    # via read-only exe paths. Fakes are real copies of /bin/sleep we start
    # and kill ourselves (symlinks would resolve to /bin/sleep).
    try:
        mock_a = "/tmp/opencode/rg-selftest-antani"
        mock_dep = os.path.join(mock_a, "target/debug/deps")
        mock_tc = "/tmp/opencode/rg-selftest-home/.rustup/toolchains/m/bin"
        os.makedirs(mock_dep, exist_ok=True)
        os.makedirs(mock_tc, exist_ok=True)
        fake_test = os.path.join(mock_dep, "fakecrate-0123456789abcdef")
        fake_ld = os.path.join(mock_tc, "fake-ld.lld")
        shutil.copy("/bin/sleep", fake_test)
        shutil.copy("/bin/sleep", fake_ld)
        sleepers = [subprocess.Popen([p, "25"]) for p in (fake_test, fake_ld)]
        try:
            time.sleep(0.5)
            res8 = subprocess.run(
                [sys.executable, script, "--no-wait", "--lock", st_lock,
                 "--lock-timeout", "10", "--min-avail-mib", "0",
                 "--rust-target-root", mock_a, "--", "/bin/true"],
                capture_output=True, text=True, timeout=60, check=False)
            hits = [lbl for _, lbl in _rust_processes((mock_a,))]
            results.append(("rust gate: exe-path detection (root+toolchain)",
                            res8.returncode == 2
                            and "RUST ACTIVE" in res8.stderr
                            and any("target-test-exe:" in h for h in hits)
                            and any("toolchain-exe:" in h for h in hits),
                            f"rc={res8.returncode} hits={hits}"))
        finally:
            for s in sleepers:
                s.kill()
                s.wait()
    except (OSError, Exception) as exc:  # noqa: BLE001
        results.append(("rust gate: exe-path detection (root+toolchain)",
                        False, repr(exc)))

    # T9: cleanup ladder mocked: stop TimeoutExpired tolerated; rc!=0 stop
    # + stuck wait escalates to own-unit SIGKILL; fully stuck scope is
    # left to systemd GC with a bounded return. No real units touched.
    try:
        ladder_ok = True
        fake_wait_ok = [0]

        def wait_ok(t):
            fake_wait_ok[0] += 1
            return 0

        def runner_raise(argv, **kw):
            raise subprocess.TimeoutExpired(argv, kw.get("timeout", 0))

        ladder_ok &= _stop_scope("rg-mock-a", wait_for_exit=wait_ok,
                                 runner=runner_raise)

        calls9: list[list[str]] = []

        def runner_rc1(argv, **kw):
            calls9.append(list(argv))

            class R:
                returncode = 1
                stderr = b"mock failure"
            return R()

        waits: list[float] = []

        def wait_stuck_once(t):
            waits.append(t)
            if len(waits) == 1:
                raise subprocess.TimeoutExpired("wait", t)
            return 0

        ladder_ok &= _stop_scope("rg-mock-b", wait_for_exit=wait_stuck_once,
                                 runner=runner_rc1)
        escalated = any("kill" in c for c in calls9)
        ladder_ok &= escalated

        def wait_forever(t):
            raise subprocess.TimeoutExpired("wait", t)

        ladder_ok &= not _stop_scope("rg-mock-c", wait_for_exit=wait_forever,
                                     runner=runner_rc1)
        results.append(("cleanup ladder: mocked failures bounded",
                        ladder_ok,
                        f"waits={waits} escalated={escalated}"))
    except Exception as exc:  # noqa: BLE001
        results.append(("cleanup ladder: mocked failures bounded",
                        False, repr(exc)))

    # T10: delegation detection: fake delegators (symlinks to /bin/true;
    # detection is argv basename based). podman w/o caps refused rc 64;
    # with all tested caps flags runs with a DELEGATION warning; flatpak
    # allowed with loud accurate warning; fake systemd-run refused 64,
    # allowed only with --allow-delegation.
    try:
        fakebin = "/tmp/opencode/rg-selftest-bin"
        os.makedirs(fakebin, exist_ok=True)
        for nm in ("podman", "flatpak", "systemd-run"):
            tp = os.path.join(fakebin, nm)
            if not os.path.exists(tp):
                os.symlink("/bin/true", tp)
        flags = ["--memory", "256m", "--memory-swap", "256m",
                 "--cpus", "1", "--pids-limit", "64"]

        def d_run(podman_extra):
            return subprocess.run(
                [sys.executable, script, "--no-systemd", "--no-wait",
                 "--lock", st_lock, "--lock-timeout", "10",
                 "--timeout", "5", "--min-avail-mib", "0",
                 "--", os.path.join(fakebin, "podman")] + podman_extra,
                capture_output=True, text=True, timeout=60, check=False)

        r_noflags = d_run([])
        r_flags = d_run(flags)
        refuse_ok = (r_noflags.returncode == 64
                     and "--memory" in r_noflags.stderr
                     and "--pids-limit" in r_noflags.stderr)
        allow_ok = (r_flags.returncode == 0
                    and "DELEGATION" in r_flags.stderr)
        r_flat = subprocess.run(
            [sys.executable, script, "--no-systemd", "--no-wait",
             "--lock", st_lock, "--lock-timeout", "10", "--timeout", "5",
             "--min-avail-mib", "0", "--", os.path.join(fakebin, "flatpak")],
            capture_output=True, text=True, timeout=60, check=False)
        flat_ok = (r_flat.returncode == 0 and "flatpak" in r_flat.stderr
                   and "app-" in r_flat.stderr)
        r_sr = subprocess.run(
            [sys.executable, script, "--no-systemd", "--no-wait",
             "--lock", st_lock, "--lock-timeout", "10", "--timeout", "5",
             "--min-avail-mib", "0", "--",
             os.path.join(fakebin, "systemd-run")],
            capture_output=True, text=True, timeout=60, check=False)
        r_sr_ok = subprocess.run(
            [sys.executable, script, "--no-systemd", "--no-wait",
             "--lock", st_lock, "--lock-timeout", "10", "--timeout", "5",
             "--min-avail-mib", "0", "--allow-delegation", "--",
             os.path.join(fakebin, "systemd-run")],
            capture_output=True, text=True, timeout=60, check=False)
        sr_ok = (r_sr.returncode == 64
                 and "--allow-delegation" in r_sr.stderr
                 and r_sr_ok.returncode == 0)
        results.append(("delegation detect/warn/refuse/opt-in",
                        refuse_ok and allow_ok and flat_ok and sr_ok,
                        f"podman={r_noflags.returncode}/{r_flags.returncode} "
                        f"flatpak={r_flat.returncode} "
                        f"sysrun={r_sr.returncode}/{r_sr_ok.returncode}"))
    except (OSError, Exception) as exc:  # noqa: BLE001
        results.append(("delegation detect/warn/refuse/opt-in",
                        False, repr(exc)))

    # T10b: recommended podman caps flags exist in this host's `podman run
    # --help` (tested requirements); SKIP-PASS if podman is absent.
    if shutil.which("podman"):
        try:
            help_out = subprocess.run(["podman", "run", "--help"],
                                      capture_output=True, text=True,
                                      timeout=20, check=False)
            missing_flags = [f for f in CONTAINER_CAPS
                             if f not in help_out.stdout]
            results.append(("podman caps flags verified against help",
                            not missing_flags,
                            f"missing={missing_flags}"))
        except (OSError, subprocess.TimeoutExpired) as exc:
            results.append(("podman caps flags verified against help",
                            False, repr(exc)))
    else:
        results.append(("podman caps flags verified against help",
                        True, "SKIP: podman not installed"))

    # T11: deadline handling: past deadline -> rc 4; unparseable -> rc 64.
    r_past = subprocess.run(
        [sys.executable, script, "--no-wait", "--lock", st_lock,
         "--lock-timeout", "10", "--deadline", "2000-01-01T00:00:00+00:00",
         "--", "/bin/true"], capture_output=True, text=True, timeout=30,
        check=False)
    r_bad = subprocess.run(
        [sys.executable, script, "--no-wait", "--lock", st_lock,
         "--lock-timeout", "10", "--deadline", "not-a-date",
         "--", "/bin/true"], capture_output=True, text=True, timeout=30,
        check=False)
    results.append(("deadline: past -> rc 4, bad ISO -> rc 64",
                    r_past.returncode == 4 and r_bad.returncode == 64,
                    f"past={r_past.returncode} bad={r_bad.returncode}"))

    width = max(len(name) for name, _, _ in results)
    all_ok = True
    for name, ok, detail in results:
        all_ok = all_ok and ok
        _log(f"self-test {'PASS' if ok else 'FAIL'}  "
             f"{name.ljust(width)}  {detail}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
