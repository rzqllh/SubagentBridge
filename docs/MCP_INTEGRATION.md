# Simpul — MCP stdio integration

Simpul keeps the technical server/module name `subagentbridge`. This guide applies to the open PR #3 candidate, **not** the default-branch prototype.

## Connect a compatible MCP host

Create a Python virtual environment and install the candidate following [Installation](INSTALLATION_QUICKSTART.md). Configure the host's MCP servers with the **actual venv Python executable**. If `python` already resolves to that venv in the host process, this minimal entry is sufficient:

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

If your IDE launches a different Python environment, replace `command` with an absolute path to the venv's `python.exe` on Windows or `bin/python` on Linux. MCP configuration file locations and exact UI steps vary by host version; confirm them within your installed host.

No production credentials should appear in an example configuration. The server uses stdio; ordinary terminal text printed to stdout can corrupt the MCP protocol.

## Current MCP tool contract

The source exposes `submit_goal(goal, workspace_path=None, model=None)`, `get_run(run_id)`, `list_tasks(run_id)`, `get_task_evidence(run_id, task_id)`, `get_pending_approvals()`, `reject_approval(action_id, reason="")`, `cancel_run(run_id, reason="")` and `get_model_usage()`.

`submit_goal` currently stores a `SUBMITTED` run and a `PENDING` task; it is **not** proof of an executing PM/Developer/QA flow. Live Antigravity MCP acceptance is still pending. See [API reference](API_REFERENCE.md) for exact behavior and legacy diagnostics.

## Security

`approve_action` is deliberately **not** an MCP tool. No model self-approvals, Always Allow, or unattended changes. `AUTONOMY: OFF` and Phase-A `RISK_ACCEPTED_SAME_IDENTITY` are active constraints; same-user isolation has not been demonstrated. See [Project Status](SIMPUL_STATUS.md).
