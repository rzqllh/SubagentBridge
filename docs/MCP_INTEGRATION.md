# SubagentBridge: Antigravity MCP Integration Guide

This guide describes how to connect SubagentBridge as a Model Context Protocol (MCP) server inside Google Antigravity IDE and other MCP-compliant hosts.

---

## 1. Antigravity IDE Configuration

Add SubagentBridge to your Antigravity configuration file (e.g. `mcp_config.json` or `.gemini/antigravity-ide/mcp_config.json`):

```json
{
  "mcpServers": {
    "subagentbridge": {
      "command": "python",
      "args": [
        "-m",
        "subagentbridge.server"
      ],
      "env": {
        "SUBAGENTBRIDGE_DB_PATH": "subagentbridge.db",
        "SUBAGENTBRIDGE_GATE_MODE": "CHAT_APPROVAL",
        "SUBAGENTBRIDGE_ROUTER_URL": "http://127.0.0.1:8080/v1"
      }
    }
  }
}
```

---

## 2. Production Control Plane Tools

The MCP server registers the following high-level orchestration tools:

| MCP Tool Name | Parameters | Purpose |
|---|---|---|
| `submit_goal` | `goal: str`, `run_id: str`, `project_id: str`, `policy_revision: str` | Creates a new managed orchestration run with policy enforcement. |
| `get_run` | `run_id: str` | Inspects state, policy revision, and execution lifecycle of a run. |
| `list_tasks` | `run_id: str` | Lists all tasks and their state machine statuses within a run. |
| `get_task_evidence` | `task_id: str` | Retrieves cryptographic evidence, tree SHAs, and QA verdicts. |
| `get_pending_approvals` | none | Lists pending human-in-the-loop approval actions awaiting tokens. |
| `reject_approval` | `action_id: str`, `reason: str` | Records an explicit denial on a pending action. |
| `get_model_usage` | none | Reports token usage and micro-unit costs recorded by the durable budget ledger. |
| `cancel_run` | `run_id: str` | Cancels an ongoing run and marks active sessions as cancelled. |

---

## 3. Human Approval Security Architecture (P0 Lockdown)

Notice that `approve_action` is **not** an MCP tool.

In SubagentBridge:
- Allowing an AI agent or LLM to call an `approve_action` tool directly would completely defeat Human-in-the-Loop (HITL) safety.
- Therefore, approvals require an out-of-band secret token via the `ApprovalBroker` (`resolve_by_human(action_id, approved=True, auth_token=...)`).
- Workers can only view pending actions via `get_pending_approvals` or record denials via `reject_approval`.
