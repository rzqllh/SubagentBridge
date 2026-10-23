# Simpul — Prioritized actionable backlog

**Snapshot source:** 2026-10-23 GitHub [PR #2](https://github.com/rzqllh/SubagentBridge/pull/2), [PR #3](https://github.com/rzqllh/SubagentBridge/pull/3), workflow [39866552770](https://github.com/rzqllh/SubagentBridge/actions/runs/39866552770), Plan v3.1 and prior SIMPUL-01 discussion. All items below are **OPEN / NOT YET VERIFIED**, regardless of whether one implementation attempt exists.

## P0 — Merge and truth blockers

| ID | Work item / source | Acceptance evidence |
| --- | --- | --- |
| SIM-001 | Repair PR #3 `docs/API_REFERENCE.md` documentation contract: both strings `Removed from MCP exposure by P0 lockdown` and `legacy worker execution is **disabled` must remain factually correct. | `tests/test_pr00_source_doc_truth.py` and four platform jobs pass on new head. **Docs wording fix bundled with this packet; verification pending**. |
| SIM-002 | PR #2 CI: pin checkout to immutable PR head SHA; preserve `workflow_dispatch` path. [Codex P1](https://github.com/rzqllh/SubagentBridge/pull/2/files). | Runner prints tested HEAD == supplied SHA; stale-base/PR-ref change cannot alter tested tree. Needs separate gate for CI edit. |
| SIM-003 | PR #2 CI: include `artifacts/bootstrap/v3_1/tests`, not just `tests/`. [Codex P2](https://github.com/rzqllh/SubagentBridge/pull/2/files). | 12 v3.1 test cases discovered and executed Windows/Linux; no invisible skipped directory. CI gate. |
| SIM-004 | PR #2 `bve_tool.py` resolves relative executables from requested `cwd`, not helper process location. [Codex P2](https://github.com/rzqllh/SubagentBridge/pull/2/files). | Real relative executable fixture and negative path checks. |
| SIM-005 | Merge-conflict reconciliation: PR #2 vs `main` updated public docs; stage PR #3 atop accepted baseline. | No lost security docs or branding; clean diff; no force push; reviews clear. |
| SIM-006 | Exact SHA-bound independent verifier; no reuse of historical implementer report. | Detached checkout, real file hashes, BVE, exit codes, log files outside checkout, verdict. |

## P1 — Safety and functional defects (PR #3 Codex)

| ID | File / finding | Status & Acceptance Evidence |
| --- | --- | --- |
| SIM-101 | `team/coordinator.py` sticky recovery state [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | **RESOLVED**: Repeated tree updates preserve `RECOVERY_REQUIRED` until `reconcile_recovery` is called; dispatch prevented. Verified in `tests/test_codex_p1_p2_fixes.py::test_SIM_101_sticky_recovery_state`. |
| SIM-102 | `server.py` goal execution [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | **RESOLVED**: Supervised native runtime, TaskDecomposer DAG, ToolExecutor receipts, independent QA verification, and MCP `execute_run`/`execute_task` tools implemented and verified. Verified in `tests/test_native_execution.py`. |
| SIM-103 | `server.py` audit failure handling [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | **RESOLVED**: DB unwritable / ledger append failure removes run/task and returns error status fail-closed. Verified in `tests/test_codex_p1_p2_fixes.py::test_SIM_103_submit_goal_audit_failure_handling`. |
| SIM-104 | `server.py` persistence and rehydration [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | **CARRIED FORWARD TO P02**: Durable control plane run/task SQLite store rehydration scheduled in Phase P02. |
| SIM-105 | `manager.py` receipt authority [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | **RESOLVED**: `verify_with_executor_receipt` validates against `ReceiptIssuerRegistry`, verifies task/dispatch/tree binding and exit code 0. Verified in `tests/test_codex_p1_p2_fixes.py::test_SIM_105_manager_receipt_authority`. |
| SIM-106 | `planner/budget.py` ledger-scope reservations [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | **RESOLVED**: Reservation queries, counts, and table migrations scoped by `ledger_id`; approved schema migration executed. Verified in `tests/test_codex_p1_p2_fixes.py::test_SIM_106_ledger_scope_reservations`. |
| SIM-107 | `team/coordinator.py` three-fix-round bypass [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | **RESOLVED**: Count tracked internally per task, terminal `BLOCKED` after 3 failed rounds, caller cannot reset to 0. Verified in `tests/test_codex_p1_p2_fixes.py::test_SIM_107_fix_round_cap_enforcement`. |
| SIM-108 | `approval/broker.py` rejection finality [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | **RESOLVED**: Rejections consumed permanently, typecheck enforces explicit bool, approved replay rejected. Verified in `tests/test_codex_p1_p2_fixes.py::test_SIM_108_approval_rejection_finality`. |

## P2 — Isolation, correctness, replay resistance (PR #3 Codex)

| ID | File / finding | Status & Acceptance Evidence |
| --- | --- | --- |
| SIM-201 | `messaging/bus.py` ack idempotency collision [P2](https://github.com/rzqllh/SubagentBridge/pull/3/files) | **RESOLVED**: Ack idempotency key length-prefixed `f'ack:{len(message_id)}:{message_id}:{recipient_id}'` prevents delimiter ambiguity. Verified in `tests/test_codex_p1_p2_fixes.py::test_SIM_201_messaging_ack_collision`. |
| SIM-202 | `storage/audit_ledger.py` reconciliation collision [P2](https://github.com/rzqllh/SubagentBridge/pull/3/files) | **RESOLVED**: Reconciliation key length-prefixed `f"recovery:{len(session_id)}:{session_id}:{evidence_key}"` eliminates ambiguity. Verified in `tests/test_codex_p1_p2_fixes.py::test_SIM_202_recovery_reconciliation_collision`. |
| SIM-203 | `server.py` per-workspace production system [P2](https://github.com/rzqllh/SubagentBridge/pull/3/files) | **RESOLVED**: Production systems tracked per workspace root path in `_production_systems`, clean shutdown on close. Verified in `tests/test_codex_p1_p2_fixes.py::test_SIM_203_per_workspace_production_system`. |
| SIM-204 | `execution/isolation/runner.py` `extra_env` redaction bypass [P2](https://github.com/rzqllh/SubagentBridge/pull/3/files) | **RESOLVED**: Sensitive keys stripped from `extra_env` and child process environment; cross-platform process group cleanup on timeout. Verified in `tests/test_codex_p1_p2_fixes.py::test_SIM_204_runner_extra_env_redaction_bypass`. |

## P0 independent acceptance and integration

| ID | Next milestone | Evidence to close |
| --- | --- | --- |
| SIM-301 | E18 real same-user broker adversarial attack | Attempt read/call/forge broker secret, environment, UI, policy, process input; clear negative proof in isolated test setting; do not imply available while Phase A same-identity. |
| SIM-302 | E21 complete BVE selftest | Real exit 0/3, timeout, external log path, independent hash; Windows runner logs. |
| SIM-303 | E22 checkout-root containment | Nested `cwd`, sibling log within checkout rejected exit 125, Git status unavailable gives `git_dirty: null`, Windows proof. |
| SIM-304 | E23 remote immutable pinned checkout | Actual GitHub remote HEAD validation, fresh clone, exact SHA/tree, reject moved branch; no local fixture substitution. |
| SIM-305 | Live 9Router authentication | **RESOLVED**: Environment variable propagation (`NINE_ROUTER_BASE_URL`, `NINE_ROUTER_API_KEY`) to composition root eliminates 401; model discovery, capability selection, bounded retries on transient errors, and D-02 enforcement verified in `tests/test_router_skills.py`. |
| SIM-306 | Real Antigravity MCP E2E | Launch MCP stdio using venv, create goal, bounded dispatch, supervised Dev patch, independent QA receipt, exact tree-verdict, cancel/restart handling. |
| SIM-307 | Native no-Orca journey | No Orca installed or enabled and E01 complete. Orca adapter remains optional and experimental until separately verified. |
| SIM-308 | Skills and Harness actual runtime dispatch | **RESOLVED**: LocalSkillRegistry metadata discovery, SHA-256 hash pinning, tamper detection, role-based filtering, and untrusted harness loading verified in `tests/test_router_skills.py`. MCP tools `discover_models` and `list_skills` exposed. |
| SIM-309 | Security and release hardening | Adversarial injection, crash/restart, child cleanup, credential redaction, resource/budget soak, signed evidence, SBOM/licenses as applicable. |
| SIM-310 | Current independent QA and release publication | Audit exact latest SHA, all required Windows/Linux gates, no unresolved P1/P2, human approval for merge/tag/release. |


## Task contract for each implementation slice

Every SIM-XXX fix must have: (a) exact file/scope and **out of scope**, (b) reproducing regression test derived from issue, (c) fail-before/pass-after evidence where practical, (d) `HEAD_SHA` and `TREE_SHA`, (e) test command / exit / logs / skips, (f) review and QA result, (g) relevant human approval record. Never mark this document complete merely because a developer says "fixed". Use [Developer runbook](DEVELOPER_RUNBOOK.md).
