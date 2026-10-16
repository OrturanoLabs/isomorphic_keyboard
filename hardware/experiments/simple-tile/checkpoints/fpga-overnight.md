# FPGA overnight scheduler checkpoint — 2026-10-15

Owner: setup subagent (this file + `tools/fpga_overnight.py` + state under
`/tmp/opencode/fpga-overnight-20261015/`). The overnight **worker** owns
`fpga/board/**` and appends evidence to `checkpoints/fpga-01.md` only; the
orchestrator appends per-batch summaries at the end of this file.
Single writers everywhere: no file has two live writers.

## Window and arming (armed 2026-10-15 ~19:05 CEST)

- Start (armed): **2026-10-15 21:43 CEST** via systemd user timer
  `fpga-overnight-20261015.timer` (`OnCalendar=2026-10-15 21:43:00`,
  AccuracySec=1s). `systemctl --user list-timers` proof: NEXT = Thu
  2026-10-15 21:43:00 CEST.
- Hard stop (triple enforcement): in-script deadline env
  `FPGA_OVERNIGHT_DEADLINE=2026-10-16T11:00:00+02:00` (fresh — NOT the
  expired 2026-10-15 12:10 cutoff); `RuntimeMaxSec=47760` on the service
  (=13h 16min, expires ~10:59 CEST, teardown completes before 11:00);
  outer belt `fpga-overnight-20261015-stop.timer` fires `systemctl --user
  stop` at exactly 11:00 CEST. KillMode=control-group kills the whole own
  process tree (standalone opencode client+server in-cgroup); the shared
  `opencode serve --service` and other sessions are untouched.
- Session: `ses_fpga_overnight_20261015` (dedicated, created by batch 1,
  reused by all retries; never `--continue`). Model
  `cern/Kimi-K3-FLATIRON`, agent `cern-worker` (installs and VCS mutation
  are permission-denied), `opencode run --standalone ... --auto --format json`.

## Units, paths, commands (exact)

- Units: `~/.config/systemd/user/fpga-overnight-20261015.{timer,service}`
  and `fpga-overnight-20261015-stop.{timer,service}` (systemd 262, verify
  clean; Linger=yes so the user manager survives logout).
- Orchestrator:
  `hardware/experiments/simple-tile/tools/fpga_overnight.py run|self-test|status`.
- State/logs: `/tmp/opencode/fpga-overnight-20261015/` — `state.env` (fresh
  deadline env), `logs/scheduler.log`, `logs/service.log`, `batches/NNN/
  {prompt.txt,output.jsonl,class.txt}`, `final.md`, `STOP` sentinel.
- Auth: `CERN_API_KEY` imported into the systemd user manager env
  (`systemctl --user import-environment CERN_API_KEY`, transient, name-only
  verified, never written to disk). If the user manager restarts before
  21:43, re-run that import command.

## Cancellation (user)

- Graceful now-or-later: `touch /tmp/opencode/fpga-overnight-20261015/STOP`
- Disarm before 21:43: `systemctl --user disable --now fpga-overnight-20261015.timer fpga-overnight-20261015-stop.timer`
- Immediate kill of our tree only: `systemctl --user stop fpga-overnight-20261015.service`
- Cleanup after the run: remove the four unit files above (or `disable`) and
  `rm -rf /tmp/opencode/fpga-overnight-20261015` if logs are no longer needed.

## Batch policy (implemented in `fpga_overnight.py`)

- Bounded batches: worker-side 45–60 min substantive target; 75 min hard
  kill; no new batch within the last 15 min before the deadline.
- Admission before each batch: one-shot `resource_guard.py` probe
  (MemAvailable ≥ 6144 MiB, PSI some avg10 ≤ 25, Rust gate — never
  `--ignore-rust`) on a private lock; denial defers 15 min holding nothing.
