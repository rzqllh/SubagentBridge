# SubagentBridge Roadmap Reconciliation & Audit (Plan v3.1)

## Executive Summary

This document reconciles the repository status against Plan v3.1 and Team Rules §0A. It audits PR #2 and PR #3, and reconciles the premature claim that all 15 roadmap stages were already "VERIFIED".

Under Plan v3.1 §0A, a passing unit test suite or an implementer report does not equal QA VERIFIED. True verification requires:
1. Exact commit and tree SHA binding.
2. Independent execution with evidence logs outside the checkout.
3. Production composition root and real subsystem integration (no mocks/stubs in production path).
4. Fulfillment of all acceptance criteria in the E01–E21 matrix.

---

## 1. Pull Request Status

| PR | Branch | HEAD SHA | Status | CI Status | Classification |
|---|---|---|---|---|---|
| PR #1 | `feat/00-baseline-and-contracts` | `a387447` | DRAFT | Rejected | Historical audit record (preserved, do not rewrite or force-push) |
| PR #2 | `feat/00-baseline-recovery` | `03abf6b` | OPEN | 4/4 PASS | Compliant baseline recovery from pre-G1 parent `1a49d138` |
| PR #3 | `integrate/roadmap-v4-verified` | `1c5aed2` | OPEN | 4/4 PASS | Roadmap integration candidate + QA conflict resolution |

---

## 2. Roadmap Stage Reconciliation (PR-00 to PR-12)

Each stage is classified according to actual verified engineering status:

| Stage | Name | Unit Tested | Fully Integrated | Independently Verified | Release Ready | Status & Blocking Gaps |
|---|---|---|---|---|---|---|
| **PR-00** | Baseline & Contracts | YES | YES | YES (PR #2) | YES | Baseline recovery compliant with Plan v3.1. |
| **PR-01** | Domain Contracts & Identity | YES | PARTIAL | NO | NO | Contracts and state machine tested in isolation; not yet wired to production server. |
| **PR-02** | Durable SQLite Audit Ledger | YES | PARTIAL | NO | NO | Atomic transaction events tested; lacks persistent transactional budget ledger table. |
| **PR-03** | Fail-Closed Policy Gate | YES | PARTIAL | NO | NO | Fail-closed classification tested; operates under D-03 `GATE_MODE: CHAT_APPROVAL`. |
| **PR-03b** | Walking Skeleton & Composition | YES (fake) | NO | NO | NO | Only fake runner exists; production composition root `subagentbridge/composition.py` missing. |
| **PR-04a** | Workspace Isolation & Cleanup | YES | PARTIAL | NO | NO | Path bounds tested; Windows process-tree cleanup requires real worker integration. |
| **PR-04b** | Supervised ToolExecutor | YES | PARTIAL | NO | NO | 4MiB bounds and read enforcement tested; operates under D-01 `RISK_ACCEPTED_SAME_IDENTITY`. |
| **PR-05** | 9Router Local Adapter | YES (offline) | PARTIAL | NO | NO | Offline tests pass; requires live loopback HTTP server integration and capability negotiation. |
| **PR-06** | Coordinator & DAG Budget | YES | PARTIAL | NO | NO | In-memory budget tested; requires durable SQLite persistence across restarts. |
| **PR-07** | Trust-Aware Skills Registry | YES | PARTIAL | NO | NO | Hash validation and 2MiB bounds tested; needs dispatch integration in composition root. |
| **PR-08** | Durable Message Bus | YES | PARTIAL | NO | NO | Atomic SQLite message replay tested; needs server control-plane integration. |
| **PR-09** | QA Evidence Engine & Pins | YES | PARTIAL | NO | NO | Test pins and evidence gate tested; needs exact-tree executor receipts in coordinator. |
| **PR-10** | Antigravity MCP Control Plane | PARTIAL | NO | NO | NO | Only read snapshot mock exists; real MCP tools (`submit_goal`, `get_run`, etc.) not wired. |
| **PR-11** | Optional Orca Adapter | YES | PARTIAL | NO | NO | Native mode completely decoupled from Orca; optional Orca isolation verified. |
| **PR-12** | Production Release Verification | NO | NO | NO | NO | Requires E01–E21 acceptance testing, packaging, and public documentation overhaul. |

---

## 3. Reconciled Verdict

- **Unit tests:** 216 tests passing, 4 skipped (platform symlinks), 13 expected failures (unresolved contract probes).
- **Architecture:** Subsystems are well-designed and tested in isolation, but the production composition root and server wiring are incomplete.
- **Action plan:** Proceed with Tasks 2 through 9 to wire the production engine, persist budgets in SQLite, expose real MCP tools, execute E01–E21 tests, update docs, and build the release candidate.
