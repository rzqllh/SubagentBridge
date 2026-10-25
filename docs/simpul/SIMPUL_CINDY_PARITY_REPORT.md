# SIMPUL — Cindy/Orca Core Parity Execution Report

> **Single authoritative record** for Simpul's orchestration-core parity work against Cindy reference.
> Appended after every phase. Never replace prior phase sections.

---

## Governance

- `AUTONOMY: OFF`
- `GATE_MODE: CHAT_APPROVAL`
- E18 = `BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)`
- No autonomous merge, release, publication, or destructive cleanup
- No fabricated receipts, QA results, subagent identities, or OS isolation claims
- Orchestration governor: Xyeena Orchestrate 0.4.1 (Antigravity host)
- All phases branch from verified Sprint 1 baseline after PR #9 is accepted

---

## Upstream Reference

- **Repository**: `https://github.com/makecindy/cindy`
- **Pinned HEAD SHA**: `b7e46bcbbe41eeee2f16381fef00df61a31a3b8b` (fetched 2026-10-25T21:28:44+07:00)
- **License**: Apache-2.0
- **Parity scope**: Orchestration-core only (Lead/Worker sessions, lifecycle, dispatch, interrupt, recovery, worktree, evidence)
- **Explicitly excluded**: Desktop UI, mobile, user accounts, cloud infrastructure, personal messaging, scheduling, design system, i18n, region/edition logic

---

## Phase Table

