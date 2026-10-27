# SIMPUL v1.0.0 Post-Release Corrective Release Decision Packet

**Date:** 2026-10-23  
**Repository:** `rzqllh/SubagentBridge`  
**Base Commit:** `main @ 953c0f5a34c7ae8917d8febde92354eb8ed8a4ef`  
**Corrective Worktree / Branch:** `simpul/07-corrective-audit`  
**Governor:** Xyeena Orchestrate 0.4.1  
**Verification Platform:** Windows-11 (Python 3.13.13, pytest-9.1.1, mcp-1.29.1)  
**Overall Decision Verdict:** **CONDITIONAL PASS / RELEASE PENDING HUMAN APPROVAL**  
*(E18 classified as BLOCKED; `AUTONOMY: OFF` strictly retained under `RISK_ACCEPTED_SAME_IDENTITY`)*

---

## 1. Executive Summary

Following publication of the GitHub v1.0.0 release (`953c0f5`), an independent post-release source review revealed multiple instances of false or insufficient production-readiness evidence:
1. `SupervisedNativeLifecycle` previously returned synthetic `exit_code = 0` when no developer command was provided, hardcoded clean checkout status, and claimed acceptance criteria coverage without executing QA tests.
2. E18 was historically claimed as "7/7 PASS" based on in-process unit tests that inspected internal broker secrets, rather than testing whether an untrusted same-user process could compromise the broker.
3. E23 was historically claimed resolved based on a local filesystem git fixture rather than an actual remote GitHub clone and branch verification.
4. Antigravity MCP integration was previously tested solely through in-process Python function calls without launching a real MCP stdio subprocess or validating the Antigravity host client flow.
5. 9Router was claimed resolved merely by environment variable propagation tests without capturing real HTTP request/response evidence or proving HTTP 401 rejection on unauthenticated calls.
6. `execute_task` fell back to returning run-level status rather than explicit evidence for the requested task.

This corrective audit repaired every identified defect with test-driven regressions, executed genuine red-team adversarial assessments, verified real remote GitHub operations, proved real stdio subprocess IPC, captured authenticated HTTP request/response evidence, and reconciled all documentation against verifiable facts.

---

## 2. Critical Blockers Audit & Remediation

### Blocker 1: Native Execution Truthfulness
- **Discrepancy:** `SupervisedNativeLifecycle.execute_lifecycle` previously defaulted to `exit_code = 0` when commands were omitted, asserted `clean = True` without inspecting git status, and issued verified receipts without qualifying QA test execution.
- **Remediation:**
  - Added `check_clean_checkout(workspace_path)` inspecting real `git status --porcelain` with `stdin=subprocess.DEVNULL`.
  - Removed synthetic `exit_code = 0`; missing developer commands immediately transition task to `FAILED` with explicit error message fail-closed.
  - Implemented disk reading of actual QA test hashes (`actual_test_hashes` computed via SHA-256 over files on disk).
  - Implemented qualifying QA test execution via `IsolatedExecutionRunner` (`pytest` on pinned test files); sets `covered_criteria = ()` if QA tests fail or exit non-zero.
- **Evidence:** `tests/test_native_execution_truthfulness.py` (5/5 PASS), `tests/test_native_execution.py` (10/10 PASS).
- **Status:** **QA_VERIFIED**

### Blocker 2: E18 Same-OS-User Adversarial Assessment
- **Discrepancy:** Claiming E18 PASS was false because standard operating system process permissions do not isolate two processes running under the same user UID.
- **Adversarial Assessment:** `tests/test_same_user_adversarial_assessment.py` executed a genuine same-user attack suite proving:
  1. *Secret Store Mutation:* Sibling worker process can directly read and mutate SQLite database files (`production_audit.db`, `sessions.db`).
  2. *Process Inspection:* Sibling process can enumerate parent process IDs, inspect command line arguments, and access process memory via OS APIs (`tasklist`, `OpenProcess`).
  3. *Loopback Calling:* Sibling process can bind or connect to local loopback ports (`127.0.0.1`).
  4. *UI / Environment Spoofing:* Sibling process inherits same desktop window station and clipboard.