- Provider resilience: TCP probe to `aigw.cern.ch:443` before each batch;
  failures wait 15/30/60 min (capped). Every 3rd probe failure still tries
  one real spawn (cheap fail-fast) so a misfiring probe cannot veto the
  night. Worker/API failure classes retry on the same ladder in the SAME
  session; exit code 0 never counts as success — classification requires the
  worker's `outcome.env` (OUTCOME=READY|BLOCKED|COMPLETE + NEXT + SUMMARY)
  or the printed sentinel line.
- Continuation only on READY with a concrete non-blocked NEXT; BLOCKED and
  COMPLETE stop the loop (no token churn, no pointless waiting).
- Single-writer guard: any foreign live process referencing our session id
  blocks the batch (BLOCKED, no duplicate writers).
- Memory caps: service cgroup MemoryMax=3072M, MemoryHigh=2560M,
  MemorySwapMax=0. The 4 GiB tier was NOT admitted at setup (host:
  MemAvailable ≈ 6.5 GiB, swap 11.4/11.5 GiB occupied, antani Rust builds
  active). Heavy per-command caps stay ≤2048 MiB; 3072 MiB only under the
  worker's own fresh 9 GiB-available/no-Rust/low-PSI re-check.

## Setup evidence

- `systemd-analyze calendar`: 2026-10-15 21:43:00 → next elapse tonight
  21:43 CEST; 2026-10-16 11:00:00 → tomorrow 11:00 CEST.
- `systemctl --user show fpga-overnight-20261015.service`:
  RuntimeMaxUSec=13h 16min, MemoryMax=3221225472, MemoryHigh=2684354560,
  MemorySwapMax=0, KillMode=control-group.
- `fpga_overnight.py self-test`: 16/16 PASS (window/dates, session id,
  binaries, state writability, unit cap cross-check, 5 classification
  fixtures incl. provider-fail-beats-exit-0, key presence, provider probe).
- Guarded probe `resource_guard.py … -- /bin/true`: rc=0 via systemd scope
  (admission path exercised).
- Provider liveness at setup: `aigw.cern.ch:443` TCP+TLS OK, unauth GET
  /v1/models → 401 (host up, auth required). Stale
  `inference001.flatironinstitute.org:8000` from the 2026-10-15 00:05
  blocker note no longer resolves (DNS); current config points at aigw.cern.ch.
- No FPGA worker batch was run before the 21:43 start (setup-only window);
  script self-guards if started early.

## Batch log (orchestrator appends below)

## Independent audit before window start — 2026-10-15 19:12 CEST (setup-only, no model traffic)

Verified: env state (CERN_API_KEY present in user-manager env by name only); both timers armed (21:43 start / 11:00 stop, RuntimeMaxSec 47760 → ~10:59); `systemd-analyze --user verify` clean; opencode v2.0.29 flags `--standalone/--model/--agent/--auto/--format json/--session/--title` all real; agent `cern-worker` + model `cern/Kimi-K3-FLATIRON` present in config metadata (credentials not inspected); provider TCP probe OK; no leftover rg-*.scope units.

Correctness fixes applied to `tools/fpga_overnight.py`: (1) `kill_child_tree` no longer the only cleanup — every batch end and `finalize()` now run `batch_teardown`: kills identity-checked (pid+start-ticks) snapshot survivors that escaped the process group, sweeps session-marker processes started at/after our child, and stops **only own** `rg-<pid>-<hex>.scope` units (pid attribution; foreign scopes never matched) — these scopes escape the service cgroup that KillMode=control-group reaps, so hard stop previously leaked them. (2) `/proc/stat` parser now splits after the last `)` (spaces/parens in comm). (3) Provider-error detection extended: 429/rate-limit/quota/overloaded/model-unavailable. (4) `_redact` masks apiKey/token/Bearer-like values in every log and checkpoint write. (5) stop/deadline kills classify as TIMEOUT-with-reason, not FAIL_UNKNOWN. (6) spawn-race tick fallback keeps sweep attribution sound.

