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
from typing import Mapping, Sequence
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
from .execution.native_runtime import (
    SupervisedNativeLifecycle,
    TaskDecomposer,
    resolve_tree_sha,
)
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
_run_commands: dict[str, dict[str, list[str]]] = {}
_production_systems: dict[Path, ProductionSystem] = {}


def rehydrate_runs_and_tasks(store: SQLiteStore) -> None:
    store.reset_stale_active_tasks()
    all_runs = store.load_all_runs()
    _runs.clear()
    _runs.update({r["run_id"]: r for r in all_runs})
    _tasks.clear()
    _tasks.update(store.load_all_tasks())
    _run_commands.clear()


rehydrate_runs_and_tasks(_store)


def get_production_system(workspace_root: str | Path | None = None) -> ProductionSystem:
    root = Path(workspace_root if workspace_root else Path.cwd()).resolve()
    if root not in _production_systems:
        bridge_db = os.environ.get("SUBAGENTBRIDGE_PRODUCTION_DB", str(root / ".subagentbridge" / "production_audit.db"))
        router_url = os.environ.get("NINE_ROUTER_BASE_URL", os.environ.get("SUBAGENTBRIDGE_ROUTER_URL", "http://127.0.0.1:9099"))
        router_key = os.environ.get("NINE_ROUTER_API_KEY", os.environ.get("SUBAGENTBRIDGE_ROUTER_KEY", "production-local-key"))
        _production_systems[root] = build_production_system(
            workspace_root=root,
            db_path=bridge_db,
            nine_router_base_url=router_url,
            nine_router_api_key=router_key,
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
    execute: bool = False,
    commands: dict[str, list[str]] | None = None,
) -> dict:
    """Submit a high-level goal to be decomposed, implemented, and verified."""
    if not goal or not isinstance(goal, str) or not goal.strip():
        return {"status": "ERROR", "error": "nonempty goal string required"}

    ws = Path(workspace_path if workspace_path else Path.cwd()).resolve()
    run_id = f"run_{uuid4().hex[:12]}"
    task_id = f"task_{uuid4().hex[:8]}"

    if commands:
        _run_commands[run_id] = {k: list(v) for k, v in commands.items()}

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
        _run_commands.pop(run_id, None)
        try:
            _store._conn.execute("DELETE FROM tasks WHERE run_id=?", (run_id,))
            _store._conn.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
            _store._conn.commit()
        except Exception:
            pass
        return {"status": "ERROR", "error": f"audit ledger write failed: {exc}"}

    if execute:
        return _execute_run(run_id, command_map=commands)

    return {
        "status": "SUBMITTED",
        "run_id": run_id,
        "initial_task_id": task_id,
        "goal": goal.strip(),
    }


