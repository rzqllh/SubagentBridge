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
| C01 | `simpul/09-parity-foundation` | **COMPLETE (local) - READY FOR PR/STACK REVIEW** | Architecture contracts, adapter boundaries, 8 baseline tests pass |
| C02 | `simpul/10-worker-sessions` | **NOT STARTED** | Real independent worker sessions with lifecycle |
| C03 | `simpul/11-multi-harness` | **NOT STARTED** | Capability-checked host adapters |
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

**Status**: COMPLETE (local) - ready for PR / stack review
**Branch**: `simpul/09-parity-foundation`
**Worktree**: `.worktrees/p09-parity-foundation`
**Base**: `eb97397` (stacked on `simpul/08-sprint1-verification`)

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

### Cindy Upstream Capabilities Mapped (from orca-team-architecture.md, SHA b7e46bc)

#### Lead Session Management

| Capability | Cindy | Simpul | Status |
|---|---|---|---|
| Lead session with distinct identity | sessions.orca_role='lead', OrcaLifecycleService | In-process PM principal only | **MISSING** |
| Team creation and lifecycle | orca_teams table | No team concept | **MISSING** |

#### Worker Sessions

| Capability | Cindy | Simpul | Status |
|---|---|---|---|
| Worker as real independent session | sessions.orca_role='worker' | Sequential role simulation | **MISSING** |
| Per-worker model/harness/effort | workerCreationPrefs | Single model per run | **MISSING** |
| Worker creation (role/label) | OrcaWorkerCreationService | No worker creation | **MISSING** |
| Worker status lifecycle | orca_workers.status | Task status only | **PARTIAL** |
| Worker archive | archive_worker tool | No archive | **MISSING** |

#### Dispatch and Queue

| Capability | Cindy | Simpul | Status |
|---|---|---|---|
| send_to_worker with queue | OrcaTeamService.dispatchWorkerTask | Sequential only | **MISSING** |
| Queue control (6 tools) | update/cancel/merge/steer/move | No queue | **MISSING** |
| Interrupt worker | interrupt_worker atomic preemption | No interrupt | **MISSING** |
| Auto-bridge worker-to-lead | OrcaInterAgentDispatcher | No inter-agent channel | **MISSING** |
| Durable queue across restart | SQLite-backed queue | No durable queue | **MISSING** |

#### Inter-Agent Communication

| Capability | Cindy | Simpul | Status |
|---|---|---|---|
| Worker reads Lead history | orca_worker_bridge.read_lead_history | No cross-session history | **MISSING** |
| Worker to Lead messaging | orca_worker_bridge auto-bridge | No worker-lead channel | **MISSING** |

#### Worktree Ownership

| Capability | Cindy | Simpul | Status |
|---|---|---|---|
| Per-worker worktree assignment | create_worker working_dir/new_worktree | No per-worker worktree | **MISSING** |
| Worktree lifecycle and recovery | WorktreeManager | No worktree management | **MISSING** |

#### Crash Recovery

| Capability | Cindy | Simpul | Status |
|---|---|---|---|
| Durable pending dispatch | store_upsert_dispatch | Basic SQLite rehydration | **PARTIAL** |
| Session resume semantics | session.resume with context | No session resume | **MISSING** |

### Baseline Failing Tests (to be created in C01)

1. test_c01_lead_worker_distinct_sessions
2. test_c01_worker_has_own_model_config
3. test_c01_dispatch_returns_queue_handle
4. test_c01_interrupt_preempts_worker
5. test_c01_worker_to_lead_handoff
6. test_c01_restart_reconstructs_sessions
7. test_c01_worktree_assignment_per_worker
8. test_c01_unapproved_command_blocked

---

## C02 through C06 - Pending

Sections will be appended after each phase completes.

---

## Feature Parity Matrix (Pre-C01 Baseline)

| Feature | Cindy/Orca | Simpul | Status |
|---|---|---|---|
| Lead session with persistent identity | Yes | No - in-process PM only | **MISSING** |
| Worker session - real independent | Yes | No - sequential simulation | **MISSING** |
| Per-worker model/harness/provider config | Yes | No - single model | **MISSING** |
| Worker creation (single + batch) | Yes | No | **MISSING** |
| Worker lifecycle (idle/running/done/error/archive) | Yes | No | **MISSING** |
| Durable message queue | Yes | No | **MISSING** |
| Queue control (6 tools) | Yes | No | **MISSING** |
| Interrupt/steer worker | Yes | No | **MISSING** |
| Lead-Worker dispatch | Yes | No | **MISSING** |
| Worker-Lead auto-bridge | Yes | No | **MISSING** |
| Per-worker worktree ownership | Yes | No | **MISSING** |
| Crash recovery - session reconstruction | Yes | Partial | **PARTIAL** |
| Crash recovery - pending queue | Yes | Partial | **PARTIAL** |
| Default-deny command authorization | No | Yes | **SIMPUL-SPECIFIC** |
| JUnitXML-based QA evidence | No | Yes | **SIMPUL-SPECIFIC** |
| Receipt authority and tree SHA binding | No | Yes | **SIMPUL-SPECIFIC** |
| Single-process supervised lifecycle | No | Yes | **SIMPUL-SPECIFIC** |
| Native no-Orca operation | Yes (optional Orca) | Yes (always native) | **PRESENT** |
| Budget ledger | Yes | Yes (in-process) | **PARTIAL** |
| SQLite persistence | Yes | Yes | **PRESENT** |
| Audit ledger | No | Yes | **SIMPUL-SPECIFIC** |

---

*Report last updated: 2026-10-25T21:30+07:00 - C00 complete locally, awaiting human push gate*
