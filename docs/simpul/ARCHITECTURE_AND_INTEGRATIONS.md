# Simpul — Architecture, runtime truth and integration boundaries

## Target, not-yet-complete production flow

~~~text
Human in Antigravity IDE
  -> MCP stdio: Simpul (subagentbridge.server)
  -> persistent Run + Task DAG + frozen acceptance criteria
  -> policy classifier + human gate (fail closed)
  -> coordinator dispatches appropriate role conditionally:
        PM -> Developer -> Independent QA
        \-> Specialist (only where sensitive/risk demands it)
  -> trustworthy per-dispatch ToolExecutor/worktree
  -> model backend (native 9Router loopback; Orca opt-in only)
  -> issued receipts + tree-pinned QA tests/verdict
  -> durable states, budget, messaging and human handoff
~~~

### Actual limitations at the reviewed source SHA

- `submit_goal` initializes `_runs` and `_tasks` module dictionaries (`SUBMITTED` / `PENDING`) and records a `GOAL_SUBMITTED` audit event in a swallowed-exception block; it does not start a worker.
- `build_production_system` wires many libraries, but initializes `coordinator=None`. Module existence ≠ the real IDE execution path.
- Restart of the MCP server loses those `_runs`/`_tasks` maps; the legacy session store is a different subsystem.
- `get_task_evidence` primarily reports task-state fields; it does not by itself prove a registered QA verdict/issued receipt.
- Single `_production_system` reused for multiple workspace inputs; must become workspace-scoped or refuse mismatched roots.
- Local 9Router Python client supports discovery and bounded text chat; streaming/tool-execution loop is not proven. Prior live completion HTTP 401. Runtime router env variables in older docs are not wired via server composition.
- Risk acceptance under the same OS identity is **not** secure sandboxing. Environment filtering can be bypassed by the currently reviewed `extra_env` path unless repaired.

## Conditional subagents / specialization

Simpul's **product target** is managed PM, Developer, QA and specialist roles; an available role does not mean an always-running worker. Before dispatch, require frozen measurable AC, explicit scope, budget, role/capability match and appropriate policy. Specialists are on-demand for security/review/dependency/architecture needs. QA is separate from Developer; PM cannot waive it. Limit peer discussion to two rounds and Dev↔QA fix loops to three; exhaustion→human `BLOCKED`.

**SIMPUL-01 execution constraint:** Earlier user instruction for the roadmap verification specifically required **Hermes subagents OFF**, serial verifier operation, no PM/Dev/QA/Orca background workers. Retain this for such verification sessions until a new explicit instruction authorizes actual worker dispatch. It is **not** a permanent removal of Simpul's planned role architecture.

## 9Router / provider layer

- Native-first: routing to local 9Router loopback; provider terms, remote egress and cloud usage require separately approved D-02 decisions. A local connection does not guarantee an upstream router never reaches the network.
- Models must be discovered with verified capabilities; "coding" requires confirmed tool calls. Never infer cost/free quotas, capability or available model from the name.
- Model usage: actual / estimated / unknown categories; don't fabricate zero cost when missing.
- No secrets in Markdown, console output, receipts or worker messages. No fallback that silently increases permissions, token budget or provider reach.

## Skills and Xyeena Harness / Xyeena Rig

Plan v3.1 PR-07 treats skill files, `AGENTS.md` and Xyeena Harness modules as **hash-pinned untrusted content/seed policy**, not as a source of permission or runtime security enforcement. Discovery may scan metadata across approved locations; lazy-load only relevant trusted skills per role/task. Unknown/modified skill→human gate. Project > user > global priority applies only *within the skills layer*, never over Team Rules, human approvals or ToolExecutor policy.

**Cross-project architectural intent from conversations:** Xyeena Rig may discover Simpul as an optional subagent backend, alongside native/orchestrated installed skills and external providers. If Simpul is absent/unavailable, Rig uses its own native path. This is an integration *design*, **not verified implementation in Simpul**; do not silently merge the repos or make Simpul depend on Xyeena Rig, Superpowers, Superior Skills, Hermes or Orca. Preserve clean optional adapter boundary.

## Orca

Explicitly optional backend, disabled by default. No hard dependency; no nested coordinator, global reset, double retry, duplicate approval or auto-verified `worker_done`. The native no-Orca E01 path is a separate release gate. CLI that bypasses tool policy is `UNSUPPORTED_ENFORCEMENT` for autonomy until proven OS-confined.

## Windows-first operational acceptance

Antigravity MCP stdio initialization, venv Python selection, SQLite handle close/restart, child/grandchild cleanup, junction/reparse-point prevention, clipboard/UI interactions only where approved by scope. Unsupported controls must remain `UNKNOWN`, never advertised as guaranteed.
