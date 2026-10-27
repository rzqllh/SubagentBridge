# Simpul release notes

## Version 1.1.0 — supervised beta release candidate

Status on this document's initial publication: **candidate pending successful combined-stack review, merge and release tag**. The GitHub release page, not this document, is authoritative for whether 1.1.0 has actually shipped.

### Highlights

- Native lead/worker coordination with durable SQLite team and queue state
- Real subprocess worker IPC, lifecycle, cancellation and process identity checks
- Capability-based host adapters and structured inter-agent messaging
- Git worktree assignment and checkpoint-backed crash recovery
- Evidence-backed handoff and SHA-256 validation
- Native Simpul schema (`simpul_*`) with zero-discard transaction-based migration from historical `orca_*` tables
- Correctness hardening for concurrent queue deduplication, terminal-state cancellation, mixed optional legacy schema columns, and worker IPC ownership after restart
- Expanded Windows/Ubuntu CI validation with Python 3.11 and 3.13

### Compatibility

The Python distribution, import namespace and MCP server are still `subagentbridge`. The legacy `Orca*` Python aliases and read-only `orca_*` SQL views are retained as compatibility shims; these do not imply a dependency on Cindy.

### Known constraints

`AUTONOMY: OFF` / `GATE_MODE: CHAT_APPROVAL`; no unattended privileged execution. E18 remains `BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)`, and a production out-of-band human approval UI is **not** part of this release. Checkpoint recovery can be at least once after ambiguous crashes. A live PID without an owned IPC channel blocks automatic resume.

### Credit

Cindy by XD Inc. (Apache-2.0) was studied as an orchestration-core architectural reference. Simpul is independently implemented. See [Third-party notices](../../THIRD_PARTY_NOTICES.md).

### Verification before publish

All release checks must run against the **final exact merge SHA** and the release commit must match the published tag. A green CI check on earlier PR branches is insufficient as a substitute for this release gate.
