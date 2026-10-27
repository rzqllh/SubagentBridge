# Simpul — project status and evidence boundaries

**Updated:** 27 October 2026. Simpul 1.1.0 follows a supervised beta release track. Publication is determined by the matching GitHub tag/release, not by this status file. The existing historical baseline is v1.0.0. See [GitHub Releases](https://github.com/rzqllh/SubagentBridge/releases).

## Implemented candidate capabilities

MCP stdio server, supervised native execution, real worker subprocess/IPC, SQLite-backed multiworker team/dispatch, steering, cancellation, evidence-based handoff, Git worktrees, checkpoint recovery and backward-compatible schema migration.

The public product name is Simpul. Existing `subagentbridge` technical identifiers remain supported; historical `Orca*` symbols are isolated compatibility aliases rather than product branding. Attribution to Cindy is retained in [third-party notices](../THIRD_PARTY_NOTICES.md).

## Verification and release gating

The feature stack is developed through reviewed pull requests. A PR CI success does not certify combined merged code, production isolation or release readiness by itself. Merge and release require checking the final Git SHA, CI matrix, integrity regressions and actual GitHub review status. The repository's current status must be verified on GitHub, not inferred from old candidate reports.

## Residual boundaries

- `AUTONOMY: OFF`, `GATE_MODE: CHAT_APPROVAL`.
- E18 same-OS-user confinement is **BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)**. A separate PID is not a security sandbox.
- Human approval in unit tests is a trusted fixture; a separately authenticated out-of-band production UI remains unimplemented.
- Checkpoint recovery is at-least-once under ambiguous crash windows, not guaranteed exactly-once.
- External harness support requires host-specific end-to-end confirmation.

See [public docs](public/README.md), [security limits](public/SECURITY.md) and [release notes](public/RELEASE_NOTES.md).

Historical candidate matrices, pinned upstream comparisons and earlier test receipts remain in `docs/simpul/` for traceability; they must not be represented as the latest production proof.
