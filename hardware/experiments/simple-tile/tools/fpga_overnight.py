#!/usr/bin/env python3
"""fpga_overnight.py -- bounded overnight FPGA worker orchestrator (2026-10-15).

Runs bounded (~45-60 min) `opencode run --standalone` batches on
cern/Kimi-K3-FLATIRON (unmetered) in ONE dedicated session
(ses_fpga_overnight_20261015), between a scheduled start and a hard
deadline. Provider failures retry with 15/30/60 min backoff. A worker
outcome sentinel (READY/BLOCKED/COMPLETE + next) decides continuation;
no token churn on blocked/complete states.

Owns only: its state dir (FPGA_OVERNIGHT_STATE) and
checkpoints/fpga-overnight.md in the repo. Never: commits, installs,
hardware, other projects, other opencode sessions (detection read-only).

Modes: run (service mode), self-test (pure/mock, no model traffic),
status (human summary).
"""
from __future__ import annotations

import datetime as dt
import os
import re
import signal
import socket
import subprocess
import sys
import time

# --------------------------------------------------------------------------
# Configuration (service passes these via EnvironmentFile; defaults match).
# --------------------------------------------------------------------------

def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


START = dt.datetime.fromisoformat(
    _env("FPGA_OVERNIGHT_START", "2026-10-15T21:43:00+02:00"))
DEADLINE = dt.datetime.fromisoformat(
    _env("FPGA_OVERNIGHT_DEADLINE", "2026-10-16T11:00:00+02:00"))
STATE = _env("FPGA_OVERNIGHT_STATE", "/tmp/opencode/fpga-overnight-20261015")
REPO = _env("FPGA_OVERNIGHT_REPO",
            "/home/marco/Documents/OrturanoLabs/isomorphic_keyboard")
SESSION = _env("FPGA_OVERNIGHT_SESSION", "ses_fpga_overnight_20261015")
MODEL = _env("FPGA_OVERNIGHT_MODEL", "cern/Kimi-K3-FLATIRON")
AGENT = _env("FPGA_OVERNIGHT_AGENT", "cern-worker")
GUARD = _env(
    "FPGA_OVERNIGHT_GUARD",
    REPO + "/hardware/experiments/simple-tile/tools/resource_guard.py")
PROBE = _env("FPGA_PROVIDER_PROBE", "aigw.cern.ch:443")  # informational gate

STOP = os.path.join(STATE, "STOP")
LOGDIR = os.path.join(STATE, "logs")
SCHEDLOG = os.path.join(LOGDIR, "scheduler.log")
REPO_CHECKPOINT = (REPO + "/hardware/experiments/simple-tile/"
                   "checkpoints/fpga-overnight.md")

BATCH_TARGET_MIN = (45, 60)          # worker-side substantive window
BATCH_HARD_TIMEOUT_S = 4500          # kill a still-running batch at 75 min
MIN_REMAINING_TO_START_S = 900       # no new batch < 15 min before deadline
BACKOFF_LADDER_S = (900, 1800, 3600)  # 15/30/60 min, capped
MAX_FAIL_STREAK = 6                  # stop dumb looping on repeated failures
MAX_NO_OUTCOME = 2
MAX_TIMEOUT_STREAK = 3

SENTINEL_RE = re.compile(
    r"FPGA_OVERNIGHT_OUTCOME:\s*(READY|BLOCKED|COMPLETE)", re.IGNORECASE)
PROVIDER_RE = re.compile(
    r"(connection refused|econnrefused|econnreset|etimedout|ename|"
    r"could not resolve|name or service not known|fetch failed|"
    r"socket hang up|network|provider\s*error|api\s*error|"
    r"server\s*error|bad[-_ ]response|status\s*code\s*5\d\d|"
    r"\b50[234]\b|\b429\b|too many requests|rate[-_ ]?limit|"
    r"insufficient[_ ]?quota|quota exceeded|overloaded|"
    r"context (length|window)|model .*(not found|unavailable)|"
    r"unauthorized|401|forbidden|internal\s*error)",
    re.IGNORECASE)

# Redaction: never put secret-looking values into logs/checkpoints. Applied
# to anything derived from foreign cmdlines or worker output.
SECRET_RE = re.compile(
    r"(?i)(\"?(?:api[_-]?key|token|secret|password|passwd|authorization)\"?"
    r"\s*[=:]\s*\"?)([^\"\s,]{4,})")
BEARER_RE = re.compile(r"(?i)bearer\s+\S+")


def _redact(text: str) -> str:
    text = BEARER_RE.sub("Bearer ***", text)  # before SECRET_RE eats 'Bearer'
    return SECRET_RE.sub(lambda m: m.group(1) + "***", text)


STOP_EVENT = False  # set by SIGTERM handler / STOP sentinel

# Last batch teardown context, so finalize() (STOP / RuntimeMaxSec SIGTERM /
# deadline exits) can also sweep our own leftovers after a hard stop.
LAST_CTX: dict = {"child_pid": None, "child_start": None,
                  "snapshot": {}, "label": "no batch yet"}


