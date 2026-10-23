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
| SIM-301 | E18 real same-user broker adversarial attack | **BLOCKED**: Genuine same-OS-user adversarial assessment in `tests/test_same_user_adversarial_assessment.py` proves processes under same OS UID can inspect memory/OS APIs, touch local databases, and access loopback. Full isolation requires separate OS identity/container/VM. Formally classified as `BLOCKED`, retaining `AUTONOMY: OFF` under `RISK_ACCEPTED_SAME_IDENTITY`. |
| SIM-302 | E21 complete BVE selftest | **RESOLVED**: Bootstrap Verification Engine selftest executed on Windows-11 Python 3.13: exit codes 0/3/124/125/127, timeout enforcement, log isolation outside checkout, and SHA-256 match verified (11/11 PASS). |
| SIM-303 | E22 checkout-root containment | **RESOLVED**: Verified explicit root and autodetected git root reject sibling logs within checkout with exit code 125, relative executable resolution in `artifacts/bootstrap/v3_1/tests/test_bve_checkout_containment.py` (6/6 PASS). |
| SIM-304 | E23 remote immutable pinned checkout | **RESOLVED**: Validated genuine remote GitHub clone and branch movement rejection against `https://github.com/rzqllh/SubagentBridge.git` at exact SHA `953c0f5` in `tests/test_remote_pinned_checkout_e23.py` (2/2 PASS). |
| SIM-305 | Live 9Router authentication | **RESOLVED**: Verified authenticated local-router completion with real HTTP request/response evidence in `tests/test_nine_router_authenticated_completion.py`: HTTP 401 on missing/invalid token, HTTP 200 with exact payload and token usage on valid token, lifecycle integration with audit ledger `MODEL_CONSULTED` events, and D-02 fail-closed enforcement (4/4 PASS). |
| SIM-306 | Real Antigravity MCP E2E | **RESOLVED**: Genuine MCP stdio subprocess client tested over protocol in `tests/test_antigravity_mcp_subprocess_client.py` and dedicated Antigravity host acceptance in `tests/test_antigravity_host_acceptance.py`. Resolved Windows child-process stdin pipe deadlock by passing `stdin=subprocess.DEVNULL` (3/3 PASS). |
| SIM-307 | Native no-Orca journey | **RESOLVED**: Native lifecycle executes end-to-end without Orca installed; verified across all phases. |
| SIM-308 | Skills and Harness actual runtime dispatch | **RESOLVED**: LocalSkillRegistry metadata discovery, SHA-256 hash pinning, tamper detection, role-based filtering, and untrusted harness loading verified in `tests/test_router_skills.py`. MCP tools `discover_models` and `list_skills` exposed. |
| SIM-309 | Security and release hardening | **RESOLVED**: Validated clean packaging (sdist and wheel), clean environment installation verification, Windows process cleanup, credential redaction, and release SHA256 checksum manifest generation in Phase P06. |
| SIM-310 | Current independent QA and release publication | **CORRECTIVE AUDIT COMPLETED**: Corrective audit across Windows (330 passed, 4 skipped, 0 warnings). Discrepancies repaired, false claims eliminated, E18 truthfully classified as BLOCKED (`AUTONOMY: OFF`), and corrective decision packet produced. |

## Post-PR #7 / PR #8 Codex Review Reassessment

| Review ID | Finding / Surface | Reassessment Verdict & Defensible Evidence |
| --- | --- | --- |
| PR7-01 (P1) | `docs/simpul/BACKLOG.md`: Keep E18 unresolved | **CONFIRMED & BLOCKED**: Real same-OS-user red-team assessment in `tests/test_same_user_adversarial_assessment.py` proves same-UID process isolation is impossible with standard OS permissions. E18 is formally classified as **BLOCKED**, retaining `AUTONOMY: OFF` under `RISK_ACCEPTED_SAME_IDENTITY`. |
| PR7-02 (P1) | `docs/simpul/BACKLOG.md`: Do not close E23 with local Git fixture | **REASSESSED & RESOLVED**: Local fixture replaced with genuine remote GitHub clone and branch-movement rejection in `tests/test_remote_pinned_checkout_e23.py` testing `https://github.com/rzqllh/SubagentBridge.git` at exact HEAD SHA `953c0f5`. |
| PR7-03 (P1) | `docs/simpul/BACKLOG.md`: Keep Antigravity MCP E2E pending | **REASSESSED & RESOLVED**: Real MCP stdio subprocess launched and tested via `stdio_client` and `ClientSession` in `tests/test_antigravity_mcp_subprocess_client.py`, and separate Antigravity IDE host acceptance tested in `tests/test_antigravity_host_acceptance.py`. |
| PR7-04 (P2) | `tests/test_antigravity_mcp_e2e.py`: Require `execute_task` to return requested task | **REASSESSED & RESOLVED**: Fixed in `subagentbridge/server.py` so `execute_task` returns explicit evidence and requested task payload. Verified in `tests/test_antigravity_mcp_e2e.py` and `tests/test_antigravity_mcp_subprocess_client.py`. |
| PR8-01 (P1) | `CHANGELOG.md`: Keep E18 open in release notes | **CONFIRMED & RECONCILED**: CHANGELOG.md updated to truthfully state E18 is BLOCKED (`AUTONOMY: OFF`) rather than claiming unconditional 7/7 PASS. |




## Task contract for each implementation slice

Every SIM-XXX fix must have: (a) exact file/scope and **out of scope**, (b) reproducing regression test derived from issue, (c) fail-before/pass-after evidence where practical, (d) `HEAD_SHA` and `TREE_SHA`, (e) test command / exit / logs / skips, (f) review and QA result, (g) relevant human approval record. Never mark this document complete merely because a developer says "fixed". Use [Developer runbook](DEVELOPER_RUNBOOK.md).
