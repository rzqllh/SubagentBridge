# Changelog

All notable changes to SubagentBridge are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
