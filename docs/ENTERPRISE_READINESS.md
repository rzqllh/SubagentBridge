# Enterprise-readiness evidence and release gates

**Status:** NOT ENTERPRISE-CERTIFIED (27 October 2026). The shipped baseline is [Simpul v1.1.0](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.0). A `v1.1.1` correction is in development; do not claim publication until GitHub Release assets exist.

Simpul is a local-first supervised MCP subagent orchestrator, not a multi-tenant secure agent execution service. The meaning of "enterprise-ready" is evidence-based: operational resilience, provable human authorization, isolation, auditability, reproducible releases, and recoverability are separate gates.

| Gate | Status | Concrete evidence / remaining requirement |
|---|---|---|
| Multi-worker subprocess lifecycle and real IPC | VERIFIED (bounded) | Python child processes, PID identity and timed IPC exercised in Windows/Linux CI; not a sandbox |
| SQLite schema migration and backup consistency | VERIFIED (bounded) | WAL-aware online SQLite backup, schema mapping, rollback tests and racing initializer regressions |
| Shared-connection writer concurrency | PATCH UNDER REVIEW | v1.1.1 adds one RLock across writers and BEGIN IMMEDIATE resume claim; require 4/4 CI and contention tests |
| Recovery of in-flight commands | PARTIAL | Trusted checkpoint identity and observable artifact validation; crash before checkpoint may leave ambiguous external side effects; automatic exactly-once is not claimed |
| Approval provenance | BLOCKED FOR ENTERPRISE | HMAC-bound tickets and replay protection exist; `ApprovalBroker` uses a test/in-process credential, not an independent production human identity provider and out-of-band interface |
| E18 hostile worker isolation | BLOCKED | Workers share same operating-system user and can reach that user's resources; requires OS-enforced least-privilege separation, identity isolation and adversarial cross-process tests |
| Independent host integration coverage | PARTIAL | Adapters and MCP subprocess tests do not imply true end-to-end certification for every Antigravity/Codex/Claude/Pi build |
| Artifact integrity and verified handoff | VERIFIED (bounded) | File existence, SHA-256, task binding and transaction-protected receipts under documented trust boundary |
| Supply-chain/release provenance | PARTIAL | Pinned QA analyzers, immutable release SHA, wheel/sdist/checksum are present; signature/SBOM/provenance attestation and documented incident rollback remain unverified |
| Operational SLO/load/chaos | NOT VERIFIED | No claimed long-duration soak, restore drill, large-scale task-queue load test or production incident exercise |

## Policy and permitted claim

- `AUTONOMY: OFF`, `GATE_MODE: CHAT_APPROVAL`. Automated agents cannot approve their own privileged commands.
- Fail closed on untrusted approval payloads, replayed tickets, stale PIDs and uncertain checkpoint side effects. Do not silently replay non-idempotent commands.
- Use a dedicated least-privileged OS identity, an expendable workspace, backup and explicit human operator supervision for tests.
- Release v1.1.1 only when **its exact source tree** has passed Ubuntu/Windows Python 3.11/3.13 CI, merged main source is identical to the tested tree, a separate main-SHA-gated build runs and publishes artifacts, and public docs disclose E18.
- A patch release passing that gate may be described as *supervised runtime integrity hardening*, **not enterprise security certification**.
- A future enterprise-readiness verdict requires an independently tested OS privilege boundary, real authenticated human approval integration, clean-environment restore evidence, and repeatable hostile-worker assessment.

See [Security Model](SECURITY_APPROVAL_MODEL.md), [Public Security Guide](public/SECURITY.md) and [Compatibility Limitations](COMPATIBILITY_LIMITATIONS.md).
