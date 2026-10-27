# Security and responsible operation

**Status: [published v1.1.0](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.0), supervised operation; not an isolation or security certification.** E18 same-user confinement is `BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)`.

## Trust boundaries

- An MCP tool caller or model output is **not** an authenticated human.
- `AUTONOMY: OFF`: do not enable unattended privileged execution.
- `GATE_MODE: CHAT_APPROVAL`: privileged commands require exact-context trusted approval. A chat approval message alone does not prove authenticated out-of-band identity.
- The in-process approval broker and HMAC ticket tests exercise a fixture. Simpul does **not** ship a production-ready isolated human-approval UI.
- Worker PIDs run under the invoking OS account and share that account's permissions. Git worktrees separate files by convention, not by OS authorization.
- Runtime result claims are not receipts. Verified completions require evidence checks and are subject to the stated trust boundary.

## Operational precautions

Use a dedicated, least-privilege OS account and an expendable workspace for experiments. Do not mount credentials or sensitive home folders in untrusted worker workspaces. Keep branch edits reviewed, disable automatic publication and do not put approval tokens or API keys in source, logs, or MCP configuration.

Data migration takes a consistent SQLite online backup before changing a legacy database. Preserve the pre-migration backups until independently checked; see [migration](MIGRATION.md).

## Limitations to disclose

E18 same-user co-process confinement remains blocked. Per-host external CLI integrations and out-of-band approval interactions require environment-specific end-to-end validation. CI passing does not certify malicious-worker confinement. No release may claim zero residual vulnerabilities or production safety solely from lint/static scanners.

For responsibly disclosed security concerns, use GitHub's repository security reporting feature if enabled or open an issue without posting secrets, exploit credentials or sensitive logs.
