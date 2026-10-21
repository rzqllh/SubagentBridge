# API Reference: SubagentBridge (Production Release Status)

This document maps the SubagentBridge MCP tool signatures, Python domain contracts, and security interfaces. In PR-00 legacy worker execution is **disabled before launch**, and production execution routes through the typed composition root. `AUTONOMY: OFF`.

---

## 1. Production MCP Tools Registered in `subagentbridge/server.py`

| Tool Name | Parameters | Description |
|---|---|---|
| `submit_goal` | `goal: str`, `run_id: str`, `project_id: str`, `policy_revision: str` | Initializes a new managed orchestration run governed by policy contracts. |
| `get_run` | `run_id: str` | Retrieves current status, policy revision, and execution state of a run. |
| `list_tasks` | `run_id: str` | Lists all tasks and their state machine statuses within a run. |
| `get_task_evidence` | `task_id: str` | Retrieves cryptographic evidence, tree SHAs, and QA verdicts for a completed task. |
| `get_pending_approvals` | none | Lists pending human-in-the-loop approval actions requiring out-of-band authorization. |
| `reject_approval` | `action_id: str`, `reason: str` | Records an explicit human or policy rejection for a pending action. |
| `get_model_usage` | none | Reports token usage and microunit costs recorded by the durable budget ledger. |
| `cancel_run` | `run_id: str` | Cancels an ongoing run and marks active sessions as cancelled. |

---

## 2. Removed from MCP exposure by P0 lockdown

- `approve_action(action_id)`: Removed from MCP exposure by P0 lockdown. Retained only as a compatibility callable returning denied; never registered as an MCP tool. To prevent models from approving their own actions, approvals require out-of-band token resolution via `ApprovalBroker`.
- `apply_code_fix(filepath, target, replacement)`: Retained only as a compatibility callable returning denied; direct arbitrary file mutation without a trusted executor raises `PermissionError`.

These names must not be represented as enabled MCP tools. Do not attempt to bypass this lockdown; all privileged operations require explicit human gate authorization.

---

## 3. Legacy MCP Compatibility Tools

| Legacy Tool | Status | Behavior |
|---|---|---|
| `spawn_agent` | Locked | Enforces `skip_permissions=False` and rejects unregistered runners. |
| `send_message` | Locked | Denies legacy raw runner execution. |
| `wait_for_idle` | Locked | Inspects legacy session state. |
| `get_agent_status` | Locked | Inspects legacy session metadata. |
| `list_agents` | Locked | Lists registered sessions. |
| `kill_agent` | Locked | Initiates process termination with timeout. |

---

## 4. MCP Resources

- `subagentbridge://audit/{stream}`: Append-only audit events for the given stream.
- `subagentbridge://budget/{run_id}`: Budget consumption metrics and reservation states.
- `agy://logs/{session_id}`: Session execution log stream.
- `agy://pending/{session_id}`: Pending action records.