def now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def log(msg: str) -> None:
    line = f"[{now():%Y-%m-%d %H:%M:%S %z}] {msg}"
    try:
        os.makedirs(LOGDIR, exist_ok=True)
        with open(SCHEDLOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    print(line, file=sys.stderr, flush=True)


def repo_checkpoint_append(text: str) -> None:
    try:
        with open(REPO_CHECKPOINT, "a", encoding="utf-8") as fh:
            fh.write(_redact(text))
    except OSError as exc:
        log(f"WARNING: repo checkpoint append failed: {exc!r}")


def handle_sigterm(signum, frame):  # noqa: ANN001, ARG001
    global STOP_EVENT
    STOP_EVENT = True
    log("SIGTERM received: stopping after current child teardown")


def stop_requested() -> bool:
    return STOP_EVENT or os.path.exists(STOP)


def sleep_sliced(seconds: float, slice_s: float = 10.0) -> None:
    """Interruptible coarse sleep; returns early on STOP/deadline."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if stop_requested() or now() >= DEADLINE:
            return
        time.sleep(min(slice_s, max(end - time.monotonic(), 0.5)))


# --------------------------------------------------------------------------
# Guards: admission (memory/PSI/rust via resource_guard), provider probe,
# single-writer enforcement. All detection strictly read-only.
# --------------------------------------------------------------------------

def admission_probe() -> tuple[bool, str]:
    """One-shot resource_guard admission check around /bin/true.

    Inherits guard defaults: MemAvailable >= 6144 MiB, PSI some avg10 <= 25,
    Rust-toolchain activity gate (never --ignore-rust). Uses our own lock so
    the shared default lock (serializing real heavy jobs) is untouched.
    rc 0 admitted; rc 2 denied; rc 4 deadline; other -> denied (safe).

    Honest memory accounting: the service cgroup MemoryMax=3072M covers the
    scheduler + opencode client/server only. resource_guard heavy jobs run
    in SIBLING rg-*.scope cgroups with their own per-job caps; that memory
    is NOT inherited inside the service cap, nor counted against it. Host
    worst case ~= service 3 GiB + one guarded job (<= 2 GiB default). This
    whole-system headroom is what the 6144 MiB admission gate protects."""
    argv = [sys.executable, GUARD, "--no-wait",
            "--lock", os.path.join(STATE, "admission.lock"),
            "--lock-timeout", "15", "--timeout", "30", "--mem-mib", "256",
            "--min-avail-mib", "6144", "--deadline", DEADLINE.isoformat(),
            "--", "/bin/true"]
    try:
        res = subprocess.run(argv, capture_output=True, text=True,
                             timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"guard probe error {exc!r}"
    tail = (res.stderr or "").strip().splitlines()
    note = tail[-1][:220] if tail else f"rc={res.returncode}"
    return (res.returncode == 0), f"guard rc={res.returncode} {note}"


def provider_probe() -> bool:
    if not PROBE:
        return True
    host, _, port = PROBE.rpartition(":")
    try:
        with socket.create_connection((host, int(port or "443")), timeout=8):
            return True
    except (OSError, ValueError):
        return False


def _parse_stat_fields(text: str) -> tuple[int, int, str]:
    """(ppid, start_ticks, state) from /proc/<pid>/stat content. comm may
    contain spaces/parens, so parse after the LAST ')'."""
    tail = text.rsplit(")", 1)[-1].split()
    return int(tail[1]), int(tail[19]), tail[0]


def _proc_stat(pid: int) -> tuple[int, int, str] | None:
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return _parse_stat_fields(fh.read())
    except (OSError, ValueError, IndexError):
        return None


def _proc_start(pid: int) -> int | None:
    st = _proc_stat(pid)
    return st[1] if st else None


def _now_ticks() -> int:
    """Approximate current time in the same clock ticks /proc/stat uses
    (CLOCK_MONOTONIC is seconds-since-boot on Linux). Fallback attribution
    for the instant right after spawn where /proc/<pid> may not exist yet."""
    try:
        return int(time.monotonic() * os.sysconf("SC_CLK_TCK"))
    except (ValueError, OSError, AttributeError):
        return int(time.monotonic() * 100)


def _session_pids() -> list[tuple[int, int, str]]:
    """[(pid, ppid, cmdline)] whose cmdline mentions our session id."""
    found = []
    for pid, ppid, _start, cmd in _marker_pids((SESSION,)):
        found.append((pid, ppid, cmd))
    return found


def _marker_pids(markers: tuple[str, ...]) -> list[tuple[int, int, int, str]]:
    """[(pid, ppid, start_ticks, cmdline)] whose cmdline contains a marker.
    Read-only scan."""
    found = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        pid = int(name)
        st = _proc_stat(pid)
        if st is None:
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                cmd = fh.read().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if any(m in cmd for m in markers):
            found.append((pid, st[0], st[1], cmd.strip()))
    return found


def _descendants(root: int) -> set[int]:
    children: dict[int, list[int]] = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        st = _proc_stat(int(name))
        if st is None:
            continue
        children.setdefault(st[0], []).append(int(name))
    out, stack = set(), [root]
    while stack:
        for c in children.pop(stack.pop(), []):
            out.add(c)
            stack.append(c)
    return out


def ensure_single_writer(child_pid: int | None) -> tuple[bool, str]:
    """No foreign process may reference our session. Our own child and its
    descendants are expected; anything else blocks this batch (no duplicate
    writers). Read-only."""
    allowed = {os.getpid()}
    if child_pid is not None:
        allowed.add(child_pid)
        allowed |= _descendants(child_pid)
    foreign = [(p, c) for p, _pp, c in _session_pids() if p not in allowed]
    if foreign:
        detail = "; ".join(
            f"pid {p}: {_redact(c)[:150]}" for p, c in foreign[:4])
        return False, detail
    return True, ""


# --------------------------------------------------------------------------
# Batch execution
# --------------------------------------------------------------------------

def kill_child_tree(proc: subprocess.Popen) -> None:
    """Terminate the process GROUP we spawned (start_new_session). Even when
    the client already exited, caller still runs batch_teardown(): detached
    leftovers are NOT covered here."""
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        try:
            proc.terminate()
        except OSError:
            pass
    try:
        proc.wait(timeout=8)
        return
    except subprocess.TimeoutExpired:
        log(f"child pgid {proc.pid} ignored SIGTERM; SIGKILL")
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        log("WARNING: child unreaped after SIGKILL; leaving to init")


# --------------------------------------------------------------------------
# Own-leftover teardown. resource_guard runs heavy commands in SIBLING
# systemd scopes (rg-<pid>-<hex>.scope) that escape this service's cgroup
# (KillMode=control-group does NOT reach them), and a crashed client can
# leave a detached standalone server/background tool writing. Everything
# below is strictly ownership-attributed: we only ever signal (a) pids from
# our own batch snapshot identity-checked by start-ticks, (b) cmdlines
# carrying our dedicated session marker started at/after our batch child,
# (c) rg-*.scope units whose embedded wrapper pid is one of our known pids.
# Anything not attributable is reported and left untouched (the
# single-writer guard will block the next batch instead of risking
# collateral kills).
# --------------------------------------------------------------------------

SCOPE_NAME_RE = re.compile(r"^rg-(\d+)-[0-9a-f]{6}\.scope$")


def _pid_exists(pid: int) -> bool:
    """Alive AND not a zombie (same-uid /proc read is enough; a zombie is
    already dead, just unreaped)."""
    st = _proc_stat(pid)
    if st is None:
        return False
    return st[2] != "Z"


def _term_kill(pids: list[int], grace_s: float = 2.0) -> None:
    """SIGTERM, bounded grace, SIGKILL leftovers. Only pids given."""
    live = set()
    for p in pids:
        try:
            os.kill(p, signal.SIGTERM)
            live.add(p)
        except OSError:
            pass
    end = time.monotonic() + grace_s
    while live and time.monotonic() < end:
        live = {p for p in live if _pid_exists(p)}
        if live:
            time.sleep(0.2)
    for p in live:
        try:
            os.kill(p, signal.SIGKILL)
        except OSError:
            pass


def _sweep_marked_leftovers(child_start: int | None,
                            markers: tuple[str, ...] = (SESSION,)) -> int:
    """Kill processes carrying our dedicated session marker started at/after
    our batch child. Conservative: earlier/foreign marker carriers are only
    logged, never signaled. Returns kill count."""
    to_kill, skipped = [], []
    for pid, _ppid, start, cmd in _marker_pids(markers):
        if pid == os.getpid():
            continue
        if child_start is not None and start < child_start:
            skipped.append((pid, cmd))
        else:
            to_kill.append(pid)
            log(f"sweep: SIGTERM own leftover pid {pid}: "
                f"{_redact(cmd)[:140]}")
    for pid, cmd in skipped:
        log(f"sweep: NOT ours (predates batch, left running) pid {pid}: "
            f"{_redact(cmd)[:140]}")
    if to_kill:
        _term_kill(to_kill)
        for pid in to_kill:
            if _pid_exists(pid):
                log(f"sweep: WARNING pid {pid} survived SIGKILL; "
                    "single-writer guard will block on it")
    return len(to_kill)


def _parse_scope_units(text: str) -> list[str]:
    units = []
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0].endswith(".scope"):
            units.append(parts[0])
    return units


def _list_scope_units() -> list[str]:
    try:
        res = subprocess.run(
            ["systemctl", "--user", "list-units", "--type=scope", "--all",
             "--no-legend", "--no-pager", "--plain"],
            capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return _parse_scope_units(res.stdout)


def _own_rg_scopes(owned_pids: set[int],
                   units: list[str] | None = None) -> list[str]:
    """OUR resource_guard scopes only: the unit name embeds the wrapper pid
    (rg-<pid>-<hex>.scope), which must be one of our captured batch pids.
    Never prefix/glob matches: a foreign rg scope from another project is
    left strictly alone."""
    if units is None:
        units = _list_scope_units()
    out = []
    for unit in units:
        m = SCOPE_NAME_RE.match(unit)
        if m and int(m.group(1)) in owned_pids:
            out.append(unit)
    return out


def _stop_own_rg_scopes(owned_pids: set[int]) -> None:
    """Stop exactly our own rg-*.scope units (bounded). These escape the
    service cgroup, so service stop/KillMode never reaps them."""
    units = _own_rg_scopes(owned_pids)
    for unit in units:
        log(f"sweep: stopping own scope {unit} (escapes service cgroup)")
        try:
            subprocess.run(["systemctl", "--user", "stop", unit],
                           capture_output=True, timeout=8, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            log(f"sweep: scope stop error {unit}: {exc!r}")
    still = [u for u in _own_rg_scopes(owned_pids) if u in units]
    for unit in still:
        log(f"sweep: SIGKILL own scope {unit}")
        try:
            subprocess.run(["systemctl", "--user", "kill",
                            "--signal=KILL", unit],
                           capture_output=True, timeout=8, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            log(f"sweep: scope kill error {unit}: {exc!r}")


def batch_teardown(child_pid: int | None, child_start: int | None,
                   snapshot: dict[int, int | None], label: str) -> None:
    """Bounded post-batch / hard-stop cleanup of ONLY our own leftovers;
    see ownership rules above. snapshot = {pid: start_ticks} captured while
    our tree was alive. Never raises; logs and moves on."""
    try:
        owned = set(snapshot)
        if child_pid is not None:
            owned.add(child_pid)
        # Identity-checked survivors: pid currently holds the SAME process
        # (start-ticks equal the captured ones -- reuse-safe) even if it
        # escaped the process group via setsid.
        survivors = []
        for p, st0 in snapshot.items():
            if p == os.getpid() or st0 is None:
                continue
            if _proc_start(p) == st0:
                survivors.append(p)
        if survivors:
            log(f"teardown {label}: {len(survivors)} owned pid(s) alive "
                f"post-exit (detached): {survivors[:10]}")
            _term_kill(survivors)
        _sweep_marked_leftovers(child_start)
        _stop_own_rg_scopes(owned)
    except Exception as exc:  # noqa: BLE001 -- teardown must never raise
        log(f"teardown {label}: INTERNAL ERROR {exc!r}; staying conservative")


def build_prompt(batch: int, batch_dir: str, first: bool,
                 prev_next: str, prev_outcome: str) -> str:
    head = f"""You are the unattended overnight FPGA worker: session {SESSION}, batch {batch}.
Authorization window: 2026-10-15 21:43 to 2026-10-16 11:00 Europe/Rome.
HARD deadline env = {DEADLINE.isoformat()} (check `date` periodically; wind
down substantive work by 10:40 and always leave time to flush checkpoints).
If file {STOP} appears, stop work within one step, write the outcome file
with your status, and exit.

HARD RULES (violating these wastes the night):
- No git commit/push/reset/clean, no installs, no purchases/logins/
  submissions, no hardware or FPGA programming. Several are permission-denied;
  do not try to route around denies.
- You may create/modify ONLY under:
  hardware/experiments/simple-tile/fpga/** and
  hardware/experiments/simple-tile/checkpoints/fpga-01.md (append evidence) and
  {batch_dir}/ (outcome file).
- Do NOT edit docs/FPGA_PLAN.md, docs/** otherwise, firmware/**, production/**,
  root tools/**, or any other project. Preserve ALL uncommitted user work
  exactly; never revert, overwrite, or stash it.
- Ordered register FPGA-01..04: work in order, no silent waivers. Record
  blockers as blockers. "Feasible improvement/preparation" = real recorded
  progress, not acceptance-gate completion claims.
- Heavy commands (synthesizers, PnR, KiCad CLI, board generators, checkers)
  run ONLY serially through resource_guard.py, each with explicit caps, e.g.:
  python3 {GUARD} --timeout 3300 --mem-mib 2048 \\
      --deadline "{DEADLINE.isoformat()}" --lock-timeout 600 -- YOUR_CMD
  Never pass --ignore-rust. Default heavy cap 2048 MiB; use 3072 ONLY if your
  own fresh pre-check shows MemAvailable >= 9216 MiB, no Rust activity and
  PSI some avg10 <= 10 (re-read /proc/meminfo and /proc/pressure/memory).
  On admission denial (rc 2/3/4): defer heavy work, switch to light
  doc/analysis tasks; never spin waiting on memory.
- Do not attach to, resume, or modify any other opencode session (in
  particular NOT ses_ec4abb8cdffepb5cQvRYDDVTDd). Detect leftovers read-only
  (pgrep -af opencode). If a live foreign process references session {SESSION}
  or writes fpga/board/**, do not write: outcome BLOCKED, explain.
- End background work BEFORE exit: the orchestrator sweeps, after every batch
  and at hard stop, leftover processes carrying this session id and any
  rg-*.scope your batch started. A process you leave behind is killed.

OUTCOME PROTOCOL (mandatory at end of batch):
1. Append evidence to hardware/experiments/simple-tile/checkpoints/fpga-01.md.
2. Write exactly:
   mkdir -p {batch_dir}
   and file {batch_dir}/outcome.env with lines:
     OUTCOME=READY|BLOCKED|COMPLETE
     NEXT=<one line: the concrete next actionable, unblocked step or 'none'>
     SUMMARY=<one line: what this batch actually did, commands + results>
   READY = progress made and real unblocked actionable work remains.
   BLOCKED = remaining work needs purchase/quote/login/hardware/permission.
   COMPLETE = nothing actionable remains in tonight's scope.
3. End your final message with one line:
   FPGA_OVERNIGHT_OUTCOME: <READY|BLOCKED|COMPLETE> | next: ... | summary: ...
A missing outcome file wastes the batch. Target {BATCH_TARGET_MIN[0]}-{BATCH_TARGET_MIN[1]}
minutes of substantive work, then a clean stop even mid-task.
"""
    if first:
        body = """
MANDATORY BOOTSTRAP THIS BATCH (read-only, before any edit):
1. Read AGENTS.md, docs/FPGA_PLAN.md, docs/architecture/current-development.md.
2. Read these checkpoints (fpga-01.md is authoritative):
   hardware/experiments/simple-tile/checkpoints/fpga-01.md,
   fpga-01-review.md, fpga-01-validation.md, fpga-resource.md,
   fpga-downstream-preparation.md, fpga-programming-review.md,
   and fpga-overnight.md.
3. Run `git status --porcelain` and `git diff --stat` (read-only). The
   uncommitted fpga/board/** changes are PRIOR SESSION WORK: preserve exactly.
4. `pgrep -af opencode` (read-only): confirm no surviving worker jobs.
VERIFIED STATE (do not re-verify unless repairing staleness): r6 batch:
fresh ERC 0 violations; S1-S7 schematic checks pass (S4 pad parity 144==144);
45 nets / 65 parts; DRC 0 error-severity violations, 107 cosmetic silk
warnings; 99 unconnected items (unrouted placement prototype, NOT fab-ready);
new d/e/f negative controls fire. Assembly quote NOT OBTAINED (no purchases);
0R source-termination positions configurable but bench-unproven; FPGA-01
remains in progress.
THEN: pick the next FPGA-01 steps from fpga-01.md's own next actions
(regulator/decoupling closure, schematic-board consistency, termination
rationale documentation, readiness/power_reg consistency, distributor-
agnostic BOM/quote preparation, then FPGA-02 preparation such as routing and
layer-comparison planning). Prefer several small verified steps over one
fragile one. Do not rerun expensive jobs whose verified results stand.
"""
    else:
        body = f"""
CONTINUATION. Previous batch outcome: {prev_outcome}; recorded next step:
{prev_next}
First re-read your checkpoint tail (fpga-01.md) and `git status --porcelain`
(read-only): confirm your own files are as you left them; foreign changes in
your owned paths mean BLOCKED. Then execute the recorded next step, choosing
details per the ordered register. If the recorded next step is done or
nonsensical, derive the next highest-value feasible FPGA-01 action from the
checkpoint; if only blocked actions remain, use outcome BLOCKED with the
blocker in NEXT.
"""
    return head + body


def classify(batch_dir: str, rc: int | None, timed_out: bool,
             log_tail: str, ended: str | None = None) -> tuple[str, str]:
    """Truthful outcome: sentinel file > sentinel line > provider-error
    heuristics > unknown. Success is never inferred from exit code alone.
    ended: None=bare exit, budget|stop|deadline=we killed the child."""
    env_path = os.path.join(batch_dir, "outcome.env")
    try:
        with open(env_path, encoding="utf-8") as fh:
            env = dict(line.strip().split("=", 1) for line in fh
                       if "=" in line and not line.startswith("#"))
        outcome = env.get("OUTCOME", "").upper()
        if outcome in ("READY", "BLOCKED", "COMPLETE"):
            return outcome, (f"file OUTCOME={outcome} "
                             f"NEXT={env.get('NEXT', '')[:120]} "
                             f"SUMMARY={env.get('SUMMARY', '')[:160]}")
    except OSError:
        pass
    m = None
    for m in SENTINEL_RE.finditer(log_tail):
        pass  # last occurrence wins
    if m:
        return m.group(1).upper(), "sentinel line in output"
    if timed_out or ended:
        why = {"budget": f"budget {BATCH_HARD_TIMEOUT_S}s",
               "stop": "STOP requested",
               "deadline": "hard deadline"}.get(ended or "budget", ended)
        return "TIMEOUT", f"we killed the child ({why}); no outcome written"
    if PROVIDER_RE.search(log_tail):
        return "PROVIDER_FAIL", "provider/model/API/network error in output"
    if rc in (None, 0):
        return "NO_OUTCOME", f"rc={rc} but no outcome file or sentinel"
    return "FAIL_UNKNOWN", f"rc={rc}, no outcome, no provider pattern"


def run_batch(batch: int, prev_next: str, prev_outcome: str) -> tuple[str, str]:
    batch_dir = os.path.join(STATE, "batches", f"{batch:03d}")
    os.makedirs(batch_dir, exist_ok=True)
    for stale in ("outcome.env",):  # never read a previous batch's outcome
        try:
            os.remove(os.path.join(batch_dir, stale))
        except OSError:
            pass
    prompt = build_prompt(batch, batch_dir, batch == 1, prev_next, prev_outcome)
    with open(os.path.join(batch_dir, "prompt.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(prompt)
    out_path = os.path.join(batch_dir, "output.jsonl")
    env = dict(os.environ)
    env.update({
        "FPGA_OVERNIGHT_BATCH": str(batch),
        "FPGA_OVERNIGHT_DEADLINE": DEADLINE.isoformat(),
        "FPGA_OVERNIGHT_STATE": STATE,
    })
    argv = ["opencode", "run", "--standalone", "--model", MODEL,
            "--agent", AGENT, "--auto", "--format", "json",
            "--session", SESSION, "--title",
            f"fpga-overnight-20261015 batch {batch}", prompt]
    remaining = (DEADLINE - now()).total_seconds()
    budget = max(min(BATCH_HARD_TIMEOUT_S, remaining - 45), 60)
    log(f"batch {batch}: spawning (budget {budget:.0f}s; log {out_path})")
    t0 = time.monotonic()
    child_start: int | None = None
    # {pid: start_ticks} identity map of everything in our batch tree,
    # refreshed at each wait tick (captured while processes are alive).
    snapshot: dict[int, int | None] = {}
    with open(out_path, "wb") as out:
        try:
            proc = subprocess.Popen(argv, cwd=REPO, env=env, stdout=out,
                                    stderr=subprocess.STDOUT,
                                    start_new_session=True)
        except OSError as exc:
            return "FAIL_UNKNOWN", f"spawn failed: {exc!r}"
        child_start = _proc_start(proc.pid)
        if child_start is None:  # spawn race: keep attribution sound
            child_start = _now_ticks()
        snapshot = {proc.pid: child_start}
        LAST_CTX.update({"child_pid": proc.pid, "child_start": child_start,
                         "snapshot": snapshot,
                         "label": f"batch {batch} (live)"})
        with open(os.path.join(STATE, "worker.pid"), "w") as pf:
            pf.write(str(proc.pid))
        timed_out = False
        ended: str | None = None
        while True:
            try:
                proc.wait(timeout=10)
                break
            except subprocess.TimeoutExpired:
                snapshot = {proc.pid: child_start}
                for p in _descendants(proc.pid):
                    snapshot[p] = _proc_start(p)
                LAST_CTX["snapshot"] = dict(snapshot)
                if stop_requested():
                    ended = "stop"
                    log("STOP: terminating current batch child")
                    kill_child_tree(proc)
                    break
                if now() >= DEADLINE:
                    ended = "deadline"
                    log("deadline reached: terminating current batch child")
                    kill_child_tree(proc)
                    break
                if time.monotonic() - t0 > budget:
                    timed_out = True
                    ended = "budget"
                    log(f"batch {batch}: timeout after {budget:.0f}s; "
                        "terminating child tree")
                    kill_child_tree(proc)
                    break
        rc = proc.returncode
    # ALWAYS sweep after the client exits (any path): a detached standalone
    # server/background tool or an rg-*.scope must not survive into the next
    # batch. Only ownership-attributed targets are ever signaled.
    batch_teardown(proc.pid, child_start, snapshot, f"batch {batch}")
    try:
        os.remove(os.path.join(STATE, "worker.pid"))
    except OSError:
        pass
    wall = time.monotonic() - t0
    try:
        with open(out_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 262144))
            tail = fh.read().decode(errors="replace")
    except OSError:
        tail = ""
    klass, detail = classify(batch_dir, rc, timed_out, tail, ended=ended)
    detail = _redact(detail)
    log(f"batch {batch}: rc={rc} wall={wall:.0f}s classified={klass} "
        f"({detail[:200]})")
    with open(os.path.join(batch_dir, "class.txt"), "w") as fh:
        fh.write(f"rc={rc} wall_s={wall:.0f}\nclass={klass}\n{detail}\n")
    return klass, detail


# --------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------

def finalize(status: str, reason: str) -> int:
    # Hard-stop belt: on service stop/RuntimeMaxSec SIGTERM we land here with
    # the last batch already dead; teardown is then a fast no-op. If anything
    # of ours still lingers (worst case only), it is ownership-attributed.
    batch_teardown(LAST_CTX["child_pid"], LAST_CTX["child_start"],
                   LAST_CTX["snapshot"], f"finalize ({status})")
    ts = f"{now():%Y-%m-%d %H:%M:%S %z}"
    summary = f"\n### Scheduler final — {ts}\n- status: {status}\n- reason: {reason}\n"
    repo_checkpoint_append(summary)
    try:
        with open(os.path.join(STATE, "final.md"), "w") as fh:
            fh.write(f"# fpga-overnight final {ts}\nstatus: {status}\nreason: {reason}\n")
    except OSError:
        pass
    log(f"FINALIZE status={status} reason={reason}")
    return 0 if status in ("COMPLETE", "BLOCKED", "DEADLINE", "STOPPED") else 3


def run() -> int:
    os.makedirs(LOGDIR, exist_ok=True)
    signal.signal(signal.SIGTERM, handle_sigterm)
    log(f"orchestrator start; window {START.isoformat()} .. "
        f"{DEADLINE.isoformat()}; session {SESSION}; model {MODEL}; "
        f"agent {AGENT}")
    if now() >= DEADLINE:
        return finalize("DEADLINE", "started after hard deadline; nothing to do")
    if not os.environ.get("CERN_API_KEY"):
        log("WARNING: CERN_API_KEY absent in this process env; batches will "
            "fail auth until it is imported into the systemd user manager env")
    if now() < START:
        log(f"waiting for scheduled start {START.isoformat()}")
        while now() < START and not stop_requested():
            sleep_sliced(min(300, (START - now()).total_seconds()), 30)
    if stop_requested():
        return finalize("STOPPED", "stop requested before window start")

    batch, fail_streak, no_outcome_streak, timeout_streak = 0, 0, 0, 0
    prev_next, prev_outcome = "bootstrap", "FIRST"
    probe_fail_streak = 0

    while not stop_requested():
        remaining = (DEADLINE - now()).total_seconds()
        if remaining <= 0:
            return finalize("DEADLINE", f"completed {batch} batch(es)")
        if remaining < MIN_REMAINING_TO_START_S:
            return finalize("DEADLINE", f"<{MIN_REMAINING_TO_START_S}s left; "
                                        f"no new batch after {batch}")
        ok, why = ensure_single_writer(child_pid=None)
        if not ok:
            return finalize("BLOCKED", "foreign process references our session "
                                       f"(no duplicate writers): {why}")
        admitted, note = admission_probe()
        if not admitted:
            log(f"admission deferred (holding nothing): {note}; retry 15 min")
            sleep_sliced(min(900, remaining - 30))
            continue
        if not provider_probe():
            probe_fail_streak += 1
            # Every 3rd probe failure, still attempt one real spawn: the probe
            # is a heuristic and must not veto a healthy provider all night.
            if probe_fail_streak % 3:
                wait_s = BACKOFF_LADDER_S[min((probe_fail_streak - 1) % 3, 2)]
                log(f"provider probe failed ({PROBE}) x{probe_fail_streak}; "
                    f"retry in {wait_s // 60} min (no spawn, no tokens)")
                sleep_sliced(min(wait_s, (DEADLINE - now()).total_seconds() - 30))
                continue
            log(f"provider probe failed x{probe_fail_streak}; attempting one "
                "probe-override spawn (cheap fail-fast if truly down)")

        batch += 1
        klass, detail = run_batch(batch, prev_next, prev_outcome)
        repo_checkpoint_append(
            f"\n### Batch {batch} — {now():%Y-%m-%d %H:%M %z}\n"
            f"- classified: {klass}\n- {detail[:300]}\n"
            f"- log: {STATE}/batches/{batch:03d}/\n")

        if klass == "READY":
            fail_streak = no_outcome_streak = timeout_streak = 0
            probe_fail_streak = 0
            m = re.search(r"NEXT=([^\n]+)", detail)
            nxt = (m.group(1).strip() if m else "").lower()
            if nxt in ("", "none", "none.", "n/a"):
                return finalize("COMPLETE", f"batch {batch} READY with no "
                                            "actionable next; stopping without churn")
            prev_next, prev_outcome = m.group(1).strip() if m else detail, "READY"
            log(f"batch {batch} READY; next: {prev_next[:140]}")
            continue
        if klass in ("BLOCKED", "COMPLETE"):
            return finalize(klass, f"batch {batch}: {detail[:250]}")
        if klass == "NO_OUTCOME":
            no_outcome_streak += 1
            if no_outcome_streak >= MAX_NO_OUTCOME:
                return finalize("BLOCKED", "worker produced no outcome sentinel "
                                           f"twice; last batch {batch}")
        if klass == "TIMEOUT":
            timeout_streak += 1
            if timeout_streak >= MAX_TIMEOUT_STREAK:
                return finalize("BLOCKED", f"{MAX_TIMEOUT_STREAK} consecutive "
                                           "batch timeouts")
        fail_streak += 1
        if fail_streak >= MAX_FAIL_STREAK:
            return finalize("BLOCKED", f"{fail_streak} consecutive failures; "
                                       f"last={klass}")
        wait_s = BACKOFF_LADDER_S[min(fail_streak - 1,
                                      len(BACKOFF_LADDER_S) - 1)]
        left = (DEADLINE - now()).total_seconds()
        if left < wait_s + 120:
            return finalize("DEADLINE", f"provider/failure retry would cross "
                                        f"deadline (left {left:.0f}s)")
        log(f"batch {batch} -> {klass}; retry {fail_streak} in "
            f"{wait_s // 60} min (same session on resume)")
        sleep_sliced(wait_s)
    return finalize("STOPPED", f"stop sentinel during/after batch {batch}")


# --------------------------------------------------------------------------
# self-test (pure/mock: no opencode spawn, no model traffic, no heavy jobs)
# --------------------------------------------------------------------------

def self_test() -> int:
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str, fatal: bool = True):
        results.append((name, ok, detail, fatal))

    check("window parses, start<deadline", START < DEADLINE,
          f"{START.isoformat()} .. {DEADLINE.isoformat()} = "
          f"{(DEADLINE - START).total_seconds():.0f}s")
    window = (DEADLINE - START).total_seconds()
    check("window is 47820s (tonight, fresh — not an old cutoff)",
          window == 47820, f"{window:.0f}")
    check("deadline in future", DEADLINE > now(),
          f"remaining {(DEADLINE - now()).total_seconds():.0f}s")
    check("session id isolated/dedicated", bool(re.fullmatch(r"ses_[A-Za-z0-9_]+", SESSION))
          and "ec4abb8cd" not in SESSION, SESSION)
    import shutil
    check("opencode binary on PATH",
          shutil.which("opencode") is not None,
          str(shutil.which("opencode")))
    check("resource_guard.py exists", os.path.isfile(GUARD), GUARD)
    check("STOP sentinel absent", not os.path.exists(STOP), STOP)
    try:
        os.makedirs(os.path.join(STATE, "batches"), exist_ok=True)
        os.makedirs(LOGDIR, exist_ok=True)
        probe = os.path.join(STATE, ".wtest")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        check("state dir writable", True, STATE)
    except OSError as exc:
        check("state dir writable", False, repr(exc))

    unit = os.path.expanduser(
        "~/.config/systemd/user/fpga-overnight-20261015.service")
    try:
        with open(unit, encoding="utf-8") as fh:
            text = fh.read()
        ok = ("RuntimeMaxSec=47760" in text
              and "MemoryMax=3072M" in text
              and "--continue" not in text)
        check("service unit: runtime cap 47760s & 3GiB cap", ok,
              "RuntimeMaxSec/MemoryMax present" if ok else "missing/mismatch")
    except OSError:
        check("service unit readable", False, unit, fatal=False)

    # Pure classification fixtures.
    import tempfile
    with tempfile.TemporaryDirectory(dir=STATE) as td:
        # 1: outcome file wins
        with open(os.path.join(td, "outcome.env"), "w") as fh:
            fh.write("OUTCOME=READY\nNEXT=route gnd\nSUMMARY=did x\n")
        k, _ = classify(td, 0, False, "noise")
        check("classify: outcome.env READY", k == "READY", k)
        os.remove(os.path.join(td, "outcome.env"))
        # 2: sentinel line fallback
        k, _ = classify(td, 0, False,
                        "... FPGA_OVERNIGHT_OUTCOME: BLOCKED | next: x")
        check("classify: sentinel BLOCKED", k == "BLOCKED", k)
        # 3: provider error beats exit-0
        k, _ = classify(td, 0, False,
                        '{"type":"error","error":"fetch failed ECONNREFUSED"}')
        check("classify: provider fail despite rc=0", k == "PROVIDER_FAIL", k)
        # 4: silent rc=0 -> NO_OUTCOME (never count as success)
        k, _ = classify(td, 0, False, "assistant text without sentinel")
        check("classify: rc0 no sentinel = NO_OUTCOME", k == "NO_OUTCOME", k)
        # 5: timeout class
        k, _ = classify(td, None, True, "partial work, no sentinel")
        check("classify: timeout", k == "TIMEOUT", k)
        # 6: ended reason variants (stop/deadline kills are NOT fail-unknown)
        k, d = classify(td, -15, False, "no sentinel", ended="stop")
        check("classify: stop-kill -> TIMEOUT", k == "TIMEOUT", k)
        k, d = classify(td, -9, False, "no sentinel", ended="deadline")
        check("classify: deadline-kill -> TIMEOUT", k == "TIMEOUT", k)
        # 7: provider model/quota errors (no tokens burned looping on these)
        k, _ = classify(td, 0, False, '{"error":"429 too many requests: '
                        'rate limit reached"}')
        check("classify: 429 rate-limit -> PROVIDER_FAIL",
              k == "PROVIDER_FAIL", k)
        k, _ = classify(td, 1, False, "insufficient_quota for this model")
        check("classify: quota error -> PROVIDER_FAIL",
              k == "PROVIDER_FAIL", k)
        # 8: sentinel STILL beats a provider-looking error (file first)
        with open(os.path.join(td, "outcome.env"), "w") as fh:
            fh.write("OUTCOME=READY\nNEXT=route\nSUMMARY=ok\n")
        k, _ = classify(td, 0, False, "fetch failed ECONNREFUSED after sentinel")
        check("classify: outcome file beats error noise", k == "READY", k)

    # Pure parser fixtures (field layout: state ppid then 17 fields, start).
    tail = ["S", "100"] + ["0"] * 17 + ["42"]
    ppid, start, state = _parse_stat_fields(
        "1234 (my weird proc) " + " ".join(tail))
    check("stat parser: spaces in comm",
          (ppid, start, state) == (100, 42, "S"),
          f"ppid={ppid} start={start} state={state}")
    tail2 = ["Z", "7"] + ["0"] * 17 + ["4242"]
    ppid, start, state = _parse_stat_fields(
        "99 ((paren) name) " + " ".join(tail2))
    check("stat parser: parens in comm",
          (ppid, start, state) == (7, 4242, "Z"),
          f"ppid={ppid} start={start} state={state}")

    # Scope ownership: only our own wrapper-pid scopes are ever selected.
    fake_units = _parse_scope_units(
        "rg-111-abcdef.scope loaded active running rg\n"
        "rg-222-aabbcc.scope loaded active running rg\n"
        "app-flatpak-xyz.scope loaded active running x\n"
        "session-3.scope loaded active running x\n")
    own = _own_rg_scopes({111, 999}, units=fake_units)
    check("scope ownership: only own pid's scope selected",
          own == ["rg-111-abcdef.scope"], str(own))

    # Redaction: apiKey-ish and bearer values masked.
    red = _redact('apiKey=sk-live-123 "token": "abc9" Authorization: Bearer zz')
    check("redact: no secret-looking values in logs",
          "sk-live-123" not in red and "zz" not in red
          and "abc9" not in red, red[:80])

    # Live owned-marker sweep: kill ONLY what started at/after our batch;
    # conservative skip first proves unattributed markers are left alone.
    marker = f"FPGA_SELFTEST_{os.getpid()}"
    sleeper1 = subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(30)", marker])
    sleeper2 = subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(30)", marker])
    try:
        s1_start = _proc_start(sleeper1.pid)
        # 1) impossible future batch start -> attribution fails -> NO kills
        skipped = _sweep_marked_leftovers(s1_start + 10**12,
                                          markers=(marker,))
        time.sleep(0.2)
        both_alive = sleeper1.poll() is None and sleeper2.poll() is None
        check("sweep: unattributed (pre-batch) markers left untouched",
              skipped == 0 and both_alive,
              f"killed={skipped} alive={both_alive}")
        # 2) real batch start -> our two marked sleepers are swept
        killed = _sweep_marked_leftovers(s1_start, markers=(marker,))
        time.sleep(0.4)
        both_dead = sleeper1.poll() is not None and sleeper2.poll() is not None
        check("sweep: own marker processes started at batch are killed",
              killed >= 2 and both_dead,
              f"killed={killed} dead={both_dead}")
    finally:
        for s in (sleeper1, sleeper2):
            try:
                s.kill()
                s.wait(timeout=5)
            except OSError:
                pass

    check("CERN_API_KEY present in env", bool(os.environ.get("CERN_API_KEY")),
          "present" if os.environ.get("CERN_API_KEY") else "ABSENT (auth would fail)",
          fatal=False)
    check("provider TCP probe", provider_probe(), PROBE, fatal=False)

    width = max(len(n) for n, *_ in results)
    all_ok = True
    for name, ok, detail, fatal in results:
        all_ok &= ok or not fatal
        print(f"{'PASS' if ok else ('FAIL' if fatal else 'WARN')}  "
              f"{name.ljust(width)}  {detail}")
    return 0 if all_ok else 1


def status() -> int:
    print(f"window   : {START.isoformat()} .. {DEADLINE.isoformat()}")
    print(f"state    : {STATE}")
    print(f"session  : {SESSION}  model: {MODEL}  agent: {AGENT}")
    print(f"now      : {now():%Y-%m-%d %H:%M:%S %z}  "
          f"remaining to deadline: {(DEADLINE - now()).total_seconds():.0f}s")
    print(f"STOP     : {'PRESENT' if os.path.exists(STOP) else 'absent'}")
    print(f"provider probe ({PROBE}): {provider_probe()}")
    for path in (SCHEDLOG, os.path.join(STATE, "final.md")):
        if os.path.exists(path):
            print(f"--- tail {path}")
            with open(path, encoding="utf-8", errors="replace") as fh:
                print("".join(fh.readlines()[-15:]).rstrip())
    return 0


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else "run"
    if mode == "run":
        return run()
    if mode == "self-test":
        return self_test()
    if mode == "status":
        return status()
    print("usage: fpga_overnight.py [run|self-test|status]", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
