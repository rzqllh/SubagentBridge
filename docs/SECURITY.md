> **Historical PR-00 threat model (Simpul, 23 October 2026):** This is a baseline-era risk analysis and not the source of truth for the PR #3 candidate's feature completion. D-01 is `RISK_ACCEPTED_SAME_IDENTITY` and D-03 is `CHAT_APPROVAL` for current Phase A, always with `AUTONOMY: OFF`. Neither decision supplies a secure, independently verified human-identity isolation boundary. E18 same-user adversarial proof and E22/E23 remain open. See [current security](SECURITY_APPROVAL_MODEL.md) and [status](SIMPUL_STATUS.md).

# Security threat model: PR-00 (design / not enforced)

**Status:** source-audited design; `AUTONOMY: OFF`. This document is a threat model, not a security certification. Governing rules: `docs/TEAM_RULES.md`. Detailed proposed controls: pinned Plan v3.1 in `artifacts/bootstrap/v3_1/candidate/`.

## Principals, assets and boundaries

| Principal | Trust | Permitted future capabilities |
|---|---|---|
| Human developer | Trusted decision maker, subject to explicit one-time approvals | Authorize exact operations through a channel unreachable by workers |
| Antigravity IDE primary agent | Untrusted for human identity; orchestrates requests via MCP | Submit, inspect, cancel and ask; **not** issue human approvals |
| Bridge control plane / policy engine | Privileged policy evaluator, must not execute arbitrary repo scripts | Deterministic gate, identity, ledger and QA state transitions |
| PM / Developer / QA / Specialist worker | Potentially malicious or compromised despite role prompts | Role- and dispatch-scoped tools; workers never hold broker credentials |
| Model / 9Router / repository file / skill / tool output | Untrusted input | Data only, cannot grant capabilities |
| GitHub Actions / BVE verifier | Separate build evidence environment, **not** production executor | Execute read-only-approved bootstrap verification and report limitations |
| Optional Orca | Untrusted external execution backend until isolated / tested | Session dispatch only; never human approval or QA VERIFICATION |

Protected assets: repository source and QA tests, Git trees and commits, credentials, broker secrets, audit/approval ledger, per-project worktrees, network and budget policy, execution receipts, QA verdicts and CI provenance.

**Attacker model:** a worker may submit adversarial prompts/tool arguments, read untrusted files, forge stdout/stderr and simulated receipts, race retries and seek symlink/junction path escape. Treat any worker running under the broker's OS user on the same interactive desktop as able to inspect/drive that UI and potentially access same-user secrets. A Git worktree, a Job Object, a shell allowlist and a hash chain do not isolate this attacker. OS administrators may modify local SQLite logs; append-only means application-enforced, not tamper-proof against administrators.

## P0 containment and unresolved hazards (current PR-00 HEAD)

1. **Contained, not solved:** `approve_action` is no longer an MCP tool; the legacy Python callable returns a denial, and `manager.PendingActionQueue.resolve(..., approved=True)` fails closed. **No authenticated human broker exists**; denial-only behavior is not successful approval enforcement. `reject_action` remains exposed as an MCP tool for deny decisions, not proof of human-origin identity.
2. **Contained, not solved:** `Session.skip_permissions` and the MCP spawn parameter now default to `False`; explicit `skip_permissions=True` and `hitl_enabled=False` are rejected. Both `send_message` and direct `_run_once` deny legacy runner execution before invoking the runner; direct manager/MCP `apply_code_fix` is disabled. This is an availability-limiting lockdown, not a functioning confined worker runtime.
3. **Still missing:** the legacy `_handle_event` architecture would observe CLI tool calls only **after** external tools may have acted if execution were enabled. That is not pre-execution enforcement. The dormant subprocess code is not a trusted tool executor; `AUTONOMY: OFF` remains mandatory.
4. `manager.check_path_in_workspace` accepts any registered workspace, not an ACL for the task and role. Path `resolve()` alone is insufficient against all races and platform-specific junction/reparse cases.
5. `Session.kill()` kills one direct subprocess; Windows child processes and inherited handles are unverified.
6. Retry instructions delivered in a prompt cannot guarantee exactly-once side effects. Persist idempotency keys and reconcile actions before retrying.
7. `reset_stale_working_sessions()` marks old processes idle without reconciliation; `RECOVERY_REQUIRED` is needed.
8. SQLite WAL preserves transaction semantics but is not an authenticated append-only audit log.
9. Output or SHA reported by an LLM is an untrusted **claim**, never an `ExecutorReceipt`.

## Forward security contract and human decision D-03

Only after independent executable proof can a trusted approval broker issue operation-bound `Allow Once` / `Deny` / `Answer Questions`. No `Always Allow`, timeouts auto-approval, agent-issued resolution, or modified-operation reuse. **D-03 has not been decided**: (a) separate OS identity/container/VM for workers with broker outside; (b) genuinely out-of-band second-device approval; or (c) Phase-A chat approvals with autonomy permanently off.

A remote phone UI is **not automatically sufficient** if a same-user worker can steal pairing/session credentials or call the broker's local endpoint. Device origin, challenge binding, actor attestation and worker inaccessibility must all be proven by E18 red-team checks.

Repository tests/builds execute arbitrary code: `run-allowlisted-command` alone does not isolate them. Require verified `ISOLATED` execution under a separate identity/container/VM to enable autonomy. `RISK_ACCEPTED_SAME_IDENTITY` is a recorded human risk acceptance, **not** isolation and is incompatible with autonomous mode. The model-only tool proxy must be the exclusive side-effect path; unconfined raw-shell CLI workers are `UNSUPPORTED_ENFORCEMENT`.

**AG-1 autonomy gate stays closed** until D-03 and D-01 are decided, independent tests prove approval isolation E18 and source/test isolation, enforcement class is verified, and E05/E07/E16/E17 all pass. `AUTONOMY: OFF` is the unconditional PR-00 outcome.

## Evidence, provenance and recovery

Only Bridge-owned `ToolExecutor` may mint product `ExecutorReceipt` with exact task/dispatch, command argv, environment allowlist hash, exit code, stdout/stderr hashes, timestamps, clean checkout tree and executor identity. Fresh-session `BootstrapVerificationEvidence` (BVE) is separate and must never be accepted by product runtime as a receipt. PM and Developer never issue QA verdicts. QA independent tests cover every frozen acceptance criterion, and any tree change revokes VERIFIED.

Gate changes to auth/secrets, dependencies, CI/deploy, schema/migrations/data deletion, pushes/history, outside-workspace writes, new network destinations, modified/skipped tests, waivers and material product tradeoffs. Record one-time operation fingerprints. Unknown credentials, network hosts, QA verdicts and process ownership must fail closed. A full immutable external ledger against same-user/privileged attacks is **not** claimed.

## PR-00 scope and non-goals

PR-00 documents and tests the missing guarantees; it does not implement a broker, tool executor, process sandbox, 9Router runtime, independent QA, Orca integration, or release gating. Named expected failures in baseline CI remain outstanding work and never count as proof that AG-1 passed.
