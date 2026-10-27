# Simpul

**Simpul** (formerly SubagentBridge) is a supervised, native-first [Model Context Protocol](https://modelcontextprotocol.io/) subagent supervisor. It provides a local MCP stdio endpoint, a lead/worker coordination layer and evidence-aware task execution for development workflows.

**Release track:** `v1.0.0` is the previously published baseline. This branch prepares **v1.1.0 (supervised beta)**; a proposed version in `pyproject.toml` or a passing PR is **not** a published release. Check [GitHub Releases](https://github.com/rzqllh/SubagentBridge/releases) for the actual published versions and matching tags.

## What Simpul does

- Runs a supervised PM → Developer → QA lifecycle with command admission, evidence and result verification.
- Exposes an MCP stdio server to a compatible client; it does not provide a standalone chat UI.
- Coordinates multiple native worker subprocesses, each with a separate PID, stdio IPC and bounded lifecycle.
- Persists teams, sessions, queue, messages, handoffs and checkpoints in SQLite WAL.
- Supports dispatch deduplication, steering, interruption, audited recovery and per-worker Git worktrees.
- Validates physical completion artifacts, SHA-256 digests and execution receipts before successful handoff.
- Registers capability-scoped host adapters; adapter presence is not proof of a completed live external-host workflow.

## Installation

Requires Git and Python 3.11–3.13. A release checkout should use a **published** GitHub tag. For current source checkout:

```bash
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge
python -m pip install -e .
python -m subagentbridge.server
```

The last command starts an MCP **stdio** server, not an interactive chat. For virtual environments, platform-specific commands, tests and host configuration, see the [public getting-started guide](docs/public/GETTING_STARTED.md).

Generic MCP client entry (point `command` to your virtual environment's Python when necessary):

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

## Safety boundary

**Supervised beta, not a malicious-worker sandbox.** `AUTONOMY: OFF` and `GATE_MODE: CHAT_APPROVAL` remain operational requirements. E18 same-user OS worker confinement is **BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)**. Separate worker processes are not separate OS security principals. A production out-of-band authenticated human approval UI is not yet integrated. Never treat the in-memory broker fixture or an MCP model message as authenticated human approval.

Git worktrees isolate working copies, not credentials; run unknown code only under an appropriately restricted OS identity and in disposable workspaces.

## Public documentation

- [Documentation index](docs/public/README.md)
- [Get started](docs/public/GETTING_STARTED.md)
- [Architecture](docs/public/ARCHITECTURE.md)
- [Security and limitations](docs/public/SECURITY.md)
- [Legacy SQLite migration](docs/public/MIGRATION.md)
- [Release notes](docs/public/RELEASE_NOTES.md)
- [Existing API reference](docs/API_REFERENCE.md)
- [Historical Cindy/Orca parity engineering report](docs/simpul/SIMPUL_CINDY_PARITY_REPORT.md)

## License and credit

Simpul is MIT licensed; see [LICENSE](LICENSE). The multi-worker architecture was informed by studying [Cindy](https://github.com/makecindy/cindy) by XD Inc. (Apache-2.0). Simpul's Python implementation is independent, not a Cindy fork. See [Third-party notices](THIRD_PARTY_NOTICES.md) for upstream license and pinned research provenance.

The Python distribution, import module, executable and MCP identifier intentionally retain `subagentbridge` for compatibility.
