# Simpul — Antigravity-First Subagent Roadmap & Upstream Parity

**Status: public v1.1.4, 29 October 2026.** This document serves as the human-readable architectural and parity reference. The machine-readable authoritative audit matrix is maintained in [`docs/simpul/parity_matrix.json`](../simpul/parity_matrix.json) and enforced by CI test [`tests/test_parity_matrix_truth.py`](../../tests/test_parity_matrix_truth.py).

## Product Direction

**Primary host: Google Antigravity IDE.** Simpul is a **native-first, supervised multi-worker subagent supervisor** connected through MCP stdio. Antigravity IDE is the front-end host where the user directs supervised tasks; Simpul is the control plane managing roles, worker subprocesses, durable queues, permissions, evidence, and crash recovery. It is **not** an alternative IDE, an Electron desktop wrapper, or an unrestricted autonomous coding autopilot.

### Upstream References and Pinned Commits

1. **Cindy Orca Team (`makecindy/cindy`)**:
   - **Pinned Commit:** `b7e46bcbbe41eeee2f16381fef00df61a31a3b8b` (Apache-2.0, Copyright 2026 XD Inc.).
   - **Role:** Primary architectural reference for Lead/Worker sessions, queues, steering, handoffs, and Git worktrees. Simpul independently implements these patterns in Python.
2. **Orca CLI (`orca-cli/orca`)**:
   - **Pinned Commit:** `5beeefcb57555962bb93facc54b5f82484731802` (MIT, Copyright 2026 John Santa).
   - **Role:** Secondary reference for DAG dependency models, pod orchestration, and command CLI workflows. Not a runtime dependency.
3. **Simpul Baseline**:
   - **Baseline Commit:** `ccac1d92efcc7cf3e40a3392978c30b8249a31bf` (`v1.1.4`).

---

## Status Classification Definitions

Every capability in the parity matrix is strictly labeled with one of six verifiable states:

