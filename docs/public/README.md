# Simpul documentation

Simpul is a **supervised, native-first MCP subagent supervisor**. The public name is Simpul; the Python package and MCP server identifier remain `subagentbridge` for compatibility.

**Start here**
- [Installation and first connection](GETTING_STARTED.md)
- [Architecture and execution flow](ARCHITECTURE.md)
- [Human approval, threat model and limitations](SECURITY.md)
- [Data migration and rollback](MIGRATION.md)
- [Release notes and support policy](RELEASE_NOTES.md)
- [Third-party notices and Cindy credit](../../THIRD_PARTY_NOTICES.md)

## Capabilities

- MCP stdio host integration; no standalone chat UI
- Supervised PM → Developer → QA execution with evidence requirements
- Independent worker OS subprocesses with stdio IPC; durable lead/worker sessions and SQLite queue
- Multi-worker dispatch, message history, steering, interruption and structured handoff
- Worktree assignment, checkpoint-based recovery and native Simpul SQLite schema
- Capability-declared host adapters (a registered adapter is not proof of live host integration)

## Supported and unsupported boundaries

The 1.1.0 candidate is **supervised beta software**, not a sandbox for hostile code. CI verifies Ubuntu/Windows on Python 3.11 and 3.13; Python 3.12 is declared supported but is not separately in that matrix.

`AUTONOMY: OFF` and `GATE_MODE: CHAT_APPROVAL` remain enforced operational policies. Worker and lead share the operating-system user; E18 is **BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)**. Human-approval tests use trusted fixtures; a production out-of-band authenticated UI is **not** included. Do not turn on unattended privileged execution.

See the [release notes](RELEASE_NOTES.md) and [security guide](SECURITY.md) before use.
