# SubagentBridge Production Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining production implementation of SubagentBridge across PR-00 to PR-12, eliminate mock/stub gaps, integrate the production composition root, enforce durable SQLite budgets, resolve all invariant security contracts, run full E01–E21 acceptance testing on Windows, update all public documentation, and prepare the release candidate.

**Architecture:** A layered, fail-closed architecture where all state changes and evidence are transactionally recorded in a WAL-mode SQLite AuditLedger. Agents (PM, Developer, QA) operate through a SupervisedCoordinator; developer operations go strictly through a bounded SupervisedToolExecutor; human approvals follow one-time operation fingerprints (`GATE_MODE: CHAT_APPROVAL`, `AUTONOMY: OFF`); QA verdicts require exact-tree binding and executor-issued receipts; local LLMs interface via a local loopback 9Router adapter.

**Tech Stack:** Python 3.11/3.13, FastMCP (`mcp>=1.28,<2`), SQLite3 (WAL mode), Ruff (`0.14.0`), mypy (`1.18.2`), Bandit (`1.9.4`), Git.

## Global Constraints
- Operating character: Xyeena Axazeela (pragmatic, analytical, assertive, evidence-first, Bahasa Indonesia communication).
- Autonomy mode: `AUTONOMY: OFF` remains in effect (`RISK_ACCEPTED_SAME_IDENTITY`, `GATE_MODE: CHAT_APPROVAL`).
- Network egress: Local loopback only (`127.0.0.1`), zero unauthorized external network egress (D-02).
- Git lifecycle: No force-push, preserve PR #1 historical audit, human-only merges on GitHub.
- Copywriting & documentation: antislop rules apply (no em dashes in prose, real verified data only).

---

### Task 1: Audit and Baseline Reconciliation
**Files:**
- Audit: PR #2, PR #3, `ROADMAP_ACCEPTANCE_MATRIX.csv`, `OPEN_TECHNICAL_BLOCKERS.md`
- Output: Initial reconciliation matrix in `docs/RECONCILIATION_AUDIT_V4.md`

- [ ] **Step 1: Document audit findings and reconcile all 15 roadmap stages**
- [ ] **Step 2: Verify git tree SHA and commit history alignment**
- [ ] **Step 3: Commit initial audit documentation**

---

### Task 2: Durable SQLite Budget Persistence (PR-02 / PR-06)
**Files:**
- Modify: `subagentbridge/storage/audit_ledger.py`
- Modify: `subagentbridge/planner/budget.py`
- Test: `tests/test_durable_budget_sqlite.py`

- [ ] **Step 1: Write failing test for SQLite-backed durable budget transactions across connection restarts**
- [ ] **Step 2: Run test to verify RED**
- [ ] **Step 3: Implement `DurableBudgetLedger` in `subagentbridge/planner/budget.py` backed by `audit_ledger` schema table**
- [ ] **Step 4: Run test to verify GREEN**
- [ ] **Step 5: Verify regression tests pass and commit**

---

### Task 3: Production Composition Root & Dependency Injection (PR-03b / PR-10 / INV-12)
**Files:**
- Create: `subagentbridge/composition.py`
- Modify: `subagentbridge/server.py`
- Test: `tests/test_composition_root.py`

- [ ] **Step 1: Write failing test for production composition root wiring and fake principal rejection**
- [ ] **Step 2: Run test to verify RED**
- [ ] **Step 3: Implement `subagentbridge/composition.py` wiring AuditLedger, DurableMessageBus, SkillRegistry, PolicyClassifier, SupervisedToolExecutor, QaEvidenceGate, NineRouterClient, SupervisedCoordinator**
- [ ] **Step 4: Run test to verify GREEN**
- [ ] **Step 5: Commit**

---

### Task 4: Real MCP Control-Plane Tools & Server Lockdown (PR-10 / INV-03)
**Files:**
- Modify: `subagentbridge/server.py`
- Modify: `subagentbridge/mcp/read_api.py`
- Test: `tests/test_mcp_production_server.py`