| Phase | Branch | Status | Acceptance Target |
|---|---|---|---|
| C00 | `simpul/08-sprint1-verification` | **COMPLETE (remote PR #9 verified, CI 4/4 PASS)** | Security hardening, corrective review, all tests pass |
| C01 | `simpul/09-parity-foundation` | **COMPLETE (remote PR #10 verified, CI 4/4 PASS)** | Architecture contracts, adapter boundaries, 8 baseline tests pass |
| C02 | `simpul/10-worker-sessions` | **COMPLETE (Correctness Gate passed, 15/15 tests PASS, PR #11 updated)** | Real independent worker processes with lifecycle, IPC, anti-spoofing & recovery |
| C03 | `simpul/11-multi-harness` | **READY TO START (Worktree `.worktrees/p11-multi-harness`)** | Capability-checked host adapters |
| C04 | `simpul/12-interagent-control` | **NOT STARTED** | Durable message queue, targeting, dedup, interrupt/steer |
| C05 | `simpul/13-durable-continuity` | **NOT STARTED** | Restart/resume, checkpoint/recovery, worktree lifecycle |
| C06 | `simpul/14-parity-acceptance` | **NOT STARTED** | End-to-end, failure injection, adversarial, cross-platform CI |

---

## C00 - Sprint 1 Closure and Security Hardening

**Status**: COMPLETE (remote updated, CI verified)
**Branch**: `simpul/08-sprint1-verification`
**HEAD Commit**: `eb97397` (pushed to origin)
**Remote PR #9**: Updated to `eb97397`
**GitHub Actions Run**: `40202959103` (4/4 jobs PASS in 2m13s)

### Task Checklist

| ID | Task | Status |
|---|---|---|
| C00-T1 | Verify commit ancestry (8500019, f422ed2) on branch | **PASS** |
| C00-T2 | Independent security review - approve_command P0 | **DOCUMENTED (E18 BLOCKED)** |
| C00-T3 | Independent security review - command execution boundary | **PASS** |
| C00-T4 | Independent security review - QA evidence integrity | **PASS (E18 caveat)** |
| C00-T5 | Independent security review - worker reservation exact-once | **PASS in-process / BLOCKED cross-process** |
| C00-T6 | Independent security review - FastMCP fallback dummy | **PASS** |
| C00-T7 | Full pytest suite (339 passed, 5 skipped) | **PASS (exit 0)** |
| C00-T8 | Ruff source-only check | **PASS (exit 0)** |
| C00-T9 | Mypy type check (47 source files) | **PASS (exit 0)** |
| C00-T10 | Bandit security scan (0 High, 0 Medium) | **PASS (exit 0)** |
| C00-T11 | Report Section 15 appended to SIMPUL_02_SPRINT_1_REPORT.md | **COMPLETE** |
| C00-T12 | Push to remote for CI | **PASS (Authorized: run 40202959103 4/4 green)** |

### Remote CI Matrix Run 40202959103

| Runner | Python | Status | Duration |
|---|---|---|---|
| `ubuntu-latest` | 3.13 | **SUCCESS** | 59s |
| `ubuntu-latest` | 3.11 | **SUCCESS** | 48s |
| `windows-latest` | 3.11 | **SUCCESS** | 1m44s |
| `windows-latest` | 3.13 | **SUCCESS** | 2m13s |

---

## C01 - Parity Foundation

**Status**: COMPLETE (remote PR #10 created, CI verified 4/4 PASS)
**Branch**: `simpul/09-parity-foundation`
**Worktree**: `.worktrees/p09-parity-foundation`
**Base**: `eb97397` (stacked on `simpul/08-sprint1-verification`)
**Remote PR #10**: https://github.com/rzqllh/SubagentBridge/pull/10
**GitHub Actions Run**: `40205275129` (4/4 jobs PASS in 2m16s)

### Implementation Summary

1. **Domain Architecture Contracts (`subagentbridge/domain/orca_contracts.py`)**:
   - `OrcaRole` (`LEAD`, `WORKER`): Distinct identity and role separation.
   - `WorkerStatus` (`IDLE`, `RUNNING`, `PAUSED`, `INTERRUPTED`, `COMPLETED`, `FAILED`, `ARCHIVED`): Comprehensive lifecycle.
   - `QueueTaskStatus` (`PENDING`, `DISPATCHED`, `RUNNING`, `INTERRUPTED`, `COMPLETED`, `CANCELLED`, `FAILED`): Queue state machine.
   - `WorkerConfig`: Per-worker model, harness, provider, system prompt, effort, and token budget.
   - `OrcaSession`: Discrete session container for Lead and Worker.
   - `QueueItem`: Durable inter-agent task queue handle with `dsp-` IDs.
   - `WorktreeAssignment`: Per-worker isolated worktree path and branch tracking.
   - `HandoffEvidence`: Structured completion evidence and artifact transport.

2. **Durable SQLite Persistence (`subagentbridge/storage/orca_store.py`)**:
   - Dedicated WAL-mode tables: `orca_teams`, `orca_sessions`, `orca_queue`, `orca_worktrees`, `orca_handoffs`.
   - Context-managed SQLite connection ensuring clean Windows file-handle disposal.
   - Full rehydration capabilities across process crashes and restarts.

3. **Orca Team Manager (`subagentbridge/team/orca_team.py`)**:
   - Team and session lifecycle management.
   - Inter-agent dispatch (`dispatch_task`).
   - Atomic worker interrupt preemption (`interrupt_worker`).
   - Worktree isolation mapping (`get_worktree_assignment`).
   - Structured handoff receipt ingestion (`submit_worker_handoff`).
   - Enforced default-deny execution policy for worker sessions (`execute_worker_command`).

### Baseline Verification Matrix

| Tool / Check | Result | Exit Code |
|---|---|---|
| `pytest tests/test_c01_parity_foundation.py -v` | 8 passed in 0.23s | 0 |
| `pytest tests/ artifacts/bootstrap/v3_1/tests/ -q` | 347 passed, 5 skipped, 135 subtests in 53.91s | 0 |
| `ruff check subagentbridge/ tests/test_c01_parity_foundation.py` | All checks passed! | 0 |
| `mypy subagentbridge/domain/orca_contracts.py subagentbridge/storage/orca_store.py subagentbridge/team/orca_team.py` | Success: no issues found in 3 source files | 0 |
| `bandit -r subagentbridge/ -ll` | 0 High, 0 Medium | 0 |

### Baseline Tests Verified (8/8 PASS)

1. `test_c01_lead_worker_distinct_sessions`: Lead and Worker have separate IDs, roles, and lifecycles.
2. `test_c01_worker_has_own_model_config`: Per-worker model, harness, provider, and effort preserved.
3. `test_c01_dispatch_returns_queue_handle`: Dispatches return typed `QueueItem` with state transitions.
4. `test_c01_interrupt_preempts_worker`: Atomic interrupt transitions worker and queue item to `INTERRUPTED`.
5. `test_c01_worker_to_lead_handoff`: Worker returns structured `HandoffEvidence` back to Lead.
6. `test_c01_restart_reconstructs_sessions`: SQLite store saves and rehydrates sessions and queues across restart.
7. `test_c01_worktree_assignment_per_worker`: Dedicated worktree paths assigned per worker without collision.
8. `test_c01_unapproved_command_blocked`: Worker execution through parity contracts enforces default-deny.

---

## C02 - Independent Worker Sessions Lifecycle

**Status**: COMPLETE (remote PR #11 created, CI verified 4/4 PASS)
**Branch**: `simpul/10-worker-sessions`
**Worktree**: `.worktrees/p10-worker-sessions`
**Base**: `330fe18` (stacked on `simpul/09-parity-foundation`)
**Remote PR #11**: https://github.com/rzqllh/SubagentBridge/pull/11
**HEAD Commit**: `3452987` (Correctness Gate passed, pushed to origin)
**GitHub Actions Run**: `40208918996` (4/4 jobs PASS in 2m39s)

### Implementation Summary

1. **Real Worker Subprocess Engine (`subagentbridge/execution/worker_process.py`)**:
   - `WorkerProcessController`: Spawns, monitors, communicates with, and reaps real OS child processes.
   - Enforces distinct OS process boundary (`child_pid != os.getpid()`).
   - Bidirectional IPC via JSON-lines over stdin/stdout pipes with immediate flushing.
   - Heartbeat polling (`ping_worker`) and liveness detection (`is_worker_alive`).
   - Preemption signal (`interrupt_worker`) setting worker and queue state to `INTERRUPTED`.
   - Clean shutdown sequence (`terminate_worker`): graceful `STOP` command, timeout handling, SIGTERM/SIGKILL fallback, and pipe cleanup.
   - Dead/stale process reaping (`reap_dead_workers`): detects unexpected process crashes and updates status to `FAILED`.
   - Crash recovery reconciliation (`reconcile_rehydrated_sessions`): inspects stored worker PIDs on startup using `psutil`, marking dead PIDs as `FAILED` rather than falsely claiming active execution.

2. **Subprocess Runtime Entrypoint (`subagentbridge/execution/worker_runtime_entrypoint.py`)**:
   - Independent Python executable entrypoint (`python -m subagentbridge.execution.worker_runtime_entrypoint`).
   - Emits handshake `INIT` event with real OS PID and process creation time.
   - Rejects false task completion: requires real authorized execution or returns `NOT_IMPLEMENTED`.
   - Prevents approval spoofing: in-payload approval booleans rejected as untrusted; requires exact worker/task/command/workspace HMAC execution ticket from `TrustedApprovalAuthority`.
   - Single-use replay protection and context mismatch rejection.
   - Real task cancellation: background stdin reader with `threading.Event`, immediate child subprocess termination, and strict guarantee that cancelled tasks never emit late `COMPLETED`.
   - Enforceable IPC deadlines via `TimedStreamReader` with timeout deadlines.
   - Safe process tree cleanup via `kill_process_tree` with recursive child termination.
   - Process identity verification via `is_process_identically_alive` with `create_time` comparison protecting against OS PID recycling.
   - Clarified token budget semantics: pre-flight admission checks vs actual metered consumption.

3. **C02 Correctness Gate Verification Matrix**:

| Tool / Check | Result | Exit Code |
|---|---|---|
| `pytest tests/test_c02_worker_sessions.py -v` | 15 passed in 4.70s | 0 |
| `pytest tests/ artifacts/bootstrap/v3_1/tests/ -q` | 362 passed, 5 skipped, 135 subtests in 60.13s | 0 |
| `python -m unittest discover -s tests -p 'test_*.py'` | 325 passed, 5 skipped in 60.87s | 0 |
| `ruff check --select E4,E7,E9,F subagentbridge` | All checks passed! | 0 |
| `mypy --ignore-missing-imports --check-untyped-defs subagentbridge` | Success: no issues found in 53 source files | 0 |
| `bandit -q -r -ll subagentbridge` | 0 High, 0 Medium findings | 0 |
| `python -B -c "...FastMCP...subagentbridge.server..."` | MCP v1 server import PASS | 0 |

### C02 Correctness Gate Acceptance Tests Verified (15/15 PASS)

1. `test_c02_real_worker_process_spawn`: Distinct OS process spawn, PID, create_time recorded, alive.
2. `test_c02_worker_heartbeat_and_status`: IPC ping/pong and heartbeat tracking.
3. `test_c02_worker_task_dispatch_ipc_real_authorized_execution`: Real authorized execution with observable evidence and exit code.
4. `test_c02_reject_false_completion_for_abstract_instruction`: Abstract instruction returns `NOT_IMPLEMENTED` instead of false completion.
5. `test_c02_prevent_approval_spoofing_in_payload`: Rejects untrusted in-payload approval booleans with `DENIED`.
6. `test_c02_reject_replayed_approval_ticket`: Single-use replay protection rejects replayed tickets with `DENIED`.
7. `test_c02_reject_approval_context_mismatch`: Rejects ticket used by unauthorized worker or command mismatch.
8. `test_c02_worker_interrupt_preemption_prevents_late_completion`: Cancellation interrupts running task and strictly prevents late completion.
9. `test_c02_worker_clean_termination_resource_cleanup`: Clean termination, closes pipes, exits with code 0.
10. `test_c02_reap_stale_worker_process`: Detects crashed child process, transitions status to `FAILED`.
11. `test_c02_budget_semantics_admission_vs_metered_consumption`: Pre-flight admission vs cumulative metered consumption tracking.
12. `test_c02_restart_process_reconciliation`: Reconciles dead PIDs after simulated crash restart without false claims.
13. `test_c02_pid_reuse_protection`: Rejects recycled PIDs when create_time mismatches.
14. `test_c02_ipc_deadline_hanging_worker`: Enforces IPC deadlines without blocking forever on hung worker.
15. `test_c02_process_tree_cleanup`: Safe recursive process-tree cleanup terminates parent and child processes.

---

## C03 through C06 - Pending

Sections will be appended after each phase completes.

## Feature Parity Matrix (Post-C02 State)

Distinguishes:
- **SCHEMA**: Data models and contracts defined and type-checked
- **WORKING**: Working in-process implementation with unit and persistence coverage
- **HOST_INTEGRATED**: Bound to real host execution/processes (Antigravity/Codex/Claude)
- **MISSING / SCHEDULED**: Not yet implemented; scheduled for designated phase

| Feature Category | Capability / Contract | Cindy Upstream Source (SHA `b7e46bc`) | Simpul Source File | Parity Classification | Phase Target |
|---|---|---|---|---|---|
| **Lead Session** | Distinct session ID & role (`lead`) | `orcaLifecycleService.ts` / `sessions.orca_role='lead'` | `subagentbridge/domain/orca_contracts.py` | **WORKING (In-Process)** | C01 (Done) |
| **Lead Session** | Team lifecycle & ownership | `orca_teams` table / `OrcaTeamService` | `subagentbridge/team/orca_team.py` | **WORKING (In-Process)** | C01 (Done) |
| **Worker Session** | Distinct session ID & role (`worker`) | `orca_workers` table / `sessions.orca_role='worker'` | `subagentbridge/domain/orca_contracts.py` | **WORKING (In-Process)** | C01 (Done) |
| **Worker Session** | Per-worker model / harness / provider config | `workerCreationPrefs` / `OrcaWorkerCreationService` | `subagentbridge/domain/orca_contracts.py` (`WorkerConfig`) | **WORKING (In-Process)** | C01 (Done) |
| **Worker Session** | Real independent worker OS process / host session | Subagent child process / MCP stdio session | `subagentbridge/execution/worker_process.py` | **WORKING (Subprocess IPC & PID Registry)** | **C02 (Done)** |
| **Worker Lifecycle** | Status state machine (`IDLE`..`ARCHIVED`) | `orca_workers.status` (7 lifecycle states) | `subagentbridge/domain/orca_contracts.py` (`WorkerStatus`) | **WORKING (State machine)** | C01 (Done) |
| **Worker Lifecycle** | Persistent vs Ephemeral lifecycle kind | `orca-team-architecture.md` (Section 3) | `subagentbridge/domain/orca_contracts.py` | **SCHEMA (Classified)** | C02 (Done) |
| **Dispatch & Queue** | Typed inter-agent queue handle (`dsp-*`) | `OrcaTeamService.dispatchWorkerTask` | `subagentbridge/domain/orca_contracts.py` (`QueueItem`) | **WORKING (SQLite Queue)** | C01 (Done) |
| **Dispatch & Queue** | Queue state transitions (`PENDING`..`COMPLETED`) | `OrcaTeamService` queue state machine | `subagentbridge/team/orca_team.py` | **WORKING (In-Process)** | C01 (Done) |
| **Queue Controls** | Worker interrupt preemption (`INTERRUPTED`) | `interrupt_worker` atomic cancellation | `subagentbridge/team/orca_team.py` (`interrupt_worker`) | **WORKING (In-Process)** | C01 (Done) |
| **Queue Controls** | Queue control tools (steer, cancel, update) | 6 queue tools in `OrcaTeamService` | `subagentbridge/team/orca_team.py` | **WORKING (Partial)** | **C04** |
| **Inter-Agent Channel**| Structured Worker-to-Lead handoff | `OrcaInterAgentDispatcher` / auto-bridge | `subagentbridge/domain/orca_contracts.py` (`HandoffEvidence`) | **WORKING (Ingested & Ledgered)** | C01 (Done) |
| **Inter-Agent Channel**| Worker reads Lead message history | `orca_worker_bridge.read_lead_history` | Scheduled for `subagentbridge/team/interagent_channel.py` | **SCHEDULED** | **C04** |
| **Worktree** | Per-worker isolated worktree path & branch | `WorktreeManager` / `create_worker working_dir` | `subagentbridge/domain/orca_contracts.py` (`WorktreeAssignment`) | **WORKING (Mapping & Tracking)** | C01 (Done) |
| **Worktree** | Automated git worktree creation & tear down | `WorktreeManager.createWorktree` | Scheduled for `subagentbridge/workspaces/worktree_manager.py` | **SCHEDULED** | **C05** |
| **Crash Recovery** | Rehydrate sessions, teams, and queues across crash | SQLite WAL persistence / session resume | `subagentbridge/storage/orca_store.py` (`OrcaStore`) | **WORKING (SQLite Rehydration)** | C01 (Done) |
| **Multi-Harness** | Host adapters (Antigravity, Codex, Claude Code, Pi) | Host specific adapter IPC | Scheduled for `subagentbridge/runners/harness_adapters.py` | **SCHEDULED** | **C03** |
| **Security & Safety** | Default-deny command authorization | N/A (Simpul-specific hardening) | `subagentbridge/team/orca_team.py` (`execute_worker_command`) | **WORKING (Fail-Closed)** | C01 (Done) |
| **Security & Safety** | E18 Same-user co-process confinement | Accepted risk boundary | Documented as `BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)` | **VERIFIED BOUNDARY** | Ongoing |

---

## 9 Review Threads on PR #9 Status (Truthful Verification)

| Thread / Topic | Severity | Local Code Remediation | Regression Test Evidence | Remote Thread Status |
|---|---|---|---|---|
| Command Authorization (`_gate_command_execution`) | P1 | Fixed in `f422ed2` | `test_p1_command_bypass_attempts` PASS | **UNRESOLVED on GitHub** (Code remediated, awaits reviewer signoff) |
| Worker Reservation exact-once | P1 | Fixed in `f422ed2` | `test_p1_worker_reservation_lock` PASS | **UNRESOLVED on GitHub** (Code remediated, in-process locked, cross-process documented) |
| Moving-main test isolation | P2 | Fixed in `8500019` | `test_remote_pinned_checkout_e23.py` PASS | **UNRESOLVED on GitHub** (Code remediated) |
| Dirty checkout filtering | P2 | Fixed in `f422ed2` | `test_p2_dirty_checkout_subpath` PASS | **UNRESOLVED on GitHub** (Code remediated) |
| Post-QA integrity recheck | P2 | Fixed in `8500019` | `test_p2_post_qa_tree_modification` PASS | **UNRESOLVED on GitHub** (Code remediated) |
| Skipped tests as verified | P2 | Fixed in `f422ed2` | `test_p2_qa_skip_detection_junitxml` PASS | **UNRESOLVED on GitHub** (Code remediated) |
| approve_command self-approval | P0 | Documented in `eb97397` | E18 BLOCKED disclosure | **UNRESOLVED on GitHub** (Risk accepted under E18) |
| Symlink skip on Windows | Lim | Documented in `eb97397` | Linux CI passes 4 symlink tests | **UNRESOLVED on GitHub** (Documented limitation) |

*Never claim that remediation automatically resolves a GitHub review thread. Threads remain open until the human author/reviewer explicitly marks them resolved.*

---

*Report last updated: 2026-10-25T22:50+07:00 - C02 Correctness Gate passed, verified 15/15 tests, PR #11 updated*
