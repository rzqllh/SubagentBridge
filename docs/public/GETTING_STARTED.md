# Get started with Simpul

The documented `subagentbridge` distribution is a supervised MCP stdio server, not a desktop app.

## Requirements

Python 3.11–3.13, Git, and a compatible MCP stdio client (for example, a developer IDE). Linux and Windows are tested in CI on Python 3.11 and 3.13. An MCP host integration must be validated against your actual installed host version.

### Windows PowerShell

```powershell
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge
git checkout v1.1.1
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pytest tests artifacts/bootstrap/v3_1/tests -rs
.\.venv\Scripts\python.exe -m subagentbridge.server
```

### Linux

```bash
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge
git checkout v1.1.1
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m pytest tests artifacts/bootstrap/v3_1/tests -rs
.venv/bin/python -m subagentbridge.server
```

The commands above check out the [published v1.1.1 tag](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.1) for reproducible installation; do not substitute a moving development branch.

The server waits for a client on MCP stdio; it does not print a chat prompt. Keep ordinary logging off protocol stdout.

## Add to an MCP client

Use the installed virtual environment interpreter as `command` (replace `python` with its absolute path if your host uses a different environment):

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

Host configuration locations and supported configuration keys vary. This is a generic MCP stdio example, not a claim of universal IDE configuration compatibility.

## First safe workflow

1. Connect the MCP server to your host and inspect its available tools.
2. Select an explicitly trusted workspace.
3. Use `submit_goal` to register the intended work; inspect `get_run` and `list_tasks`.
4. For real execution, supply the required commands only through a trusted supervised workflow. Unauthorized model-supplied commands must remain blocked, not silently approved.
5. Review evidence and QA results; do not infer success from a successful process exit alone.

`approve_action` is intentionally not model-callable. See [security](SECURITY.md) for actual human-approval limitations. Never paste API keys, approval secrets, or production credentials into example JSON.
