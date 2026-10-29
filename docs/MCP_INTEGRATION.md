# Simpul v1.1.4 : MCP integration (Antigravity IDE first)

**Published release:** [v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4). `subagentbridge` is the Python package, module and MCP server identifier. Its public product name is **Simpul**.

## Antigravity IDE setup

Use the [first-run installation guide](public/GETTING_STARTED.md) for Windows/Linux commands and exact examples of `mcp_config.json`. The [official Antigravity MCP guide](https://antigravity.google/docs/mcp) describes the IDE steps: **Agent panel → … → MCP Servers → Manage MCP Servers → View raw config**. Global configuration lives at `~/.gemini/config/mcp_config.json`; a workspace-local configuration can live under `.agents/mcp_config.json`.

Add a local stdio server under `mcpServers`; its `command` should be the **absolute path to your virtual environment's Python executable**:

```json
{
  "mcpServers": {
    "subagentbridge": {
      "command": "/absolute/path/to/SubagentBridge/.venv/bin/python",
      "args": ["-m", "subagentbridge.server"]
    }
  }
}
```

On Windows, replace `command` with an absolute `C:\\...\\.venv\\Scripts\\python.exe` path (escape Windows backslashes in JSON). Do not run the stdio server as an interactive terminal chatbot. Its stdout belongs to MCP protocol messages. After configuring, reload the MCP server and inspect tools in your IDE.

## MCP tool surface implemented in v1.1.4

| Tool | Purpose |
|---|---|
| `submit_goal(goal, workspace_path=None, model=None, execute=False, commands=None)` | Register a supervised goal; default only records the run; optional execution remains gated |
| `get_run(run_id)` / `list_tasks(run_id)` | Read run and task state |
| `execute_run(run_id, commands=None)` / `execute_task(run_id, task_id, command=None)` | Attempt explicitly supervised execution; unsafe/unauthorized commands return `BLOCKED` |
| `get_task_evidence(run_id, task_id)` | Inspect reported evidence/QA state, not assume completion from one exit code |
| `get_pending_approvals()` / `reject_approval(action_id, reason="")` | Inspect/deny pending gated actions; **neither grants approval** |
| `cancel_run(run_id, reason="")` / `get_model_usage()` | Cancellation and model usage inspection |

Some historical session tools remain registered as compatibility/diagnostics; arbitrary legacy worker spawning or `approve_action` is **not** a supported autonomous-approval route. Native team/worker Python APIs are not automatically separate MCP tools.

**Safety boundary:** `AUTONOMY: OFF`, `GATE_MODE: CHAT_APPROVAL`; same-user hostile-worker containment E18 is BLOCKED. Simpul ships no standalone human WebAuthn/OIDC approval UI or guaranteed live Antigravity host-integration parity. An MCP client-side permission grant is different from a human operator signing a specific privileged command.

See [API](API_REFERENCE.md), [parity roadmap](public/PARITY_AND_ROADMAP.md), [configuration](CONFIGURATION.md), [security](public/SECURITY.md).
