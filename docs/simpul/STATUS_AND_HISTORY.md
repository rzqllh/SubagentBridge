# Simpul — Status, timeline and unresolved evidence

**Observed baseline:** 2026-10-23; source snapshot PR #3 `a9840e5af80f18c43db88a01f7a2413fc559f891`. The timestamps below refer to recorded events/reports, not assertions of current completion.

## Actual remote state when packet was prepared

| GitHub item | Target/source | Observed state | Consequence |
| --- | --- | --- | --- |
| `main` | historical imported baseline; public docs updated | Not RC runtime | Never claim main has PR #3 capabilities |
| [PR #1](https://github.com/rzqllh/SubagentBridge/pull/1) | obsolete draft baseline | Draft/open, historical QA rejected due approval-order issue | Preserve audit; do not force-push/rewrite |
| [PR #2](https://github.com/rzqllh/SubagentBridge/pull/2) | `feat/00-baseline-recovery` → `main`, HEAD `03abf6b9…` | Open, merge conflict, 3 unresolved Codex threads | Repair baseline and independently verify before merge |
| [PR #3](https://github.com/rzqllh/SubagentBridge/pull/3) | `integrate/roadmap-v4-verified` → `feat/00-baseline-recovery` | Open; no merge conflict with its current base; 12 unresolved Codex threads, 4 CI jobs failed | **Not merge-ready**; likely new PR head after this documentation packet |
| `1.0.0rc1` | package/source metadata and historical wheel/sdist report | Candidate only; no GitHub release/merge verified | Do not publish/announce readiness |

### Why the four red CI jobs were red

At [workflow run 39866552770](https://github.com/rzqllh/SubagentBridge/actions/runs/39866552770) (candidate commit `a9840e5`), all four Windows/Ubuntu Python 3.11/3.13 jobs failed at `test_pr00_source_doc_truth.CurrentP0DocumentationContract.test_live_docs_no_old_approval_default_claim`, because the earlier docs rewrite removed **exact required wording** from `docs/API_REFERENCE.md`. Log shows 250 tests, one failing test (plus four skips). This was introduced by a documentation refresh, **not** four independent runtime regressions. A targeted wording repair is included with this packet, but must be validated by *new* CI; never promote old green results to new HEAD.

### Historical checkpoints and interpretation

- **2026-10-19–20:** Plan v3.1 bootstrap, DP-00/DP-VERIFY and independent PR-00 verification. Original draft PR #1 was **REJECTED/UNVERIFIED** due approval-order G1 concerns, regardless of some passing tests.
- **2026-10-21:** PR #2 compliant baseline recovery proposed. Candidate PR #3 reported E01–E21 tests and a 250-test suite (246 pass / 4 skip), plus ruff/mypy/bandit and cross-platform CI. These reports are **bound to earlier commits**, not unconditional release signoff. Codex found substantive runtime/security concerns.
- **2026-10-22:** SIMPUL-01 reconciliation discussion: a claimed set of source edits contradicted identical HEAD/tree and clean worktree; classification **CHANGES_REQUIRED**, demanding real diff/commit/evidence. E18 token rejection ≠ same-user red-team; E21 trivial hash checks ≠ full BVE; E22 fixture ≠ E23 actual remote pinned clone.
- **2026-10-23:** Public branding/documentation updated to Simpul; technical `subagentbridge` identifiers retained. Documentation-only commits caused doc-contract CI regression. At snapshot: 12 open PR #3 review threads (8 P1, 4 P2) and 3 open PR #2 threads (1 P1, 2 P2). New docs must not obscure these blockers.

## Facts vs claims

**Present in candidate source:** typed contracts, SQLite audit/budget/messaging modules, approval broker, policy, local skill registry, tool executor utilities, QA evidence gate, coordinator module and stdio MCP facade.

**Not demonstrated as a production full journey:** `server.submit_goal` only creates in-memory `SUBMITTED` run and `PENDING` task; composition root returns `coordinator=None`. No proven real PM→Dev→QA dispatch, restart recovery of MCP run/task maps, safe same-user broker boundary, or authenticated live 9Router completion. A reported HTTP 401 prevented the earlier live completion attempt. Real Antigravity MCP flow requires a clean independently observed smoke.

## Evidence status vocabulary

- `CODE_PRESENT`: file/function exists; may be unintegrated.
- `UNIT_TESTED`: unit test log for an exact revision exists; not OS/security certification.
- `INTEGRATED`: proven through actual control-plane path.
- `QA_VERIFIED`: independent tester attests exact SHA/tree and all required acceptance/evidence.
- `BLOCKED`: unresolved safety/gate/human decision; no waiver by implication.
- `HISTORICAL`: report from a previous revision.
- `UNKNOWN`: must investigate; never convert to green.
