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

| ID | File / finding | Required correction and acceptance |
| --- | --- | --- |
| SIM-101 | `team/coordinator.py` sticky recovery state [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | Repeated tree updates never clear `RECOVERY_REQUIRED` or start new dispatch before reconciliation; regression test. |
| SIM-102 | `server.py` goal execution [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | `submit_goal` schedules supervised real PM/Dev/QA lifecycle or truthfully exposes a different API. No eternally pending synthetic goal; end-to-end test. |
| SIM-103 | `server.py` audit failure handling [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | DB unwritable / ledger append failure returns error, with no orphan `SUBMITTED` state. |
| SIM-104 | `server.py` persistence and rehydration [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | Run/task state survives restart and has no duplicate workers/side effects after recovery. |
| SIM-105 | `manager.py` receipt authority [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | Arbitrary string receipt cannot verify; issuer, task, dispatch, tree, QA verdict checked. |
| SIM-106 | `planner/budget.py` ledger-scope reservations [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | Reservation identity/query/refund scoped by `ledger_id`; two-ledger cross-contamination and concurrency tests. May require schema migration → human approval. |
| SIM-107 | `team/coordinator.py` three-fix-round bypass [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | Count persisted per task, reaches terminal `BLOCKED` after cap, caller cannot reset to 0 and bypass. |
| SIM-108 | `approval/broker.py` rejection finality [P1](https://github.com/rzqllh/SubagentBridge/pull/3/files) | Rejected action remains rejected; `approved=True` replay forbidden regardless of token. Human auth/secret work needs gate. |

## P2 — Isolation, correctness, replay resistance (PR #3 Codex)

| ID | File / finding | Acceptance |
| --- | --- | --- |
| SIM-201 | `messaging/bus.py` ack idempotency collision [P2](https://github.com/rzqllh/SubagentBridge/pull/3/files) | (`a:b`, `c`) and (`a`, `b:c`) must form distinct keys; replay semantics remain correct. |
| SIM-202 | `storage/audit_ledger.py` reconciliation collision [P2](https://github.com/rzqllh/SubagentBridge/pull/3/files) | Independently reconcile ambiguous colon-containing pairs; second cannot get `ReplayConflict` from first. |
| SIM-203 | `server.py` per-workspace production system [P2](https://github.com/rzqllh/SubagentBridge/pull/3/files) | Two workspace roots cannot share foreign executor, pinset, audit or resources; cleanup on close. |
| SIM-204 | `execution/isolation/runner.py` `extra_env` redaction bypass [P2](https://github.com/rzqllh/SubagentBridge/pull/3/files) | Sensitive keys rejected/scrubbed even if caller supplies them in `extra_env`; child does not see broker/OpenAI/etc keys. |

## P0 independent acceptance and integration

| ID | Next milestone | Evidence to close |
| --- | --- | --- |
| SIM-301 | E18 real same-user broker adversarial attack | Attempt read/call/forge broker secret, environment, UI, policy, process input; clear negative proof in isolated test setting; do not imply available while Phase A same-identity. |
| SIM-302 | E21 complete BVE selftest | Real exit 0/3, timeout, external log path, independent hash; Windows runner logs. |
| SIM-303 | E22 checkout-root containment | Nested `cwd`, sibling log within checkout rejected exit 125, Git status unavailable gives `git_dirty: null`, Windows proof. |
| SIM-304 | E23 remote immutable pinned checkout | Actual GitHub remote HEAD validation, fresh clone, exact SHA/tree, reject moved branch; no local fixture substitution. |
| SIM-305 | Live 9Router authentication | Resolve HTTP 401 with **no credentials in docs/logs**; discovered model capability, budget, real authorized completion, usage. External provider terms D-02 approval separate. |
| SIM-306 | Real Antigravity MCP E2E | Launch MCP stdio using venv, create goal, bounded dispatch, supervised Dev patch, independent QA receipt, exact tree-verdict, cancel/restart handling. |
| SIM-307 | Native no-Orca journey | No Orca installed or enabled and E01 complete. Orca adapter remains optional and experimental until separately verified. |
| SIM-308 | Skills and Harness actual runtime dispatch | Metadata scan only initially; SHA/path/allowlist, role relevance, lazy loading, tamper denial; harness is **untrusted content**, never an enforcement boundary. |
| SIM-309 | Security and release hardening | Adversarial injection, crash/restart, child cleanup, credential redaction, resource/budget soak, signed evidence, SBOM/licenses as applicable. |
| SIM-310 | Current independent QA and release publication | Audit exact latest SHA, all required Windows/Linux gates, no unresolved P1/P2, human approval for merge/tag/release. |

## Task contract for each implementation slice

Every SIM-XXX fix must have: (a) exact file/scope and **out of scope**, (b) reproducing regression test derived from issue, (c) fail-before/pass-after evidence where practical, (d) `HEAD_SHA` and `TREE_SHA`, (e) test command / exit / logs / skips, (f) review and QA result, (g) relevant human approval record. Never mark this document complete merely because a developer says "fixed". Use [Developer runbook](DEVELOPER_RUNBOOK.md).