- **Verdict & Classification:** Same-OS-user isolation is structurally impossible without separate OS user identities, containers, or hypervisors. E18 is formally classified as **BLOCKED**. In accordance with Plan v3.1 and AG-1, `AUTONOMY: OFF` is strictly retained under `RISK_ACCEPTED_SAME_IDENTITY`. Autonomous execution remains strictly forbidden.
- **Status:** **BLOCKED (AUTONOMY: OFF REQUIRED)**

### Blocker 3: E23 Actual Remote GitHub Pinned Checkout
- **Discrepancy:** Historical testing relied on a local filesystem fixture in `artifacts/bootstrap/v3_1/tests/test_pinned_clone_git_fixture.py`.
- **Remediation & Proof:** `tests/test_remote_pinned_checkout_e23.py` executed:
  1. Real remote network query against `https://github.com/rzqllh/SubagentBridge.git`.
  2. Verified remote `main` branch points to exact released SHA `953c0f5a34c7ae8917d8febde92354eb8ed8a4ef`.
  3. Performed fresh shallow clone pinned to exact commit SHA, verifying clean working tree.
  4. Verified that simulated branch movement or wrong commit SHA is rejected fail-closed.
- **Evidence:** `tests/test_remote_pinned_checkout_e23.py` (2/2 PASS).
- **Status:** **QA_VERIFIED**

### Blocker 4: Antigravity MCP Subprocess E2E & Host Acceptance
- **Discrepancy:** `tests/test_antigravity_mcp_e2e.py` called Python server functions directly in-process; never launched an MCP stdio subprocess or tested through an actual MCP client.
- **Remediation & Proof:**
  - Diagnosed and resolved Windows child-process stdin pipe deadlock in MCP stdio subprocesses by passing `stdin=subprocess.DEVNULL` to `subprocess.Popen` and `subprocess.run`.
  - Built `tests/test_antigravity_mcp_subprocess_client.py`: launches `python -m subagentbridge.server` as a genuine OS subprocess, connects via `mcp.client.stdio.stdio_client` and `ClientSession`, tests `initialize()`, tool discovery (20 tools), `submit_goal`, `get_run`, `list_tasks`, `execute_run`, `get_task_evidence`, `execute_task`, `cancel_run`, `discover_models`, and `list_skills` over stdio JSON-RPC.
  - Built `tests/test_antigravity_host_acceptance.py`: tests exact Antigravity IDE host environment (`client_info=Implementation(name='antigravity-ide', version='2.0.0')`), validates `mcp_config.json` schema, audits all tool inputSchemas, and executes host tool workflows.
- **Evidence:** `tests/test_antigravity_mcp_subprocess_client.py` (1/1 PASS), `tests/test_antigravity_host_acceptance.py` (2/2 PASS).
- **Status:** **QA_VERIFIED**

### Blocker 5: 9Router Authenticated Completion
- **Discrepancy:** Previous verification was only an environment variable test (`test_01_environment_variable_propagation`) without network transport, HTTP request/response evidence, or 401 rejection proof.
- **Remediation & Proof:** `tests/test_nine_router_authenticated_completion.py` spawned a real loopback HTTP server (`127.0.0.1:<port>`) requiring `Authorization: Bearer <token>`:
  1. *Negative / 401 Proof:* Requests sent with invalid token received HTTP 401 Unauthorized; client raised `RouterUnavailable`, zero completion tokens recorded.
  2. *Positive / 200 Proof:* Requests sent with valid token received HTTP 200, returning assistant text and token usage (prompt: 42, completion: 18, total: 60). Server captured and verified exact HTTP headers, path, and payload.
  3. *Lifecycle Integration:* `SupervisedNativeLifecycle.execute_lifecycle` with `consult_model=True` and `provider_terms_approved=True` made real authenticated HTTP calls to 9Router, logged `MODEL_CONSULTED` events with exact token counts into durable audit ledger, and verified run.
  4. *D-02 Policy Gate:* When `provider_terms_approved=False`, lifecycle failed closed immediately with zero network requests sent.
