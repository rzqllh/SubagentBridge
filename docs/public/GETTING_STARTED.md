# Install and use Simpul v1.1.4 with Antigravity IDE

**Latest published release:** [v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4), 28 October 2026. **Primary target:** Google Antigravity IDE, via a **local MCP stdio server**. Simpul is a supervised Python subagent *supervisor*, not an IDE extension, autonomous agent replacement, or standalone chat application.

**Safety first:** only use trusted disposable workspaces, preferably under a dedicated OS account. Default workers are not OS-sandboxed from the supervisor. `AUTONOMY: OFF` and `GATE_MODE: CHAT_APPROVAL`; real privileged actions cannot be self-approved by a model. Genuine WebAuthn/OIDC operator authentication is not included.

## 1. Install from the published release

Prerequisites: Python 3.11 or 3.13 (both tested on Windows and Ubuntu), Git, and Antigravity IDE. Python 3.12 is declared compatible but is not part of the four-job CI matrix.

**Windows PowerShell:**

```powershell
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge
git checkout v1.1.4
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -c "import subagentbridge.server; print('Simpul MCP import OK')"
```

**Linux (bash):**

```bash
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge
git checkout v1.1.4
python3.11 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -c "import subagentbridge.server; print('Simpul MCP import OK')"
```

These commands install from the **tag**, not the latest development branch. `pip install -e .` is a local editable install for this checkout; the release also has a [wheel and source archive](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4). This guide makes **no claim** that v1.1.4 is available on PyPI.

**Do not run** `python -m subagentbridge.server` manually and expect a chat window. It is an MCP stdio process waiting for its host client. The optional `-c` smoke test above only checks package import.

## 2. Connect to Antigravity IDE (primary path)

According to the [official Antigravity MCP guide](https://antigravity.google/docs/mcp):

1. Open the **Agent** side panel in Antigravity IDE.
2. Choose **… → MCP Servers → Manage MCP Servers → View raw config**.
3. Open `mcp_config.json`. For a global server use `~/.gemini/config/mcp_config.json`; for a single project use `<workspace>/.agents/mcp_config.json`.
4. Add the `subagentbridge` entry below **inside the existing** `mcpServers` object. Preserve any other installed servers.

Windows example (replace `YOUR_USER` with the real account and directory; JSON uses escaped backslashes):

```json
{
  "mcpServers": {
    "subagentbridge": {
      "command": "C:\\Users\\YOUR_USER\\Documents\\Code\\SubagentBridge\\.venv\\Scripts\\python.exe",
      "args": ["-m", "subagentbridge.server"]
    }
  }
}
```

Linux example (replace `YOUR_USER`):

```json
{
  "mcpServers": {
    "subagentbridge": {
      "command": "/home/YOUR_USER/SubagentBridge/.venv/bin/python",
      "args": ["-m", "subagentbridge.server"]
    }
  }
}
```

Use the **absolute path to the venv interpreter** for your actual checkout. Do not insert approval tokens, provider credentials or other secrets in public configuration examples. Refresh/reload MCP servers in Antigravity and confirm that Simpul tools appear. The IDE's MCP permission dialog is separate from Simpul's own execution approval policy.

This is a documented MCP connection procedure, **not proof of live acceptance for every installed Antigravity version**. IDE menus can change; consult the official guide if yours differs.

## 3. First safe usage

Use the Antigravity Agent panel to call these MCP tools, or ask your assistant to use them **by exact name**:

1. `submit_goal(goal="Audit the README for clarity", workspace_path="ABSOLUTE_PATH_TO_TRUSTED_REPO")` creates a supervised run and a run ID; by default it **does not execute code**.
2. `get_run(run_id="RETURNED_RUN_ID")` reads that run; `list_tasks(run_id="RETURNED_RUN_ID")` lists task states.
3. `get_pending_approvals()` shows gated actions, if any; `reject_approval(action_id="...", reason="Not authorized")` explicitly denies one.
4. `get_task_evidence(run_id="...", task_id="...")` inspects evidence. A `SUBMITTED`, `BLOCKED`, or successful process exit is **not** a verified coding completion.

For actual supervised execution, `execute_run(run_id, commands={...})`, `execute_task(run_id, task_id, command=[...])`, or `submit_goal(..., execute=True, commands={...})` exist. Only an explicitly trusted and **allowed** command may run; all other commands stay `BLOCKED` until a genuinely trusted approval is available. A chat message saying "approved" is **not** a cryptographic human approval. No `Always Allow` shortcut is provided.

Simpul has a **native multi-worker orchestration engine** (worker processes, queue, handoffs, worktrees and recovery). Its Python team APIs are not all exposed as separate MCP tools; simply connecting the server does **not** add a new IDE sidebar or guarantee that any arbitrary coding request auto-spawns independently authorized workers. See [MCP tool reference](../API_REFERENCE.md) and [Orca/Cindy parity roadmap](PARITY_AND_ROADMAP.md).

## 4. If something does not work

- **MCP server not found:** check the exact executable path and JSON syntax, then refresh/reload MCP servers. Do not add a second top-level `mcpServers` block.
- **Process exits immediately:** run the exact interpreter with `-c "import subagentbridge.server"` from a terminal to check Python dependency/import issues; running a stdio server outside an MCP client is not an interactive test.
- **Actions return BLOCKED:** expected for commands without adequate authorization. Do not disable approval checks or grant the model your OS credentials.
- **Wrong workspace:** always supply an **absolute trusted repository path** to `workspace_path`; never assume the IDE and MCP process share the same working directory.
- **Recovery or privileged-operation uncertainty:** stop and reconcile evidence with a trusted operator; do not automatically replay unknown external side effects.

## What is actually supported

**Implemented (bounded CI evidence):** MCP stdio, explicit run tools, native worker subprocesses, SQLite queue/handoff/checkpoints, Git worktrees, tests on Ubuntu/Windows Python 3.11/3.13, action-specific **opt-in** approval verification and release provenance. **Not verified as production safety:** hostile-worker sandbox (E18), real WebAuthn/OIDC authenticated operator UI, independent Antigravity IDE host acceptance across versions, and exactly-once arbitrary external side effects.

See [security guide](SECURITY.md), [current release](RELEASE_NOTES.md), and [main installation reference](../INSTALLATION_QUICKSTART.md).
