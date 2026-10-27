# Simpul

**Simpul** (formerly **SubagentBridge**) is a native-first Model Context Protocol (MCP) subagent supervisor for supervised development workflows. It targets Google Antigravity IDE and other compatible MCP stdio hosts. Its architecture separates orchestration, worker identities, policy gates, evidence and local model transport.

> **Published:** [Simpul v1.1.1](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.1), 27 October 2026, merge SHA `861f040dc12c33da681331e454ef41299f2dc70b`. 4/4 CI PASS; release workflow [40444832484](https://github.com/rzqllh/SubagentBridge/actions/runs/40444832484) SUCCESS. Supervised runtime patch, **not** enterprise OS isolation certification.

## What is implemented in Simpul

- Typed `Run`, `Task`, `Dispatch`, `Evidence` and approval contracts.
- SQLite-backed audit events, message bus and budget reservations with transaction controls.
- Policy classification, operation-bound approval broker and replay checks.
- Supervised read-only executor, bounded output and worker lifecycle components.
- PM → Developer → QA coordinator and evidence/receipt interfaces.
- Locally pinned skills registry with path and hash checking.
- Local-loopback 9Router text-client interface with explicit model discovery and budget bounds.
- MCP stdio server with run submission, readback, cancellation, and supervised execution tools (`submit_goal`, `execute_run`, `execute_task`).
- Native multi-worker team coordination: Lead/Worker distinct sessions, durable priority dispatch queue, status lifecycles, SQLite transactional persistence, worktree isolation, and crash recovery (architecturally inspired by Cindy research, independently implemented in Python).

**Execution Lifecycle:** `submit_goal(..., execute=True)` or `execute_run(run_id, commands=...)` executes the complete supervised PM → Developer → QA lifecycle. Under SIM-403 strict fail-closed enforcement, tasks without genuine execution commands cannot issue receipts or achieve `VERIFIED` status.

See [Worker Isolation & Environment Security](docs/WORKER_ISOLATION.md) for credential-environment scrubbing and the experimental Linux dedicated-user policy. The E18 operating-system security boundary remains **BLOCKED**.

## Safety and evidence status

| Area | Current boundary |
| --- | --- |
| Autonomy | `AUTONOMY: OFF`; unattended privileged changes are prohibited |
| Worker containment | D-01 `RISK_ACCEPTED_SAME_IDENTITY`; **not** OS-level isolation (E18 classified as **BLOCKED**) |
| Human decisions | D-03 `CHAT_APPROVAL`; an LLM is not an authenticated human approver |
| Model transport | D-02 local literal IP loopback with verified Bearer token authentication |
| Verification | 23 October Post-Release Corrective Audit: 330 passed, 4 skipped across Windows test discovery |
| Confinement Status | E18 is **BLOCKED**; standard OS user permissions cannot isolate workers under same UID; autonomy strictly forbidden |
| Host Integration | MCP stdio protocol/subprocess tests verified; independently validate real Antigravity/Codex/Claude host integration for each deployment |

See [project status](docs/SIMPUL_STATUS.md), [acceptance gates](docs/simpul/ACCEPTANCE_GATES.md), and [security limitations](docs/COMPATIBILITY_LIMITATIONS.md).

## Quick start — v1.1.1

Requires Python 3.11–3.13 and Git. Example for PowerShell:

```powershell
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge
git checkout v1.1.1
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe -m subagentbridge.server
```

The last command runs an MCP stdio server and expects an MCP client; it does not open an interactive chat. Installing dependencies may access package indexes. Consult the [installation guide](docs/INSTALLATION_QUICKSTART.md) for Linux and configuration considerations.

### MCP host entry

Use the venv's Python interpreter, or launch your MCP host with that venv on `PATH`:

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

The display name is **Simpul**, but the MCP tool namespace, Python module, distribution, and `SUBAGENTBRIDGE_*` settings intentionally keep their existing technical identifiers. No mandatory migration/renaming is implied.

### Exposed production-oriented MCP operations

`submit_goal(goal, workspace_path=None, model=None)`, `get_run(run_id)`, `list_tasks(run_id)`, `get_task_evidence(run_id, task_id)`, `get_pending_approvals()`, `reject_approval(action_id, reason="")`, `get_model_usage()`, and `cancel_run(run_id, reason="")`.

The legacy session inspection endpoints remain available in this candidate, but legacy raw-runner execution paths are locked down. `approve_action` and `apply_code_fix` are **not model-callable MCP tools**; their compatibility functions deny privileged operations.

## Multi-worker coordination (C01–C07, v1.1.0)

The [C07 integration PR #16](https://github.com/rzqllh/SubagentBridge/pull/16) merged into `main`, and these capabilities are **included in v1.1.0 but not v1.0.0**.

Simpul now maintains separate Lead and Worker session identities, OS subprocess IPC, a durable SQLite task queue, step-indexed checkpoints, authenticated message and artifact handoffs, per-worker Git worktrees, and capability-checked host adapters. The core is Python-based and does not require running Cindy.

The application-facing names are `AgentRole`, `AgentSession`, `AgentTeam`, `TeamStore`, `TeamManager` and `IntegrationProbe`. Legacy `Orca*` Python aliases and read-only `orca_*` SQLite views remain as **migration compatibility**, not separate runtime engines. New databases use `simpul_*` tables; migration includes a pre-migration SQLite online backup, explicit transaction rollback, full-column row comparison and concurrent initializer tests. Legacy SQL views are **read-only**; consumers must write through the Python store API.

Operational boundaries remain important: host capability declaration is not proof of an interactive external host end-to-end deployment; subprocess isolation is not an OS sandbox; automated test approval is not authenticated human approval; and a crash between an external side effect and its checkpoint can require operator reconciliation. No autonomous merge/release is permitted absent operator authorization.

For architecture and the exact implementation/verification distinction see [core parity report](docs/simpul/SIMPUL_CINDY_PARITY_REPORT.md) and [release readiness](docs/simpul/RELEASE_READINESS.md). Source attribution to [Cindy](https://github.com/makecindy/cindy) is maintained in [third-party notices](THIRD_PARTY_NOTICES.md). Simpul is independently implemented and is not a Cindy fork.

## Documentation

- [Enterprise production readiness and unresolved security gates](docs/ENTERPRISE_READINESS.md) — explicit PASS/PARTIAL/BLOCKED criteria; v1.1.1 is a supervised corrective patch, not certification.

- **[Start here: public user documentation](docs/public/README.md)** — installation, MCP integration, architecture, migration, security and release notes.

- [Developer roadmap, backlog, acceptance gates and next-session handoff](docs/simpul/README.md)

- [Project status and evidence boundaries](docs/SIMPUL_STATUS.md)
- [Installation](docs/INSTALLATION_QUICKSTART.md)
- [MCP integration](docs/MCP_INTEGRATION.md) · [API reference](docs/API_REFERENCE.md)
- [Architecture](docs/ARCHITECTURE.md) · [Configuration](docs/CONFIGURATION.md)
- [Security / HITL](docs/SECURITY_APPROVAL_MODEL.md) · [Confinement](docs/TOOL_EXECUTOR_CONFINEMENT.md)
- [9Router](docs/NINE_ROUTER_SETUP.md) · [Skills registry](docs/SKILLS_REGISTRY.md)
- [Compatibility and limitations](docs/COMPATIBILITY_LIMITATIONS.md)
- [Historical candidate test evidence](docs/ACCEPTANCE_MATRIX_E01_E21_EVIDENCE.md)

## License and attribution

[MIT](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md) (including Cindy/Orca architectural attribution under Apache-2.0). Technical identity retains `SubagentBridge` identifiers for compatibility.
