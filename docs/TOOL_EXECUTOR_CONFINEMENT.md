# SubagentBridge: ToolExecutor and Execution Confinement

This document describes how SubagentBridge isolates process execution and enforces workspace confinement boundaries.

---

## 1. Confinement Classes and Invariants

Under Plan v3.1 and Decision D-01:
- `RISK_ACCEPTED_SAME_IDENTITY`: Supervised development mode where execution occurs under the current user account, but with strict path checking, scrubbed environment variables, and timeout supervision.
- `ISOLATED_CONTAINER_OR_VM`: Future target mode for unattended autonomous execution.

---

## 2. Supervised Read-Only Executor (`SupervisedReadOnlyExecutor`)

The `SupervisedReadOnlyExecutor` verifies that safe read commands can run without modifying workspace files:
- Only allowlisted commands (e.g. `python -m unittest`, `git status`, `git rev-parse`) are executed.
- Modifying actions or unapproved file writes fail closed.
- Issues verifiable `ExecutorReceipt` records containing exact command arguments, exit codes, and output hashes.

---

## 3. Environment Sanitization and Isolation (`IsolatedExecutionRunner`)

When child processes are launched:
- Sensitive environment variables are scrubbed from the child environment:
  - `SUBAGENTBRIDGE_BROKER_SECRET`
  - `SUBAGENTBRIDGE_API_KEY`
  - `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`
  - `GITHUB_TOKEN`
  - `NINE_ROUTER_API_KEY`
  - Any key starting with `SECRET_`
- Child processes cannot inspect parent credentials to forge approvals or bypass limits.

---

## 4. Windows Process-Tree Cleanup

On Windows systems, child subprocesses may leave orphaned processes or open file locks if not terminated cleanly:
- SubagentBridge ensures process-tree termination with configurable timeout limits.
- Process exit codes and standard error streams are captured, hashed with SHA-256, and bound to `ExecutorReceipt` records.
- Verified under Scenario E08 in `tests/test_acceptance_matrix_e01_e21.py`.
