> **Latest published:** [Simpul v1.1.1](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.1) — 27 Oct 2026, merge `861f040dc12c33da681331e454ef41299f2dc70b`, CI 4/4 PASS, release workflow `40444832484` SUCCESS. Production certification is **not** implied; E18 same-user OS confinement and production human-approval identity remain BLOCKED. Historical project snapshots below are archival.

> **Release verified — 27 October 2026:** [Simpul v1.1.0](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.0) is published from merge commit `a29f0d98957651e482fbae989a906bb09873f329`; candidate CI ran 4/4 successfully, release workflow [40440851542](https://github.com/rzqllh/SubagentBridge/actions/runs/40440851542) succeeded. Historical candidate notes below are not current status. E18 remains BLOCKED (RISK_ACCEPTED_SAME_IDENTITY).

## Historical snapshot — pre-v1.1.0 release candidate (superseded)

The C00–C07 PR stack (#9–#16) adds team sessions, real subprocess IPC, authenticated handoffs, SQLite state/checkpoints, worktree continuity, native Simpul names and Cindy-attributed migration compatibility. This work is being developed and verified on `simpul/15-native-naming`, **not yet published from `main`**. Follow the exact PR head SHA, GitHub Actions matrix and unresolved review threads before describing it as released. The existing `v1.0.0` tag remains the documented published baseline. Safety boundary: `AUTONOMY: OFF`, `GATE_MODE: CHAT_APPROVAL`, E18 `BLOCKED`. See [release readiness](simpul/RELEASE_READINESS.md) and [parity report](simpul/SIMPUL_CINDY_PARITY_REPORT.md).

# Simpul — Project status and evidence boundaries

**As of:** 23 October 2026  
**Public name:** Simpul (formerly SubagentBridge)  
**Repository:** `rzqllh/SubagentBridge` (repository has not been renamed)  
**Compatibility:** `subagentbridge` imports/distribution/CLI, `SUBAGENTBRIDGE_*` variable namespace

## Source, branch and publication

- `main` contains the fully integrated and hardened release commit `953c0f5a34c7ae8917d8febde92354eb8ed8a4ef`.
- PRs #2 through #8 covering phases P00 through P06 have all been sequentially merged into `main` on 2026-10-23.
- Release `v1.0.0` is published on GitHub Releases (`https://github.com/rzqllh/SubagentBridge/releases/tag/v1.0.0`) with verified SHA-256 asset checksums.
- Active development and sprint verification occurs on dedicated sprint branches (e.g. `simpul/08-sprint1-verification`), never directly on `main`.

## What the code actually provides

A Python composition root wires SQLite audit and budget layers, a message bus, skill registry, policy classifier, supervised read-only executor, identity and receipt registries, QA evidence gate and local 9Router client. The server exposes production MCP stdio tools. Its execution lifecycle coordinator (`SupervisedNativeLifecycle`) executes the complete PM → Developer → QA workflow under strict fail-closed enforcement: tasks without genuine execution commands cannot issue receipts or achieve `VERIFIED` status. `get_task_evidence` reads independently issued receipts and evidence records.

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
