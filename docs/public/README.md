# Simpul documentation

**Latest published release:** [v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4) (28 October 2026), [CI 4/4 PASS](https://github.com/rzqllh/SubagentBridge/actions/runs/40622640492) and [signed release workflow SUCCESS](https://github.com/rzqllh/SubagentBridge/actions/runs/40623111287). Supervised security patch, **NOT enterprise certification**.

Simpul is a **supervised, native-first MCP subagent supervisor** with **Antigravity IDE as its primary intended host**. Orca/Cindy inform the worker/dispatch/queue roadmap, but complete UI/host parity is **not** claimed. The public name is Simpul; the Python package and MCP server identifier remain `subagentbridge` for compatibility.

**Start here**
- **[Install + use in Antigravity IDE](GETTING_STARTED.md)** — Windows/Linux, MCP settings, first goal and troubleshooting
- **[Orca/Cindy parity and Antigravity-first roadmap](PARITY_AND_ROADMAP.md)** — shipped vs missing
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

v1.1.4 is **supervised security-hardening software**, not a sandbox for hostile code. CI verifies Ubuntu/Windows on Python 3.11 and 3.13; Python 3.12 is declared supported but is not separately in that matrix.

`AUTONOMY: OFF` and `GATE_MODE: CHAT_APPROVAL` remain enforced operational policies. Worker and lead share the operating-system user; E18 is **BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)**. Human-approval tests use trusted fixtures; a production out-of-band authenticated UI is **not** included. Do not turn on unattended privileged execution.

See the [release notes](RELEASE_NOTES.md) and [security guide](SECURITY.md) before use.
