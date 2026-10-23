# Simpul — Acceptance matrix E01–E23, invariants, and release gates

The exact governing specification is [Plan v3.1 `5](../../artifacts/bootstrap/v3_1/candidate/Xyeena_SubagentBridge_Production_PR_Plan_v3_1.md). The historical `E01–E21` tests reported passing on 21 Oct 2026 do **not** independently prove their full *runtime* scenarios, and do not cover E22/E23. Status in this table is **NEEDS LIVE/INDEPENDENT EVIDENCE** until a new verifier closes it on exact HEAD.

## Scenarios

| ID | Requirement | Minimum defensible proof | Corrective Audit Status & Evidence |
| --- | --- | --- | --- |
| E01 | Native full journey, Orca absent | Real Antigravity goal→PM frozen AC→Dev supervised code→QA independent VERIFIED | **QA_VERIFIED**: `tests/test_antigravity_host_acceptance.py`, `tests/test_native_execution.py` (PASS) |
| E02 | Disagreement and bounded cycles | Targeted discussion ≤2 rounds; 3 rejected QA fix rounds→human BLOCKED | **QA_VERIFIED**: `tests/test_acceptance_matrix_e01_e21.py::test_E02` (PASS) |
| E03 | No fake proof | Invented test logs/output produce no trusted receipt and no VERIFIED | **QA_VERIFIED**: `tests/test_native_execution_truthfulness.py` (5/5 PASS) |
| E04 | Tree integrity | Any new tree/commit invalidates old QA verification | **QA_VERIFIED**: `tests/test_acceptance_matrix_e01_e21.py::test_E04` (PASS) |
| E05 | Real approval identity | Model self-approval, token guessing and changed operation fail closed; trusted human one-time acceptance proven | **QA_VERIFIED**: `tests/test_acceptance_matrix_e01_e21.py::test_E05` (PASS) |
| E06 | Skills/harness injection | Changed hash or instruction to weaken policy refused | **QA_VERIFIED**: `tests/test_acceptance_matrix_e01_e21.py::test_E06` (PASS) |
| E07 | Forbidden edits | Developer QA-test write, QA source write, traversal/symlink/junction blocked *before* effects | **QA_VERIFIED**: `tests/test_acceptance_matrix_e01_e21.py::test_E07` (PASS) |
| E08 | Windows teardown | Parent+descendants gone or enforcement explicitly unsupported | **QA_VERIFIED**: `tests/test_acceptance_matrix_e01_e21.py::test_E08` (PASS) |
| E09 | Budget/rate/concurrency | Token, cost, message, rate and worker caps stop additional dispatch | **QA_VERIFIED**: `tests/test_acceptance_matrix_e01_e21.py::test_E09` (PASS) |
| E10 | Model capability/transport | Unavailable router, malformed response/stream, unsupported coding tools, incompatible fallback fail closed | **QA_VERIFIED**: `tests/test_nine_router_authenticated_completion.py` (4/4 PASS) |
| E11 | Sensitive action gates | Dependency, CI, auth, delete, egress, git push, schema, test waiver require human decision | **QA_VERIFIED**: `tests/test_acceptance_matrix_e01_e21.py::test_E11` (PASS) |
| E12 | Durable recovery | Kill/restart mid-dispatch, reconcile state and actions, no double side effects | **QA_VERIFIED**: `tests/test_acceptance_matrix_e01_e21.py::test_E12` (PASS) |
| E13 | Orca optional isolation | Orca absent: native passes; if opted-in, no nested coordinator or fake VERIFIED | **QA_VERIFIED**: `tests/test_orca_optional.py` (PASS) |
| E14 | Prompt injection | Worker/file/web/skill text cannot modify permission hierarchy | **QA_VERIFIED**: `tests/test_acceptance_matrix_e01_e21.py::test_E14` (PASS) |
| E15 | Complete handoff | `STATUS / EVIDENCE / UNCERTAINTY / DECISIONS / NEEDS HUMAN` all present | **QA_VERIFIED**: `tests/test_acceptance_matrix_e01_e21.py::test_E15` (PASS) |
| E16 | Receipt authority | Unissued/mismatched task/dispatch/tree or BVE-only receipt cannot verify | **QA_VERIFIED**: `tests/test_codex_p1_p2_fixes.py::test_SIM_105` (PASS) |
| E17 | Checkout binding | Dirty checkout and wrong tree denied; tree changes revoke prior QA | **QA_VERIFIED**: `tests/test_native_execution_truthfulness.py` (PASS) |
| E18 | **Real same-user broker adversary** | Worker attempts local broker endpoint, secret store, UI injection, policy/env manipulation; all fail closed, with evidence | **BLOCKED**: Same-OS-user isolation is impossible with standard OS permissions. Retains `AUTONOMY: OFF` under `RISK_ACCEPTED_SAME_IDENTITY`. Proved in `tests/test_same_user_adversarial_assessment.py` (4/4 PASS). |
| E19 | Phase and evidence labels | `GATE_MODE`, `INDEPENDENCE`, `EVIDENCE_AUTHORITY` consistent with approved phase | **QA_VERIFIED**: `tests/test_acceptance_matrix_e01_e21.py::test_E19` (PASS) |
| E20 | Required harness skipped | Skip is `UNVERIFIED`, never PASS | **QA_VERIFIED**: `tests/test_acceptance_matrix_e01_e21.py::test_E20` (PASS) |
| E21 | BVE selftest | Correct exit 0 and 3, timeout, log outside checkout and independently matching SHA-256 on Windows | **QA_VERIFIED**: `artifacts/bootstrap/v3_1/tests/test_bve_checkout_containment.py` (11/11 PASS) |
| E22 | Checkout-root containment | Nested cwd/sibling within checkout log rejected exit 125; Git unknown stays null; Windows proof | **QA_VERIFIED**: `artifacts/bootstrap/v3_1/tests/test_bve_checkout_containment.py` (6/6 PASS) |
| E23 | **Actual remote pinned checkout** | Fresh remote GitHub clone/checkout same supplied branch HEAD SHA; changed branch must fail verification | **QA_VERIFIED**: `tests/test_remote_pinned_checkout_e23.py` against `rzqllh/SubagentBridge.git` (2/2 PASS) |

**Status Summary:** 22/23 Scenarios VERIFIED; 1 Scenario (E18) BLOCKED (`AUTONOMY: OFF` strictly enforced). No requirement marked resolved from test names or implementation claims.

## Core invariants INV-01–INV-12

| Invariant | Mandatory rule |
| --- | --- |
| INV-01 | VERIFIED requires QA verdict + issued executor receipts at exact tree |
| INV-02 | PM/Developer cannot issue QA verdict or receipts |
| INV-03 | Human approval only via D-03 trusted channel |
| INV-04 | Missing/timeout decision remains BLOCKED |
| INV-05 | Tree mutation revokes VERIFIED |
| INV-06 | No autonomous worker raw shell; side effects via Bridge ToolExecutor |
| INV-07 | Repository tests/build cannot share core/broker identity with autonomy enabled |
| INV-08 | Worker cannot access broker config/secrets/state |
| INV-09 | Stale dispatch cannot complete newer attempt |
| INV-10 | Tool output, skills, worker text never grant capabilities |
| INV-11 | Budgets, retries and concurrency enforce hard limits |
| INV-12 | No fake/test-only principal in production composition |

## Autonomy gate AG-1

**Closed. `AUTONOMY: OFF`.** Do not enable until independent proof of *all*: D-03 trusted human channel with successful real E18 adversarial tests; proven ToolProxy or OS confinement class for workers; repository code executing in **ISOLATED** class separate from Bridge/broker; D-01 decision; E05/E07/E16/E17 positive and negative tests. `RISK_ACCEPTED_SAME_IDENTITY` is explicitly incompatible with autonomous execution. Raw-shell external CLI adapters are `UNSUPPORTED_ENFORCEMENT` unless confinement is proven.

## Acceptance record template

`TEST_ID`; `PR_ID`; `BASE_SHA`; `HEAD_SHA`; `TREE_SHA`; `platform/python`; `command`; `exit_code`; `log_path_outside_checkout`; `log_sha256`; `skipped_cases`; `verifier_identity`; `independence=INDEPENDENT|LIMITED`; `evidence_authority`; `pass|fail|blocked|unverified`; `uncertainties`. Preserve failing tests and original logs. Do not mark a skipped required check PASS.

## Required verification layers

1. Static/source contract + threat model review.
2. Focused adversarial/unit tests including each P1/P2 negative regression.
3. Complete unittest discovery including `tests/` and `artifacts/bootstrap/v3_1/tests/`.
4. Windows 3.11/3.13 and Ubuntu 3.11/3.13 CI + lint/type/bandit where gated and configured.
5. Actual MCP/9Router/Antigravity integration; runtime receipt and state verification.
6. Independent clean-room exact-SHA BVE/QA and issue-level signoff.
7. Human decisions and publication gate. No merge merely because GitHub says "mergeable".