| Status | Definition |
|---|---|
| `CODE_PRESENT` | Contract or logic exists in the codebase, but lacks dedicated automated unit or integration verification. |
| `UNIT_TESTED` | Verified by automated unit tests covering both positive and negative logic branches. |
| `INTEGRATED` | Wired into end-to-end multi-component execution flow (e.g., Coordinator + Process + Queue + Store). |
| `HOST_E2E_PASS` | Proven through live, end-to-end execution on the actual host (Antigravity IDE / real OS host). |
| `BLOCKED` | Hard security or architectural blocker preventing production certification (e.g. E18 OS sandbox, #22 WebAuthn). |
| `NOT_ADOPTED` | Intentionally excluded from scope with explicit rationale (e.g. desktop chat UI, mobile, remote SSH). |

---

## Comprehensive Upstream Parity Matrix

The following table reflects the 26 audited features across 6 functional categories defined in `docs/simpul/parity_matrix.json`:

### 1. Lead / Worker Lifecycle & Batching

| Feature ID | Feature Name | Upstream Source (SHA `b7e46bc` / `5beeefc`) | Simpul Source File | Status | Security Boundary |
|---|---|---|---|---|---|
| `PAR-FEAT-01` | Lead and Worker Role Separation | Cindy `orcaTeamService.ts` | `subagentbridge/domain/team_contracts.py` | `INTEGRATED` | Subprocess identity separation; intra-process role confusion denied |
| `PAR-FEAT-02` | Worker Lifecycle State Machine | Cindy `orcaTeamService.ts` | `subagentbridge/domain/team_contracts.py` | `INTEGRATED` | 7 explicit states; interrupted workers rejected from submitting completion |
| `PAR-FEAT-03` | Batch Worker Creation & Provisioning | Cindy `orcaTeamService.ts` | `subagentbridge/team/team_manager.py` | `UNIT_TESTED` | Per-worker working_dir validation and process isolation |
| `PAR-FEAT-04` | Per-Worker Model & Budget Config | Cindy `orcaTeamService.ts` | `subagentbridge/domain/team_contracts.py` | `INTEGRATED` | Fail-closed execution refusal upon budget exhaustion |

### 2. Queue, Steering & Inter-Agent Control

| Feature ID | Feature Name | Upstream Source (SHA `b7e46bc` / `5beeefc`) | Simpul Source File | Status | Security Boundary |
|---|---|---|---|---|---|
| `PAR-FEAT-05` | Durable Priority Queue | Cindy `orcaTeamService.ts` | `subagentbridge/storage/team_store.py` | `INTEGRATED` | SQLite persisted queue; cross-team task dispatch denied |
| `PAR-FEAT-06` | Queue Deduplication & Idempotency | Cindy `orcaTeamService.ts` | `subagentbridge/storage/team_store.py` | `INTEGRATED` | Idempotent dispatch via `dedup_key`; prevents duplicate tasks |
| `PAR-FEAT-07` | In-Flight Task Steering | Cindy `orcaTeamService.ts` | `subagentbridge/team/team_manager.py` | `INTEGRATED` | Mid-flight instruction injection authenticated to owning lead |
| `PAR-FEAT-08` | Authenticated Inter-Agent Messaging | Cindy `orcaTeamService.ts` | `subagentbridge/storage/team_store.py` | `INTEGRATED` | Cross-team message injection and sender impersonation denied |
| `PAR-FEAT-09` | Evidence-Bound Handoff & Receipts | Cindy `orcaTeamService.ts` | `subagentbridge/domain/team_contracts.py` | `INTEGRATED` | SHA-256 artifact hashes; spoofed handoffs strictly rejected |
| `PAR-FEAT-10` | Task DAG, Pods & Retry Semantics | Orca CLI `internal/dag/dag.go` | `subagentbridge/domain/contracts.py` | `CODE_PRESENT` | Circular dependencies rejected fail-closed |

### 3. Workspace & Worktree Safety

| Feature ID | Feature Name | Upstream Source (SHA `b7e46bc` / `5beeefc`) | Simpul Source File | Status | Security Boundary |
|---|---|---|---|---|---|
| `PAR-FEAT-11` | Isolated Git Worktree Lifecycle | Cindy `orcaTeamService.ts` | `subagentbridge/workspaces/worktree_manager.py` | `INTEGRATED` | Dedicated worktrees; dirty uncommitted worktrees fail closed on delete |
| `PAR-FEAT-12` | Workspace Path Containment | Cindy `orcaTeamService.ts` | `subagentbridge/workspaces/scope.py` | `INTEGRATED` | Path traversal (`..`) and symlink escapes strictly denied |
| `PAR-FEAT-13` | Branch Merge & Conflict Safety | Orca CLI `internal/worktree` | `subagentbridge/workspaces/worktree_manager.py` | `UNIT_TESTED` | No auto-push or direct push to protected main; review-gated merge |

### 4. Resilience & Crash Recovery

| Feature ID | Feature Name | Upstream Source (SHA `b7e46bc` / `5beeefc`) | Simpul Source File | Status | Security Boundary |
|---|---|---|---|---|---|
| `PAR-FEAT-14` | Step-Indexed Checkpoints | Cindy `orcaTeamService.ts` | `subagentbridge/domain/team_contracts.py` | `INTEGRATED` | Step-indexed snapshots; cross-worker checkpoint overwrite denied |
| `PAR-FEAT-15` | Crash Detection & Recovery | Cindy `orcaTeamService.ts` | `subagentbridge/recovery/crash_recovery.py` | `INTEGRATED` | Reconciles dead processes; late completions after crash rejected |
| `PAR-FEAT-16` | Ambiguous Side-Effect Quarantine | Cindy `orcaTeamService.ts` | `subagentbridge/domain/team_contracts.py` | `INTEGRATED` | Tasks transition to `AMBIGUOUS`; requires human reconciliation |
| `PAR-FEAT-17` | Zero-Data-Loss SQLite Migration | Cindy `orcaTeamService.ts` | `subagentbridge/storage/team_store.py` | `INTEGRATED` | Online backup, row verification, read-only legacy SQL views |

### 5. Host Integration & MCP Operations

| Feature ID | Feature Name | Upstream Source (SHA `b7e46bc` / `5beeefc`) | Simpul Source File | Status | Security Boundary |
|---|---|---|---|---|---|
| `PAR-FEAT-18` | Antigravity IDE Stdio MCP Server | Cindy `orcaTeamService.ts` | `subagentbridge/server.py` | `INTEGRATED` | Stdio MCP protocol; privileged execution requires human approval |
| `PAR-FEAT-19` | Multi-Harness Capability Checking | Cindy `orcaTeamService.ts` | `subagentbridge/runners/harness_adapters.py` | `INTEGRATED` | Fine-grained capabilities; unsupported harness raises KeyError |
| `PAR-FEAT-20` | Safe Model-Callable Team Tools | Cindy `orcaTeamService.ts` | `subagentbridge/server.py` | `INTEGRATED` | Inspection tools only; self-approval strictly unexposed |
| `PAR-FEAT-21` | Progress Timeline & Observability | Cindy `orcaTeamService.ts` | `subagentbridge/storage/team_store.py` | `UNIT_TESTED` | Read-only event stream; no execution side effects |

### 6. Security Boundaries & Decision Gates

| Feature ID | Feature Name | Upstream Source (SHA `b7e46bc` / `5beeefc`) | Simpul Source File | Status | Security Boundary |
|---|---|---|---|---|---|
| `PAR-FEAT-22` | Hostile-Worker OS Isolation (E18) | None (Simpul Hardening) | `subagentbridge/execution/worker_isolation.py` | `BLOCKED` | **BLOCKED (Issue #21):** Default is same-user; `AUTONOMY: OFF` enforced |
| `PAR-FEAT-23` | Authenticated Human Operator Approval | Cindy Electron UI | `subagentbridge/approval/verified_operator_authority.py` | `BLOCKED` | **BLOCKED (Issue #22):** In-process test fixtures are not WebAuthn/OIDC |
| `PAR-FEAT-24` | Cryptographic Ticket Binding | None (Simpul Hardening) | `subagentbridge/approval/trusted_authority.py` | `INTEGRATED` | HMAC-SHA256 bound to worker, task, command, workspace, and nonce |
| `PAR-FEAT-25` | Remote SSH & Device Link | Cindy `deviceLink.ts` | None | `NOT_ADOPTED` | Excluded under Issue #60 decision gate; high attack surface |
| `PAR-FEAT-26` | Desktop/Mobile Apps & Marketplace | Cindy `src/main/index.ts` | None | `NOT_ADOPTED` | Excluded under Issue #61 decision gate; Antigravity IDE is primary |

---

## Governance and Operating Protocol

- **Autonomy:** `AUTONOMY: OFF`. No unsupervised privileged modifications or silent production executions.
- **Approval Gate:** `GATE_MODE: CHAT_APPROVAL`. All commands modifying code or system state require explicit human confirmation.
- **Protected Main:** All PRs target `main` with strict GitHub Ruleset 26006115 enforcement. No force-push, no self-approval, and 4/4 passing matrix jobs (`ubuntu-latest` and `windows-latest` on Python 3.11 and 3.13) required before merge.
