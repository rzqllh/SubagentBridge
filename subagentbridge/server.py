"""server.py — Production FastMCP entry point for SubagentBridge.

Hardened MCP interface exposing:
- submit_goal: Initiates a verified lifecycle run under supervised coordination.
- get_run: Reads run status and task counts.
- list_tasks: Lists tasks in a run with their statuses and dependencies.
- get_task_evidence: Retrieves verified executor receipts and QA verdicts.
- get_pending_approvals: Queries actions awaiting human authorization (CHAT_APPROVAL).
- reject_approval: Rejects a pending gated action.
- get_model_usage: Reports aggregate token and cost usage from the durable budget.
- cancel_run: Cancels an active run.

Legacy backward-compatible tools are retained for diagnostic queries.
Model-callable approval functions are forbidden (INV-03).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    class FastMCP:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._tool_manager = None
            self.tools: dict[str, object] = {}

        def tool(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def decorator(fn):  # type: ignore[no-untyped-def]
                return fn
            return decorator

        def resource(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def decorator(fn):  # type: ignore[no-untyped-def]
                return fn
            return decorator

from . import runners as runner_registry
from .composition import ProductionSystem, build_production_system
from .manager import (
    AgentManager,
    PendingActionQueue,
    SessionNotFoundError,
)
from .storage.sqlite_store import SQLiteStore

DB_PATH = os.environ.get(
    "SUBAGENTBRIDGE_DB_PATH", str(Path.home() / ".subagentbridge" / "sessions.db")
)
DEFAULT_MAX_RETRIES = int(os.environ.get("SUBAGENTBRIDGE_MAX_RETRIES", "2"))
DEFAULT_TIMEOUT_S = float(os.environ.get("SUBAGENTBRIDGE_DEFAULT_TIMEOUT_S", "600"))

mcp = FastMCP("subagentbridge")

_store = SQLiteStore(DB_PATH)
_pending = PendingActionQueue(store=_store)
_manager = AgentManager(pending_actions=_pending, store=_store)
_rehydrated_count = _manager.rehydrate(runner_registry)

# In-memory tracking for runs and tasks, with SQLite persistence and audit logging via composition root
_runs: dict[str, dict] = {}
_tasks: dict[str, list[dict]] = {}
_production_systems: dict[Path, ProductionSystem] = {}


def rehydrate_runs_and_tasks(store: SQLiteStore) -> None:
    store.reset_stale_active_tasks()
    all_runs = store.load_all_runs()
    _runs.clear()
    _runs.update({r["run_id"]: r for r in all_runs})
    _tasks.clear()
    _tasks.update(store.load_all_tasks())


rehydrate_runs_and_tasks(_store)


def get_production_system(workspace_root: str | Path | None = None) -> ProductionSystem:
    root = Path(workspace_root if workspace_root else Path.cwd()).resolve()
    if root not in _production_systems:
        bridge_db = os.environ.get("SUBAGENTBRIDGE_PRODUCTION_DB", str(root / ".subagentbridge" / "production_audit.db"))
        _production_systems[root] = build_production_system(
            workspace_root=root,
            db_path=bridge_db,
        )
    return _production_systems[root]


def close_production_system(workspace_root: str | Path | None = None) -> None:
    if workspace_root is not None:
        root = Path(workspace_root).resolve()
        sys = _production_systems.pop(root, None)
        if sys is not None:
            sys.close()
    else:
        errors = []
        for root, sys in list(_production_systems.items()):
            try:
                sys.close()
            except Exception as e:
                errors.append(e)
            finally:
                _production_systems.pop(root, None)
        if errors:
            raise errors[0]


@mcp.tool()
def submit_goal(
    goal: str,
    workspace_path: str | None = None,
    model: str | None = None,
) -> dict:
    """Submit a high-level goal to be decomposed, implemented, and verified."""
    if not goal or not isinstance(goal, str) or not goal.strip():
        return {"status": "ERROR", "error": "nonempty goal string required"}

    ws = Path(workspace_path if workspace_path else Path.cwd()).resolve()
    run_id = f"run_{uuid4().hex[:12]}"
    task_id = f"task_{uuid4().hex[:8]}"

    run_record = {
        "run_id": run_id,
        "goal": goal.strip(),
        "workspace_path": str(ws),
        "status": "SUBMITTED",
        "model": model or "default",
    }
    task_record = {
        "task_id": task_id,
        "run_id": run_id,
        "title": "Decompose and execute goal under supervised coordination",
        "status": "PENDING",
        "role": "PM",
        "dependencies": [],
        "evidence_ids": [],
    }

    _store.upsert_run(run_record)
    _store.upsert_task(task_record)
    _runs[run_id] = run_record
    _tasks[run_id] = [task_record]

    try:
        sys = get_production_system(ws)
        sys.ledger.append_once(
            stream=f"run:{run_id}",
            idempotency_key=f"goal:{run_id}",
            event_type="GOAL_SUBMITTED",
            payload={"goal": goal.strip(), "run_id": run_id, "initial_task_id": task_id},
        )
    except Exception as exc:
        _runs.pop(run_id, None)
        _tasks.pop(run_id, None)
        try:
            _store._conn.execute("DELETE FROM tasks WHERE run_id=?", (run_id,))
            _store._conn.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
            _store._conn.commit()
        except Exception:
            pass
        return {"status": "ERROR", "error": f"audit ledger write failed: {exc}"}

    return {
        "status": "SUBMITTED",
        "run_id": run_id,
        "initial_task_id": task_id,
        "goal": goal.strip(),
    }


@mcp.tool()
def get_run(run_id: str) -> dict:
    """Read summary status and task count for a given run."""
    run = _runs.get(run_id)
    if run is None:
        run = _store.get_run(run_id)
        if run is not None:
            _runs[run_id] = run
    if run is None:
        return {"status": "NOT_FOUND", "run_id": run_id}
    tasks = _tasks.get(run_id)
    if tasks is None:
        tasks = _store.load_tasks_for_run(run_id)
        _tasks[run_id] = tasks
    return {
        "run_id": run_id,
        "status": run["status"],
        "goal": run["goal"],
        "workspace_path": run["workspace_path"],
        "task_count": len(tasks),
    }


@mcp.tool()
def list_tasks(run_id: str) -> list[dict]:
    """List all tasks in a run with their status, role, and dependencies."""
    tasks = _tasks.get(run_id)
    if tasks is None:
        tasks = _store.load_tasks_for_run(run_id)
        _tasks[run_id] = tasks
    return [dict(t) for t in tasks]


@mcp.tool()
def get_task_evidence(run_id: str, task_id: str) -> dict:
    """Retrieve verified executor receipts and QA verdicts for a specific task."""
    tasks = _tasks.get(run_id)
    if tasks is None:
        tasks = _store.load_tasks_for_run(run_id)
        _tasks[run_id] = tasks
    for t in tasks:
        if t["task_id"] == task_id:
            ev_ids = t.get("evidence_ids", [])
            # Honest MCP status: cannot claim verified: True without valid evidence
            is_verified = (t["status"] == "VERIFIED" and len(ev_ids) > 0)
            return {
                "run_id": run_id,
                "task_id": task_id,
                "status": t["status"],
                "role": t.get("role", "UNKNOWN"),
                "evidence_ids": ev_ids,
                "verified": is_verified,
            }
    return {"status": "NOT_FOUND", "run_id": run_id, "task_id": task_id}


@mcp.tool()
def get_pending_approvals() -> list[dict]:
    """List all pending actions requiring human approval under CHAT_APPROVAL mode."""
    return [
        {
            "action_id": a.action_id,
            "session_id": a.session_id,
            "description": a.description,
            "created_at": a.created_at,
        }
        for a in _pending.list_pending()
    ]


@mcp.tool()
def reject_approval(action_id: str, reason: str = "") -> dict:
    """Reject a pending gated action."""
    try:
        _pending.resolve(action_id, approved=False, reason=reason)
    except KeyError as exc:
        return {"status": "ERROR", "error": str(exc)}
    return {"status": "REJECTED", "action_id": action_id, "reason": reason}


@mcp.tool()
def cancel_run(run_id: str, reason: str = "") -> dict:
    """Cancel an active run and mark its tasks cancelled."""
    run = _runs.get(run_id)
    if run is None:
        run = _store.get_run(run_id)
        if run is not None:
            _runs[run_id] = run
    if run is None:
        return {"status": "NOT_FOUND", "run_id": run_id}
    run["status"] = "CANCELLED"
    _store.upsert_run(run)
    tasks = _tasks.get(run_id)
    if tasks is None:
        tasks = _store.load_tasks_for_run(run_id)
        _tasks[run_id] = tasks
    for t in tasks:
        if t["status"] not in ("VERIFIED", "FAILED", "CANCELLED"):
            t["status"] = "CANCELLED"
            _store.upsert_task(t)
    try:
        ws = Path(run.get("workspace_path", ".")).resolve()
        sys = get_production_system(ws)
        sys.ledger.append_once(
            stream=f"run:{run_id}",
            idempotency_key=f"cancel:{run_id}",
            event_type="RUN_CANCELLED",
            payload={"run_id": run_id, "reason": reason},
        )
    except Exception:
        pass
    return {"status": "CANCELLED", "run_id": run_id, "reason": reason}


@mcp.tool()
def get_model_usage() -> dict:
    """Aggregate token and cost usage across active budget ledgers and sessions."""
    usage = _manager.get_model_usage()
    try:
        sys = get_production_system()
        budget_snap = sys.budget.snapshot()
        usage["budget_tokens_available"] = budget_snap["tokens_available"]
        usage["budget_cost_available"] = budget_snap["cost_available"]
        usage["budget_active_reservations"] = budget_snap["active"]
    except Exception:
        pass
    return usage


@mcp.tool()
def spawn_agent(
    session_id: str,
    workspace_path: str,
    runner: str = "agy",
    model: str | None = None,
    agent_type: str | None = None,
    reasoning_effort: str | None = None,
    skip_permissions: bool = False,
    hitl_enabled: bool = True,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> str:
    """Legacy helper: create a new background subagent session on the given backend runner."""
    try:
        runner_obj = runner_registry.get_runner(runner)
    except KeyError as exc:
        return f"error: {exc}"
    try:
        _manager.spawn(
            session_id,
            workspace_path,
            runner_obj,
            model=model,
            agent_type=agent_type,
            reasoning_effort=reasoning_effort,
            skip_permissions=skip_permissions,
            hitl_enabled=hitl_enabled,
            max_retries=max_retries,
        )
    except (ValueError, PermissionError) as exc:
        return f"error: {exc}"
    return f"spawned session {session_id!r} on runner {runner!r}"


@mcp.tool()
async def send_message(session_id: str, message: str) -> str:
    """Legacy helper: queue a prompt for a session."""
    try:
        await _manager.send_message(session_id, message)
    except (SessionNotFoundError, RuntimeError, PermissionError) as exc:
        return f"error: {exc}"
    return f"message queued for session {session_id!r}"


@mcp.tool()
async def wait_for_idle(session_id: str, timeout_seconds: float = DEFAULT_TIMEOUT_S) -> dict:
    """Legacy helper: block until the session is idle/done/error or times out."""
    try:
        return await _manager.wait_for_idle(session_id, timeout_seconds)
    except SessionNotFoundError as exc:
        return {"status": "error", "error": str(exc)}


@mcp.tool()
def get_agent_status(session_id: str) -> dict:
    """Legacy helper: session diagnostics."""
    try:
        return _manager.get_status(session_id)
    except SessionNotFoundError as exc:
        return {"error": str(exc)}


@mcp.tool()
def list_agents() -> list[dict]:
    """Legacy helper: list diagnostics for every known session."""
    return _manager.list_agents()


@mcp.tool()
async def kill_agent(session_id: str) -> str:
    """Legacy helper: force-terminate a session's subprocess immediately."""
    try:
        return await _manager.kill_agent(session_id)
    except SessionNotFoundError as exc:
        return f"error: {exc}"


