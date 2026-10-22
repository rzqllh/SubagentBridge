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

## Verification scope and outstanding gates

The 21 October candidate reports 250 tests discovered (246 passed, 4 skipped), E01–E21 acceptance test methods and Windows/Linux CI. Treat those as **dated candidate evidence**. No fresh test, build, real IDE invocation, external model call, or independent clean checkout was performed during the 23 October documentation update.

- **E18:** token validation test is not a sufficient same-user attacker/broker-secret isolation test; independent adversarial evidence remains needed.
- **E22:** checkout-root containment has not received completed independent evidence.
- **E23:** remote pinned Git clone/checkout has not received completed independent evidence.
- **9Router:** offline discovery/capability tests exist; a prior authenticated live completion attempt returned HTTP 401.
- **Integration:** a real end-to-end Antigravity MCP PM/Developer/QA workflow has not been demonstrated.
- **Release:** PR review, merge, independent verifier signoff and published distribution are pending.

## Security posture

`AUTONOMY: OFF`. Decision D-01 `RISK_ACCEPTED_SAME_IDENTITY` is risk acceptance, **not container/VM isolation**. Decision D-03 `CHAT_APPROVAL` is an operational gate mode, **not proof of human identity** against same-user workers. No Always Allow or agent self-approval. Decision D-02 restricts the client to literal HTTP loopback addresses; an upstream proxy may have separate provider/network obligations.

Tests that execute project source are not safe merely because their command lines are allowlisted. Local SQLite entries and Git hashes do not make receipts tamper-proof against a privileged local attacker. Do not enable unattended execution based on the present candidate evidence.

## Historical evidence

The [candidate acceptance matrix](ACCEPTANCE_MATRIX_E01_E21_EVIDENCE.md) and [release candidate report](RELEASE_CANDIDATE_V1_0_0.md) are retained as historical reports; more stringent independent checks supersede their unconditional readiness language. The display-name change does not rename Python imports, env vars, or existing repository URLs.

## Next-development source of truth

See [Simpul developer roadmap and handoff](simpul/README.md). Its task list and staged release gates describe proposed work, not independently verified completion.
