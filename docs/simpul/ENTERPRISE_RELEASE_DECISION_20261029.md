# SIMPUL — Enterprise release decision packet (29 October 2026)

**Decision: ENTERPRISE RELEASE = NO-GO.** This is an evidence-backed
release gate, not an authorization to publish, create tags, or enable autonomy.

## Verified source versus shipped artifact

- **Latest public release:** [v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4), built with verified GitHub/Sigstore artifact attestations for its own exact source SHA.
- **Post-release source work:** [#65](https://github.com/rzqllh/SubagentBridge/pull/65) truthful harness/IPC hardening, [#66](https://github.com/rzqllh/SubagentBridge/pull/66) bounded batch worker roster, [#67](https://github.com/rzqllh/SubagentBridge/pull/67) atomic task steering and priority, [#68](https://github.com/rzqllh/SubagentBridge/pull/68) immutable team/worker IDs. Each was gated by four PR CI jobs before merge; these commits have **not** shipped in a published version.
- **Protected `main`** is required for any future release; every merge must additionally have exact-main 4/4 CI. Check actual current main SHA again at decision time; historical numbers are not future evidence.
- `pyproject.toml` still declares `1.1.4`. A future version number, tag, package and release have not been authorized. Do not create `release/v*` branches as a rehearsal: pushes to them automatically invoke the publish workflow if all gates pass.

## Go/no-go gates

| Gate | Current status | Proof needed before declaring enterprise release-ready |
|---|---|---|
| Source integrity and protected CI | **VERIFIED PER PR; recheck latest main** | Exact intended main SHA has 4/4 Ubuntu/Windows 3.11/3.13 PASS, no unresolved review threads or unapproved changes |
| Hostile-worker OS security (E18, [#21](https://github.com/rzqllh/SubagentBridge/issues/21)) | **BLOCKED** | Independently tested Windows restricted identity/account ACL sandbox and supported Linux UID/namespace/network/filesystem confinement; real negative tests against home, secrets, sibling worktrees and parent processes |
| Operator authentication ([#22](https://github.com/rzqllh/SubagentBridge/issues/22)) | **BLOCKED** | Real out-of-band WebAuthn or OIDC relying party, separate trusted operator UI, role validation, fresh action-bound approval and replay/expiry tests; no test-only HMAC or in-process broker as identity proof |
| Durable failure recovery ([#23](https://github.com/rzqllh/SubagentBridge/issues/23)) | **PARTIAL** | Operator reconciliation of ambiguous side effects; kill/restart drills, multi-supervisor consistency, SQLite WAL restore and rollback with actual loss/replay receipts |
| Supply-chain completeness ([#23](https://github.com/rzqllh/SubagentBridge/issues/23)) | **PARTIAL** | Runtime dependency-accurate signed SBOM, clean-environment wheel/sdist install and uninstall, verify attestation workflow against new exact source SHA, rollback and independent provenance review |
| Soak / resource boundedness ([#23](https://github.com/rzqllh/SubagentBridge/issues/23)) | **NOT VERIFIED** | Documented Windows/Linux long-running load+chaos run with queue size, CPU/RAM, timeout, error/retry rates and cleanup evidence; no fake performance numbers |
| Real Antigravity and external harness end-to-end | **PARTIAL** | Trusted disposable Windows host: actual IDE MCP tool enumeration; lead→worker→QA flow, explicit human decision, blocked negative attempts and restart recovery; distinguish simulator/CI from real IDE |
| Independent human review | **NOT VERIFIED** | GitHub required independent reviewer ≥1, actual qualified review of safety-critical changes and recorded owner signoff; protected branch alone is not peer review |
| Publication authorization | **NOT GRANTED** | Explicit owner approval of release version, risk report, immutable SHA and signed artifacts **after** all mandatory gates pass |

## Operator-only actions required outside this GitHub connector

1. **Host test lab:** provide a disposable Windows system for Antigravity IDE and a separate Linux test host. Define OS account/ACL, network isolation and workspace test fixtures; never use production credentials during hostile-worker tests.
2. **Identity provider:** select/configure an independent WebAuthn relying party or enterprise OIDC IdP with explicit issuer/audience/authorized role, registration process and trusted approval UI. Keep verifier signing keys and tokens **outside** model/worker tools; do not paste secrets into issues, PRs, or chat.
3. **Reviewer and ruleset:** enable at least one genuine independent PR approval in GitHub protection, assign a non-author security reviewer, and review the E18/approval trust boundary and adverse E2E receipts.
4. **Operational proof:** run signed-SBOM, recovery/WAL restore, rollback, resource soak, adversarial and real MCP host acceptance on expendable machines; attach redacted results to #21/#22/#23.
5. **Release decision:** only after all gates close, approve a new semantic version and exact main SHA. Update package version and public docs, run all exact-main CI and build provenance checks, independently verify artifacts, and *then* approve publication.

## Mandatory governance

`AUTONOMY: OFF` · `GATE_MODE: CHAT_APPROVAL` · `E18: BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)`

No model self-approval, privileged unattended commands, force push, direct main
bypass, recursive deletion of unknown user worktrees, silent fallback to less
isolated workers, invented host evidence, or marketing claim of
`ENTERPRISE_READY`. A future **limited-public supervised** release could be
considered separately with explicit risk acceptance and owner authorization;
that is *not* enterprise security certification.

Supporting evidence: [Enterprise readiness](../ENTERPRISE_READINESS.md),
[Operator approval](../OPERATOR_APPROVAL_INTEGRATION.md),
[Worker isolation](../WORKER_ISOLATION.md),
[Release attestations](../RELEASE_ATTESTATION.md), and
[parity epic #43](https://github.com/rzqllh/SubagentBridge/issues/43).
