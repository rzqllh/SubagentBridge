# Verified operator approval to worker IPC — integration status

**Enterprise acceptance: BLOCKED.** This module is only the connection between
host-verified operator grants and worker IPC tickets. It does **not** include a
production WebAuthn/OIDC relying party, IdP enrollment, authorization UI, or
Windows/Linux hostile-worker isolation.

## What is implemented

The trusted host may explicitly construct an
`IndependentOperatorApprovalBoundary` with **both** an independently authenticated
`operator_verifier` and an **action-specific** `decision_verifier`, then inject
`VerifiedOperatorApprovalAuthority` into
`WorkerProcessController(approval_authority=...)`. The adapter now refuses
construction when the action-specific decision verifier is missing. A reusable
identity token by itself is not transaction authorization.

A migrated legacy approval row starts with `action_bound_verified=0` even if
its previous identity-only state was `APPROVED`; the adapter refuses its
consumption. A fresh external action-bound decision is required. The migration
runs under the existing serialized SQLite schema transaction.

The runtime adapter:
- Creates exact worker/session/task/command/workspace approval requests.
- Rejects legacy local broker-secret approval.
- Consumes a durable `ALLOW_ONCE` decision only after operator verification,
  then issues the **existing worker IPC ticket format** with a per-worker secret.
- Rejects command, task, workspace, session mismatches and replay.
- Leaves the existing default `TrustedApprovalAuthority` for compatibility;
  **default construction does not turn on production operator authentication**.

## Requirements before any production use

1. Implement a trusted server-side WebAuthn relying-party flow or OIDC verifier
   with cryptographic issuer/signature, audience, expiry, nonce and role checks.
   WebAuthn must check expected challenge, origin, RP ID hash, user presence/
   verification, assertion signature, and credential owner/counter policy.
2. Compute `operator_decision_challenge(request, decision)` only from the
   trusted persisted approval request. It domain-separates and hashes action ID,
   worker session, task, command digest, canonical workspace, unique request
   nonce, created/expiry timestamps, and **decision type**. The trusted RP must
   verify a fresh assertion bound to this challenge, not merely check that an
   identity token belongs to a user. Require an explicit decision for each
   approval; `ALLOW_ONCE` proof cannot authorize `DENY` or another action.
   A reusable identity bearer token is **not** an action approval.
3. Keep verifier and resolution API off all MCP/model/worker-callable surfaces.
   Do not inject callbacks derived from model-controlled input or untrusted code.
4. Use durable approval storage protected by a separate least-privilege OS
   identity. Separate audit anchor/chain verification from worker writable state.
5. Fail closed on unavailable verification, broker replay, operator mismatch,
   crash, rollback or lost external approval evidence. Record the exact action.
6. Complete real Windows/Linux host adversarial tests and have an independent
   security reviewer validate trust boundaries before claiming issue #22 complete.

## Verification scope

`tests/test_verified_operator_authority.py` exercises the adapter and a real
worker subprocess through the command dispatcher using a clearly labeled
**test-only** HMAC decision challenge. These fixtures demonstrate replay and
wrong-decision denial, **not** WebAuthn user verification, RP origin validation,
credential signature verification, IdP role provenance or production SSO. Check exact-head four-platform GitHub CI; these
checks establish functionality, not enterprise security certification.

E18 remains `BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)`. There is no default
fail-open to authenticated human approval merely by importing this module.