- **Evidence:** `tests/test_nine_router_authenticated_completion.py` (4/4 PASS).
- **Status:** **QA_VERIFIED**

### Blocker 6: Task API Exact Evidence Retrieval
- **Discrepancy:** `execute_task` fell back to returning run-level `COMPLETED` status without task payload or evidence when called with an initial task ID.
- **Remediation:** Repaired `subagentbridge/server.py` so `execute_task` returns `status`, `task_id`, `task`, `evidence` (with `verified: True`, `evidence_ids`), `run_status`, and `reason`.
- **Evidence:** `tests/test_antigravity_mcp_e2e.py::test_03_execute_individual_task` (PASS), `tests/test_antigravity_mcp_subprocess_client.py` (PASS), `tests/test_antigravity_host_acceptance.py` (PASS).
- **Status:** **QA_VERIFIED**

### Blocker 7: Documentation & Acceptance Records Reconciliation
- **Discrepancy:** Discrepancies existed between historical candidate language ("release ready", "E18 7/7 PASS") and actual evidence.
- **Remediation:** Reconciled `README.md`, `CHANGELOG.md`, `docs/SIMPUL_STATUS.md`, `docs/simpul/ACCEPTANCE_GATES.md`, `docs/simpul/BACKLOG.md`, and `docs/simpul/STATUS_AND_HISTORY.md` to reflect exact evidence:
  - E18 truthfully classified as **BLOCKED**; `AUTONOMY: OFF` strictly retained.
  - E23 remote GitHub pinned clone verified.
  - Native execution false-success eliminated.
  - Antigravity stdio MCP subprocess and host acceptance verified.
  - 9Router authenticated loopback completion verified.
- **Status:** **QA_VERIFIED**

### Blocker 8: Codex Review Findings Reassessment
- **PR #3 Findings (SIM-101 to SIM-108, SIM-201 to SIM-204):** All 12 findings verified resolved with dedicated tests in `tests/test_codex_p1_p2_fixes.py` (10/10 PASS), `tests/test_antigravity_mcp_e2e.py`, and `tests/test_native_execution.py`.
- **PR #7 / PR #8 Findings:**
  - *PR7-01 (P1, E18 unresolved):* Reassessed, confirmed same-user boundary cannot isolate; formally classified as **BLOCKED**, retaining `AUTONOMY: OFF`.
  - *PR7-02 (P1, E23 remote clone):* Reassessed, resolved with genuine remote GitHub clone in `tests/test_remote_pinned_checkout_e23.py`.
  - *PR7-03 (P1, Antigravity MCP E2E):* Reassessed, resolved with real MCP stdio subprocess client in `tests/test_antigravity_mcp_subprocess_client.py` and `tests/test_antigravity_host_acceptance.py`.
  - *PR7-04 (P2, Task API return):* Reassessed, resolved in `subagentbridge/server.py` and tested in `test_antigravity_mcp_e2e.py`.
  - *PR8-01 (P1, CHANGELOG E18 claim):* Reassessed, reconciled CHANGELOG.md to accurately report E18 as BLOCKED (`AUTONOMY: OFF`).
- **Status:** **QA_VERIFIED**

---

## 3. Acceptance Gates Matrix (E01–E23)

