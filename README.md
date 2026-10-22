# Simpul

**Simpul** (formerly **SubagentBridge**) is a native-first Model Context Protocol (MCP) subagent supervisor for supervised development workflows. It targets Google Antigravity IDE and other compatible MCP stdio hosts. Its architecture separates orchestration, worker identities, policy gates, evidence and local model transport.

> **Development candidate — 23 October 2026:** This branch contains `subagentbridge==1.0.0rc1` source, **not** a published or security-certified release. [PR #3](https://github.com/rzqllh/SubagentBridge/pull/3) remains open and targets [PR #2](https://github.com/rzqllh/SubagentBridge/pull/2)'s baseline branch. The default `main` still contains the older imported prototype.

## What is implemented in this candidate

- Typed `Run`, `Task`, `Dispatch`, `Evidence` and approval contracts.
- SQLite-backed audit events, message bus and budget reservations with transaction controls.
- Policy classification, operation-bound approval broker and replay checks.
- Supervised read-only executor, bounded output and worker lifecycle components.
- PM → Developer → QA coordinator and evidence/receipt interfaces.
- Locally pinned skills registry with path and hash checking.
- Local-loopback 9Router text-client interface with explicit model discovery and budget bounds.
- MCP stdio server with run submission, readback, cancellation and diagnostic tools.
- Optional Orca integration seam; native mode does not depend on Orca.

**Important:** Presence of these modules and passing unit tests does not demonstrate that MCP `submit_goal` automatically executes a complete PM → Developer → QA workflow. In this branch `submit_goal` currently registers a `SUBMITTED` run and a `PENDING` task; it does not dispatch a worker in that handler.

## Safety and evidence status

| Area | Current boundary |
| --- | --- |
| Autonomy | `AUTONOMY: OFF`; unattended privileged changes are prohibited |
| Worker containment | D-01 `RISK_ACCEPTED_SAME_IDENTITY`; **not** OS-level isolation |
| Human decisions | D-03 `CHAT_APPROVAL`; an LLM is not an authenticated human approver |
| Model transport | D-02 local literal IP loopback; upstream router egress is outside this client's guarantee |
| Verification | 21 October report: 250 discovered tests (246 pass, 4 skip), E01–E21 matrix tests; this is historical evidence, not a new independent run |
| Still open | Same-user E18 red-team proof, E22 containment, E23 exact remote checkout, live authenticated 9Router (previously HTTP 401), end-to-end IDE acceptance, merge and release |

See [project status](docs/SIMPUL_STATUS.md) and [security limitations](docs/COMPATIBILITY_LIMITATIONS.md). Do not mark E18/E22/E23 verified from unit-test names alone.

## Quick start — candidate branch

Requires Python 3.11–3.13 and Git. Example for PowerShell:

```powershell
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge
git checkout 44d70b5f05836a867978dcadb166bd1122943a3b
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

## Documentation

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

[MIT](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md). Development history retains `SubagentBridge` names where required for traceability.
