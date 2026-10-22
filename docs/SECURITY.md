# Simpul — Security status (default branch)

> **Historical baseline notice (23 October 2026):** `main` contains an older SubagentBridge prototype and planning-era security documents. Its code and claims have **not** been upgraded to the current candidate by this documentation-only change. Do not run untrusted repositories, code, or agents on `main` expecting guaranteed pre-execution enforcement, child-process isolation, verified human identity, or robust cleanup.

## What can and cannot be trusted

- A model-callable `approve_action` is **not** proof of human consent. This branch's legacy design should not be used as an authorization boundary.
- Merely reading a worker's emitted tool logs cannot prevent a side effect that already happened.
- A workspace path check, Git worktree, subprocess timeout, SQLite ledger or hash does not isolate malicious code running under the same OS user.
- Never configure `skip_permissions=True` expecting Simpul's newer controls to protect the legacy code.
- Network egress and credentials must be independently controlled. Do not paste production API keys into public example config files.

## Status of the safer candidate

PR #2 proposes baseline lockdown; PR #3 contains a separate approval broker and supervised execution components, but both remain unmerged. The candidate runs with `AUTONOMY: OFF`, Phase-A `RISK_ACCEPTED_SAME_IDENTITY` (D-01), and `CHAT_APPROVAL` (D-03). Same-user broker adversarial proof (E18), checkout-root containment (E22), and real pinned remote checkout (E23) remain open for independent verification.

See [Simpul project status](SIMPUL_STATUS.md), [PR #2](https://github.com/rzqllh/SubagentBridge/pull/2), and [PR #3](https://github.com/rzqllh/SubagentBridge/pull/3). These boundaries supersede the historical planning-era security promises on `main`.