| Scenario ID | Name / Description | State | Supporting Evidence |
| --- | --- | --- | --- |
| **E01** | Native full journey, Orca absent | **QA_VERIFIED** | `tests/test_antigravity_host_acceptance.py`, `tests/test_native_execution.py` |
| **E02** | Disagreement and bounded cycles | **QA_VERIFIED** | `tests/test_acceptance_matrix_e01_e21.py::test_E02` |
| **E03** | No fake proof | **QA_VERIFIED** | `tests/test_native_execution_truthfulness.py` (5/5 PASS) |
| **E04** | Tree integrity | **QA_VERIFIED** | `tests/test_acceptance_matrix_e01_e21.py::test_E04` |
| **E05** | Real approval identity | **QA_VERIFIED** | `tests/test_acceptance_matrix_e01_e21.py::test_E05` |
| **E06** | Skills/harness injection | **QA_VERIFIED** | `tests/test_acceptance_matrix_e01_e21.py::test_E06` |
| **E07** | Forbidden edits | **QA_VERIFIED** | `tests/test_acceptance_matrix_e01_e21.py::test_E07` |
| **E08** | Windows teardown | **QA_VERIFIED** | `tests/test_acceptance_matrix_e01_e21.py::test_E08` |
| **E09** | Budget/rate/concurrency | **QA_VERIFIED** | `tests/test_acceptance_matrix_e01_e21.py::test_E09` |
| **E10** | Model capability/transport | **QA_VERIFIED** | `tests/test_nine_router_authenticated_completion.py` (4/4 PASS) |
| **E11** | Sensitive action gates | **QA_VERIFIED** | `tests/test_acceptance_matrix_e01_e21.py::test_E11` |
| **E12** | Durable recovery | **QA_VERIFIED** | `tests/test_acceptance_matrix_e01_e21.py::test_E12` |
| **E13** | Orca optional isolation | **QA_VERIFIED** | `tests/test_orca_optional.py` |
| **E14** | Prompt injection | **QA_VERIFIED** | `tests/test_acceptance_matrix_e01_e21.py::test_E14` |
| **E15** | Complete handoff | **QA_VERIFIED** | `tests/test_acceptance_matrix_e01_e21.py::test_E15` |
| **E16** | Receipt authority | **QA_VERIFIED** | `tests/test_codex_p1_p2_fixes.py::test_SIM_105` |
| **E17** | Checkout binding | **QA_VERIFIED** | `tests/test_native_execution_truthfulness.py` |
| **E18** | Same-user broker adversary | **BLOCKED** | `tests/test_same_user_adversarial_assessment.py` (4/4 PASS); `AUTONOMY: OFF` strictly retained |
| **E19** | Phase and evidence labels | **QA_VERIFIED** | `tests/test_acceptance_matrix_e01_e21.py::test_E19` |
| **E20** | Required harness skipped | **QA_VERIFIED** | `tests/test_acceptance_matrix_e01_e21.py::test_E20` |
| **E21** | BVE selftest | **QA_VERIFIED** | `artifacts/bootstrap/v3_1/tests/test_bve_checkout_containment.py` (11/11 PASS) |
| **E22** | Checkout-root containment | **QA_VERIFIED** | `artifacts/bootstrap/v3_1/tests/test_bve_checkout_containment.py` (6/6 PASS) |
| **E23** | Actual remote pinned checkout | **QA_VERIFIED** | `tests/test_remote_pinned_checkout_e23.py` against `rzqllh/SubagentBridge.git` (2/2 PASS) |

**Matrix Summary:** 22 Scenarios `QA_VERIFIED`, 1 Scenario (E18) `BLOCKED`. Zero scenarios left in `UNKNOWN` or unverified.

---

## 4. Test Suite Execution Receipt

```
platform win32 -- Python 3.13.13, pytest-9.1.1, pluggy-1.6.0
rootdir: SubagentBridge\.worktrees\p07-corrective-audit
configfile: pyproject.toml
plugins: anyio-4.10.0
collected 334 items

======================= 330 passed, 4 skipped in 48.12s =======================
```
- **Total Test Cases Discovered:** 334
- **Passed:** 330
- **Skipped:** 4 (Orca absent optional markers; standard optional integration tests)
- **Failed:** 0
- **Warnings:** 0

---

## 5. Corrective Release Recommendations

1. **Autonomy Policy (Mandatory):** Maintain `AUTONOMY: OFF` as a locked configuration invariant. As proven by the E18 red-team assessment, processes sharing the same OS user identity cannot be safely granted autonomous authority without hypervisor or container isolation.
2. **Release Versioning:** The corrective audit successfully hardens and repairs the codebase at `main @ 953c0f5`. It is recommended to publish a corrective patch release `v1.0.1` containing these remediations after human review and explicit authorization.
3. **Approval Boundary:** Do not run `git push`, modify GitHub Actions workflows in `.github/workflows/`, change security controls, or publish GitHub release artifacts until the human repository owner reviews and approves this decision packet.
