# Simpul : v1.1.4 MCP API reference

**Current published release:** [v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4), 28 October 2026. Source-of-truth for actual model-callable tools is the `@mcp.tool()` registration in `subagentbridge/server.py`. The public product name is **Simpul**; `subagentbridge` is intentionally preserved for MCP and Python compatibility.

## Primary supervised tools

| Tool | Signature | Semantics |
|---|---|---|
| `submit_goal` | `goal: str, workspace_path: str \| None = None, model: str \| None = None, execute: bool = False, commands: dict[str, list[str]] \| None = None` | Creates a run and initial task in the SQLite-backed registry; without `execute=True`, returns `SUBMITTED` instead of running code |
| `get_run` | `run_id: str` | Reads recorded run status, or NOT_FOUND |
| `list_tasks` | `run_id: str` | Reads associated task state |
| `execute_run` | `run_id: str, commands: dict[str, list[str]] \| None = None` | Attempts supervised PM/Dev/QA lifecycle, denies commands outside the trusted allowlist unless a genuine authorization route exists |
| `execute_task` | `run_id: str, task_id: str, command: list[str] \| None = None` | Attempts a specific supervised task and returns evidence/status; blocked execution is not success |
| `get_task_evidence` | `run_id: str, task_id: str` | Reads evidence and QA status of the identified task |
| `get_pending_approvals` | none | Inspects pending actions; not a grant operation |
| `reject_approval` | `action_id: str, reason: str = ""` | Explicitly rejects a pending privileged action |
| `get_model_usage` | none | Reports budget / usage where available |
| `cancel_run` | `run_id: str, reason: str = ""` | Requests cancellation of an active run |

A **safe first call** is `submit_goal(goal="Review this trusted project's documentation", workspace_path="ABSOLUTE_TRUSTED_REPOSITORY_PATH")`, followed by `get_run` and `list_tasks` with the returned ID. A model message containing "approve" is **never** proof of authenticated human intent; `get_pending_approvals` and `reject_approval` are not approval-grant tools.

## Removed from MCP exposure by P0 lockdown

The legacy worker execution is **disabled** before its unsafe raw-runner dispatch path can execute. The Python compatibility callables `approve_action` and `apply_code_fix` are deliberately **not** exposed as model-callable MCP tools and do not authenticate or approve privileged commands. A caller must never bypass permission gates by setting `skip_permissions=True`.

## Other / historical interfaces

The source retains legacy session inspection and diagnostics (`spawn_agent`, `send_message`, `wait_for_idle`, `get_agent_status`, `list_agents`, `kill_agent`, `reject_action` and `list_pending_actions`). Registered names should not be mistaken for unrestricted execution: legacy raw-runner routes and unsafe approval paths are deliberately default-denied.

`approve_action` and `apply_code_fix` are **not** model-callable MCP tools. The Python-level native team manager, dispatch, queue, steering, worker and crash-recovery interfaces do **not** all have a one-to-one MCP endpoint.

## Capability and persistence boundaries

The server rehydrates registered runs/tasks from SQLite at startup; this does not imply that every partially completed external side effect can be safely replayed. Simpul supports native supervised worker subprocesses, but **hostile-worker OS isolation is not certified** (E18). The opt-in verified-operator adapter requires a trusted action-specific verifier, **not provided** as a production WebAuthn/OIDC relying party. CI unit tests and MCP subprocess tests are not independent live acceptance of a specific Antigravity IDE installation.

See [Antigravity setup](public/GETTING_STARTED.md), [MCP integration](MCP_INTEGRATION.md), [parity](public/PARITY_AND_ROADMAP.md) and [security](public/SECURITY.md).