- [ ] **Step 1: Write failing test verifying MCP tools: `submit_goal`, `get_run`, `list_tasks`, `get_task_evidence`, `get_pending_approvals`, `reject_approval`, `get_model_usage`, `cancel_run`, and absence of `approve_action`**
- [ ] **Step 2: Run test to verify RED**
- [ ] **Step 3: Implement real production FastMCP tool bindings connected to `composition.py` and remove insecure legacy `approve_action`**
- [ ] **Step 4: Run test to verify GREEN**
- [ ] **Step 5: Commit**

---

### Task 5: AgentManager Invariant Contract Realization (INV-01 to INV-11)
**Files:**
- Modify: `subagentbridge/manager.py`
- Test: `tests/test_invariants_contract.py`
- Test: `tests/test_legacy_security_gaps.py`

- [ ] **Step 1: Write tests verifying `_manager.verify_with_executor_receipt`, `_manager.enforce_principal_role_boundary`, `_manager.reconcile_tree_invalidation`, `_manager.execute_with_skill_trust_boundary`, `_manager.durable_budget_ledger`, and `check_path_in_workspace` per-dispatch boundaries**
- [ ] **Step 2: Run tests to verify RED/failures**
- [ ] **Step 3: Implement corresponding methods on `AgentManager` delegating to `composition.py` subsystems**
- [ ] **Step 4: Run tests to verify GREEN**
- [ ] **Step 5: Commit**

---

### Task 6: Local 9Router Loopback Integration & Capability Verification (PR-05 / D-02)
**Files:**
- Test: `tests/test_nine_router_live_loopback.py`
- Modify: `subagentbridge/models/nine_router.py` (if needed)

- [ ] **Step 1: Write failing test with local loopback HTTP server fixture verifying SSE streaming, capability negotiation, token counting, and fail-closed error handling**
- [ ] **Step 2: Run test to verify RED**
- [ ] **Step 3: Ensure `NineRouterClient` completes real loopback transport cleanly without mock stubs**
- [ ] **Step 4: Run test to verify GREEN**
- [ ] **Step 5: Commit**

---

### Task 7: Full Acceptance Matrix E01–E21 Execution & Verification (PR-12)
**Files:**
- Create: `tests/test_acceptance_matrix_e01_e21.py`
- Output: `docs/ACCEPTANCE_MATRIX_E01_E21_EVIDENCE.md`

- [ ] **Step 1: Write comprehensive acceptance test suite executing scenarios E01 to E21**
- [ ] **Step 2: Run test suite with BVE capture on Windows**
- [ ] **Step 3: Verify all 21 acceptance scenarios pass with exit 0 and immutable logs**
- [ ] **Step 4: Commit**

---

### Task 8: Public Documentation Overhaul
**Files:**
- Modify: `README.md`
- Modify: `docs/API_REFERENCE.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/SECURITY.md`
- Create: `docs/INSTALLATION_QUICKSTART.md`
- Create: `docs/NINE_ROUTER_SETUP.md`
- Create: `docs/MCP_INTEGRATION.md`
- Create: `docs/TROUBLESHOOTING_FAQ.md`
- Modify: `CHANGELOG.md`
- Modify: `THIRD_PARTY_NOTICES.md`

- [ ] **Step 1: Update README.md with Windows-first quickstart, architecture, capabilities, and explicit status**
- [ ] **Step 2: Update all technical guides in docs/**
- [ ] **Step 3: Update CHANGELOG.md and THIRD_PARTY_NOTICES.md**
- [ ] **Step 4: Check documentation against antislop rules (no em dashes, verifiable claims only)**
- [ ] **Step 5: Commit**

---

### Task 9: Packaging and Release Candidate Preparation
**Files:**
- Create/Modify: `pyproject.toml`
- Output: Release artifacts in `dist/`
- Output: Checksums and release readiness report in `docs/RELEASE_CANDIDATE_V1_0_0.md`

- [ ] **Step 1: Configure build tool (`pyproject.toml` or `setup.py`) for clean reproducible packaging**
- [ ] **Step 2: Build wheel and sdist packages**
- [ ] **Step 3: Verify installation in a clean temporary virtual environment**
- [ ] **Step 4: Generate SHA-256 digests of release packages**
- [ ] **Step 5: Run full verification suite (tests, Ruff, mypy, Bandit, bootstrap)**
- [ ] **Step 6: Prepare final release candidate report and Git release tags ready for human publication**
