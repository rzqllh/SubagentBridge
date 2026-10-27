# Changelog

> **23 October 2026 — Simpul v1.0.0 release reality & governance boundaries:** Simpul v1.0.0 is published on GitHub Releases (tag `v1.0.0`, commit `953c0f5`). Current governance strictly operates under `AUTONOMY: OFF` and `GATE_MODE: CHAT_APPROVAL`. In accordance with genuine adversarial evidence (E18), same-user OS process isolation is recognized as a documented residual boundary (`RISK_ACCEPTED_SAME_IDENTITY`), not OS-level containerization. See [SIMPUL_STATUS.md](docs/SIMPUL_STATUS.md). The Python package name remains `subagentbridge`.

All notable changes to Simpul (formerly SubagentBridge) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — v1.1.2 P0 approval-gate security correction

This security patch is not published until CI/review and a SHA-gated release pass.

- Remove `approve_command` from the MCP tool registry: model callers cannot grant their own privileged command approval.
- Preserve the legacy Python callable only as an unconditional `BLOCKED` response; `approver` and `auth_token` parameters are never trusted.
- Add tests that enumerate actual registered MCP tools, inspect decorator removal, and prove forged approvals cannot mutate pending states or the execution gate.
- Breaking safety restriction: privileged commands remain BLOCKED until an independently authenticated operator approval channel is deployed. **Do not substitute chat/model text for human identity.**
- E18 worker OS confinement and production out-of-band human approval remain BLOCKED; this patch is an emergency default-deny correction, not enterprise certification.

## [1.1.1] - 2026-10-27

**Published:** [v1.1.1](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.1) from `861f040dc12c33da681331e454ef41299f2dc70b`. PR #19 CI 4/4 PASS, release workflow 40444832484 SUCCESS. Contains wheel, source archive and SHA256 checksum manifest. Independent enterprise security certification remains outstanding.

### Fixed
- Serialize all SQLite TeamStore readers and writers sharing one connection; acquire an immediate database write reservation before cross-process resume claims.
- Require the effective worker workspace to match both execution-ticket and human-approval action binding, including workers without Git worktrees.
- Obtain approval for all outstanding multi-step commands before beginning any side effects; reuse pending actions but request a new human approval after a ticket is consumed.
- Fail closed when previously observed side effects cannot be reconciled against a trusted checkpoint instead of promising exactly-once execution.
- Launch child workers with Python `-P` safe-path, preventing workspace-local `subagentbridge` package shadowing of the trusted worker entrypoint.
- Add runtime regressions for concurrent readers/writers, competing resume claims, workspace binding, approval renewal, preflight, default-deny and malicious package shadowing.

### Security limitations
- E18 same-user process confinement remains **BLOCKED**. Worker subprocesses are not an adversarial OS security sandbox.
- Interactive production out-of-band human authentication is **not** implemented by the test broker.
- The candidate should be treated as a **supervised patch**, not independently enterprise security-certified.
- Cindy reference attribution and compatibility semantics remain unchanged.

## [1.1.0] - 2026-10-27

**Published:** [v1.1.0](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.0) from `a29f0d9`. The `v1.0.0` tag does not contain these changes.

### Added
- Native Simpul `AgentTeam`, `AgentSession`, `TeamStore`, `TeamManager` contracts.
- Real child-process worker IPC, lead/worker coordination, durable SQLite dispatch queue, inter-agent channels, priority/steering/cancellation, auditable handoff evidence and checkpointed recovery.
- Capability-aware adapters for native and other supported host categories, with unsupported integrations reported explicitly.
- Per-worker Git worktrees with safe ownership and dirty-worktree protection.
- Migration from legacy `orca_*` SQL tables to `simpul_*`, logical pre-migration backup and compatibility read-only views.

### Fixed
- Dispatch deduplication is now serialized across connections; failed/cancelled retries cannot mask an active successor.
- Cancellation cannot overwrite a terminal `COMPLETED` task.
- Migration preserves each optional queue column individually and uses parameterized SQL rather than interpolated query text.
- Recovery refuses orphaned live worker PIDs without owned IPC; human command approvals pause rather than self-approve.
- Handoff evidence is checked for real file existence, hashes, execution receipts and transaction-safe uniqueness.

### Security & compatibility
- `AUTONOMY: OFF`, `GATE_MODE: CHAT_APPROVAL`, and the E18 same-user isolation limitation remain.
- Older `Orca*` Python aliases and read-only compatibility views remain temporarily supported.
- Cindy attribution is retained in `THIRD_PARTY_NOTICES.md`. This is an independent implementation, not a fork.
- Release v1.1.0 includes wheel, sdist and SHA256 checksum manifest.

## [1.0.0] - 2026-10-23

### Production Release
- **Production Release v1.0.0**: Simpul (SubagentBridge) production release, passing mandatory acceptance gates E01–E17, E19–E23, core invariants INV-01–INV-12, with gate E18 explicitly blocked under documented residual risk `RISK_ACCEPTED_SAME_IDENTITY` (`AUTONOMY: OFF`, `GATE_MODE: CHAT_APPROVAL`).

