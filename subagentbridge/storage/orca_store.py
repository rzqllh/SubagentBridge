"""SQLite persistence store for Cindy/Orca orchestration-core parity.

Provides durable persistence for teams, sessions, worker configurations,
inter-agent dispatch queues, worktree assignments, and handoff evidence.
WAL mode and transaction safety enabled.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from subagentbridge.domain.orca_contracts import (
    OrcaRole,
    WorkerStatus,
    QueueTaskStatus,
    WorkerConfig,
    OrcaTeam,
    OrcaSession,
    QueueItem,
    WorktreeAssignment,
    HandoffEvidence,
)

ORCA_SCHEMA = """
CREATE TABLE IF NOT EXISTS orca_teams (
    team_id TEXT PRIMARY KEY,
    lead_session_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS orca_sessions (
    session_id TEXT PRIMARY KEY,
    orca_role TEXT NOT NULL,
    team_id TEXT NOT NULL,
    status TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS orca_queue (
    dispatch_id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    from_session_id TEXT NOT NULL,
    to_session_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS orca_worktrees (
    worker_id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS orca_handoffs (
    dispatch_id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    from_worker_id TEXT NOT NULL,
    to_lead_id TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    artifacts_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    submitted_at REAL NOT NULL
);
"""


class OrcaStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(ORCA_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> OrcaStore:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # ---- Teams -----------------------------------------------------------

    def save_team(self, team: OrcaTeam) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO orca_teams (team_id, lead_session_id, title, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(team_id) DO UPDATE SET
                    lead_session_id = excluded.lead_session_id,
                    title = excluded.title
                """,
                (team.team_id, team.lead_session_id, team.title, team.created_at),
            )

    def load_team(self, team_id: str) -> OrcaTeam | None:
        cur = self._conn.execute("SELECT * FROM orca_teams WHERE team_id = ?", (team_id,))
        row = cur.fetchone()
        if not row:
            return None
        return OrcaTeam(
            team_id=row["team_id"],
            lead_session_id=row["lead_session_id"],
            title=row["title"],
            created_at=row["created_at"],
        )

    # ---- Sessions --------------------------------------------------------

    def save_session(self, session: OrcaSession) -> None:
        cfg_dict = {
            "worker_id": session.config.worker_id,
            "team_id": session.config.team_id,
            "role": session.config.role,
            "harness": session.config.harness,
            "model": session.config.model,
            "provider": session.config.provider,
            "system_prompt": session.config.system_prompt,
            "working_dir": session.config.working_dir,
            "effort": session.config.effort,
            "budget_tokens": session.config.budget_tokens,
            "pid": session.config.pid,
            "process_create_time": session.config.process_create_time,
            "tokens_consumed": session.config.tokens_consumed,
        }
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO orca_sessions (session_id, orca_role, team_id, status, config_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    status = excluded.status,
                    config_json = excluded.config_json,
                    updated_at = excluded.updated_at
                """,
                (
                    session.session_id,
                    session.orca_role.value,
                    session.team_id,
                    session.status.value,
                    json.dumps(cfg_dict),
                    session.created_at,
                    session.updated_at,
                ),
            )

    def load_session(self, session_id: str) -> OrcaSession | None:
        cur = self._conn.execute("SELECT * FROM orca_sessions WHERE session_id = ?", (session_id,))
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_session(row)

    def list_all_sessions(self) -> list[OrcaSession]:
        cur = self._conn.execute("SELECT * FROM orca_sessions ORDER BY created_at ASC")
        return [self._row_to_session(row) for row in cur.fetchall()]

    def list_sessions_by_team(self, team_id: str) -> list[OrcaSession]:
        cur = self._conn.execute(
            "SELECT * FROM orca_sessions WHERE team_id = ? ORDER BY created_at ASC", (team_id,)
        )
        return [self._row_to_session(row) for row in cur.fetchall()]

    def _row_to_session(self, row: sqlite3.Row) -> OrcaSession:
        raw_cfg = json.loads(row["config_json"])
        cfg = WorkerConfig(
            worker_id=raw_cfg.get("worker_id", row["session_id"]),
            team_id=raw_cfg.get("team_id", row["team_id"]),
            role=raw_cfg.get("role", "worker"),
            harness=raw_cfg.get("harness", "native"),
            model=raw_cfg.get("model"),
            provider=raw_cfg.get("provider"),
            system_prompt=raw_cfg.get("system_prompt"),
            working_dir=raw_cfg.get("working_dir"),
            effort=raw_cfg.get("effort"),
            budget_tokens=raw_cfg.get("budget_tokens"),
            pid=raw_cfg.get("pid"),
            process_create_time=raw_cfg.get("process_create_time"),
            tokens_consumed=raw_cfg.get("tokens_consumed", 0),
        )
        return OrcaSession(
            session_id=row["session_id"],
            orca_role=OrcaRole(row["orca_role"]),
            team_id=row["team_id"],
            status=WorkerStatus(row["status"]),
            config=cfg,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ---- Queue -----------------------------------------------------------

    def save_queue_item(self, item: QueueItem) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO orca_queue (
                    dispatch_id, team_id, from_session_id, to_session_id,
                    task_id, payload_json, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dispatch_id) DO UPDATE SET
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    item.dispatch_id,
                    item.team_id,
                    item.from_session_id,
                    item.to_session_id,
                    item.task_id,
                    json.dumps(item.payload),
                    item.status.value,
                    item.created_at,
                    item.updated_at,
                ),
            )

    def load_queue_item(self, dispatch_id: str) -> QueueItem | None:
        cur = self._conn.execute("SELECT * FROM orca_queue WHERE dispatch_id = ?", (dispatch_id,))
        row = cur.fetchone()
        if not row:
            return None
        return QueueItem(
            dispatch_id=row["dispatch_id"],
            team_id=row["team_id"],
            from_session_id=row["from_session_id"],
            to_session_id=row["to_session_id"],
            task_id=row["task_id"],
            payload=json.loads(row["payload_json"]),
            status=QueueTaskStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_queue_by_team(self, team_id: str) -> list[QueueItem]:
        cur = self._conn.execute(
            "SELECT * FROM orca_queue WHERE team_id = ? ORDER BY created_at ASC", (team_id,)
        )
        items = []
        for row in cur.fetchall():
            items.append(
                QueueItem(
                    dispatch_id=row["dispatch_id"],
                    team_id=row["team_id"],
                    from_session_id=row["from_session_id"],
                    to_session_id=row["to_session_id"],
                    task_id=row["task_id"],
                    payload=json.loads(row["payload_json"]),
                    status=QueueTaskStatus(row["status"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )
        return items

    # ---- Worktrees -------------------------------------------------------

    def save_worktree(self, assignment: WorktreeAssignment) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO orca_worktrees (worker_id, team_id, worktree_path, branch_name, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    worktree_path = excluded.worktree_path,
                    branch_name = excluded.branch_name
                """,
                (
                    assignment.worker_id,
                    assignment.team_id,
                    assignment.worktree_path,
                    assignment.branch_name,
                    assignment.created_at,
                ),
            )

    def load_worktree(self, worker_id: str) -> WorktreeAssignment | None:
        cur = self._conn.execute("SELECT * FROM orca_worktrees WHERE worker_id = ?", (worker_id,))
        row = cur.fetchone()
        if not row:
            return None
        return WorktreeAssignment(
            worker_id=row["worker_id"],
            team_id=row["team_id"],
            worktree_path=row["worktree_path"],
            branch_name=row["branch_name"],
            created_at=row["created_at"],
        )

    # ---- Handoffs --------------------------------------------------------

    def save_handoff(self, team_id: str, evidence: HandoffEvidence) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO orca_handoffs (
                    dispatch_id, team_id, from_worker_id, to_lead_id,
                    status, summary, artifacts_json, metrics_json, submitted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dispatch_id) DO UPDATE SET
                    status = excluded.status,
                    summary = excluded.summary,
                    artifacts_json = excluded.artifacts_json,
                    metrics_json = excluded.metrics_json,
                    submitted_at = excluded.submitted_at
                """,
                (
                    evidence.dispatch_id,
                    team_id,
                    evidence.from_worker_id,
                    evidence.to_lead_id,
                    evidence.status,
                    evidence.summary,
                    json.dumps(evidence.artifacts),
                    json.dumps(evidence.metrics),
                    evidence.submitted_at,
                ),
            )

    def list_handoffs_by_team(self, team_id: str) -> list[HandoffEvidence]:
        cur = self._conn.execute(
            "SELECT * FROM orca_handoffs WHERE team_id = ? ORDER BY submitted_at ASC", (team_id,)
        )
        handoffs = []
        for row in cur.fetchall():
            handoffs.append(
                HandoffEvidence(
                    dispatch_id=row["dispatch_id"],
                    from_worker_id=row["from_worker_id"],
                    to_lead_id=row["to_lead_id"],
                    status=row["status"],
                    summary=row["summary"],
                    artifacts=json.loads(row["artifacts_json"]),
                    metrics=json.loads(row["metrics_json"]),
                    submitted_at=row["submitted_at"],
                )
            )
        return handoffs
