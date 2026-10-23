# Simpul — Project status and evidence boundaries

**As of:** 23 October 2026  
**Display name:** Simpul (formerly SubagentBridge)  
**Repository:** `rzqllh/SubagentBridge` (GitHub repository has not been renamed)  
**Technical compatibility:** `subagentbridge` package/import/CLI; `SUBAGENTBRIDGE_*` environment namespace

## Branch and release status

- `main` at `2a467bd4a82c65a30931554acef879fda9794a5f` is the imported baseline, not the release candidate.
- [PR #2](https://github.com/rzqllh/SubagentBridge/pull/2), PR-00 baseline recovery, is open and targets `main`.
- [PR #3](https://github.com/rzqllh/SubagentBridge/pull/3), `integrate/roadmap-v4-verified` at `44d70b5f05836a867978dcadb166bd1122943a3b`, is open and targets PR #2's branch.
- `1.0.0rc1` exists as candidate source/packaging metadata in PR #3. **Do not call it a published release or a merged production version.**

## Candidate implementation versus verified evidence

The PR #3 tree includes a composition root, typed contracts, persistent SQLite audit and budget layers, policy classification, one-time approval broker, supervised read-only executor, local-loopback 9Router adapter, skill pinning, QA evidence controls, and MCP tool endpoints. This describes code present in the candidate, **not** comprehensive real-world validation.

The candidate's 21 October 2026 evidence report records `250` discovered tests (`246` passed and `4` skipped), `21/21` E01–E21 test methods, and a four-job Windows/Linux CI matrix. These are **reported historical results** tied to an earlier verification scope; they do not prove today's branch state or all security properties.

**Unresolved gates:**

1. **E18:** Prior token-guessing tests do not establish broker isolation from a malicious same-OS-user worker. An independent same-user adversarial test is still required.
2. **E22:** Prove checkout-root containment across supported path and platform edge cases.
3. **E23:** Prove exact pinned remote Git checkout in an independently observed clean environment.
4. **9Router:** Offline capability tests do not replace live authenticated inference; a prior live completion check returned HTTP 401.
5. **Integration:** Verify actual PM → Developer → QA progression through a real host, not only contracts or staged simulations.
6. **Release:** Independent QA, merges, signed/tagged release, and published distribution remain pending.

## Current safety contract

- `AUTONOMY: OFF`, including for any security-gated action.
- D-01: `RISK_ACCEPTED_SAME_IDENTITY` is a documented Phase-A risk acceptance, **not sandbox isolation**.
- D-03: `CHAT_APPROVAL`; a language model is **not** an authenticated human approver. No auto-approve or Always Allow.
- D-02: the 9Router client accepts literal HTTP loopback origins and rejects redirects; this **does not** certify the upstream router's own external data flows.
- Audit data and Git worktrees do not defeat same-user/administrator access or isolate arbitrary test code.

## Reading order

Use this page for public status, the [open release candidate](https://github.com/rzqllh/SubagentBridge/pull/3) for working code, and `docs/TEAM_RULES.md` in the candidate for the governing human gates. Historical reports remain retained as evidence **from their recorded commits**, not current certification.

Last reviewed against GitHub branch/source snapshots on 23 October 2026. No new build, test, live-provider call or security adversarial exercise was executed by this documentation update.
