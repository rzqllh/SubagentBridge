# Security and responsible operation

**Status: [published v1.1.1](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.1), supervised operation; not an isolation or enterprise-security certification.** E18 same-user confinement is `BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)`.

## v1.1.1 security correction

The child process now uses Python `-P` safe-path, so a workspace-local `subagentbridge` module cannot replace the real worker entrypoint. SQLite reads/writes share an internal lock. Recovery preflights all human approvals and refuses stale or consumed execution tickets; unverified side effects require operator reconciliation. These controls are defense in depth and **do not remove E18**.

## Worker environment security hardening (unreleased candidate)

The latest development branch introduces a trusted-host worker environment allowlist that excludes API keys, GitHub/cloud tokens, and arbitrary `PYTHONPATH`, plus an optional Linux dedicated-user UID/GID drop that fails closed without required privileges. This reduces accidental credential inheritance but does not isolate a malicious same-user worker; Windows dedicated-user execution, network confinement, and adversarial validation are not yet supported. Details: [Worker Isolation Boundary](../WORKER_ISOLATION.md).

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
