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

## Feature Parity Matrix (Post-C01 Foundation State)

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
| **Worker Session** | Real independent worker OS process / host session | Subagent child process / MCP stdio session | Scheduled for `subagentbridge/execution/worker_process.py` | **SCHEMA (Not yet spawned)** | **C02** |
| **Worker Lifecycle** | Status state machine (`IDLE`..`ARCHIVED`) | `orca_workers.status` (7 lifecycle states) | `subagentbridge/domain/orca_contracts.py` (`WorkerStatus`) | **WORKING (State machine)** | C01 (Done) |
| **Worker Lifecycle** | Persistent vs Ephemeral lifecycle kind | `orca-team-architecture.md` (Section 3) | `subagentbridge/domain/orca_contracts.py` | **SCHEMA (Classified)** | **C02** |
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

*Report last updated: 2026-10-25T22:04+07:00 - C01 complete and verified, C02 worktree setup next*
