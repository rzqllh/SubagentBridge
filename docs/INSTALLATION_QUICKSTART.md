# Simpul — Installation and Quick Start

**Current published release:** [v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4) (28 October 2026). The Python package and executable namespace remain `subagentbridge`.

## Requirements

- Python **3.11–3.13**; CI exercises 3.11 and 3.13 on Windows and Linux. Python 3.12 is declared compatible but is not in the current four-job CI matrix.
- Git, a compatible MCP stdio client, and permission to create a virtual environment.
- A dedicated, least-privileged user and explicitly trusted workspace. **Do not** expose untrusted credentials or assume workers are OS-sandboxed.

## Windows PowerShell

```powershell
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge
git checkout v1.1.4
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m subagentbridge.server
```

## Linux

```bash
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge
git checkout v1.1.4
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m subagentbridge.server
```

The last command starts an **MCP stdio server** and waits for a client. It is not a terminal chatbot; avoid writing diagnostics to MCP protocol stdout.

**Antigravity IDE primary setup:** See [step-by-step Antigravity IDE installation, MCP menus, config JSON and first safe tool calls](public/GETTING_STARTED.md). The generic snippet below is not a substitute for setting the **absolute** venv interpreter path in the IDE. Simpul is an MCP subagent supervisor, **not** a stand-alone chat UI.

## MCP client configuration

Set your MCP client's `command` to the virtual environment Python (absolute path recommended) and its `args` to `["-m", "subagentbridge.server"]`. A generic example:

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

Each IDE/host uses its own configuration format; an adapter capability declaration is not proof of acceptance testing against every external host version. See [MCP Integration](MCP_INTEGRATION.md) and [public getting started](public/GETTING_STARTED.md).

## Verify locally

With the virtual environment active:

```bash
python -m pytest tests artifacts/bootstrap/v3_1/tests -rs
python -m ruff check --select E4,E7,E9,F subagentbridge
python -m mypy --ignore-missing-imports --check-untyped-defs subagentbridge
python -m bandit -q -r -ll subagentbridge
```

The last three commands require development-only `ruff`, `mypy` and `bandit`; see [Release Readiness](simpul/RELEASE_READINESS.md) for pinned versions.

## Existing SQLite databases

Before migration, keep a separate known-good database backup. The v2 migration creates a logical SQLite pre-migration snapshot (including committed WAL contents) and retains non-colliding older backups. Verify backup readability and `PRAGMA integrity_check` before decommissioning data. SQL `orca_*` compatibility views are read-only; Python compatibility aliases remain. See [migration](public/MIGRATION.md).

## Security and operating mode

`AUTONOMY: OFF` and `GATE_MODE: CHAT_APPROVAL` remain mandatory. A model tool call is not proof of authenticated human approval. E18 same-user OS confinement is **BLOCKED**: worker subprocesses are not independent privilege sandboxes. This release is supervised runtime-hardening, not enterprise isolation certification. See [Security](public/SECURITY.md) and [Enterprise Readiness](ENTERPRISE_READINESS.md).

## Source and attribution

The release tag is immutable for reproducibility; [GitHub Release v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4) includes Python wheel, source distribution, and SHA256 manifest. Cindy's Apache-2.0 architectural research attribution is preserved in [Third-party Notices](../THIRD_PARTY_NOTICES.md). Simpul is an independent Python implementation.
