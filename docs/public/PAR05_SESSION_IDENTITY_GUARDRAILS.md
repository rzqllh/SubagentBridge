# PAR-05 : Immutable local Lead/Worker session registration

Status: **CODE_PRESENT; HOST_SECURITY_E2E_UNVERIFIED; enterprise human-identity gate BLOCKED**.

Trusted Python API: `TeamManager.create_team` now registers team + lead together via one `BEGIN IMMEDIATE` transaction, preventing a duplicate team ID from silently replacing the lead, a title, or the lead session's metadata. Exact repeated registration is idempotent; conflicting ownership is rejected.

`TeamManager.register_worker` and `create_worker` use a separate atomic insert-only path. A duplicate worker ID across any team, a worker ID matching its own lead, a mismatched team binding, a forged lead role and an unverified claimed OS PID are rejected. Optional worktree metadata commits in the same transaction so partial worker records do not survive a failed write. SQLite concurrency tests use independent supervisor connections.

**Limits:** These functions only operate on **trusted local in-process metadata**. A caller-supplied lead ID is not human authentication or a sandbox. The legacy `TeamStore.save_team` and `save_session` methods remain general persistence update functions used by recovery/migration, and are not treated as independent permission checks. Existing session updates still require higher-level authorization and reviewer scrutiny. No model-callable MCP self-approval, automatic worker spawning, remote tenant account verification or release is enabled.

See [PAR-05 #48](https://github.com/rzqllh/SubagentBridge/issues/48), [operator-authentication #22](https://github.com/rzqllh/SubagentBridge/issues/22), and [hostile-worker isolation #21](https://github.com/rzqllh/SubagentBridge/issues/21).
