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
| C00 | `simpul/08-sprint1-verification` | **COMPLETE (remote PR #9 verified, CI 4/4 PASS, run 40202959103)** | Security hardening, corrective review, all tests pass |
| C01 | `simpul/09-parity-foundation` | **COMPLETE (remote PR #10 verified, CI 4/4 PASS, run 40205275129)** | Architecture contracts, adapter boundaries, 8 baseline tests pass |
| C02 | `simpul/10-worker-sessions` | **COMPLETE (Correctness Gate passed, 15/15 tests PASS, PR #11 updated, CI 4/4 PASS, run 40208918996)** | Real independent worker processes with lifecycle, IPC, anti-spoofing & recovery |
| C03 | `simpul/11-multi-harness` | **COMPLETE (remote PR #12 verified, CI 4/4 PASS, run 40210028969)** | Capability-checked host adapters, model/provider selection, host routing |
| C04 | `simpul/12-interagent-control` | **COMPLETE (remote PR #13 verified, CI 4/4 PASS, run 40250742777)** | Durable deduplicated priority queue, authenticated messaging, steering, handoff binding |
| C05 | `simpul/13-durable-continuity` | **CORRECTED & VERIFIED (PR #14 updated commit f2a6aaa, CI 4/4 PASS, run 40257332940)** | P0 Data safety in worktree manager, verified multi-step task resume |
| C06 | `simpul/14-parity-acceptance` | **CORRECTED & VERIFIED (PR #15 updated commit 5de9771, CI 4/4 PASS, run 40258895787)** | Real execution evidence, in-flight crash injection, human approval truth, Cindy parity mapping |
| C07 | `simpul/15-native-naming` | **COMPLETE & VERIFIED (PR #16 updated commit d11878f, CI 4/4 PASS, run 40293982843)** | Native Simpul naming, zero-data-loss schema migration, concurrent race closure, Cindy attribution |

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

## Phase C03: Multi-Harness Adapters & Host Routing (COMPLETE)

- **Target Branch**: `simpul/11-multi-harness` (stacked on `simpul/10-worker-sessions`)
- **Key Modules Implemented**:
  - `subagentbridge/runners/harness_adapters.py`:
    - `HarnessCapability` enum and `HarnessCapabilities` contract: declaring `file_read`, `file_write`, `terminal_exec`, `web_search`, `subagents`, `streaming`, and `token_metering`.
    - Capability matrix for all Cindy / Orca supported harnesses:
      - `native`: Local stdlib runner with default command-line tools.
      - `antigravity`: Antigravity IDE agent runner (supports subagents, web search, token metering).
      - `codex`: OpenAI Codex / workspace tool runner.
      - `claude_code`: Anthropic Claude Code runner with tool-use hooks.
      - `pi`: Inflection Pi lightweight conversational harness (no terminal exec).
    - `HarnessRegistry`: Thread-safe registry with dynamic discovery and fallback error handling.
    - Model & Provider selection validation: ensures model/provider pairings comply with capability constraints.
    - Unsupported Host handling: Gracefully returns diagnostic error response (`status="UNSUPPORTED_HOST"`) instead of crashing or misreporting completion.
  - `subagentbridge/execution/worker_process.py`:
    - `spawn_worker()` propagates `--harness <name>` to worker child process.
    - Propagates workspace `PYTHONPATH` to child OS process environment.
    - Captures child process `stderr` during handshake timeouts for diagnostic reporting.
  - `subagentbridge/execution/worker_runtime_entrypoint.py`:
    - Integrates `get_harness_registry()` to dynamically route instruction tasks to configured harness adapter.
    - Cumulative metered token budget enforcement updated from harness execution results.
- **Verification Suite**:
  - `tests/test_c03_multi_harness.py`:
    1. `test_c03_harness_registry_and_discovery`: Tests registry discovery, registration, and built-in harnesses.
    2. `test_c03_harness_capability_contracts`: Verifies declared capabilities across native, antigravity, codex, claude_code, and pi.
    3. `test_c03_model_and_provider_selection`: Validates model/provider selection semantics.
    4. `test_c03_unsupported_host_graceful_handling`: Validates unknown harness raises `KeyError` and reports `UNSUPPORTED_HOST`.
    5. `test_c03_capability_mismatch_rejection`: Rejects tasks requiring missing capabilities (e.g. terminal exec on Pi).
    6. `test_c03_native_harness_real_execution`: Validates real instruction execution and metered tokens on native harness.
    7. `test_c03_worker_process_harness_routing`: Proves full end-to-end child process IPC instruction routing to harness.
  - Full Test Suite: 369 passed, 5 skipped (Windows symlink limitations), 135 subtests passed.
  - Static Analysis: Ruff clean (0 errors), Mypy clean (54 source files checked), Bandit clean (0 findings).
  - MCP Server Import Smoke Test: PASS.

---

---

## Phase C04: Inter-Agent Control, Messaging, Queue, Steering, and Verified Handoffs (COMPLETE)

- **Target Branch**: `simpul/12-interagent-control` (stacked on `simpul/11-multi-harness`)
- **Key Modules Implemented**:
  - `subagentbridge/domain/orca_contracts.py`:
    - `ChannelMessage`: typed message contract with sender, recipient, team, role, and timestamp.
    - `QueueItem` enhanced with `dedup_key: str | None`, `priority: int`, and `steering_instructions: list[dict[str, Any]]`.
  - `subagentbridge/storage/orca_store.py`:
    - `orca_channel_messages` table and index for team message history.
    - `orca_queue` schema extended with `dedup_key`, `priority`, and `steering_json` (with backward-compatible migrations).
    - `save_channel_message()` and `list_channel_messages_by_team()` for durable audit trail.
    - `find_queue_item_by_dedup()` for deduplicating retried task submissions.
    - `fetch_next_pending_task()` supporting priority-based and FIFO worker task retrieval.
  - `subagentbridge/team/orca_team.py`:
    - `post_message()`: Authenticated messaging verifying sender and recipient belong to the same team.
    - `read_lead_history()`: Lead and worker message history retrieval.
    - `dispatch_task()`: Idempotent dispatch deduplication via `dedup_key` (returns existing active dispatch).
    - `fetch_next_pending_task()`: Targeted FIFO queue polling.
    - `steer_task()`: Lead-only guidance steering for in-flight tasks (`PENDING`/`RUNNING`), rejecting terminal tasks.
    - `cancel_task()`: Lead-only atomic cancellation of queued/running tasks.
    - `interrupt_worker()`: Worker-level preemption transitioning worker and all active queue items to `INTERRUPTED`.
    - `submit_worker_handoff()`: **Verified handoff binding** strictly enforcing:
      1. Worker identity matches assigned worker (`evidence.from_worker_id == item.to_session_id`).
      2. Lead identity matches team lead (`evidence.to_lead_id == team.lead_session_id`).
      3. Task status is active (`PENDING`, `DISPATCHED`, `RUNNING`); late handoffs for `INTERRUPTED`/`CANCELLED` tasks are strictly rejected.
      4. Worker session is active and not interrupted.
- **Verification Suite**:
  - `tests/test_c04_interagent_control.py`:
    1. `test_c04_authenticated_lead_worker_messaging`: Validates message exchange and history reading within team.
    2. `test_c04_targeted_queue_fifo_order`: Validates targeted worker dispatch and FIFO fetching.
    3. `test_c04_dispatch_deduplication`: Validates duplicate dispatch rejection and idempotency.
    4. `test_c04_lead_steering_active_task`: Validates Lead task steering, rejection of non-lead or finished tasks.
    5. `test_c04_worker_interruption_and_cancellation`: Validates task cancellation and worker interruption preemption.
    6. `test_c04_verified_handoff_binding_success`: Validates clean handoff, status completion, and worker idle reset.
    7. `test_c04_reject_spoofed_worker_handoff`: Rejects unauthorized worker submitting handoff for another worker.
    8. `test_c04_reject_late_handoff_after_interruption`: Rejects late completion after task interruption.
  - Full Test Suite: 377 passed, 5 skipped (Windows symlink limitations), 135 subtests passed.
  - Static Analysis: Ruff clean (0 errors), Mypy clean (54 source files checked), Bandit clean (0 findings).
  - MCP Server Import Smoke Test: PASS.

---

---

## Phase C05: Durable Continuity, Checkpoints, Worktrees, and Crash Recovery (COMPLETE)

- **Target Branch**: `simpul/13-durable-continuity` (stacked on `simpul/12-interagent-control`)
- **Remote PR #14**: https://github.com/rzqllh/SubagentBridge/pull/14
- **HEAD Commit**: `6d623a5` (pushed to origin)
- **GitHub Actions Run**: `40251601336` (4/4 jobs PASS in 2m19s)
- **Key Modules Implemented**:
  - `subagentbridge/domain/orca_contracts.py`:
    - `WorkerCheckpoint`: Typed snapshot contract recording worker ID, team ID, step index, state summary, cumulative tokens consumed, and context snapshot dictionary.
  - `subagentbridge/storage/orca_store.py`:
    - `orca_checkpoints` table and indices for durable snapshotting.
    - `save_checkpoint()`, `load_latest_checkpoint()`, and `list_checkpoints()` with step-index and timestamp ordering.
    - `delete_worktree()` for worktree lifecycle tracking cleanup.
  - `subagentbridge/workspaces/worktree_manager.py`:
    - `GitWorktreeManager`: Automated creation and teardown of isolated Git worktrees and branches bound to worker sessions (`git worktree add -b`, `git worktree remove --force`, `git branch -D`).
    - Worktree directory isolation under `.worktrees/w-<worker_id>`.
  - `subagentbridge/recovery/crash_recovery.py`:
    - `reconcile_team_after_crash()`: Verifies real OS process liveness across all worker sessions using `is_process_identically_alive(pid, create_time)`. Dead worker processes are transitioned to `FAILED`, and assigned in-flight queue items are transitioned to `FAILED` (strictly eliminating false completion claims).
    - `resume_worker_from_checkpoint()`: Rehydrates worker session from latest checkpoint, restores exact cumulative metered tokens consumed, spawns a fresh worker child process, and resets status to `IDLE`.
  - `subagentbridge/execution/worker_process.py`:
    - Added `terminate_all()` for safe batch termination of tracked worker child processes.
- **Verification Suite**:
  - `tests/test_c05_durable_continuity.py`:
    1. `test_c05_checkpoint_save_and_latest_retrieval`: Validates step-indexed checkpoint persistence and latest retrieval.
    2. `test_c05_git_worktree_lifecycle`: Validates automated git worktree creation, branch checkout, directory isolation, and clean teardown.
    3. `test_c05_crash_recovery_detects_dead_worker`: Proves dead OS processes are detected and transitioned to `FAILED` without false completion.
    4. `test_c05_resume_worker_from_checkpoint`: Proves checkpoint restoration, token count continuity, and fresh process spawn.
    5. `test_c05_durable_rehydration_across_restart`: Proves complete cold-restart rehydration of teams, sessions, queues, and checkpoints.
  - Full Test Suite: 382 passed, 5 skipped (Windows symlink limitations), 135 subtests passed.
  - Static Analysis: Ruff clean (0 errors), Mypy clean (56 source files checked), Bandit clean (0 findings).
  - MCP Server Import Smoke Test: PASS.

---

---

## Phase C06: Multi-Worker Parity Acceptance & Adversarial Hardening (COMPLETE)

- **Target Branch**: `simpul/14-parity-acceptance` (stacked on `simpul/13-durable-continuity`)
- **Remote PR #15**: https://github.com/rzqllh/SubagentBridge/pull/15
- **HEAD Commit**: `9e32472` (pushed to origin)
- **GitHub Actions Run**: `40252310376` (4/4 jobs PASS in 2m33s)
- **Key Modules & Verification Scenarios**:
  - `tests/test_c06_parity_acceptance.py`:
    1. `test_c06_e2e_multiworker_workflow`: Executes full end-to-end pipeline with Lead and 2 real independent child OS processes (coder and tester) communicating over IPC. Lead dispatches coding task with verified authorization ticket, receives structured handoff, dispatches testing task, receives verification handoff, and cleans up processes.
    2. `test_c06_fault_injection_and_recovery`: Simulates ungraceful child process termination during active task execution via `kill_process_tree`. Verifies reconciler audits OS process table, detects dead worker without false completion, transitions worker and queue item to `FAILED`, and resumes worker from checkpoint with exact token count restoration.
    3. `test_c06_adversarial_authorization_hardening`: Validates strict rejection of:
       - Cross-team task dispatches (`ValueError`).
       - Cross-team channel messaging leaks (`ValueError`).
       - Cross-team task steering / hijacking (`PermissionError`).
       - Spoofed worker handoffs by unassigned workers (`PermissionError`).
       - Spoofed lead handoffs to incorrect lead sessions (`PermissionError`).
    4. `test_c06_queue_controls_dedup_steering_and_interrupt_preemption`: Validates:
       - Queue deduplication via idempotent keys.
       - Priority FIFO task fetching.
       - Lead task steering for in-flight jobs.
       - Worker atomic interruption preemption strictly preventing late handoff completion.
    5. `test_c06_worktree_isolation_and_path_containment`: Proves isolated git worktrees per worker and workspace containment denying path escapes.
    6. `test_c06_host_adapters_truthful_verification`: Validates declared capabilities across all 5 harnesses (`native`, `antigravity`, `codex`, `claude_code`, `pi`), distinguishing executable local tools from capability limits.
    7. `test_c06_pinned_cindy_parity_contract_verification`: Validates 1:1 structural contract conformance against upstream Cindy / Orca pinned commit `b7e46bcbbe41eeee2f16381fef00df61a31a3b8b`:
       - 7 worker lifecycle states (`IDLE`, `RUNNING`, `PAUSED`, `INTERRUPTED`, `COMPLETED`, `FAILED`, `ARCHIVED`).
       - 7 queue task states (`PENDING`, `DISPATCHED`, `RUNNING`, `INTERRUPTED`, `COMPLETED`, `CANCELLED`, `FAILED`).
       - Lead and Worker role definitions.
  - Full Test Suite: 389 passed, 5 skipped (Windows symlink limitations), 135 subtests passed in 70.95s.
  - Static Analysis: Ruff clean (0 errors), Mypy clean (57 source files checked), Bandit clean (0 findings).
  - MCP Server Import Smoke Test: PASS.

---

## Feature Parity Matrix (Post-C06 Final Parity State)

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
| **Queue Controls** | Worker interrupt preemption (`INTERRUPTED`) | `interrupt_worker` atomic cancellation | `subagentbridge/team/orca_team.py` (`interrupt_worker`) | **WORKING (In-Process & Preemptive)** | **C04 (Done)** |
| **Queue Controls** | Queue control tools (steer, cancel, update) | 6 queue tools in `OrcaTeamService` | `subagentbridge/team/orca_team.py` | **WORKING (Durable & Deduplicated)** | **C04 (Done)** |
| **Inter-Agent Channel**| Structured Worker-to-Lead handoff | `OrcaInterAgentDispatcher` / auto-bridge | `subagentbridge/domain/orca_contracts.py` (`HandoffEvidence`) | **WORKING (Identity & Lifecycle Bound)** | **C04 (Done)** |
| **Inter-Agent Channel**| Worker reads Lead message history | `orca_worker_bridge.read_lead_history` | `subagentbridge/team/orca_team.py` (`read_lead_history`) | **WORKING (Authenticated History)** | **C04 (Done)** |
| **Worktree** | Per-worker isolated worktree path & branch | `WorktreeManager` / `create_worker working_dir` | `subagentbridge/domain/orca_contracts.py` (`WorktreeAssignment`) | **WORKING (Mapping & Tracking)** | C01 (Done) |
| **Worktree** | Automated git worktree creation & tear down | `WorktreeManager.createWorktree` | `subagentbridge/workspaces/worktree_manager.py` | **WORKING (Git CLI & SQLite Tracking)** | **C05 (Done)** |
| **Crash Recovery** | Rehydrate sessions, teams, and queues across crash | SQLite WAL persistence / session resume | `subagentbridge/storage/orca_store.py` (`OrcaStore`) | **WORKING (SQLite Rehydration & Audited Liveness)** | **C05 (Done)** |
| **Multi-Harness** | Host adapters (Antigravity, Codex, Claude Code, Pi) | Host specific adapter IPC | `subagentbridge/runners/harness_adapters.py` | **WORKING (Capability-Checked Host Registry)** | **C03 (Done)** |
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

## Final C05/C06 Corrective Gate Acceptance (Gates 1–6)

**Governance Context**:
- Orchestration Governor: Xyeena Orchestrate v0.4.1
- `AUTONOMY: OFF`
- `GATE_MODE: CHAT_APPROVAL`
- E18: `BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)`
- Final Verdict: **`MERGE_REVIEW_READY`** (ready for authorized human merge review; no autonomous merge executed)

---

### Gate 1 — C05 P0 Data Safety Audit & Remediation

- **Finding & Root Cause**: `subagentbridge/workspaces/worktree_manager.py` previously employed routine `git worktree remove --force` on conflict, called `shutil.rmtree(..., ignore_errors=True)` as a routine fallback, pruned worktrees indiscriminately, and deleted tracking records even if underlying git commands failed. This created severe P0 data-loss risks for existing user files, uncommitted edits, untracked changes, and potential symlink escape paths.
- **Remediation**:
  1. **Strict Worker ID Validation**: Enforced regex `^[A-Za-z0-9_-]+$` preventing path injection or normalization attacks.
  2. **Canonical Path Containment**: Enforced strict containment within repo root; verified paths are canonicalized without traversing outside root.
  3. **Symlink Rejection**: Explicitly rejects symlinks or junction links in worktree roots to eliminate filesystem escape vectors.
  4. **Fail-Closed on Dirty or Untracked Files**: Routine cleanup inspects `git status --porcelain`. If modified tracked or untracked files exist, cleanup strictly fails closed (`RuntimeError: Cannot cleanup dirty worktree ... untracked files present`) unless `force=True` is explicitly specified.
  5. **Worktree Lock Inspection**: Worktrees marked as locked in `git worktree list --porcelain` cannot be routinely removed.
  6. **Safe Branch Deletion**: Uses safe branch deletion (`git branch -d`); only invokes `-D` under explicit force authorization.
  7. **Ownership Persistence on Failure**: If any git deletion step fails, database tracking records are strictly preserved for audit recovery.
  8. **Concurrency Protection**: Added reentrant threading lock (`self._lock`) preventing concurrent race conditions during worktree creation and cleanup.
- **Evidence Before vs. After**:
  - *Before*: Untracked files and dirty worktrees were forcefully wiped by `rmtree(ignore_errors=True)`.
  - *After*: Regression tests prove dirty/untracked files trigger `RuntimeError` and worktrees fail closed.
- **Verification**: `tests/test_c05_durable_continuity.py`: 5 regression tests added (10/10 tests PASS).

---

### Gate 2 — C05 True Durable Task Resume

- **Finding & Root Cause**: `resume_worker_from_checkpoint()` in `subagentbridge/recovery/crash_recovery.py` previously restored token budgets and launched a fresh subprocess, but did not resume the in-flight interrupted task, recover worktree binding, or prove idempotent continuation without duplicate side effects.
- **Remediation**:
  1. **Runtime Token Flag**: Updated `WorkerProcessController.spawn_worker()` and `worker_runtime_entrypoint.py` to pass `--tokens-consumed`, ensuring fresh child OS processes inherit exact cumulative token consumption.
  2. **`resume_task_from_checkpoint()`**: Implemented true task-level continuation in `crash_recovery.py`:
     - Rehydrates worker session and verifies worktree path and commit binding.
     - Restores checkpoint `context_snapshot` containing completed subtasks.
     - Executes remaining subtasks idempotently (skipping already-completed steps without duplicate execution).
     - Transitions durable queue task status to `COMPLETED` and saves updated checkpoint.
- **Evidence Before vs. After**:
  - *Before*: Only worker process was rebooted to `IDLE`; task was stranded in `FAILED` or unresumed.
  - *After*: Full logical task resumed across process boundary and completed with verifiable output.
- **Verification**: `test_c05_resume_task_from_checkpoint_multi_step` in `tests/test_c05_durable_continuity.py` PASS.

---

### Gate 3 — C06 Real Execution Evidence & Artifact Hashing

- **Finding & Root Cause**: `tests/test_c06_parity_acceptance.py` previously relied on mock-like echo commands (`GENERATING_CODE_ARTIFACT`, `ALL_TESTS_PASS`) and declared unverified string artifacts (`artifact.py`, `test_report.xml`) that were never written to disk.
- **Remediation**:
  1. **Handoff Verification Boundary (`subagentbridge/team/orca_team.py`)**:
     - `submit_worker_handoff(evidence, verify_artifacts=True)` strictly inspects worker's worktree.
     - Verifies every declared artifact physically exists on disk.
     - Verifies SHA256 content hashes match `evidence.metrics["artifact_hashes"]`.
     - Verifies `metrics["exit_code"] == 0` and `metrics["qa_verdict"] in ("PASS", "VERIFIED")`.
     - Strictly rejects replayed handoffs and unauthorized worker sessions.
  2. **End-to-End Multiworker Test**:
     - Worker 1 (Coder) writes real executable Python module `math_utils.py` to disk; computes exact SHA256.
     - Worker 2 (Tester) executes real test suite against `math_utils.py` and produces `test_report.json` containing test results; computes exact SHA256.
     - Negative tests prove:
       - Invented artifacts (e.g., `ghost_module.py`) are strictly rejected (`FileNotFoundError`).
       - Fabricated QA verdicts (`FAILED` or missing) are strictly rejected (`ValueError`).
- **Evidence Before vs. After**:
  - *Before*: `sys.executable -c print('...')` with zero disk artifacts.
  - *After*: Real file artifacts created on disk, hash-verified, tested by second worker, and validated before handoff acceptance.
- **Verification**: `test_c06_e2e_multiworker_workflow` PASS.

---

### Gate 4 — C06 Real In-Flight Crash Injection (Addressing Codex Review)

- **Finding & Root Cause**: Codex review finding on PR #15 (`https://github.com/rzqllh/SubagentBridge/pull/15#discussion_r4373221954`) identified that `test_c06_fault_injection_and_recovery` killed an idle worker process: `dispatch_task()` and `update_queue_status()` only altered SQLite records without sending work over IPC, passing the test without exercising an in-flight command or process-tree termination.
- **Remediation**:
  1. Dispatched genuine long-running 30s task over subprocess IPC via background thread `send_task_async()`.
  2. Worker subprocess actively executes and writes observable filesystem marker `task_in_flight.marker`.
  3. Test verifies process exists in OS process table and marker is written before injecting fault.
  4. Fault injected via `kill_process_tree(record.pid)`.
  5. Verified OS process table confirms process is terminated.
  6. Reconciler (`reconcile_team_after_crash`) audits OS process table, detects dead worker, and transitions worker and in-flight queue task to `FAILED`.
  7. Late completion response strictly rejected (`ValueError`/`PermissionError`).
  8. Resumed worker from checkpoint with fresh controller, proving new PID, restored token budget (2500), and healthy `IDLE` state.
- **Evidence Before vs. After**:
  - *Before*: Idle worker killed with zero in-flight IPC activity.
  - *After*: Observable active IPC task interrupted mid-execution, descendant processes cleaned up, late completion denied, durable failure recorded.
- **Verification**: `test_c06_fault_injection_and_recovery` PASS. Codex PR #15 review finding fully remediated.

---

### Gate 5 — C06 Human Approval Truth & Replay Boundary

- **Finding & Root Cause**: `test_c06` tests accessed `authority.broker._secret` and called `approve_by_human()`, which serves only as an automated test fixture and does not constitute verification of an interactive human approval path.
- **Remediation & Boundary Audit**:
  1. Clarified and audited trust boundary: model/MCP layer is strictly untrusted.
  2. In-payload boolean approval claims (e.g. `{"approved": True}` or `{"approver": "human"}`) are strictly ignored and denied.
  3. Single-Use Replay Protection: Tickets are bound to exact `(worker_id, task_id, command, workspace_path, session_secret)`. Any tampering with task ID, worker ID, or command invalidates the HMAC ticket.
  4. Action ID cannot be re-issued for a second execution ticket (`replay prevented`).
  5. Confined Limitation: E18 same-user co-process execution remains `BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)`. Automated tests use trusted fixtures; interactive production approvals require separate out-of-band channel.
- **Evidence**: `test_c06_human_approval_truth_and_tampering_boundaries` PASS.

---

### Gate 6 — C06 Pinned Cindy Parity Truth & Semantic Mapping

- **Finding & Root Cause**: Previous reports claimed 1:1 identical 7 worker statuses matching Cindy upstream. In reality, Cindy upstream `orcaTeamService.ts` defines 4 worker states: `'idle' | 'running' | 'done' | 'error'`.
- **Remediation**:
  1. Updated parity verification to document exact semantic mapping rather than false string equivalence:
     - Cindy `'idle'` ↔ Simpul `WorkerStatus.IDLE`
     - Cindy `'running'` ↔ Simpul `WorkerStatus.RUNNING`
     - Cindy `'done'` ↔ Simpul `{WorkerStatus.COMPLETED, WorkerStatus.ARCHIVED}`
     - Cindy `'error'` ↔ Simpul `{WorkerStatus.FAILED, WorkerStatus.INTERRUPTED}`
  2. Explicitly classified Simpul `WorkerStatus.PAUSED` as a `SIMPUL_EXTENSION`.
  3. Verified 7 queue task statuses and Lead/Worker role separation against pinned Cindy SHA `b7e46bcbbe41eeee2f16381fef00df61a31a3b8b`.
- **Evidence**: `test_c06_pinned_cindy_parity_contract_verification` PASS.

---

### Affected Files Audit

| File | Status | Description of Change |
|---|---|---|
| `subagentbridge/workspaces/worktree_manager.py` | Modified (C05) | Removed `--force`, `rmtree`, and `prune`. Added regex worker ID check, dirty/untracked fail-closed, symlink rejection, path containment, and threading lock. |
| `subagentbridge/execution/worker_process.py` | Modified (C05) | Added `--tokens-consumed` flag propagation to child processes. |
| `subagentbridge/execution/worker_runtime_entrypoint.py` | Modified (C05) | Added `--tokens-consumed` argument parsing and initial counter setup. |
| `subagentbridge/recovery/crash_recovery.py` | Modified (C05) | Restored cumulative tokens and worktree in worker resume; added `resume_task_from_checkpoint()` for idempotent task continuation. |
| `tests/test_c05_durable_continuity.py` | Modified (C05) | Added 5 data safety regression tests and 1 multi-step task resume test (10/10 PASS). |
| `subagentbridge/team/orca_team.py` | Modified (C06) | Added artifact existence and SHA256 verification in `submit_worker_handoff()`; added QA verdict validation and replayed handoff rejection. |
| `tests/test_c06_parity_acceptance.py` | Modified (C06) | Implemented real file generation & hashing, genuine in-flight crash injection, human approval truth test, and Cindy semantic mapping (8/8 PASS). |
| `docs/simpul/SIMPUL_CINDY_PARITY_REPORT.md` | Modified (Both) | Appended full Corrective Acceptance section for Gates 1–6. |

---

### Execution Receipts, Artifact Hashes & Test Commands

1. **Unit Test Receipts (C05)**:
   - Command: `python -m pytest tests/test_c05_durable_continuity.py -v`
   - Result: 10 passed in 1.45s (Exit code 0).
2. **Unit Test Receipts (C06)**:
   - Command: `python -m pytest tests/test_c06_parity_acceptance.py -v`
   - Result: 8 passed in 2.15s (Exit code 0).
3. **Full Discovery Suite**:
   - Command: `python -B -m unittest discover -s tests -p "test_*.py"`
   - Result: Ran 325 tests in 53.396s, OK (skipped=5) (Exit code 0).
4. **Static Analysis & Security Scans**:
   - `python -m mypy --ignore-missing-imports --check-untyped-defs subagentbridge tests/test_c06_parity_acceptance.py`: Success: no issues found in 57 source files (Exit code 0).
   - `python -m ruff check --select E4,E7,E9,F subagentbridge tests/test_c06_parity_acceptance.py`: All checks passed! (Exit code 0).
   - `python -m bandit -q -r -ll subagentbridge`: 0 issues found (Exit code 0).
5. **Real Artifact Hashes Generated in C06 Workflow**:
   - `math_utils.py`: SHA256 verified in handoff receipt (`a8...`).
   - `test_report.json`: SHA256 verified in handoff receipt (`7f...`).

---

### Exact Tested SHA & Final Branch Status

- **C05 Branch**: `simpul/13-durable-continuity`
  - Tested & Pushed Commit: `59d7aa2`
  - Remote PR #14: https://github.com/rzqllh/SubagentBridge/pull/14
  - GitHub Actions CI Run: `40268292379` (4/4 jobs PASS in 2m33s on Ubuntu & Windows, Python 3.11 & 3.13)
- **C06 Branch**: `simpul/14-parity-acceptance`
  - Merged C05 Commit: `59d7aa2`
  - Local HEAD with C06 Final Closure: Incorporates full pytest CI integration, handoff artifact integrity, and Codex review fixes.
  - Remote PR #15: https://github.com/rzqllh/SubagentBridge/pull/15
  - Target CI Execution: 404 tests collected across `tests` and `artifacts/bootstrap/v3_1/tests`.

---

### Remote Review Threads Status

| PR | Reviewer / Bot | Thread Subject | Status | Remediation Note |
|---|---|---|---|---|
| #9 | Human Reviewers | 8 security/isolation threads | **REMEDIATED (Awaits Reviewer Resolution)** | Code remediated across previous gates; awaits human reviewer signoff on GitHub. |
| #15 | Codex (`chatgpt-codex-connector`) | P2: Start real task execution before injecting worker crash | **REMEDIATED (Commit 5de9771 & C06 HEAD)** | Real in-flight IPC worker subprocess with observable disk marker and process-tree SIGKILL in `test_c06_fault_injection_and_recovery`. |
| #15 | Codex (`chatgpt-codex-connector`) | P2: Handoff fixture breaks C01/C04 parity contracts | **REMEDIATED (C06 HEAD)** | Updated C01 & C04 fixtures to create physical artifacts with SHA256 hashes in trusted temporary directories, explicit RUNNING state, and validated execution receipts. |
| #16 | Codex (`chatgpt-codex-connector` 4375020701) | P2: Concurrent migration race on legacy table discovery | **REMEDIATED (PR #16 HEAD)** | Re-query actual legacy table objects strictly after acquiring BEGIN IMMEDIATE write lock; prevents DROP TABLE against compatibility views during simultaneous initialization. |

---

### Final CI Coverage, Handoff Integrity & Data Safety Closure

#### 1. Explicit Full Pytest Step in CI
- **Problem**: Previous CI `.github/workflows/ci.yml` executed only `unittest discover` and bootstrap tests. Pytest-style functions in C01–C06 parity suites were not automatically discovered by unittest.
- **Remediation**: Added explicit full pytest step to `.github/workflows/ci.yml`:
  ```yaml
  - name: Run full pytest suite (core & parity acceptance)
    run: python -m pytest tests artifacts/bootstrap/v3_1/tests -rs -v
  ```
- **Observed Execution**:
  - `python -m pytest tests artifacts/bootstrap/v3_1/tests -rs`: **404 collected, 399 passed, 5 skipped (Windows symlink / offline flag), 0 failed** in 81.34s.
  - `python -B -m unittest discover -s tests -p "test_*.py"`: **Ran 325 tests, OK (skipped=5, 0 failed)** in 67.14s.

#### 2. C05 P0 Data Safety & Continuation Hardening (PR #14 Verified)
- **Worktree Cleanup**:
  - Permanently excised `shutil.rmtree` and routine `git worktree prune`.
  - Fail-closed on any `git status` or `git worktree list` inspection errors.
  - Strictly blocked removal of dirty, untracked, or ignored user files (`git status --porcelain=v1 --ignored=matching`).
  - Verified worktree identity and branch ownership against porcelain worktree records before any removal.
  - Regression tested in `test_c05_worktree_cleanup_rejects_ignored_user_files`.
- **Durable Continuation**:
  - Bound checkpoints strictly to `(dispatch_id, task_id, team_id, commit_hash)`.
  - Checkpoints from differing dispatches cannot skip steps in active tasks (`test_c05_resume_task_rejects_checkpoint_from_different_dispatch`).
  - Validated physical disk presence of `expected_artifacts` prior to granting `COMPLETED` status.
- **Verification**: PR #14 commit `59d7aa2` verified green across all 4 matrix jobs in GitHub Actions Run `40268292379`.

#### 3. C06 Handoff Integrity & Path Containment Hardening (PR #15)
- **Execution Receipt Mandate**:
  - `OrcaTeamService.submit_worker_handoff()` requires a trusted execution receipt (`exit_code == 0`, `qa_verdict in ('PASS', 'VERIFIED')`).
  - Model-supplied self-reporting metrics are rejected as substitutes for verified execution receipts.
- **Pending Task Rejection**:
  - Handoff submission strictly rejects tasks in `PENDING` status (`ValueError: Cannot accept handoff for task in PENDING state`).
- **Path Traversal & Symlink Escape Prevention**:
  - All declared artifacts are validated for canonical containment within the worker's working directory (`resolved_path.relative_to(worker_dir)`).
  - Traversal attempts (`../../etc/passwd`) and symlink escapes raise `PermissionError`.
- **Concurrency & Duplication Protection**:
  - Handoff submissions are synchronized with `self._lock = threading.Lock()`, preventing duplicate or concurrent handoff finalization races.

---

### Final Runtime Integrity Closure on PR #15

#### 1. Verified Handoff Bypass Excised
- **No Production Bypass**: Explicitly disallow `verify_artifacts=False` for successful completions (`status in ("SUCCESS", "PASSED")`), raising `PermissionError`.
- **Mandatory SHA256 Hashes**: Every declared artifact requires an explicit 64-hex SHA256 digest in `metrics["artifact_hashes"]`; missing or invalid hashes raise `ValueError`.
- **Trusted Receipt Enforcement**: For `SUCCESS`/`PASSED`, genuine execution receipts (`receipt_id` or `execution_receipt`) and matching `qa_verdict in ('PASS', 'VERIFIED')` are strictly required; client-supplied `exit_code: 0` without receipt provenance is rejected.
- **Empty / Fabricated Evidence Rejection**: Empty summaries or empty metrics dictionaries raise `ValueError`.
- **Pre-Resolution Symlink Defense**: Artifact paths are checked for symlinks before `.resolve()`, blocking internal workspace symlink bypasses (`PermissionError`).
- **Transactional Finalization & Replay Protection**: `OrcaStore.finalize_handoff_transaction()` atomically verifies non-completed queue status, inserts into `orca_handoffs` (raising `ValueError` on duplicate replay), transitions queue status, and resets worker session to `IDLE` in a single SQLite ACID transaction.
- **Contract-Only Separation**: Contract-only submissions (`status in ("CONTRACT_FIXTURE", "CONTRACT_ONLY")`) return `CONTRACT_VERIFIED` and do NOT advance queue items to `COMPLETED`.

#### 2. Strict Checkpoint Integrity & Continuation
- **Strict Commit Identity Binding**: Resuming from a checkpoint requires explicit, non-empty matching `commit_hash` between the checkpoint snapshot and the worktree HEAD (`git rev-parse HEAD`). If either commit is missing or differs, execution skipping is denied (`is_valid_checkpoint = False`).
- **Task-Specific Evidence Validation**: Completed steps in a checkpoint must have verified physical disk artifacts before skipping. Checkpoints claiming all steps completed without physical evidence are rejected and safely re-executed.
- **Recovery Ambiguity Classification**: When crashes occur between side effects and checkpoint writes, execution is classified as `RECOVERABLE_AMBIGUITY_AT_LEAST_ONCE` rather than asserting strict exactly-once.
- **Concurrent & Duplicate Resume Prevention**: `OrcaStore.mark_task_resuming()` atomically verifies queue state, rejecting concurrent resumes (`RUNNING`) and duplicate replays (`COMPLETED`) with `RuntimeError`.

#### 3. Worktree Safety Confirmation
- **`force=True` Rejection**: Passing `force=True` to `cleanup_worktree()` is strictly forbidden and raises `ValueError`.
- **Raw Symlink & Junction Defense**: The raw worktree path is checked with `is_symlink()` prior to resolution.
- **Worktree Branch Identity Verification**: Verified that the porcelain `git worktree list` record contains the exact assigned branch `refs/heads/{branch_name}` before cleanup.
- **Record Preservation**: SQLite worktree ownership records are deleted only after all Git operations succeed.

#### 4. Verification Evidence & Test Inventory
- **Full Pytest Suite**: **415 items collected: 409 passed, 6 skipped, 0 failed** in 70.09s.
- **Unittest Suite**: **Ran 325 tests, OK (skipped=5, 0 failed)** in 50.41s.
- **Ruff Check**: Exit code 0 (all checks passed).
- **Mypy Typecheck**: Exit code 0 (no issues found in 56 source files).
- **Bandit Security**: Exit code 0 (0 issues found).

#### 5. Changed Files Inventory
- `subagentbridge/domain/orca_contracts.py` (Preserved exact 7 Cindy queue states)
- `subagentbridge/storage/orca_store.py` (Added `finalize_handoff_transaction` and `mark_task_resuming`)
- `subagentbridge/team/orca_team.py` (Hardened `submit_worker_handoff` with receipt, hash, symlink, and transaction guarantees)
- `subagentbridge/workspaces/worktree_manager.py` (Rejected `force=True`, added raw symlink check and branch identity verification)
- `subagentbridge/recovery/crash_recovery.py` (Strict commit binding, evidence validation, concurrent resume protection, ambiguity classification)
- `tests/test_c01_parity_foundation.py` (Updated handoff receipt)
- `tests/test_c04_interagent_control.py` (Added 7 handoff integrity negative tests)
- `tests/test_c05_durable_continuity.py` (Added 4 checkpoint and worktree negative tests)
- `tests/test_c06_parity_acceptance.py` (Updated h1 and h2 handoff receipts)
- `docs/simpul/SIMPUL_CINDY_PARITY_REPORT.md` (Updated authoritative report)

---

### Parity Realism Classification

| Parity Capability | Classification | Verification & Evidence |
|---|---|---|
| In-process Dummy Workers & Role Contracts | **Contract / Test Fixture** | Validated via `OrcaTeamService` unit contracts. |
| Interactive Human Confirmation Broker | **Contract / Test Fixture** | In-process secret broker fixture. Fails closed under `GATE_MODE: CHAT_APPROVAL`. |
| Subprocess CLI Worker Execution & IPC | **Real Native Execution** | Verified via subprocess worker spawn, stdio pipes, and process tree lifecycle. |
| Git Worktree Isolation & Ownership | **Real Native Execution** | Validated via real `git worktree` commands, porcelain status, and SQLite tracking. |
| SQLite State Persistence & Crash Recovery | **Real Native Execution** | ACID transactions, WAL checkpoints, and durable step resumption verified. |
| Handoff Artifact Hashing & Verification | **Real Native Execution** | Physical file creation, SHA256 hashing, and canonical path traversal defense. |
| External Claude Desktop & Codex CLI Harnesses | **Real External Harness Integration** | Harness wrappers with schema/transport validation tested. |
| Same-User OS Confinement (E18) | **Blocked / Accepted Risk** | `BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)` — Lead and worker share OS user identity. |
| Autonomous Production Merge & Push | **Human-Owned Action** | `AUTONOMY: OFF` — Autonomous merging blocked. Awaits explicit human merge approval. |

---

### Phase C07: Native Naming Migration & Cindy Attribution Closure

#### 1. Complete Naming Inventory (Before & After)

| Component Category | Legacy Name / Path | Native Simpul Name / Path | Backward Compatibility Status |
|---|---|---|---|
| **Domain Contracts** | `subagentbridge/domain/orca_contracts.py` | `subagentbridge/domain/team_contracts.py` | Re-export shim preserved in `orca_contracts.py` |
| **Persistence Store** | `subagentbridge/storage/orca_store.py` | `subagentbridge/storage/team_store.py` | Re-export shim preserved in `orca_store.py` |
| **Team Management** | `subagentbridge/team/orca_team.py` | `subagentbridge/team/team_manager.py` | Re-export shim preserved in `orca_team.py` |
| **Role Enum** | `OrcaRole` (`lead`, `worker`) | `AgentRole` (`lead`, `worker`) | `OrcaRole = AgentRole` alias |
| **Team Model** | `OrcaTeam` | `AgentTeam` | `OrcaTeam = AgentTeam` alias |
| **Session Model** | `OrcaSession` (`orca_role`) | `AgentSession` (`role`) | `OrcaSession = AgentSession`, `@property orca_role` |
| **Store Class** | `OrcaStore` | `TeamStore` | `OrcaStore = TeamStore` alias |
| **Service Class** | `OrcaTeamManager` / `OrcaTeamService` | `TeamManager` | Aliases preserved |
| **Integration Probe** | `OrcaProbe` | `IntegrationProbe` | `OrcaProbe = IntegrationProbe` alias |
| **Database Table** | `orca_teams` | `simpul_teams` | Compatibility VIEW `orca_teams` |
| **Database Table** | `orca_sessions` | `simpul_sessions` | Compatibility VIEW `orca_sessions` |
| **Database Table** | `orca_queue` | `simpul_queue` | Compatibility VIEW `orca_queue` |
| **Database Table** | `orca_worktrees` | `simpul_worktrees` | Compatibility VIEW `orca_worktrees` |
| **Database Table** | `orca_handoffs` | `simpul_handoffs` | Compatibility VIEW `orca_handoffs` |
| **Database Table** | `orca_channel_messages` | `simpul_channel_messages` | Compatibility VIEW `orca_channel_messages` |
| **Database Table** | `orca_checkpoints` | `simpul_checkpoints` | Compatibility VIEW `orca_checkpoints` |
| **External Adapter** | `OptionalOrcaBackend` | `OptionalOrcaBackend` (isolated boundary) | Retained as optional compatibility seam |

#### 2. Zero Data Loss SQLite Migration & Rollback Behavior
- **Schema Versioning**: Version tracked in `simpul_schema_version` (Version `2`).
- **Fail-Closed Transactional Migration**: In a single SQLite ACID transaction, existing records from `orca_*` are validated and copied to `simpul_*`. Row counts are asserted before dropping legacy tables. Any count mismatch raises `RuntimeError` and triggers immediate transaction rollback.
- **Backward Compatibility Views**: SQL views `CREATE VIEW orca_* AS SELECT * FROM simpul_*` are established, guaranteeing legacy queries continue to execute without modification.
- **Migration Suite**: `tests/test_team_store_migration.py` covers fresh DB init, legacy data migration with full state, idempotency across 5 restart cycles, and fail-closed rollback.

#### 3. Cindy Attribution & Provenance Findings
- **Upstream Reference**: `https://github.com/makecindy/cindy` (pinned commit `b7e46bcbbe41eeee2f16381fef00df61a31a3b8b`).
- **Copyright & License**: Cindy, Copyright 2026 XD Inc., Apache License 2.0.
- **Source Provenance Audit**:
  - *Architectural Inspiration*: Cindy's Orca core provided conceptual patterns for Lead/Worker sessions, task dispatch queue states, status lifecycles, and crash recovery.
  - *Clean-Room Implementation*: Simpul's codebase was written from scratch in Python 3.11+ using native standard library and SQLite primitives. No TypeScript sources were copied or transliterated.
  - *Not a Fork*: Simpul is an independent library with explicit architectural credit recorded in `THIRD_PARTY_NOTICES.md` and `README.md`.
  - Historical research logs and parity matrices in this report are preserved as permanent research provenance.

#### 4. Changed Files Inventory
- **Created (4 files)**:
  - `subagentbridge/domain/team_contracts.py`
  - `subagentbridge/storage/team_store.py`
  - `subagentbridge/team/team_manager.py`
  - `tests/test_team_store_migration.py`
- **Modified (19 files)**:
  - `subagentbridge/domain/orca_contracts.py` (shim)
  - `subagentbridge/storage/orca_store.py` (shim)
  - `subagentbridge/team/orca_team.py` (shim)
  - `subagentbridge/execution/orca_adapter.py` (`IntegrationProbe` + seam documentation)
  - `subagentbridge/execution/worker_process.py` (native imports & role checks)
  - `subagentbridge/execution/worker_runtime_entrypoint.py` (native import)
  - `subagentbridge/recovery/crash_recovery.py` (native imports & signatures)
  - `subagentbridge/runners/harness_adapters.py` (native import)
  - `subagentbridge/workspaces/worktree_manager.py` (native imports & annotations)
  - `subagentbridge/domain/__init__.py` (re-exports)
  - `subagentbridge/storage/__init__.py` (re-exports)
  - `subagentbridge/team/__init__.py` (re-exports)
  - `tests/test_c01_parity_foundation.py`
  - `tests/test_c02_worker_sessions.py`
  - `tests/test_c03_multi_harness.py`
  - `tests/test_c04_interagent_control.py`
  - `tests/test_c05_durable_continuity.py`
  - `tests/test_c06_parity_acceptance.py`
  - `tests/test_orca_optional.py`
  - `README.md`
  - `THIRD_PARTY_NOTICES.md`
  - `docs/simpul/SIMPUL_CINDY_PARITY_REPORT.md`
- **Deleted (0 files)**: Zero features removed.

#### 5. Local Verification Evidence & Test Inventory
- **Full Pytest Suite (`tests` + `artifacts/bootstrap/v3_1/tests`)**: **420 items collected: 414 passed, 6 skipped, 135 subtests passed** in 74.40s (0 failures).
- **Unittest Suite (`tests`)**: **325 tests passed, 0 failed, 5 skipped** in 60.14s.
- **Bootstrap Suite (`artifacts/bootstrap/v3_1/tests`)**: **13 tests passed, 0 failed** in 2.47s.
- **Ruff Check (`--select E4,E7,E9,F subagentbridge`)**: Exit code 0 (`All checks passed!`).
- **Mypy Static Typecheck (`subagentbridge`)**: Exit code 0 (`Success: no issues found in 59 source files`).
- **Bandit Security Analysis (`subagentbridge`)**: Exit code 0 (0 issues found).
- **MCP Server Smoke Test**: `MCP v1 server import PASS`.

---

### Phase C07 Final Cleanup, Safe Migration & Repository Hygiene Closure

#### 1. Complete Naming & Shims Inventory

| Category | Native Simpul Identifier | Legacy Identifier | Shim / Compatibility Status | Justification |
|---|---|---|---|---|
| **Domain Module** | `subagentbridge/domain/team_contracts.py` | `subagentbridge/domain/orca_contracts.py` | Clean re-export shim | Third-party scripts and backward-compatible import paths |
| **Role Enum** | `AgentRole` (`LEAD`, `WORKER`, etc.) | `OrcaRole` | Deprecated alias (`OrcaRole = AgentRole`) | Consumer type-hint compatibility |
| **Team Model** | `AgentTeam` | `OrcaTeam` | Deprecated alias (`OrcaTeam = AgentTeam`) | Multi-worker team construction compatibility |
| **Session Model** | `AgentSession` | `OrcaSession` | Deprecated alias (`OrcaSession = AgentSession`) | `@property orca_role` and worker lifecycle compatibility |
| **Storage Module** | `subagentbridge/storage/team_store.py` | `subagentbridge/storage/orca_store.py` | Clean re-export shim | Storage import backward compatibility |
| **Store Engine** | `TeamStore` | `OrcaStore` | Deprecated alias (`OrcaStore = TeamStore`) | Writable Python API compatibility across legacy scripts |
| **Coordination Module** | `subagentbridge/team/team_manager.py` | `subagentbridge/team/orca_team.py` | Clean re-export shim | Orchestrator import backward compatibility |
| **Manager Service** | `TeamManager` | `OrcaTeamManager` / `OrcaTeamService` | Deprecated aliases | Service invocation compatibility |
| **Adapter Module** | `subagentbridge/execution/integration_adapter.py` | `subagentbridge/execution/orca_adapter.py` | Clean re-export shim | Optional external CLI probe isolation |
| **Adapter Probe** | `IntegrationProbe` / `OptionalIntegrationBackend` | `OrcaProbe` / `OptionalOrcaBackend` | Deprecated aliases | Isolated compatibility boundary for external CLI |
| **Database Tables** | `simpul_teams`, `simpul_sessions`, `simpul_queue`, `simpul_worktrees`, `simpul_handoffs`, `simpul_channel_messages`, `simpul_checkpoints`, `simpul_schema_version` | `orca_*` tables | Migrated to `simpul_*`; replaced with read-only SQL views | Read-only SQL compatibility views for legacy inspector queries |

#### 2. Hardened Zero-Data-Loss Migration & Complete Column Mapping Engine
- **Logical Snapshot Pre-Migration Backup**: `conn.backup()` automatically snapshots the active database to `<db_path>.pre_migration.bak` prior to executing any DDL or data mutations.
  - *Distinction*: Distinguishes SQLite online backup API (`conn.backup()`) from raw filesystem file copies (`shutil.copyfile`). In WAL mode, raw file copying can miss pages in the `-wal` file or capture torn/inconsistent frames. `conn.backup()` captures all active pages in a transactionally consistent logical snapshot.
  - *Readability & Verification*: Immediately verified via `PRAGMA integrity_check == 'ok'`.
  - *Silent Overwrite Prevention*: If `<db_path>.pre_migration.bak` already exists from a prior run, a non-colliding timestamped backup `<db_path>.pre_migration.<timestamp>.bak` is created, ensuring existing backup points are never silently overwritten.
- **Explicit Transaction Management**: Autocommit is explicitly disabled (`isolation_level = None`), wrapping all DDL creation, conflict checks, data copies, row verifications, referential integrity checks, and table drops in a single atomic `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` block.
- **Schema-Aware Complete Column Mapping Across All 7 Legacy Tables**:
  Every single column across all 7 legacy tables is explicitly mapped and verified:
  1. `orca_teams` -> `simpul_teams`: `team_id`, `lead_session_id`, `title`, `created_at`.
  2. `orca_sessions` -> `simpul_sessions`: `session_id`, `role` (mapped from `orca_role` or `role`), `team_id`, `status`, `config_json`, `created_at`, `updated_at`.
  3. `orca_queue` -> `simpul_queue`: `dispatch_id`, `team_id`, `from_session_id`, `to_session_id`, `task_id`, `payload_json`, `status`, `dedup_key`, `priority`, `steering_json`, `created_at`, `updated_at`. Preserves documented defaults (`dedup_key = NULL`, `priority = 0`, `steering_json = '[]'`) when genuinely absent in older legacy schema.
  4. `orca_worktrees` -> `simpul_worktrees`: `worker_id`, `team_id`, `worktree_path`, `branch_name`, `created_at`.
  5. `orca_handoffs` -> `simpul_handoffs`: `dispatch_id`, `team_id`, `from_worker_id`, `to_lead_id`, `status`, `summary`, `artifacts_json`, `metrics_json`, `submitted_at`.
  6. `orca_channel_messages` -> `simpul_channel_messages`: `message_id`, `team_id`, `from_session_id`, `to_session_id`, `content`, `role`, `created_at`.
  7. `orca_checkpoints` -> `simpul_checkpoints`: `checkpoint_id`, `worker_id`, `team_id`, `step_index`, `state_summary`, `tokens_consumed`, `context_json`, `created_at`.
- **Exhaustive Primary Key & Omitted Column Conflict Detection**:
  - Compares every mapped data column for existing primary keys before copying.
  - Any mismatch in previously omitted columns (`sessions.updated_at`, `queue.from_session_id`, `queue.to_session_id`, `queue.dedup_key`, `queue.priority`, `queue.steering_json`, timestamps, `checkpoints.team_id`, `checkpoints.created_at`, `checkpoints.tokens_consumed`, `checkpoints.context_json`, `channel_messages.from_session_id`, `channel_messages.to_session_id`, `channel_messages.created_at`, `handoffs.metrics_json`, `handoffs.submitted_at`) fails closed with `MigrationConflictError` and rolls back all mutations.
- **Application-Level Referential Integrity Verification**:
  - `PRAGMA foreign_key_check` alone is insufficient when SQLite tables lack explicit `FOREIGN KEY (...) REFERENCES ...` DDL clauses.
  - Implemented `_verify_application_referential_integrity(conn)` which explicitly asserts that no orphaned records exist across teams, sessions, queue items, worktrees, handoffs, channel messages, and checkpoints prior to dropping legacy tables.
- **Injected Failure State Restoration**:
  - Verified that an injected failure after data copying but before legacy table deletion rolls back the transaction completely, restoring the database to its exact initial state with zero data loss.
- **Read-Only Compatibility Views vs. Writable API**:
  - SQL `orca_*` views are established as read-only compatibility views for legacy inspection tools.
  - Full read/write compatibility is provided at the Python API level by the `OrcaStore` class (mapping writes directly to `simpul_*` tables).
- **Concurrency & Multi-Process Safety**: `TeamStore` enables `PRAGMA busy_timeout=5000` alongside WAL mode and reentrant threading locks (`threading.RLock()`), preventing lock collisions.

#### 3. Repository Worktree & Branch Hygiene

##### Active Worktree Inventory (Preserved - No Destructive Pruning)
All 16 active repository worktrees are intact and preserved without destructive pruning:
1. `SubagentBridge` (root, branch `simpul/08-sprint1-verification`, PR #9)
2. `.worktrees/p00-baseline-recovery` (`feat/00-baseline-recovery`)
3. `.worktrees/p01-roadmap-v4-verified` (`integrate/roadmap-v4-verified`)
4. `.worktrees/p02-durable-control-plane` (`simpul/02-durable-control-plane`)
5. `.worktrees/p03-native-execution` (`simpul/03-native-execution`)
6. `.worktrees/p04-router-skills` (`simpul/04-router-skills`)
7. `.worktrees/p05-antigravity-qa` (`simpul/05-antigravity-qa`)
8. `.worktrees/p06-release-hardening` (`simpul/06-release-hardening`)
9. `.worktrees/p07-corrective-audit` (`simpul/07-corrective-audit`)
10. `.worktrees/p09-parity-foundation` (`simpul/09-parity-foundation`, PR #10)
11. `.worktrees/p10-worker-sessions` (`simpul/10-worker-sessions`, PR #11)
12. `.worktrees/p11-multi-harness` (`simpul/11-multi-harness`, PR #12)
13. `.worktrees/p12-interagent-control` (`simpul/12-interagent-control`, PR #13)
14. `.worktrees/p13-durable-continuity` (`simpul/13-durable-continuity`, PR #14)
15. `.worktrees/p14-parity-acceptance` (`simpul/14-parity-acceptance`, PR #15)
16. `.worktrees/p15-native-naming` (`simpul/15-native-naming`, PR #16)

##### Deferred Cleanup Manifest
Per safety rules, no worktrees or branches may be deleted while PRs #9–#16 remain unmerged.
Upon human-authorized merge of the stacked PRs into `main`, the following cleanup actions are scheduled:
- Remove merged parity worktrees: `p09` through `p15`.
- Delete merged remote tracking branches: `simpul/09` through `simpul/15`.
- Retain root worktree and `main` branch.

#### 4. Cindy Attribution & Provenance
- Upstream: `https://github.com/makecindy/cindy` (pinned commit `b7e46bcbbe41eeee2f16381fef00df61a31a3b8b`).
- License: Apache-2.0, Copyright 2026 XD Inc.
- Source Provenance: Clean-room Python 3.11+ implementation with architectural attribution documented in `THIRD_PARTY_NOTICES.md` and `README.md`. Historical research parity records preserved.

#### 5. Verification Matrix (Tested on `simpul/15-native-naming` HEAD)
- **Pytest Full Suite**: **432 items collected: 426 passed, 6 skipped (Windows symlink privileges/offline flags), 135 subtests passed** in 77.69s (0 failures).
- **Migration Suite (`tests/test_team_store_migration.py`)**: **17 comprehensive tests passed** in 1.63s (including all omitted-column conflict tests, application referential integrity, and injected failure rollback).
- **Unittest Discovery (`tests`)**: **325 passed, 0 failed, 5 skipped** in 55.11s.
- **Bootstrap Tests (`artifacts/bootstrap/v3_1/tests`)**: **13 passed** in 3.11s.
- **Ruff Check**: Exit code 0 (`All checks passed!`).
- **Mypy Static Analysis**: Exit code 0 (`Success: no issues found in 60 source files`).
- **Bandit Security Analysis**: Exit code 0 (`0 issues found with -ll`).
- **MCP Server Smoke Test**: `MCP v1 server import PASS`.

---

### Phase C07: Concurrent Migration Race Closure (Codex Review Comment 4375020701)

#### 1. Finding & Root Cause Analysis
- **Review Finding**: Codex review comment `4375020701` on PR #16 identified that `migrate_schema()` in `subagentbridge/storage/team_store.py` discovered `legacy_tables` prior to acquiring the migration write lock (`BEGIN IMMEDIATE`).
- **Failure Mode Under Concurrency**: When two connections or processes simultaneously initialized against an unmigrated legacy database:
  1. Connection 1 and Connection 2 both observed `legacy_tables = {'orca_teams', ...}` from `sqlite_master`.
  2. Connection 1 acquired `BEGIN IMMEDIATE`, completed migration, dropped legacy `orca_*` tables, created read-only compatibility views with the same names (`CREATE VIEW orca_*`), and committed.
  3. Connection 2 subsequently acquired `BEGIN IMMEDIATE`. Because Connection 2 retained its pre-lock metadata snapshot `legacy_tables`, it attempted `DROP TABLE orca_teams` against the view created by Connection 1, raising `sqlite3.OperationalError: use DROP VIEW to delete view orca_teams`.
- **Secondary Masking Defect**: If `BEGIN IMMEDIATE` raised an `OperationalError` (e.g., lock contention or busy timeout failure), the unconditional `conn.execute("ROLLBACK")` in `except Exception:` threw `OperationalError: cannot rollback - no transaction is active`, hiding the actual lock error.
- **Backup Deadlock Constraint**: Calling `conn.backup()` directly on the writer connection holding an uncommitted `BEGIN IMMEDIATE` lock in SQLite blocks/deadlocks on Windows.

#### 2. Architecture & Implementation Remediation
1. **Post-Lock Legacy Table Discovery**:
   - Write lock acquisition (`conn.execute("BEGIN IMMEDIATE")`) is executed at the very entry of `migrate_schema()`.
   - Legacy tables are queried strictly from `sqlite_master` *after* the write lock is granted:
     ```python
     cur_tables = conn.execute(
         "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'orca_%'"
     )
     active_legacy_tables = {r["name"] for r in cur_tables.fetchall()}
     ```
   - Because `type='table'` filters out views, any racing second connection observes `active_legacy_tables` as empty (`set()`).
   - If `current_version >= 2 and not active_legacy_tables:`, the second connection idempotently verifies views, commits, and returns cleanly without re-executing migration or attempting `DROP TABLE`.
2. **Dedicated Reader Connection for Pre-Migration Snapshot**:
   - Pre-migration logical byte backups (`conn.backup()`) are taken safely inside the write-locked block via a dedicated reader connection:
     `backup_src = sqlite3.connect(str(db_file))`
   - Safely captures committed pages in WAL mode without deadlocking against the writer connection.
   - If backup creation or `PRAGMA integrity_check` fails, the partial backup file is unlinked and closed before re-raising.
3. **Transaction State Tracking & Unmasked Error Propagation**:
   - `in_transaction = True` is set only after `BEGIN IMMEDIATE` succeeds.
   - Rollback is invoked only when `in_transaction` is true, ensuring any lock contention or driver-level error during `BEGIN IMMEDIATE` is raised directly without masking.
4. **Targeted Legacy Table Deletions**:
   - `DROP TABLE IF EXISTS` is executed strictly against `active_legacy_tables`.

#### 3. Deterministic Regression & Concurrency Stress Test Suite
All 5 concurrency requirements are verified in `tests/test_team_store_migration.py`:
1. `test_deterministic_two_connection_concurrent_migration_race`:
   - Both connections observe legacy tables in `sqlite_master` before migration completes.
   - Coordinated via `threading.Event`: Connection 1 acquires `BEGIN IMMEDIATE`; Connection 2 calls `migrate_schema` and blocks on write lock; Connection 1 commits; Connection 2 unblocks, queries post-lock metadata, safely detects views, commits, and exits with 0 errors.
   - Asserts schema version 2, all original rows intact, views created, and singular valid backup.
2. `test_deterministic_two_process_concurrent_migration_race`:
   - 2 independent operating system processes (`subprocess.Popen`) observe legacy tables and compete simultaneously for `TeamStore(db_path)`. Both exit code 0 (`PROC_MIGRATION_OK`).
3. `test_concurrent_multi_thread_stress_initialization`:
   - 10 threads barrier-synchronized (`threading.Barrier(10)`) simultaneously initialize `TeamStore(db_path)` against legacy database. 10/10 succeed with 0 lock errors.
4. `test_concurrency_failure_injection_and_competing_initializer_recovery`:
   - Thread 1 fails transaction via injected exception and cleanly rolls back. Competing Thread 2 takes over, acquires lock, migrates database, and commits successfully.
5. `test_failed_begin_immediate_does_not_mask_original_error`:
   - Verified that a busy timeout failure on `BEGIN IMMEDIATE` raises original `sqlite3.OperationalError: database is locked` directly without `cannot rollback` masking.

#### 4. Complete Verification Matrix & CI Receipts
- **Exact Tested HEAD SHA**: `d11878fa16b8a669e2ec9e3fe5b7c63b5bb0b4e9`
- **GitHub Actions CI Run**: `40293982843` (PR #16 `simpul/15-native-naming`) — **4/4 PASS** in 4m15s:
  | Runner | Python | Status | Duration | Job ID |
  |---|---|---|---|---|
  | `ubuntu-latest` | 3.13 | **SUCCESS** | 1m43s | `121475456557` |
  | `ubuntu-latest` | 3.11 | **SUCCESS** | 1m29s | `121475456883` |
  | `windows-latest` | 3.13 | **SUCCESS** | 4m01s | `121475456907` |
  | `windows-latest` | 3.11 | **SUCCESS** | 4m12s | `121475457004` |
- **Review Thread Disposition**: Codex review comment `4375020701` on PR #16 — **RESOLVED & VERIFIED**.
  - Root cause resolved: post-lock table discovery via `sqlite_master` under `BEGIN IMMEDIATE`.
  - Stale metadata race completely closed; two initializers succeed deterministically.
  - Zero masked rollbacks on busy timeout failure.
- **Local Full Pytest Suite**: **437 items collected: 431 passed, 6 skipped, 135 subtests passed** in 78.94s (0 failures).
- **Migration Suite (`tests/test_team_store_migration.py`)**: **22 comprehensive tests passed** in 2.98s.
- **Unittest Discovery (`tests`)**: **325 tests passed, 0 failed, 5 skipped** in 56.40s.
- **Bootstrap Tests (`artifacts/bootstrap/v3_1/tests`)**: **13 tests passed, 0 failed** in 2.78s.
- **Ruff Check (`--select E4,E7,E9,F subagentbridge tests/test_team_store_migration.py`)**: Exit code 0 (`All checks passed!`).
- **Mypy Static Analysis (`subagentbridge`)**: Exit code 0 (`Success: no issues found in 60 source files`).
- **Bandit Security Analysis (`subagentbridge`)**: Exit code 0 (0 issues found with `-ll`).
- **FastMCP Server Smoke Test**: `MCP v1 server import PASS`.

---

### Final Quality Classification & Verdict

- **`CODE_CLEAN`**: Verified — native Simpul naming across domain, storage, team, and execution modules; clean shims retained; zero orphaned orca branding in production logic; no hardcoded personal machine paths.
- **`MIGRATION_VERIFIED`**: Verified — post-lock table discovery, schema-aware explicit column mapping for all 7 legacy tables, complete omitted column conflict detection, application-level referential integrity validation, physical online snapshot backup with collision avoidance, unmasked rollback, and read-only compatibility views tested and passing.
- **`CONCURRENCY_CERTIFIED`**: Verified — deterministic two-connection race, two-process OS race, 10-thread simultaneous stress, and failure injection recovery all PASS.
- **`ATTRIBUTION_PRESERVED`**: Verified — Cindy Apache-2.0, Copyright 2026 XD Inc., pinned commit `b7e46bcbbe41eeee2f16381fef00df61a31a3b8b` fully credited in `THIRD_PARTY_NOTICES.md` and research records.
- **`CI_PASS`**: Local & remote matrix green across GitHub Actions 40293982843 (4/4 PASS), 437 pytest items, 325 unittests, 13 bootstrap tests, Ruff, Mypy, and Bandit.
- **`GIT_CLEANUP_DEFERRED`**: Verified — all 16 worktrees and branches preserved; cleanup manifest documented pending human merge authorization.
- **`MERGE_REVIEW_READY`**: Verified — ready for review and human-approved push/merge.

**Final Verdict:** **`PASS (CONCURRENCY_CERTIFIED, MIGRATION_VERIFIED, MERGE_REVIEW_READY)`**

---

*Report last updated: 2026-10-26T15:47+07:00 - C07 Concurrent Migration Race Closure Verified (Codex 4375020701 Resolved, CI 40293982843 4/4 PASS).*






---

## Release v1.1.0 — verified integration receipt (27 October 2026)

- **Published release:** [v1.1.0](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.0) (public, not draft/prerelease).
- **Integration:** PR #16 merged C04–C07 and corrective fixes into `main` at `a29f0d98957651e482fbae989a906bb09873f329`. PR #12 was individually merged. PR #13–#15 were closed as **superseded**, not individually merged; their HEADs were checked as ancestors of this merge.
- **CI evidence:** candidate commit `fb9bc1c78efb066ecbbc1341e5f2c84aee1733bc`, Actions run `40440192101` (4/4 SUCCESS). Tested source tree `36551fe8faa25bd4c2886db0c41c8d4cab7bd39c` was identical to the merge commit tree.
- **Release:** workflow [40440851542](https://github.com/rzqllh/SubagentBridge/actions/runs/40440851542) SUCCESS at the exact merged `main` SHA. Published wheel, source archive and `SHA256SUMS.txt` after test/static security/build gates.
- **Corrections:** independent optional-column SQLite queue migration with static parameterized SQL; cross-connection atomic active dispatch dedup; terminal-safe cancellation; fail-closed unattached worker PID; explicit `AWAITING_APPROVAL` for recovered command steps.
- **Attribution:** Cindy Apache-2.0 and research provenance retained in `THIRD_PARTY_NOTICES.md`; independent Python implementation, not a source fork.
- **Residual:** E18 same-user process isolation remains `BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)`; automated test fixtures do not substitute for actual interactive human confirmation. Historical PR review threads remain at their actual GitHub states.
- **Cleanup:** user-local Windows worktrees and backups were not accessible and were not removed; only PR closures and repo source changes were performed remotely.
