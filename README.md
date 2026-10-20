# SubagentBridge

Native-first, **experimental** MCP-based subagent supervisor under development for Antigravity IDE. The repository contains an initial MCP server, async session manager, runner interface and SQLite store; it is **not** an independently verified multi-agent engineering team or a security boundary.

## Current implementation status (PR-00)

- Source present: `subagentbridge/server.py`, `manager.py`, `storage/sqlite_store.py`, `runners/base.py`.
- On `main`, the runner registry is empty. Names shown in legacy runner docs are proposed backends, **not supported active runners**. An unmerged `hardening/m2.5-runtime-safety` branch contains experimental runner and bootstrap work; it is not incorporated in this PR.
- **P0 lockdown at this PR HEAD:** `approve_action` is retained only as a denied compatibility callable, **not** exposed as an MCP tool; the pending-action queue rejects positive approvals without a trusted broker. `skip_permissions` now defaults to `False`, and attempts to set it to `True` or disable HITL are rejected. Legacy worker execution and direct `apply_code_fix` writes are blocked before side effects. A true human approval broker, tool executor and OS confinement are **not implemented**. Reading CLI `tool_call` events after side effects is not pre-execution enforcement.
- `Session.kill()` does not establish whole-process-tree termination on Windows; workspace checks are not scoped per dispatch/role; retry prompt reminders cannot establish idempotence.
- **AUTONOMY: OFF.** Do not connect an unconfined CLI or use this experimental server for unattended privileged changes. No production security, recovery, QA VERIFIED, 9Router or Orca support is claimed.
- Team Rules `docs/TEAM_RULES.md` is binding. See `docs/SECURITY.md`, `docs/INVARIANTS.md` and `docs/TEST_PLAN.md`.

## Bootstrap baseline and verification

Active *planning* references: `artifacts/bootstrap/v3_1/ACTIVE_BASELINE.md`; v1/v2/v3 are archived, not silently rewritten. The v3.1 BVE helper captures bootstrap verification evidence, **not** product `ExecutorReceipt`s. PR-00 CI runs standard-library contract tests on Ubuntu and Windows but passing that CI, especially with named expected failures, is **not** production QA.

To run the PR-00 baseline tests (Python 3.11+):

```sh
python -B -m unittest discover -s tests -p 'test_*.py' -v
```

The tests currently have known unmet security invariants marked `expectedFailure`. These are a visible **red security backlog**; any `unexpected success` requires investigation and independent review, not a silent acceptance. No dependency installation is required for these tests.

## Roadmap

Follow the versioned Plan v3.1 through separate, independently verified PRs: domain/state contracts, durable audit, human approval and OS trust boundary, tool-proxy executor, 9Router worker runtime, PM/Developer/QA team, skills, messaging, independent QA, Antigravity, optional Orca, then release hardening. Orca is **never** required for native mode.

## Attribution and license

Design references are credited in `THIRD_PARTY_NOTICES.md`. Repository license is in `LICENSE`. This PR does not add or change a dependency or a license.
