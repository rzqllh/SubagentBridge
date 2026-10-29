# Enterprise-readiness evidence and release gates

**Status:** NOT ENTERPRISE-CERTIFIED / ENTERPRISE RELEASE BLOCKED (29 October 2026).

## Current post-v1.1.4 source qualification (not a published release)

The latest published public version is **v1.1.4**. Later protected-main
changes PRs **#65–#68** add truthful 9Router harness fail-closed behavior,
correlated worker IPC and safe switching, bounded worker batch registration,
atomic queue steering, and immutable Lead/Worker metadata registration. Each
PR passed four Ubuntu/Windows Python 3.11/3.13 CI jobs before merge.
Check the **new exact-main** push CI independently after every merge; a green
PR alone is not proof that a new package has been released.

None of these patches implements a production independently authenticated
operator UI/IdP (#22), a supported hostile-worker OS sandbox (#21), or
complete operational/SBOM/soak/restore evidence (#23). A source-candidate
hardening PR is not `ENTERPRISE_READY`. Branch protection is enabled, but
independent reviewer approval and real-host negative tests remain release
requirements. See
[Release decision packet](simpul/ENTERPRISE_RELEASE_DECISION_20261029.md).

The **[published v1.1.4 supervised security release](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4)** contains merged PRs #30–#41.
The active `main` ruleset requires pull requests and four Windows/Linux checks.
[Exact-main CI](https://github.com/rzqllh/SubagentBridge/actions/runs/40622640492)
passed 4/4; the [release workflow](https://github.com/rzqllh/SubagentBridge/actions/runs/40623111287)
successfully built, attested, verified, and published the wheel/sdist/checksums.
This verifies bounded build provenance, **not** production WebAuthn identity,
hostile-worker OS sandbox isolation, or recovery/enterprise acceptance.

Simpul is a local-first supervised MCP subagent orchestrator, not a multi-tenant secure agent execution service. The meaning of "enterprise-ready" is evidence-based: operational resilience, provable human authorization, isolation, auditability, reproducible releases, and recoverability are separate gates.

| Gate | Status | Concrete evidence / remaining requirement |
|---|---|---|
| Multi-worker subprocess lifecycle and real IPC | VERIFIED (bounded) | Python child processes, PID identity and timed IPC exercised in Windows/Linux CI; not a sandbox |
| SQLite schema migration and backup consistency | VERIFIED (bounded) | WAL-aware online SQLite backup, schema mapping, rollback tests and racing initializer regressions |
| Shared-connection reader/writer concurrency | VERIFIED (bounded) | v1.1.1 serializes 13 reads and 10 writers via RLock; BEGIN IMMEDIATE protects cross-process resume; concurrency regressions PASS on Ubuntu/Windows Python 3.11/3.13 |
| Recovery of in-flight commands | PARTIAL | Trusted checkpoint identity and observable artifact validation; crash before checkpoint may leave ambiguous external side effects; automatic exactly-once is not claimed |
| Approval provenance | BLOCKED FOR ENTERPRISE | PRs #34/#35/#37/#39/#40 add opt-in verifier-injected approval, durable cross-process decision/consumption CAS, action-bound challenge and legacy provenance migration. Default TrustedApprovalAuthority remains; **no production WebAuthn/OIDC verifier or operator UI exists** |
| E18 hostile worker isolation | BLOCKED (merged partial hardening) | Default workers retain same-user privileges. PRs #31/#38 add env scrubbing, opt-in Linux dedicated UID/GID, strict distinct-identity refusal and Windows Job Object UI limits. **No supported Windows hostile-worker sandbox** or verified Linux filesystem/network/process confinement. Issue #21 remains OPEN |
| Independent host integration coverage | PARTIAL | Adapters and MCP subprocess tests do not imply true end-to-end certification for every Antigravity/Codex/Claude/Pi build |
| Artifact integrity and verified handoff | VERIFIED (bounded) | File existence, SHA-256, task binding and transaction-protected receipts under documented trust boundary |
| Supply-chain/release provenance | PARTIAL | PR #36 adds SHA-pinned Sigstore/GitHub build attestation and verification before release, alongside exact-main QA, wheel/sdist and SHA256 sums. The v1.1.4 GitHub release workflow passed attestation and artifact verification; clean-environment independent installation, signed dependency-accurate SBOM and restore/rollback drills remain missing |
| Operational SLO/load/chaos | NOT VERIFIED | No claimed long-duration soak, restore drill, large-scale task-queue load test or production incident exercise |

## v1.1.4 supervised-release limitations

The v1.1.4 release is permitted only as a **limited public supervised security
hardening** patch; it MUST NOT be marketed as enterprise ready, sandboxed for
hostile workers, or genuine independently authenticated human approvals.
Required unresolved issue gates are
[#21](https://github.com/rzqllh/SubagentBridge/issues/21) (OS isolation),
[#22](https://github.com/rzqllh/SubagentBridge/issues/22) (real RP/IdP and
operator UI), and [#23](https://github.com/rzqllh/SubagentBridge/issues/23)
(SBOM, restore/rollback, long-duration adversarial/chaos evidence).

The release flow must use an exact-main source commit with **4/4 main-push
CI success**, verified SHA-pinned GitHub/Sigstore build attestations and
checksums before publishing. This is build provenance, not safety certification.

## Post-v1.1.1 security delta

- **v1.1.2:** removed model-callable unauthenticated approval route; default-deny preserved for legacy callers.
- **v1.1.3:** action expiry (default 900s), fresh approval on expiration, finite 60s maximum issued IPC execution tickets, malformed expiry rejection, and constant-time local credential comparison.
- **Unresolved:** [E18 OS confinement](https://github.com/rzqllh/SubagentBridge/issues/21), [production out-of-band identity](https://github.com/rzqllh/SubagentBridge/issues/22), and [operational recovery/attestation](https://github.com/rzqllh/SubagentBridge/issues/23).

## Policy and permitted claim

- `AUTONOMY: OFF`, `GATE_MODE: CHAT_APPROVAL`. Automated agents cannot approve their own privileged commands.
- Fail closed on untrusted approval payloads, replayed tickets, stale PIDs and uncertain checkpoint side effects. Do not silently replay non-idempotent commands.
- Use a dedicated least-privileged OS identity, an expendable workspace, backup and explicit human operator supervision for tests.
- Release gating requires the exact source tree to have passed Ubuntu/Windows Python 3.11/3.13 CI, merged main source is identical to the tested tree, a separate main-SHA-gated build runs and publishes artifacts, and public docs disclose E18.
- The published v1.1.1 patch is described as *supervised runtime integrity hardening*, **not enterprise security certification**.
- A future enterprise-readiness verdict requires an independently tested OS privilege boundary, real authenticated human approval integration, clean-environment restore evidence, and repeatable hostile-worker assessment.

See [Security Model](SECURITY_APPROVAL_MODEL.md), [Public Security Guide](public/SECURITY.md) and [Compatibility Limitations](COMPATIBILITY_LIMITATIONS.md).

## P0 approval-gate correction published in v1.1.2

A source audit of v1.1.1 found that model-callable `approve_command(action_id, approver, auth_token)` could grant approvals without authenticating the caller. Published v1.1.2 removes MCP registration and makes the compatibility callable unconditionally `BLOCKED`. **This does not provide authenticated human approval.** Follow the remaining integration in [issue #22](https://github.com/rzqllh/SubagentBridge/issues/22) and the experimental worker boundary in [Worker Isolation](WORKER_ISOLATION.md).
