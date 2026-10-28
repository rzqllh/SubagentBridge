# Security and responsible operation

> **Current release:** [v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4), 28 October 2026. **Supervised security hardening; NOT enterprise-certified.** Worker hostile-code OS isolation (E18/#21), independent production human WebAuthn/OIDC approval (#22) and operational acceptance (#23) remain OPEN/BLOCKED.
>
> **v1.1.4 improvements:** PRs #34–#40 introduce opt-in verifier injection, durable SQLite single-use decision/consumption protections, and a distinct action-specific challenge bound to an operator decision. `VerifiedOperatorApprovalAuthority` refuses an identity-only verifier without an action-proof verifier. Previously approved legacy identity-only grants are not trusted by this new worker IPC adapter after migration. The external verifier is **not included** in the product; a test-only HMAC checker does not constitute human authentication. GitHub build attestations and checksums are verified release-provenance controls, not code-safety or sandbox certification.

## v1.1.1 security correction

The child process now uses Python `-P` safe-path, so a workspace-local `subagentbridge` module cannot replace the real worker entrypoint. SQLite reads/writes share an internal lock. Recovery preflights all human approvals and refuses stale or consumed execution tickets; unverified side effects require operator reconciliation. These controls are defense in depth and **do not remove E18**.

## v1.1.2–v1.1.3 approval security updates

v1.1.2 removes unauthenticated MCP self-approval. v1.1.3 expires all pending/approved broker actions (900-second default), refuses expired decisions and malformed execution ticket expiries, and binds tickets to a finite maximum 60-second lifetime. An expired action must be requested and explicitly approved again.

The broker remains **in-process and credential-gated**; fixture token tests do not demonstrate independently authenticated human identity, durable identity policy, or hostile-worker OS isolation. See [Enterprise Readiness](../ENTERPRISE_READINESS.md).

## Post-merge operator authentication limitation

Merged PRs #33–#40 contain an optional `IndependentOperatorApprovalBoundary` plus an explicitly injectable `VerifiedOperatorApprovalAuthority` for worker IPC. When configured, the latter requires both an independently trusted **identity** verifier and a trusted **action-specific decision** verifier; otherwise it refuses construction. Its challenge digest is a reference value, **not a WebAuthn assertion**. The default server path still uses the older local authority for compatibility; no genuine independently authenticated human UI/relying party is shipped. Issue #22 remains OPEN.

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

## Historical v1.1.2 approval-gate correction (published)

The `v1.1.1` MCP implementation inadvertently exposed `approve_command` as a model-callable tool and did not authenticate the supplied `auth_token`. The security-corrective v1.1.2 branch removes this tool from the MCP registry and turns the legacy Python function into unconditional `BLOCKED`. Privileged commands cannot be approved by a model, chat string, or caller-provided token. A genuine independently authenticated human-operator approval channel remains to be implemented. This is a deliberate fail-closed compatibility restriction and must not be treated as full E18 or enterprise approval assurance. See [Issue #22](https://github.com/rzqllh/SubagentBridge/issues/22).