### Added & Hardened
- **Post-Release Corrective Audit (Phase P07)**:
  - **Native Execution Truthfulness**: Eliminated synthetic exit code 0 and fabricated criteria coverage; added real `check_clean_checkout` (`git status --porcelain`), disk hash calculation of QA test files, and qualifying QA test execution before issuing verified receipts (`tests/test_native_execution_truthfulness.py`, 5/5 PASS).
  - **E18 Same-User Adversarial Assessment**: Executed genuine same-user red-team assessment (`tests/test_same_user_adversarial_assessment.py`, 4/4 PASS). Proved standard OS permissions cannot isolate processes under the same user UID from inspecting memory, accessing DB files, or calling local loopback. Formally classified E18 as **BLOCKED** and strictly retained `AUTONOMY: OFF` under `RISK_ACCEPTED_SAME_IDENTITY`.
  - **E23 Remote Pinned Checkout**: Validated genuine remote GitHub clone and branch-movement rejection against `https://github.com/rzqllh/SubagentBridge.git` at exact commit SHA `953c0f5a34c7ae8917d8febde92354eb8ed8a4ef` (`tests/test_remote_pinned_checkout_e23.py`, 2/2 PASS).
  - **Antigravity E2E Subprocess & Host Acceptance**: Verified real MCP stdio subprocess client communication (`tests/test_antigravity_mcp_subprocess_client.py`) and dedicated Antigravity IDE host acceptance (`tests/test_antigravity_host_acceptance.py`). Resolved Windows child process stdin pipe deadlock by passing `stdin=subprocess.DEVNULL`.
  - **9Router Authenticated Completion**: Proved authenticated local-router completion with real HTTP request/response evidence (`tests/test_nine_router_authenticated_completion.py`): verified HTTP 401 rejection on invalid tokens, HTTP 200 completion on valid tokens, and audit ledger `MODEL_CONSULTED` token tracking.
  - **Task API Evidence Integrity**: Ensured `execute_task` returns explicit evidence and requested task payload.
- **Baseline Recovery & CI Pinning (Phase P00 / PR #2)**: Pinned CI checkout to exact immutable PR commit HEAD, integrated v3.1 bootstrap tests into discovery, and resolved BVE relative executable resolution.
- **Codex Safety & Integrity Resolutions (Phase P01 / PR #3)**: Resolved all 12 open P1/P2 Codex review findings with dedicated regression tests. Enforced approval rejection finality, replay resistance, sticky recovery states, ledger-scoped reservations, and 3-round fix limits.
- **Durable Control Plane (Phase P02 / PR #4)**: Implemented persistent SQLite store for runs, tasks, and dispatches; crash/restart rehydration restoring active task states; and honest MCP evidence reporting preventing fabricated `verified` claims.
- **Supervised Native Lifecycle (Phase P03 / PR #5)**: Implemented full supervised native execution: `submit_goal -> PM task decomposition -> frozen acceptance criteria -> controlled developer dispatch -> ToolExecutor -> trustworthy receipts -> independent QA -> final result`. Added MCP `execute_run` and `execute_task` tools.
- **Model Routing & Pinned Skills (Phase P04 / PR #6)**: Resolved HTTP 401 root cause via environment variable propagation into composition root; added truthful capability discovery and selection; bounded retries on transient router errors; safe read-only tool dispatch; SHA-256 hash pinning, tamper detection, role filtering, and untrusted prompt harness loading.
- **Antigravity QA & E01–E23 Gates (Phase P05 / PR #7)**: End-to-end FastMCP verification; Windows BVE selftest (E21, 11/11 PASS); checkout-root containment (E22, 6/6 PASS); real broker adversarial unit checks; E18 classified as BLOCKED (`AUTONOMY: OFF` retained); and remote pinned checkout (E23).

---

## [1.0.0-rc1] - 2026-10-21

### Added
- **Domain Contracts & State Machine (PR-01):** Immutable dataclass contracts for `Run`, `Task`, `Dispatch`, `Approval`, `Evidence`, `ExecutorReceipt`, and `QaVerdict` with positive attempt and schema version validation.
- **Durable Persistence & Budget Ledger (PR-02, PR-06):** SQLite WAL-mode audit ledger and `DurableBudgetLedger` with `BEGIN IMMEDIATE` transaction serialization, active worker concurrency tracking, and persistent token and microunit reservation enforcement.
- **Human Approval Broker (PR-03, D-03):** Isolated `ApprovalBroker` implementing one-time approval tokens, operation fingerprinting, and replay prevention. Removed model-callable approval tools from the MCP surface.
- **Policy Classification Engine (PR-03, PR-08):** Conservative `classify()` function identifying sensitive triggers (dependencies, git push, credential modifications, test mutations) and requiring human gates.
- **Supervised Tool Executor & Confinement (PR-04b, D-01):** `SupervisedReadOnlyExecutor` and `IsolatedExecutionRunner` with environment variable scrubbing, Windows process-tree termination, and output SHA hashing.
- **Local 9Router Loopback Transport (PR-05, D-02):** Capability negotiation table failing closed on unsupported capabilities, strictly bound to `127.0.0.1` loopback transport with zero unauthorized egress.
- **Skills Registry (PR-07):** `LocalSkillRegistry` with SHA-256 cryptographic hash pinning, path traversal blocking, and junction denial.
- **Independent QA Evidence Gate (PR-09):** `QaEvidenceGate` enforcing frozen acceptance criteria verification, clean Git checkout check, tree SHA binding, and 3-round disagreement loop termination.
- **Production MCP Server & Composition Root (PR-10):** Registered production tools `submit_goal`, `get_run`, `list_tasks`, `get_task_evidence`, `get_pending_approvals`, `reject_approval`, `get_model_usage`, and `cancel_run`.
- **Native Independence & Optional Orca (PR-11):** Fully native execution without Orca dependency, plus safe probe seam.
- **Acceptance Matrix Verification (PR-12):** Complete automated test coverage for Plan v3.1 criteria E01 through E21 with 250 test suite discovery passing cleanly.

### Security
- Set `AUTONOMY: OFF` by default across all subsystems.
- Realized all 12 core invariant contracts (INV-01 through INV-12).
- Locked down legacy worker entry points and compatibility callables.
