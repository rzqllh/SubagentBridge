# Simpul — MCP API reference (development candidate)

The public name is **Simpul**; the Python module and MCP server name remain `subagentbridge`. This reference describes signatures found in `subagentbridge/server.py` on the `integrate/roadmap-v4-verified` branch as reviewed 23 October 2026, **not** the older default-branch implementation.

## Production-oriented tools

| MCP tool | Actual arguments | Observed behavior / limit |
| --- | --- | --- |
| `submit_goal` | `goal: str, workspace_path: str \| None = None, model: str \| None = None` | Creates an in-memory `SUBMITTED` run and one `PENDING` task, attempts to append a submission event. **Does not dispatch an agent in this handler.** |
| `get_run` | `run_id: str` | Reads the in-process run table, or returns `NOT_FOUND` |
| `list_tasks` | `run_id: str` | Returns in-process task snapshots |
| `get_task_evidence` | `run_id: str, task_id: str` | Returns task status, evidence ID list, and status-derived `verified` flag; does **not** itself validate a receipt |
| `get_pending_approvals` | none | Reads pending actions |
| `reject_approval` | `action_id: str, reason: str = ""` | Records rejection; not human approval |
| `cancel_run` | `run_id: str, reason: str = ""` | Marks an in-process run and nonterminal tasks cancelled |
| `get_model_usage` | none | Reads legacy session usage and, when available, budget snapshot |

Run/task lookup tables are currently in process memory. Treat an audit event as history, **not** proof that run-state rehydration is implemented.

## Legacy diagnostic tools still registered

`spawn_agent(session_id, workspace_path, runner="agy", model=None, agent_type=None, reasoning_effort=None, skip_permissions=False, hitl_enabled=True, max_retries=2)`, `send_message(session_id, message)`, `wait_for_idle(session_id, timeout_seconds=600)`, `get_agent_status(session_id)`, `list_agents()`, `kill_agent(session_id)`, `reject_action(action_id, reason="")`, and `list_pending_actions(session_id=None)`.

These are compatibility/diagnostic surfaces. Existing legacy execution lockdown means registering a tool is not evidence of permission to execute unsafe workers. Do not set `skip_permissions=True` or `hitl_enabled=False` to try to bypass the gate.

## Removed from MCP exposure by P0 lockdown

In the retained legacy raw-runner paths, legacy worker execution is **disabled** before the unsafe subprocess launch. This is not a claim that the new `submit_goal` endpoint automatically dispatches workers. The following legacy compatibility callables do not grant approval or write permission.

## Deliberately not exposed as MCP tools

- `approve_action(...)` is a compatibility callable returning denial, not authenticated permission.
- `apply_code_fix(...)` is a compatibility callable returning denial, not a code-edit tool.

The separate `ApprovalBroker` module has one-time token and fingerprint checks but an authenticated human approval channel, accessible independently of same-user workers, **has not been proven**.

## MCP resources

Currently registered: `agy://logs/{session_id}` and `agy://pending/{session_id}`. Do not assume other legacy or design-only resource URIs are available.

See [Simpul status](SIMPUL_STATUS.md), [MCP setup](MCP_INTEGRATION.md) and [security](SECURITY_APPROVAL_MODEL.md).
