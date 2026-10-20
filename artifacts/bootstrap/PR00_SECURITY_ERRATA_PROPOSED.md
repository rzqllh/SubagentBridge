# PR-00 Security and Verification Errata (proposed amendment to Plan v2)

**Status:** PROPOSED; binding TEAM_RULES remain unchanged. The uploaded Plan v2, Goal v2 and verifier prompt are preserved without modification in `artifacts/bootstrap/`. This addendum does not silently supersede them. Ratification and an updated integrity-checked Goal are needed before implementation beyond PR-00.

## P0 — approval identity and trust boundary
- Never equate an agent-facing MCP call, localhost HTTP, UI dialog click, or shared-user token with authenticated human intent.
- A same-OS-user worker with arbitrary shell access must be considered capable of spoofing a broker and editing its state. Challenge-only protocols are insufficient without a demonstrable isolation boundary.
- PR-03 can deliver/test the **decision engine** and unprivileged approval requests. It cannot claim an enforced human broker when a raw-shell worker runs with equivalent privileges.
- **Revise Phase B entry condition:** only after broker **and** an appropriate executor confinement/capability boundary are independently verified (PR-04b or later). Otherwise remain `GATE_MODE: CHAT_APPROVAL` in supervised bootstrap, and do not launch unconfined autonomous workers.
- Human approval in Phase A is a process protocol, not a technical authenticity guarantee; use it only while work is supervised. Always BLOCK on missing/ambiguous human authorization.

## P0 — execution trust vs test invocation
- Worktrees, Windows Job Objects and shell allowlists are **not** a filesystem/network security sandbox. Repo build scripts/tests execute arbitrary code; no capability guarantee exists without OS-level isolation. `trusted_repo` is informed human risk acceptance, not enforcement.
- API-based coding workers must exclusively use Bridge-owned tools with a verified constrained execution boundary. External CLI bypass permissions are denied in autonomous mode until separately verified.
- Untrusted repos must not execute their own tests under the privileged Bridge or broker account. Explicit classification `UNSUPPORTED_ENFORCEMENT` blocks autonomous execution.

## P1 — receipts, QA, and bootstrap contract
- Separate `BootstrapVerificationRecord` (fresh independent verifier, Phases A/B) from `ExecutorReceipt` (Bridge-owned executor, Phase C). Do not claim a receipt from an unimplemented issuer.
- PR-03b can reach a **test-only simulated verified state** via a fake QA verifier and fake executor. Fakes must be impossible to configure in production. No claim of deployed QA from this skeleton.
- `QA VERIFIED` requires independently derived test cases, executable receipts bound to exact clean tree, acceptance mapping, QA-owned test hashes, and provenance. Process exit zero alone is never a QA verdict.
- An attacker with equal OS privileges may forge evidence/audit storage; the receipt and audit trust model is conditional on the verified runtime isolation boundary. Hash chains detect accidental/application-level modifications, not privileged attackers.

## P1 — verifier and local-only git mechanics
- Verifier must access **the exact implementation commit** without unauthorized push: a fresh clone from a readable local path or an explicitly approved Git bundle transfer; never assume the remote has unpushed SHA.
- Make verification cross-platform: on Windows use an appropriate PowerShell SHA-256 and UTC timestamp command; on POSIX use platform-supported equivalents. Capture the **tested command's** exit status, not `tee` pipeline status, and write logs outside the checkout.
- Immutable verifier scenario/test artifacts must be content-hashed and bound to the evidence. Any external verifier tests need a digest and declared import/environment constraints.
- Running an untrusted PR test suite is itself a side-effecting operation; require repository trust/isolation before executing it on the verifier's host.

## P1 — independent source and lifecycle
- PR-00 baseline must enumerate `hardening/m2.5-runtime-safety` (9 commits ahead of main at inspection). Do not overwrite, cherry-pick or merge automatically; audit it during implementation.
- A previous approval is not portable across changed operation fingerprints, tasks, dispatches or policy revisions.
- Cancellation and recovery must reconcile untracked child processes and pending decisions; an unknown process state is `RECOVERY_REQUIRED`, not `idle`.
- Verification is invalidated by any relevant change to the tree/test artifacts; status transitions remain guarded by the same authoritative store in both native and optional Orca modes.

## Ratification and execution gates
Before implementing PR-00B, the human must approve the exact scoped changes and any gated operations in DP-00. Then update the canonical plan/Goal integrity hashes with machine-observed values, and use an independent verifier. Only after all relevant security invariants have executable negative tests may production security guarantees be claimed.
