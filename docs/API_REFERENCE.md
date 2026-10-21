# API Reference — SubagentBridge (PR-00 lockdown status)

This file maps the **current source**, not the unimplemented legacy roadmap. In PR-00 the runner registry has no registered production backends and all legacy worker execution is **disabled before launch**. `AUTONOMY: OFF`.

## MCP tools currently registered in `subagentbridge/server.py`

| Tool | PR-00 behavior |
|---|---|
| `spawn_agent(session_id, workspace_path, runner="agy", model=None, agent_type=None, reasoning_effort=None, skip_permissions=False, hitl_enabled=True, max_retries=...)` | Rejects unregistered runner names and permission bypass/HITL-off parameters; registration alone does not allow execution. |
| `send_message(session_id, message)` | Denies the legacy execution path (error string); no agent subprocess starts. |
| `wait_for_idle(session_id, timeout_seconds=...)` | Inspects legacy session state; **does not** prove Windows process-tree cleanup. |
| `get_agent_status(session_id)` / `list_agents()` | Inspect legacy session metadata. |
| `get_model_usage()` | Aggregates legacy accounting, not verified billing. |
| `kill_agent(session_id)` | Attempts to terminate legacy session process; OS-wide child process guarantees remain unverified. |
| `reject_action(action_id, reason="")` | Records a **denial** on a pending action; it is not an authenticated human decision channel. |
| `list_pending_actions(session_id=None)` | Lists pending legacy queue entries. |

## Removed from MCP exposure by P0 lockdown

- `approve_action(action_id)`: retained only as a Python compatibility callable returning **denied**; never registered as MCP tool. Direct positive `PendingActionQueue.resolve` calls also raise `PermissionError`.
- `apply_code_fix(filepath, target, replacement)`: retained only as a Python compatibility callable returning **denied**; direct `AgentManager.apply_code_fix` also raises `PermissionError`.

These names **must not** be represented as enabled MCP functionality. Do not attempt to bypass this lockdown by calling internals; a trusted broker and scoped ToolExecutor are separate future PR deliverables.

## Current MCP resources

- `agy://logs/{session_id}` — legacy session log.
- `agy://pending/{session_id}` — pending legacy queue entries.

`send_message_with_schema`, `check_inbox`, and `agy://inbox/{session_id}` are historical design/API references, **not registered by the current PR-00 server**.

## Runner names

`agy`, `claude`, GPT-family and DeepSeek-family labels in prior PRD and runner specs are **planned only**. No complete, authenticated or enforced runner has been independently certified on this PR. Never claim GPT model names or APIs are implemented solely because old documents name them.
