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
| C00 | `simpul/08-sprint1-verification` | **COMPLETE (local) - PENDING PUSH** | Security hardening, corrective review, all tests pass |
| C01 | `simpul/09-parity-foundation` | **NOT STARTED** | Architecture contracts, adapter boundaries, baseline failing tests |
| C02 | `simpul/10-worker-sessions` | **NOT STARTED** | Real independent worker sessions with lifecycle |
| C03 | `simpul/11-multi-harness` | **NOT STARTED** | Capability-checked host adapters |
| C04 | `simpul/12-interagent-control` | **NOT STARTED** | Durable message queue, targeting, dedup, interrupt/steer |
| C05 | `simpul/13-durable-continuity` | **NOT STARTED** | Restart/resume, checkpoint/recovery, worktree lifecycle |
| C06 | `simpul/14-parity-acceptance` | **NOT STARTED** | End-to-end, failure injection, adversarial, cross-platform CI |

---

## C00 - Sprint 1 Closure and Security Hardening

**Status**: COMPLETE locally - awaiting human push to remote
**Branch**: `simpul/08-sprint1-verification`
**HEAD**: `f422ed2`
**Remote PR #9**: Last observed at `dece7bb` - NOT YET UPDATED

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
| C00-T12 | Push to remote for CI | **BLOCKED - awaiting human gate** |

### Verification Matrix

| Tool | Result | Exit Code |
|---|---|---|
| `pytest tests/ artifacts/bootstrap/v3_1/tests/ -q` | 339 passed, 5 skipped in 59.31s | 0 |
| `ruff check subagentbridge/` | All checks passed! | 0 |
| `mypy subagentbridge/ --ignore-missing-imports` | Success: no issues found in 47 source files | 0 |
| `bandit -r subagentbridge/ -ll` | No issues identified (0 High, 0 Medium) | 0 |
| `git status` | nothing to commit, working tree clean | 0 |

### Key Security Findings

| Finding | Severity | Status |
|---|---|---|
| approve_command callable by same-user process = model self-approval risk | P0 | DOCUMENTED - E18 BLOCKED, no code change; honest disclosure |
| Default-deny command execution correctly implemented | P0 | PASS |
| JUnitXML temp file spoofable by same-user co-process | P0 | DOCUMENTED - E18 BLOCKED accepted risk |
| Thread lock is in-process only, not cross-process | P1 | DOCUMENTED - BLOCKED for cross-process exactly-once |
| Ruff 109 style violations in tests/ | Style | PRE-EXISTING - not a regression |

### Human Gate Required

Push command for human to execute:
`git push origin simpul/08-sprint1-verification`

Then verify CI run passes 4/4 matrix jobs before C01 begins.

---

## C01 - Parity Foundation

**Status**: NOT STARTED
**Branch**: `simpul/09-parity-foundation` (to be created)
**Depends on**: C00 push + CI passing + PR #9 accepted (or stacked ancestry explicitly noted)

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