def _gate_command_execution(
    cmd: Sequence[str],
    workspace_path: Path,
    run_id: str,
    task_id: str | None = None,
) -> tuple[bool, str, str, str | None]:
    """Inspect model-supplied commands under CHAT_APPROVAL and fail-closed policy (Thread #7 fix).

    Returns (is_gated, category, reason, action_id).
    """
    import re
    cmd_list = [str(x) for x in cmd]
    cmd_str = " ".join(cmd_list)
    lower_cmd = cmd_str.lower()
    ws_resolved = workspace_path.resolve()
    ws_str = str(ws_resolved)

    # 1. Inspect arguments (excluding executable binary at index 0) for paths escaping workspace
    for arg in cmd_list[1:]:
        # Check path traversal
        if ".." in arg:
            try:
                candidate = (workspace_path / arg).resolve()
                if candidate != ws_resolved and ws_resolved not in candidate.parents:
                    cat = "OUTSIDE_WORKSPACE_WRITE"
                    reason = f"path traversal in argument {arg!r} resolves outside workspace"
                    act = _pending.enqueue(run_id, {
                        "command": cmd_str,
                        "path": str(workspace_path),
                        "operation": cat,
                        "reason": reason,
                        "task_id": task_id or "run",
                    })
                    return True, cat, reason, act.action_id
            except Exception:
                pass

        # Check explicit absolute target path outside workspace
        try:
            p = Path(arg)
            if p.is_absolute():
                resolved_p = p.resolve()
                if resolved_p != ws_resolved and ws_resolved not in resolved_p.parents:
                    # Exclude interpreter/virtualenv directories if referenced
                    import sys as _sys
                    sys_dirs = [Path(_sys.prefix).resolve(), Path(_sys.base_prefix).resolve()]
                    is_sys = any(s == resolved_p or s in resolved_p.parents for s in sys_dirs)
                    if not is_sys:
                        cat = "OUTSIDE_WORKSPACE_WRITE"
                        reason = f"argument path {arg!r} references outside workspace {ws_str}"
                        act = _pending.enqueue(run_id, {
                            "command": cmd_str,
                            "path": str(workspace_path),
                            "operation": cat,
                            "reason": reason,
                            "task_id": task_id or "run",
                        })
                        return True, cat, reason, act.action_id
        except Exception:
            pass

    # 2. Inspect inline Python code (-c) or scripts for file modification functions
    for idx, arg in enumerate(cmd_list):
        if arg == "-c" and idx + 1 < len(cmd_list):
            code = cmd_list[idx + 1]
            write_patterns = (
                r"\bopen\s*\([^)]*['\"][wa\+]",
                r"\.write_text\s*\(",
                r"\.write_bytes\s*\(",
                r"\bos\.remove\b",
                r"\bos\.unlink\b",
                r"\bshutil\.rmtree\b",
            )
            for pat in write_patterns:
                if re.search(pat, code):
                    cat = "OUTSIDE_WORKSPACE_WRITE"
                    reason = f"inline command contains filesystem modification pattern: {pat}"
                    act = _pending.enqueue(run_id, {
                        "command": cmd_str,
                        "path": str(workspace_path),
                        "operation": cat,
                        "reason": reason,
                        "task_id": task_id or "run",
                    })
                    return True, cat, reason, act.action_id

    # 3. Check for destructive, git push, or dependency change patterns
    gated_patterns = {
        "rm -rf": "DESTRUCTIVE",
        "rmdir": "DESTRUCTIVE",
        "git push": "GIT_PUSH_OR_REWRITE",
        "git reset --hard": "DESTRUCTIVE",
        "git clean -f": "DESTRUCTIVE",
        "sudo ": "AUTH_OR_SECRET",
        "pip install": "DEPENDENCY",
        "npm install": "DEPENDENCY",
    }
    for pat, cat in gated_patterns.items():
        if pat in lower_cmd:
            reason = f"command contains gated pattern {pat!r}"
            act = _pending.enqueue(run_id, {
                "command": cmd_str,
                "path": str(workspace_path),
                "operation": cat,
                "reason": reason,
                "task_id": task_id or "run",
            })
            return True, cat, reason, act.action_id

    return False, "READ_ONLY_REQUEST", "", None


def _execute_run(run_id: str, command_map: Mapping[str, Sequence[str]] | None = None) -> dict:
    run = _runs.get(run_id)
    if run is None:
        run = _store.get_run(run_id)
        if run is not None:
            _runs[run_id] = run
    if run is None:
        return {"status": "NOT_FOUND", "run_id": run_id}
    if run.get("status") in ("COMPLETED", "VERIFIED", "CANCELLED"):
        return {"status": run["status"], "run_id": run_id, "tasks": _tasks.get(run_id, [])}

    ws = Path(run.get("workspace_path", ".")).resolve()
    sys = get_production_system(ws)
    tree_sha = resolve_tree_sha(ws)
    goal = run.get("goal", "")

    tasks_contracts, dependencies, task_records = TaskDecomposer.decompose_goal(goal, run_id, tree_sha)

    # Clean previous pending task and register decomposed tasks
    try:
        _store._conn.execute("DELETE FROM tasks WHERE run_id=? AND status='PENDING'", (run_id,))
        _store._conn.commit()
    except Exception:
        pass
    for r in task_records:
        _store.upsert_task(r)
    _tasks[run_id] = task_records

    effective_commands = dict(command_map or {})
    if not effective_commands and run_id in _run_commands:
        effective_commands.update(_run_commands[run_id])

    # Gate model-supplied commands under CHAT_APPROVAL (Thread #7 fix)
    for target_key, cmd_seq in effective_commands.items():
        if cmd_seq:
            is_gated, cat, reason, act_id = _gate_command_execution(cmd_seq, ws, run_id, target_key)
            if is_gated:
                try:
                    sys.ledger.append_once(
                        stream=f"run:{run_id}",
                        idempotency_key=f"gate:{act_id}",
                        event_type="COMMAND_GATED",
                        payload={"run_id": run_id, "category": cat, "reason": reason, "action_id": act_id},
                    )
                except Exception:
                    pass
                run["status"] = "BLOCKED"
                _store.upsert_run(run)
                _runs[run_id] = run
                return {
                    "status": "BLOCKED",
                    "run_id": run_id,
                    "reason": f"command execution gated: requires human approval under CHAT_APPROVAL: {reason}",
                    "action_id": act_id,
                }

    lifecycle = SupervisedNativeLifecycle(sys=sys, workspace_path=ws, store=_store)
    coordinator, principals = lifecycle.create_coordinator_for_run(
        run_id=run_id,
        tasks=tasks_contracts,
        dependencies=dependencies,
    )

    result = lifecycle.execute_lifecycle(
        run_id=run_id,
        coordinator=coordinator,
        principals=principals,
        task_records=task_records,
        command_map=effective_commands,
    )

    if result.get("status") == "COMPLETED":
        run["status"] = "COMPLETED"
        _store.upsert_run(run)
        _runs[run_id] = run
        _tasks[run_id] = result.get("tasks", task_records)
    elif result.get("status") in ("FAILED", "BLOCKED"):
        run["status"] = result["status"]
        _store.upsert_run(run)
        _runs[run_id] = run

    return result