Scheduler memory caveat (truthfulness): service `MemoryMax=3072M` covers scheduler+opencode client/server **only**. resource_guard jobs run in **sibling** rg-*.scope cgroups with their own per-job caps (≤2048 MiB default): their memory is NOT inherited inside the service cap. Host worst case ≈ 3 GiB service + 2 GiB one guarded job; the 6144 MiB admission gate exists for exactly this headroom. Residual accepted risk: service-cgroup OOM SIGKILLs the scheduler before teardown (guard deadlines bound any leaked scope to ≤ the 11:00 deadline).

Tests: `self-test` 27/27 PASS incl. new fixtures (stop/deadline classes, 429/quota, stat-comm-parens, scope-name ownership precision, redaction, live kill-own-vs-spare-foreign marker sweep). Live integration mock: own rg scope discovered/stopped; wrong pid set selected and stopped nothing. No Kimi job or inference was started.

### Batch 1 — 2026-10-15 22:02 +0200
- classified: READY
- file OUTCOME=READY NEXT=Refresh remaining canonical reports in an admitted window (board_net_check, pincon_check, footprint_verify, both DRC run SUMMARY=Batch 1: fresh guarded schematic_check rerun PASS S1-S7 (21:58, closes validator refresh item); fixed stale SCH0 40->45-net ledger row; power_reg.m
- log: /tmp/opencode/fpga-overnight-20261015/batches/001/

### Batch 2 — 2026-10-15 22:12 +0200
- classified: READY
- file OUTCOME=READY NEXT=FPGA-02 prep continuation: draft the freerouting/fanout plan detail (DSN export feasibility check, EP thermal-via decisi SUMMARY=Batch 2: canonical refresh battery all PASS (board_net_check N1-N10 + controls; pincon B1-B6/H1/S1 both variants AFTER repairing parse_cst for the 
- log: /tmp/opencode/fpga-overnight-20261015/batches/002/

### Batch 3 — 2026-10-15 22:24 +0200
- classified: PROVIDER_FAIL
- provider/model/API/network error in output
- log: /tmp/opencode/fpga-overnight-20261015/batches/003/

### Batch 4 — 2026-10-15 22:43 +0200
- classified: READY
- file OUTCOME=READY NEXT=draft tools/netclass_apply.py: apply docs/netclasses.json class assignments + 0.2/0.3 reference rules to a COPY of the p SUMMARY=Batch 004 (recovery+close of batch 003): verified batch-3 artifacts deterministic (pcb sha256[:12] c7d5b66fa1db == validator snapshot; dsn_check PA
- log: /tmp/opencode/fpga-overnight-20261015/batches/004/

### Batch 5 — 2026-10-15 22:55 +0200
- classified: READY
- file OUTCOME=READY NEXT=draft tools/fanout_prep.py (FPGA-02 phase-B prereq): compute per-power-net stub/via positions off routing_geo obstacles, SUMMARY=Batch 005: phase-A rule delivery empirically solved. NEGATIVE RESULT recorded: hand-written pcb net_class text segfaults KiCad 10.0.6 ExportSpecctr
- log: /tmp/opencode/fpga-overnight-20261015/batches/005/

### Batch 6 — 2026-10-15 23:03 +0200
- classified: READY
- file OUTCOME=READY NEXT=pre-routing length/loading budget: machine-derive per-net Manhattan/span length estimates for the 45 nets from placement SUMMARY=Batch 006: tools/fanout_prep.py -> docs/fanout_prep.json PASS (58 power pads = 6 anchors + 52 planned, 0 conflicts, 0 cross-net collisions; via-fre
- log: /tmp/opencode/fpga-overnight-20261015/batches/006/

### Batch 7 — 2026-10-15 23:10 +0200
- classified: READY
- file OUTCOME=READY NEXT=draft tools/ses_import_check.py (FPGA-02 phase-C prereq): pure-python SES parser+verifier against the in-tree discrete * SUMMARY=Batch 007: tools/length_budget.py -> docs/length_budget.json PASS (45 nets Manhattan-MST budget; DSN pin census PASS; vacuity PASS; DRV stubs 5-11 
- log: /tmp/opencode/fpga-overnight-20261015/batches/007/

### Batch 8 — 2026-10-15 23:15 +0200
- classified: READY
- file OUTCOME=READY NEXT=freerouting availability sweep (java -version, jar/container per downstream-prep notes, read-only); if present: preparat SUMMARY=Batch 008: ses_import_check.py built+characterized on in-tree discrete fixture (S1-S7 PASS; --full gate proven to fire at 46/52); real round-trip t
- log: /tmp/opencode/fpga-overnight-20261015/batches/008/

### Batch 9 — 2026-10-15 23:26 +0200
- classified: READY
- file OUTCOME=READY NEXT=draft tools/fanout_apply_probe.py: pcbnew-apply fanout_prep.json stub/via plan onto a COPY pcb (SaveBoard), re-export DS SUMMARY=Batch 009: freerouting present as localhost/freerouting:2.4.1 (host java absent); guard-enforced container limits; dry run COMPLETED 519s (peak hea
- log: /tmp/opencode/fpga-overnight-20261015/batches/009/

### Batch 10 — 2026-10-15 23:46 +0200
- classified: READY
- file OUTCOME=READY NEXT=draft tools/route_report.py: parse freerouting logs + both SES files into docs/route_arms.json (one comparison table: it SUMMARY=Batch 010: fanout_apply_probe.py applied 52 stubs/0 vias to pcbnew COPY (SaveBoard, artifact untouched c7d5b66fa1db); probe dsn exported+class-spli
- log: /tmp/opencode/fpga-overnight-20261015/batches/010/

### Batch 11 — 2026-10-16 00:01 +0200
- classified: READY
- file OUTCOME=READY NEXT=draft tools/widen_check.py: per-net width audit per SES arm against class minimums (emit the fix_routed-style widen list SUMMARY=Batch 011: route_report.py OK (3 arms, invariants+canon pass, own gained/lost label defect caught+fixed); dsn_4l_probe.py OK (4L DSN splice, invers
- log: /tmp/opencode/fpga-overnight-20261015/batches/011/

### Batch 12 — 2026-10-16 00:06 +0200
- classified: READY
- file OUTCOME=READY NEXT=write docs/fpga02_handoff.md: index of all FPGA-02 preparation artifacts+tools with one-line statuses (netclasses/fanout SUMMARY=Batch 012: widen_check.py -> docs/widen_report.json after 2 own-defect fixes (path regex trailing ws, budget key); audit: bare 7 widen (power@375 v
- log: /tmp/opencode/fpga-overnight-20261015/batches/012/

### Batch 13 — 2026-10-16 00:09 +0200
- classified: READY
- file OUTCOME=READY NEXT=draft tools/widen_apply_probe.py (pcbnew-COPY pass widening widen_report paths to class minima + recheck) OR annotate do SUMMARY=Batch 013: docs/fpga02_handoff.md written — 5 sections: artifact index w/ one-line statuses, router I/O chain map, 3-arm measurement table + open d
- log: /tmp/opencode/fpga-overnight-20261015/batches/013/

### Batch 14 — 2026-10-16 00:13 +0200
- classified: READY
- file OUTCOME=READY NEXT=draft tools/integrity_check.py: single trust-anchor rerun asserting all campaign invariants (pcb hash, dsn split/4l inve SUMMARY=Batch 014: widen_apply_probe.py text-level SES repair — bare 7 + 4L 9 widths raised to class minima (incl. K5 150->200), inverse identity PASS, 0 g
- log: /tmp/opencode/fpga-overnight-20261015/batches/014/

### Batch 15 — 2026-10-16 00:17 +0200
- classified: READY
- file OUTCOME=READY NEXT=run router-variance replicate: guarded freerouting bare-arm rerun -> tile_gw1nz_rep2.ses (teed log), register bare_rep2  SUMMARY=Batch 015: integrity_check.py built (2 own defects fixed: subprocess cwd, REPO depth) -> INTEGRITY PASS 14/14 in 0.6s: pcb hash anchored, arms-tabl
- log: /tmp/opencode/fpga-overnight-20261015/batches/015/

### Batch 16 — 2026-10-16 00:31 +0200
- classified: READY
- file OUTCOME=READY NEXT=extend route_report.py to parse teed router logs (provenance.log) into a per-stage table — fanout escapes / autoroute tr SUMMARY=Batch 016: variance replicate ZERO VARIANCE — rep2 SES byte-identical sha256 fa54ef9b0920, same score trajectory; 46/99 is exact-for-router not an 
- log: /tmp/opencode/fpga-overnight-20261015/batches/016/

### Batch 17 — 2026-10-16 00:35 +0200
- classified: READY
- file OUTCOME=READY NEXT=annotate docs/readiness.md: mark which FPGA-01 open items the night evidence shifts (EP/placement, corridor pinch bindin SUMMARY=Batch 017: route_report.py parses teed logs into per-stage tables (fanout 115/114 escapes, autoroute trajectories, optimizer stops, job elapsed) wi
- log: /tmp/opencode/fpga-overnight-20261015/batches/017/

### Batch 18 — 2026-10-16 00:37 +0200
- classified: READY
- file OUTCOME=READY NEXT=write CAMPAIGN RESULT executive block into checkpoint tail: 10-12 lines pinning register status, one number per major fi SUMMARY=Batch 018: readiness.md appended with scoped overnight evidence-deltas section — shifts recorded (routing gap quantified incl 46/99 deterministic +
- log: /tmp/opencode/fpga-overnight-20261015/batches/018/

### Batch 19 — 2026-10-16 00:38 +0200
- classified: READY
- file OUTCOME=READY NEXT=optional decisive last measurement: 4L ATTACH-VIA probe arm — inject fanout_prep via-feasible attach vias as fixed DSN w SUMMARY=Batch 019: CAMPAIGN RESULT executive block written as checkpoint session 23 — register status, five headline numbers (46/99 exact deterministic; 79
- log: /tmp/opencode/fpga-overnight-20261015/batches/019/

### Batch 20 — 2026-10-16 01:01 +0200
- classified: READY
- file OUTCOME=READY NEXT=re-run tools/integrity_check.py on a quiet machine to refresh the 14/14 anchor for the 5-arm route_arms.json (batch-20 r SUMMARY=Batch 020: 4L attach-via probe arm built+run+registered -- dsn_attach_probe.py injected 17 stub+via sites (GND 11, VCC1V2 6) into the 4L DSN; guard
- log: /tmp/opencode/fpga-overnight-20261015/batches/020/

### Batch 21 — 2026-10-16 01:18 +0200
- classified: COMPLETE
- file OUTCOME=COMPLETE NEXT=none: all remaining work needs owner decision (a vs c, session 23) or the standing blockers (quote account, bench hardwa SUMMARY=Batch 021: recorded next steps executed -- integrity_check.py PASS 14/14 on the 5-arm state (route_arms.json byte-stable, pcb c7d5b66fa1db uncha
- log: /tmp/opencode/fpga-overnight-20261015/batches/021/

### Scheduler final — 2026-10-16 01:18:56 +0200
- status: COMPLETE
- reason: batch 21: file OUTCOME=COMPLETE NEXT=none: all remaining work needs owner decision (a vs c, session 23) or the standing blockers (quote account, bench hardwa SUMMARY=Batch 021: recorded next steps executed -- integrity_check.py PASS 14/14 on the 5-arm state (r
