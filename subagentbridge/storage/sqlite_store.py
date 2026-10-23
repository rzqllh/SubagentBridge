"""
storage/sqlite_store.py — persistence for sessions, log entries, and pending
HITL actions. WAL mode so a crash mid-write doesn't corrupt the DB and reads
aren't blocked by an in-progress write.

Only plain data is stored (session_id, runner NAME as a string, status,
etc.) — never a live runner object. Rehydration (docs/TEST_PLAN.md T11) looks
the runner name back up via runners.get_runner().
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    workspace_path TEXT NOT NULL,
    runner_name TEXT NOT NULL,
    model TEXT,
    agent_type TEXT,
    reasoning_effort TEXT,
    skip_permissions INTEGER NOT NULL DEFAULT 1,
    hitl_enabled INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 2,
    last_error TEXT,
    cursor INTEGER NOT NULL DEFAULT 0,
    pending_action_id TEXT,
    token_usage_json TEXT NOT NULL DEFAULT '{"input":0,"output":0}',
    updated_at REAL NOT NULL DEFAULT (unixepoch('now'))
);

CREATE TABLE IF NOT EXISTS log_entries (
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);

CREATE TABLE IF NOT EXISTS pending_actions (
    action_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    description TEXT NOT NULL,
    raw_tool_call_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    approved INTEGER,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    workspace_path TEXT NOT NULL,
    status TEXT NOT NULL,
    model TEXT NOT NULL,
    policy_revision TEXT NOT NULL DEFAULT 'v1',
    created_at REAL NOT NULL DEFAULT (unixepoch('now')),
    updated_at REAL NOT NULL DEFAULT (unixepoch('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    role TEXT NOT NULL,
    tree_sha TEXT NOT NULL DEFAULT '',
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL DEFAULT (unixepoch('now')),
    updated_at REAL NOT NULL DEFAULT (unixepoch('now')),
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS dispatches (
    dispatch_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1,
    idempotency_key TEXT NOT NULL,
    tree_sha TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'DISPATCHED',
    created_at REAL NOT NULL DEFAULT (unixepoch('now')),
    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);
"""


class SQLiteStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ---- sessions -------------------------------------------------------

    def upsert_session(self, s: dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT INTO sessions (
                session_id, workspace_path, runner_name, model, agent_type,
                reasoning_effort, skip_permissions, hitl_enabled, status,
                retry_count, max_retries, last_error, cursor,
                pending_action_id, token_usage_json, updated_at
            ) VALUES (
                :session_id, :workspace_path, :runner_name, :model, :agent_type,
                :reasoning_effort, :skip_permissions, :hitl_enabled, :status,
                :retry_count, :max_retries, :last_error, :cursor,
                :pending_action_id, :token_usage_json, unixepoch('now')
            )
            ON CONFLICT(session_id) DO UPDATE SET
                status=excluded.status,
                retry_count=excluded.retry_count,
                last_error=excluded.last_error,
                cursor=excluded.cursor,
                pending_action_id=excluded.pending_action_id,
                token_usage_json=excluded.token_usage_json,
                updated_at=excluded.updated_at
            """,
            s,
        )
        self._conn.commit()

    def load_all_sessions(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM sessions").fetchall()
        cols = [d[0] for d in self._conn.execute("SELECT * FROM sessions").description]
        return [dict(zip(cols, row)) for row in rows]

    def reset_stale_working_sessions(self) -> int:
        """
        T11: any session still marked 'working' at load time means the
        server died mid-run — the subprocess is gone, so the status is a
        lie. Reset to 'idle' rather than leaving a phantom 'working' state
        that nothing will ever resolve.
        """
        cur = self._conn.execute(
            "UPDATE sessions SET status='idle' WHERE status='working'"
        )
        self._conn.commit()
        return cur.rowcount

    # ---- log entries ------------------------------------------------------

    def append_log_entry(self, session_id: str, seq: int, payload: dict) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO log_entries (session_id, seq, payload_json) VALUES (?, ?, ?)",
            (session_id, seq, json.dumps(payload)),
        )
        self._conn.commit()

    def load_log_entries(self, session_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT payload_json FROM log_entries WHERE session_id = ? ORDER BY seq",
            (session_id,),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]

    # ---- pending actions --------------------------------------------------

    def upsert_pending_action(self, a: dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT INTO pending_actions (
                action_id, session_id, description, raw_tool_call_json,
                created_at, resolved, approved, reason
            ) VALUES (
                :action_id, :session_id, :description, :raw_tool_call_json,
                :created_at, :resolved, :approved, :reason
            )
            ON CONFLICT(action_id) DO UPDATE SET
                resolved=excluded.resolved,
                approved=excluded.approved,
                reason=excluded.reason
            """,
            a,
        )
        self._conn.commit()

    def load_unresolved_pending_actions(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM pending_actions WHERE resolved = 0"
        ).fetchall()
        cols = [d[0] for d in self._conn.execute("SELECT * FROM pending_actions").description]
        return [dict(zip(cols, row)) for row in rows]

    # ---- runs -------------------------------------------------------------

    def upsert_run(self, r: dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT INTO runs (
                run_id, goal, workspace_path, status, model,
                policy_revision, created_at, updated_at
            ) VALUES (
                :run_id, :goal, :workspace_path, :status, :model,
                :policy_revision, :created_at, unixepoch('now')
            )
            ON CONFLICT(run_id) DO UPDATE SET
                status=excluded.status,
                updated_at=excluded.updated_at
            """,
            {
                "run_id": r["run_id"],
                "goal": r["goal"],
                "workspace_path": str(r["workspace_path"]),
                "status": r["status"],
                "model": r.get("model", "default"),
                "policy_revision": r.get("policy_revision", "v1"),
                "created_at": r.get("created_at", time.time()),
            },
        )
        self._conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            return None
        cols = [d[0] for d in self._conn.execute("SELECT * FROM runs").description]
        return dict(zip(cols, row))

    def load_all_runs(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM runs ORDER BY created_at").fetchall()
        cols = [d[0] for d in self._conn.execute("SELECT * FROM runs").description]
        return [dict(zip(cols, row)) for row in rows]

    # ---- tasks ------------------------------------------------------------

    def upsert_task(self, t: dict[str, Any]) -> None:
        deps = t.get("dependencies", [])
        evs = t.get("evidence_ids", [])
        self._conn.execute(
            """
            INSERT INTO tasks (
                task_id, run_id, title, status, role,
                tree_sha, dependencies_json, evidence_ids_json,
                created_at, updated_at
            ) VALUES (
                :task_id, :run_id, :title, :status, :role,
                :tree_sha, :dependencies_json, :evidence_ids_json,
                :created_at, unixepoch('now')
            )
            ON CONFLICT(task_id) DO UPDATE SET
                status=excluded.status,
                tree_sha=excluded.tree_sha,
                dependencies_json=excluded.dependencies_json,
                evidence_ids_json=excluded.evidence_ids_json,
                updated_at=excluded.updated_at
            """,
            {
                "task_id": t["task_id"],
                "run_id": t["run_id"],
                "title": t.get("title", ""),
                "status": t["status"],
                "role": t.get("role", "PM"),
                "tree_sha": t.get("tree_sha", ""),
                "dependencies_json": json.dumps(deps) if not isinstance(deps, str) else deps,
                "evidence_ids_json": json.dumps(evs) if not isinstance(evs, str) else evs,
                "created_at": t.get("created_at", time.time()),
            },
        )
        self._conn.commit()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not row:
            return None
        cols = [d[0] for d in self._conn.execute("SELECT * FROM tasks").description]
        d = dict(zip(cols, row))
        d["dependencies"] = json.loads(d.get("dependencies_json", "[]"))
        d["evidence_ids"] = json.loads(d.get("evidence_ids_json", "[]"))
        return d

    def load_tasks_for_run(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM tasks WHERE run_id = ? ORDER BY created_at", (run_id,)).fetchall()
        cols = [d[0] for d in self._conn.execute("SELECT * FROM tasks").description]
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            d["dependencies"] = json.loads(d.get("dependencies_json", "[]"))
            d["evidence_ids"] = json.loads(d.get("evidence_ids_json", "[]"))
            result.append(d)
        return result

    def load_all_tasks(self) -> dict[str, list[dict[str, Any]]]:
        rows = self._conn.execute("SELECT * FROM tasks ORDER BY created_at").fetchall()
        cols = [d[0] for d in self._conn.execute("SELECT * FROM tasks").description]
        result: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            d = dict(zip(cols, row))
            d["dependencies"] = json.loads(d.get("dependencies_json", "[]"))
            d["evidence_ids"] = json.loads(d.get("evidence_ids_json", "[]"))
            result.setdefault(d["run_id"], []).append(d)
        return result

    def reset_stale_active_tasks(self) -> int:
        """Crash recovery: reset any task left in DISPATCHED or active transient state to RECOVERY_REQUIRED."""
        cur = self._conn.execute(
            "UPDATE tasks SET status='RECOVERY_REQUIRED', updated_at=unixepoch('now') WHERE status IN ('DISPATCHED', 'PROCESS_SUCCEEDED')"
        )
        self._conn.commit()
        return cur.rowcount

    # ---- dispatches -------------------------------------------------------

    def upsert_dispatch(self, d: dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT INTO dispatches (
                dispatch_id, task_id, attempt, idempotency_key,
                tree_sha, status, created_at
            ) VALUES (
                :dispatch_id, :task_id, :attempt, :idempotency_key,
                :tree_sha, :status, :created_at
            )
            ON CONFLICT(dispatch_id) DO UPDATE SET
                status=excluded.status
            """,
            {
                "dispatch_id": d["dispatch_id"],
                "task_id": d["task_id"],
                "attempt": d.get("attempt", 1),
                "idempotency_key": d["idempotency_key"],
                "tree_sha": d.get("tree_sha", ""),
                "status": d.get("status", "DISPATCHED"),
                "created_at": d.get("created_at", time.time()),
            },
        )
        self._conn.commit()

    def load_dispatches_for_task(self, task_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM dispatches WHERE task_id = ? ORDER BY attempt", (task_id,)).fetchall()
        cols = [d[0] for d in self._conn.execute("SELECT * FROM dispatches").description]
        return [dict(zip(cols, row)) for row in rows]
