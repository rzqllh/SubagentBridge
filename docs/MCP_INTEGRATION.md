# Simpul — MCP stdio integration

The Python module and MCP server identifier remain `subagentbridge` for compatibility.

After installing with the [current guide](public/GETTING_STARTED.md), add this generic entry to a compatible MCP client:

```json
{
  "mcpServers": {
    "subagentbridge": {
      "command": "python",
      "args": ["-m", "subagentbridge.server"]
    }
  }
}
```

Replace `python` with your virtual environment's Python interpreter if required. Configuration file locations and exact schemas are host-specific. No server secret should be embedded in this example. Keep diagnostic output away from MCP protocol stdout.

The MCP API includes `submit_goal`, `get_run`, `list_tasks`, `get_task_evidence`, `get_pending_approvals`, `reject_approval`, `get_model_usage`, `cancel_run` and gated execution operations. A stored goal is not proof that code ran; inspect actual execution, evidence and QA states.

**Security:** `approve_action` is not model-callable. E18 same-user confinement remains BLOCKED; no autonomous privileged execution. See [public security guide](public/SECURITY.md) and [API reference](API_REFERENCE.md).
