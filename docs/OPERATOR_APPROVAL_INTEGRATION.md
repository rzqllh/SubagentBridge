# Verified operator approval to worker IPC — integration status

**Enterprise acceptance: BLOCKED.** This module is only the connection between
host-verified operator grants and worker IPC tickets. It does **not** include a
production WebAuthn/OIDC relying party, IdP enrollment, authorization UI, or
Windows/Linux hostile-worker isolation.

## What is implemented

The trusted host may explicitly construct an
`IndependentOperatorApprovalBoundary` with its own authenticated
`operator_verifier`, then inject `VerifiedOperatorApprovalAuthority` into
`WorkerProcessController(approval_authority=...)`.

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
2. Bind approval to a fresh server-generated action challenge including its
   `session_id`, `task_id`, canonical command, canonical workspace, request
   nonce and TTL. A reusable identity bearer token is **not** an action approval.
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
**test-only** verifier. Test fixtures do not represent WebAuthn, a signature
verifier, or production SSO. Check exact-head four-platform GitHub CI; these
checks establish functionality, not enterprise security certification.

E18 remains `BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)`. There is no default
fail-open to authenticated human approval merely by importing this module.