@mcp.tool()
def execute_run(run_id: str, commands: dict[str, list[str]] | None = None) -> dict:
    """Execute the full supervised PM/Developer/QA lifecycle for a submitted run with explicit commands."""
    return _execute_run(run_id, command_map=commands)


@mcp.tool()
def execute_task(run_id: str, task_id: str, command: list[str] | None = None) -> dict:
    """Execute a specific task in a run through the supervised workflow and return evidence."""
    cmd_map: dict[str, list[str]] = {}
    if run_id in _run_commands:
        cmd_map.update(_run_commands[run_id])
    if command:
        cmd_map[task_id] = list(command)

    res = _execute_run(run_id, command_map=cmd_map)
    if res.get("status") == "BLOCKED":
        return {
            "status": "BLOCKED",
            "run_id": run_id,
            "task_id": task_id,
            "reason": res.get("reason"),
            "action_id": res.get("action_id"),
            "evidence": None,
            "run_status": "BLOCKED",
        }

    # Return evidence for the exact requested task
    ev = get_task_evidence(run_id, task_id)
    tasks = _tasks.get(run_id, [])
    target_task = None
    for t in tasks:
        if t.get("task_id") == task_id:
            target_task = t
            break

    status = target_task.get("status") if target_task else res.get("status", "UNKNOWN")
    return {
        "status": status,
        "run_id": run_id,
        "task_id": task_id,
        "task": target_task,
        "evidence": ev,
        "run_status": res.get("status"),
        "reason": res.get("reason"),
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
def discover_models(workspace_path: str | None = None) -> list[dict]:
    """Discover available models and their capabilities from the local 9Router instance."""
    try:
        sys = get_production_system(workspace_path)
        caps = sys.nine_router.discover()
        return [
            {
                "model_id": c.model_id,
                "tool_calls": c.tool_calls,
                "structured_output": c.structured_output,
                "streaming": c.streaming,
                "input_cost_known": c.input_cost_known,
                "output_cost_known": c.output_cost_known,
            }
            for c in caps
        ]
    except Exception as exc:
        return [{"status": "ERROR", "error": str(exc)}]


@mcp.tool()
def list_skills(role: str | None = None, workspace_path: str | None = None) -> list[dict]:
    """List approved, pinned skills and discovered skills for a specific role or workspace."""
    try:
        sys = get_production_system(workspace_path)
        if role:
            skill_names = sys.skills.get_skills_for_role(role)
        else:
            discovered = sys.skills.discover_skills()
            all_names = set(sys.skills.pins.keys()) | set(discovered.keys())
            skill_names = tuple(sorted(all_names))

        result = []
        for name in skill_names:
            is_pinned = name in sys.skills.pins
            pin_sha = sys.skills.pins.get(name, "")
            result.append({
                "skill": name,
                "pinned": is_pinned,
                "sha256": pin_sha,
            })
        return result
    except Exception as exc:
        return [{"status": "ERROR", "error": str(exc)}]



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