# Legacy callables preserved as non-MCP denied functions (P0 lockdown contract)
def apply_code_fix(filepath: str, target: str, replacement: str) -> str:
    """Denied until the trusted per-dispatch ToolExecutor exists."""
    return "error: direct file mutation unavailable until trusted ToolExecutor enforcement"


def approve_action(*args: object, **kwargs: object) -> str:
    """Disabled: model cannot self-approve. Approval requires isolated human broker."""
    return "error: approval unavailable until an isolated, authenticated human broker exists"


@mcp.tool()
def reject_action(action_id: str, reason: str = "") -> str:
    """Legacy alias: reject a pending action."""
    res = reject_approval(action_id, reason)
    if res.get("status") == "ERROR":
        return f"error: {res.get('error')}"
    return f"action {action_id!r} rejected"


@mcp.tool()
def list_pending_actions(session_id: str | None = None) -> list[dict]:
    """Legacy alias: list pending actions."""
    return [
        {
            "action_id": a.action_id,
            "session_id": a.session_id,
            "description": a.description,
            "created_at": a.created_at,
        }
        for a in _pending.list_pending(session_id)
    ]


@mcp.resource("agy://logs/{session_id}")
def get_logs(session_id: str) -> str:
    """Raw log stream for a session."""
    session = _manager.get_session(session_id)
    return json.dumps(session.log, default=str)


@mcp.resource("agy://pending/{session_id}")
def get_pending_for_session(session_id: str) -> str:
    """Actions from this session currently awaiting approval."""
    actions = _pending.list_pending(session_id)
    return json.dumps([a.__dict__ for a in actions], default=str)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
