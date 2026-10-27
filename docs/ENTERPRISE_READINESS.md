# Enterprise-readiness evidence and release gates

**Status:** NOT ENTERPRISE-CERTIFIED (27 October 2026). The latest published release is [Simpul v1.1.3](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.3), from merge commit `a47473edf4ff9ef9e59d2dd5f5d682941d0e1826`. The v1.1.2 and v1.1.3 patches harden MCP self-approval default-deny and action/ticket expiration; they do NOT implement independent human authentication or OS worker isolation.

Simpul is a local-first supervised MCP subagent orchestrator, not a multi-tenant secure agent execution service. The meaning of "enterprise-ready" is evidence-based: operational resilience, provable human authorization, isolation, auditability, reproducible releases, and recoverability are separate gates.

| Gate | Status | Concrete evidence / remaining requirement |
|---|---|---|
| Multi-worker subprocess lifecycle and real IPC | VERIFIED (bounded) | Python child processes, PID identity and timed IPC exercised in Windows/Linux CI; not a sandbox |
| SQLite schema migration and backup consistency | VERIFIED (bounded) | WAL-aware online SQLite backup, schema mapping, rollback tests and racing initializer regressions |
| Shared-connection reader/writer concurrency | VERIFIED (bounded) | v1.1.1 serializes 13 reads and 10 writers via RLock; BEGIN IMMEDIATE protects cross-process resume; concurrency regressions PASS on Ubuntu/Windows Python 3.11/3.13 |
| Recovery of in-flight commands | PARTIAL | Trusted checkpoint identity and observable artifact validation; crash before checkpoint may leave ambiguous external side effects; automatic exactly-once is not claimed |
| Approval provenance | BLOCKED FOR ENTERPRISE (P0 hardened candidate) | HMAC-bound tickets and replay protection exist; `ApprovalBroker` uses a test/in-process credential, not an independent production human identity provider and out-of-band interface |
| E18 hostile worker isolation | BLOCKED (unreleased partial hardening) | Default workers retain same-user privileges. The development branch adds child environment scrubbing and opt-in Linux dedicated UID/GID with protected runtime path checks. Windows privilege separation, ACL/network/process limits and adversarial host tests remain missing |
| Independent host integration coverage | PARTIAL | Adapters and MCP subprocess tests do not imply true end-to-end certification for every Antigravity/Codex/Claude/Pi build |
| Artifact integrity and verified handoff | VERIFIED (bounded) | File existence, SHA-256, task binding and transaction-protected receipts under documented trust boundary |
| Supply-chain/release provenance | PARTIAL | Pinned QA analyzers, immutable release SHA, wheel/sdist/checksum are present; signature/SBOM/provenance attestation and documented incident rollback remain unverified |
| Operational SLO/load/chaos | NOT VERIFIED | No claimed long-duration soak, restore drill, large-scale task-queue load test or production incident exercise |

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
