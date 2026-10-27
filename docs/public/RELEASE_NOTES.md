# Simpul release notes

## Version 1.1.1 — published 27 October 2026

[GitHub Release v1.1.1](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.1) was published from commit `861f040dc12c33da681331e454ef41299f2dc70b` after PR #19 passed Ubuntu/Windows Python 3.11/3.13 (4/4 PASS). Git tree of merged `main` equals the tested PR head tree. Release workflow [40444832484](https://github.com/rzqllh/SubagentBridge/actions/runs/40444832484) re-ran QA, built wheel and source distribution, and published the SHA256 checksum manifest.

**Corrected:** SQLite shared-connection read/write concurrency and cross-process resume claim; human approval preflight across command steps; consumed-ticket renewal; configured-workspace approval binding; fail-closed replay of unverifiable side effects; Python safe-path `-P` blocks workspace-local package shadowing. PR #17 was closed as superseded (not merged). No local worktrees were removed.

**Not certified for hostile multi-tenant operation:** E18 shared-OS-identity confinement and independent production human-identity approval UI remain unresolved. Use a least-privileged dedicated account and supervised trusted workspaces.

---


## Version 1.1.0 — published 27 October 2026

[Simpul v1.1.0](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.0) was published as a public non-prerelease from merge commit `a29f0d98957651e482fbae989a906bb09873f329`. The merged source tree matched the PR #16 commit tested on Ubuntu/Windows (Python 3.11/3.13); release workflow 40440851542 rechecked the exact merged SHA, built the wheel/sdist, and uploaded `SHA256SUMS.txt`.

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

### Verified release gate

The release workflow required the exact `origin/main` SHA and ran its verification/build/publish steps successfully. The 4-runner CI evidence on the PR source tree is byte-for-byte equivalent to the merged `main` tree. E18 remains BLOCKED.
