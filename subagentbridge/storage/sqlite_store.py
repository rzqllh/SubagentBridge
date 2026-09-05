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
from pathlib import Path
from typing import Any, Optional

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
