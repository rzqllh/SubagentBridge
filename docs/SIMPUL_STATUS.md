# Simpul — Project status and evidence boundaries

**As of:** 23 October 2026  
**Public name:** Simpul (formerly SubagentBridge)  
**Repository:** `rzqllh/SubagentBridge` (repository has not been renamed)  
**Compatibility:** `subagentbridge` imports/distribution/CLI, `SUBAGENTBRIDGE_*` variable namespace

## Source, branch and publication

- `main` contains the old imported September 2026 baseline.
- [PR #2](https://github.com/rzqllh/SubagentBridge/pull/2) contains PR-00 baseline safety recovery; open, unmerged.
- [PR #3](https://github.com/rzqllh/SubagentBridge/pull/3), branch `integrate/roadmap-v4-verified`, baseline `44d70b5f05836a867978dcadb166bd1122943a3b`, contains the candidate implementations; open and unmerged.
- Project metadata declares `1.0.0rc1`, but no merge, GitHub release or published package is confirmed.

## What the candidate code actually provides

A Python composition root wires SQLite audit and budget layers, a message bus, skill registry, policy classifier, supervised read-only executor, identity and receipt registries, QA evidence gate and local 9Router client. The server exposes MCP stdio tools. Its `submit_goal` handler currently creates an in-memory run with a pending task and appends a `GOAL_SUBMITTED` event; **it does not start worker execution**. `get_task_evidence` reads stored task metadata, rather than returning independently proven receipt bodies.

## Verification scope and corrective audit status

The 23 October Post-Release Corrective Audit executed 334 tests (330 passed, 4 skipped, 0 warnings) across the full Windows test matrix:

- **E18:** Proved via genuine red-team assessment (`tests/test_same_user_adversarial_assessment.py`) that same-OS-user isolation is impossible under standard OS permissions. Formally classified as **BLOCKED**; `AUTONOMY: OFF` strictly retained under `RISK_ACCEPTED_SAME_IDENTITY`.
- **E22:** Checkout-root containment verified in `artifacts/bootstrap/v3_1/tests/test_bve_checkout_containment.py` (6/6 PASS).
- **E23:** Remote pinned Git clone and branch-movement rejection verified against `https://github.com/rzqllh/SubagentBridge.git` at exact commit `953c0f5` in `tests/test_remote_pinned_checkout_e23.py` (2/2 PASS).
- **9Router:** Authenticated local completion proved with real request/response evidence in `tests/test_nine_router_authenticated_completion.py` (HTTP 401 on invalid token, HTTP 200 on valid token, ledger token accounting, D-02 fail-closed enforcement; 4/4 PASS).
- **Integration:** Real end-to-end Antigravity MCP PM/Developer/QA workflow verified over genuine stdio subprocess (`tests/test_antigravity_mcp_subprocess_client.py`) and Antigravity IDE host acceptance (`tests/test_antigravity_host_acceptance.py`).
- **Release:** Corrective audit completed; decision packet prepared. Human approval required before merge or publication.

## Security posture

`AUTONOMY: OFF`. Decision D-01 `RISK_ACCEPTED_SAME_IDENTITY` is risk acceptance, **not container/VM isolation**. Decision D-03 `CHAT_APPROVAL` is an operational gate mode, **not proof of human identity** against same-user workers. No Always Allow or agent self-approval. Decision D-02 restricts the client to literal HTTP loopback addresses; an upstream proxy may have separate provider/network obligations.

Tests that execute project source are not safe merely because their command lines are allowlisted. Local SQLite entries and Git hashes do not make receipts tamper-proof against a privileged local attacker. Do not enable unattended execution based on the present candidate evidence.

## Historical evidence

The [candidate acceptance matrix](ACCEPTANCE_MATRIX_E01_E21_EVIDENCE.md) and [release candidate report](RELEASE_CANDIDATE_V1_0_0.md) are retained as historical reports; more stringent independent checks supersede their unconditional readiness language. The display-name change does not rename Python imports, env vars, or existing repository URLs.

## Next-development source of truth

See [Simpul developer roadmap and handoff](simpul/README.md). Its task list and staged release gates describe proposed work, not independently verified completion.
