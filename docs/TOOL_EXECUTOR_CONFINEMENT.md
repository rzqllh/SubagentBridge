# Simpul — Supervised execution and containment limits

The PR #3 candidate contains `SupervisedReadOnlyExecutor` and process-management utilities intended for bounded test/inspection workflows. **This is not a sandbox for arbitrary untrusted code.** D-01 is `RISK_ACCEPTED_SAME_IDENTITY`; `AUTONOMY: OFF`.

## Implemented components

- A supervised executor checks permitted command/workspace inputs and records bounded execution outputs and hashes.
- Child environment scrubbing removes selected secret variables from newly launched subprocess environments.
- Process cleanup and timeout code is present, including Windows-focused test coverage.
- QA evidence uses identity/receipt and Git-tree checks in separate modules.

## What these controls do not prove

- A process running as the same user may obtain same-user files, memory, IPC, credentials or UI access even if selected child environment variables were stripped.
- Running `python -m unittest` can execute arbitrary repository test code; command allowlisting alone is not read-only confinement.
- A hash or receipt generated in-process is not tamper-proof against a privileged or same-identity attacker.
- Unit-test process teardown is not exhaustive proof of Windows child-process-tree cleanup under every failure mode.
- Git worktree checks alone do not close checkout-root symlink/junction/race escapes (E22).

Treat `ISOLATED_CONTAINER_OR_VM` or separate OS identities as **future proof requirements**, not existing feature claims. E18/E22/E23 and full live IDE verification remain unresolved. See [Security](SECURITY_APPROVAL_MODEL.md).
