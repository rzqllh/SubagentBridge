"""SQLite persistence store for Simpul native team and task coordination.

Provides durable persistence for teams, sessions, worker configurations,
inter-agent dispatch queues, worktree assignments, and handoff evidence.
WAL mode and transaction safety enabled.
Supports zero data loss schema migration from legacy orca_* structures.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from subagentbridge.domain.team_contracts import (
    AgentRole,
    AgentSession,
    AgentTeam,
    ChannelMessage,
    HandoffEvidence,
    QueueItem,
    QueueTaskStatus,
    WorkerCheckpoint,
    WorkerConfig,
    WorkerStatus,
    WorktreeAssignment,
)


class MigrationError(RuntimeError):
    """Base exception for database schema migration failures."""


class MigrationConflictError(MigrationError):
    """Raised when destination table contains conflicting records for existing legacy keys."""


class MigrationIntegrityError(MigrationError):
    """Raised when row-by-row equivalence or foreign key verification fails during schema migration."""


SIMPUL_SCHEMA = """
CREATE TABLE IF NOT EXISTS simpul_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at REAL NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simpul_teams (
    team_id TEXT PRIMARY KEY,
    lead_session_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS simpul_sessions (
    session_id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    team_id TEXT NOT NULL,
    status TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS simpul_queue (
    dispatch_id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    from_session_id TEXT NOT NULL,
    to_session_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL,
    dedup_key TEXT,
    priority INTEGER NOT NULL DEFAULT 0,
    steering_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS simpul_worktrees (
    worker_id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS simpul_handoffs (
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

CREATE TABLE IF NOT EXISTS simpul_channel_messages (
    message_id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    from_session_id TEXT NOT NULL,
    to_session_id TEXT NOT NULL,
    content TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_simpul_channel_team ON simpul_channel_messages(team_id, created_at);

CREATE TABLE IF NOT EXISTS simpul_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    state_summary TEXT NOT NULL,
    tokens_consumed INTEGER NOT NULL,
    context_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_simpul_checkpoint_worker ON simpul_checkpoints(worker_id, created_at);
"""

SIMPUL_COMPATIBILITY_VIEWS = """
CREATE VIEW IF NOT EXISTS orca_teams AS SELECT * FROM simpul_teams;
CREATE VIEW IF NOT EXISTS orca_sessions AS SELECT session_id, role AS orca_role, team_id, status, config_json, created_at, updated_at FROM simpul_sessions;
CREATE VIEW IF NOT EXISTS orca_queue AS SELECT * FROM simpul_queue;
CREATE VIEW IF NOT EXISTS orca_worktrees AS SELECT * FROM simpul_worktrees;
CREATE VIEW IF NOT EXISTS orca_handoffs AS SELECT * FROM simpul_handoffs;
CREATE VIEW IF NOT EXISTS orca_channel_messages AS SELECT * FROM simpul_channel_messages;
CREATE VIEW IF NOT EXISTS orca_checkpoints AS SELECT * FROM simpul_checkpoints;
"""


def _execute_ddl_statements(conn: sqlite3.Connection, script: str) -> None:
    for stmt in script.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)



def _verify_application_referential_integrity(conn: sqlite3.Connection) -> None:
    """Verify application-level foreign key and referential integrity.

    Ensures no orphaned entities exist across teams, sessions, queue items,
    worktrees, handoffs, channel messages, and checkpoints.
    """
    # 1. Sessions must reference existing teams
    orphaned_sessions = conn.execute("""
        SELECT s.session_id, s.team_id FROM simpul_sessions s
        LEFT JOIN simpul_teams t ON s.team_id = t.team_id
        WHERE t.team_id IS NULL
    """).fetchall()
    if orphaned_sessions:
        raise MigrationIntegrityError(
            f"Referential integrity failure: sessions referencing non-existent teams: {[r[0] for r in orphaned_sessions]}"
        )

    # 2. Queue dispatches must reference existing teams
    orphaned_queue = conn.execute("""
        SELECT q.dispatch_id, q.team_id FROM simpul_queue q
        LEFT JOIN simpul_teams t ON q.team_id = t.team_id
        WHERE t.team_id IS NULL
    """).fetchall()
    if orphaned_queue:
        raise MigrationIntegrityError(
            f"Referential integrity failure: queue dispatches referencing non-existent teams: {[r[0] for r in orphaned_queue]}"
        )

    # 3. Worktrees must reference existing teams and existing worker sessions
    orphaned_worktree_teams = conn.execute("""
        SELECT w.worker_id, w.team_id FROM simpul_worktrees w
        LEFT JOIN simpul_teams t ON w.team_id = t.team_id
        WHERE t.team_id IS NULL
    """).fetchall()
    if orphaned_worktree_teams:
        raise MigrationIntegrityError(
            f"Referential integrity failure: worktrees referencing non-existent teams: {[r[0] for r in orphaned_worktree_teams]}"
        )
    orphaned_worktree_sessions = conn.execute("""
        SELECT w.worker_id FROM simpul_worktrees w
        LEFT JOIN simpul_sessions s ON w.worker_id = s.session_id
        WHERE s.session_id IS NULL
    """).fetchall()
    if orphaned_worktree_sessions:
        raise MigrationIntegrityError(
            f"Referential integrity failure: worktrees referencing non-existent worker sessions: {[r[0] for r in orphaned_worktree_sessions]}"
        )

    # 4. Handoffs must reference existing teams
    orphaned_handoffs = conn.execute("""
        SELECT h.dispatch_id, h.team_id FROM simpul_handoffs h
        LEFT JOIN simpul_teams t ON h.team_id = t.team_id
        WHERE t.team_id IS NULL
    """).fetchall()
    if orphaned_handoffs:
        raise MigrationIntegrityError(
            f"Referential integrity failure: handoffs referencing non-existent teams: {[r[0] for r in orphaned_handoffs]}"
        )

    # 5. Channel messages must reference existing teams
    orphaned_messages = conn.execute("""
        SELECT m.message_id, m.team_id FROM simpul_channel_messages m
        LEFT JOIN simpul_teams t ON m.team_id = t.team_id
        WHERE t.team_id IS NULL
    """).fetchall()
    if orphaned_messages:
        raise MigrationIntegrityError(
            f"Referential integrity failure: channel messages referencing non-existent teams: {[r[0] for r in orphaned_messages]}"
        )

    # 6. Checkpoints must reference existing teams and worker sessions
    orphaned_checkpoint_teams = conn.execute("""
        SELECT c.checkpoint_id, c.team_id FROM simpul_checkpoints c
        LEFT JOIN simpul_teams t ON c.team_id = t.team_id
        WHERE t.team_id IS NULL
    """).fetchall()
    if orphaned_checkpoint_teams:
        raise MigrationIntegrityError(
            f"Referential integrity failure: checkpoints referencing non-existent teams: {[r[0] for r in orphaned_checkpoint_teams]}"
        )
    orphaned_checkpoint_sessions = conn.execute("""
        SELECT c.checkpoint_id, c.worker_id FROM simpul_checkpoints c
        LEFT JOIN simpul_sessions s ON c.worker_id = s.session_id
        WHERE s.session_id IS NULL
    """).fetchall()
    if orphaned_checkpoint_sessions:
        raise MigrationIntegrityError(
            f"Referential integrity failure: checkpoints referencing non-existent worker sessions: {[r[0] for r in orphaned_checkpoint_sessions]}"
        )


def migrate_schema(conn: sqlite3.Connection, db_path: str | Path | None = None) -> None:
    """Execute idempotent, fail-closed zero-data-loss schema migration.

    Guarantees:
    1. Physical pre-migration byte backup via conn.backup() if file-based and legacy tables exist.
    2. Explicit transaction control with manual isolation level (no implicit commits).
    3. Complete schema-aware column mapping and full row-by-row equivalence validation.
    4. Primary key conflict detection across ALL columns against destination simpul_* tables.
    5. Foreign key and application-level referential integrity verification before dropping legacy tables.
    6. Complete transaction rollback restoring all tables if any step fails.
    7. Read-only compatibility views established for orca_* table queries.
    """
    # 1. Determine database file path for verified byte backup
    db_file: Path | None = None
    if db_path is not None and str(db_path) != ":memory:":
        db_file = Path(db_path)
    else:
        try:
            for row in conn.execute("PRAGMA database_list").fetchall():
                if row[1] == "main" and row[2]:
                    db_file = Path(row[2])
                    break
        except Exception:
            pass

    # 2. Explicit transaction execution under migration write lock
    prev_isolation = conn.isolation_level
    conn.isolation_level = None  # Autocommit off for driver, full manual transaction control
    in_transaction = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        in_transaction = True

        # Create destination simpul_* tables if not existing
        _execute_ddl_statements(conn, SIMPUL_SCHEMA)

        # Check existing schema version
        cur = conn.execute("SELECT MAX(version) AS max_v FROM simpul_schema_version")
        row = cur.fetchone()
        current_version = row["max_v"] if row and row["max_v"] is not None else 0

        # Re-query actual legacy TABLE objects strictly from sqlite_master after acquiring write lock.
        # This guarantees we never use stale pre-lock metadata to authorize DDL, migration, or deletion.
        cur_tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'orca_%'"
        )
        active_legacy_tables = {r["name"] for r in cur_tables.fetchall()}

        if current_version >= 2 and not active_legacy_tables:
            _execute_ddl_statements(conn, SIMPUL_COMPATIBILITY_VIEWS)
            conn.execute("COMMIT")
            in_transaction = False
            return

        if active_legacy_tables:
            # 3. If legacy tables exist and we have a disk database, preserve bytes with verified backup.
            # Executed after acquiring BEGIN IMMEDIATE so no concurrent writer can race or corrupt backups.
            # Dedicated reader connection captures the committed legacy database snapshot safely.
            if db_file and db_file.exists():
                primary_bak = Path(f"{db_file}.pre_migration.bak")
                if primary_bak.exists():
                    ts = int(time.time())
                    backup_path = Path(f"{db_file}.pre_migration.{ts}.bak")
                    counter = 1
                    while backup_path.exists():
                        backup_path = Path(f"{db_file}.pre_migration.{ts}_{counter}.bak")
                        counter += 1
                else:
                    backup_path = primary_bak

                backup_src = sqlite3.connect(str(db_file))
                backup_src.execute("PRAGMA busy_timeout=5000")
                backup_dest = sqlite3.connect(str(backup_path))
                try:
                    try:
                        backup_src.backup(backup_dest)
                        chk = backup_dest.execute("PRAGMA integrity_check").fetchone()
                        if not chk or chk[0] != "ok":
                            raise MigrationIntegrityError(f"Pre-migration backup integrity check failed: {chk}")
                    finally:
                        backup_dest.close()
                        backup_src.close()
                except Exception:
                    try:
                        if backup_path.exists():
                            backup_path.unlink()
                    except Exception:
                        pass
                    raise

                if not backup_path.exists() or backup_path.stat().st_size == 0:
                    raise MigrationIntegrityError(f"Pre-migration backup failed: {backup_path} is empty or missing")

            # 1. Teams (Comparing ALL columns: team_id, lead_session_id, title, created_at)
            if "orca_teams" in active_legacy_tables:
                conflicts = conn.execute("""
                    SELECT o.team_id FROM orca_teams o
                    INNER JOIN simpul_teams s ON o.team_id = s.team_id
                    WHERE o.lead_session_id != s.lead_session_id
                       OR o.title != s.title
                       OR ABS(o.created_at - s.created_at) > 0.001
                """).fetchall()
                if conflicts:
                    raise MigrationConflictError(
                        f"Conflicting primary keys between legacy orca_teams and simpul_teams: {[c[0] for c in conflicts]}"
                    )
                conn.execute("""
                    INSERT INTO simpul_teams (team_id, lead_session_id, title, created_at)
                    SELECT team_id, lead_session_id, title, created_at FROM orca_teams
                    WHERE team_id NOT IN (SELECT team_id FROM simpul_teams)
                """)
                for r in conn.execute("SELECT team_id, lead_session_id, title, created_at FROM orca_teams").fetchall():
                    nr = conn.execute("SELECT team_id, lead_session_id, title, created_at FROM simpul_teams WHERE team_id = ?", (r["team_id"],)).fetchone()
                    if nr is None or (nr["lead_session_id"], nr["title"]) != (r["lead_session_id"], r["title"]) or abs(nr["created_at"] - r["created_at"]) > 0.001:
                        raise MigrationIntegrityError(f"Row equivalence verification failure for team {r['team_id']}")

            # 2. Sessions (Comparing ALL columns: session_id, role/orca_role, team_id, status, config_json, created_at, updated_at)
            if "orca_sessions" in active_legacy_tables:
                cols = {r["name"] for r in conn.execute("PRAGMA table_info(orca_sessions)").fetchall()}
                if "orca_role" in cols:
                    conflicts = conn.execute("""
                        SELECT o.session_id FROM orca_sessions o
                        INNER JOIN simpul_sessions s ON o.session_id = s.session_id
                        WHERE o.orca_role != s.role
                           OR o.team_id != s.team_id
                           OR o.status != s.status
                           OR o.config_json != s.config_json
                           OR ABS(o.created_at - s.created_at) > 0.001
                           OR ABS(o.updated_at - s.updated_at) > 0.001
                    """).fetchall()
                    if conflicts:
                        raise MigrationConflictError(
                            f"Conflicting primary keys between legacy orca_sessions and simpul_sessions: {[c[0] for c in conflicts]}"
                        )
                    conn.execute("""
                        INSERT INTO simpul_sessions (session_id, role, team_id, status, config_json, created_at, updated_at)
                        SELECT session_id, orca_role, team_id, status, config_json, created_at, updated_at FROM orca_sessions
                        WHERE session_id NOT IN (SELECT session_id FROM simpul_sessions)
                    """)
                    for r in conn.execute("SELECT session_id, orca_role, team_id, status, config_json, created_at, updated_at FROM orca_sessions").fetchall():
                        nr = conn.execute("SELECT session_id, role, team_id, status, config_json, created_at, updated_at FROM simpul_sessions WHERE session_id = ?", (r["session_id"],)).fetchone()
                        if (
                            nr is None
                            or (nr["role"], nr["team_id"], nr["status"], nr["config_json"]) != (r["orca_role"], r["team_id"], r["status"], r["config_json"])
                            or abs(nr["created_at"] - r["created_at"]) > 0.001
                            or abs(nr["updated_at"] - r["updated_at"]) > 0.001
                        ):
                            raise MigrationIntegrityError(f"Row equivalence verification failure for session {r['session_id']}")
                else:
                    conflicts = conn.execute("""
                        SELECT o.session_id FROM orca_sessions o
                        INNER JOIN simpul_sessions s ON o.session_id = s.session_id
                        WHERE o.role != s.role
                           OR o.team_id != s.team_id
                           OR o.status != s.status
                           OR o.config_json != s.config_json
                           OR ABS(o.created_at - s.created_at) > 0.001
                           OR ABS(o.updated_at - s.updated_at) > 0.001
                    """).fetchall()
                    if conflicts:
                        raise MigrationConflictError(
                            f"Conflicting primary keys between legacy orca_sessions and simpul_sessions: {[c[0] for c in conflicts]}"
                        )
                    conn.execute("""
                        INSERT INTO simpul_sessions (session_id, role, team_id, status, config_json, created_at, updated_at)
                        SELECT session_id, role, team_id, status, config_json, created_at, updated_at FROM orca_sessions
                        WHERE session_id NOT IN (SELECT session_id FROM simpul_sessions)
                    """)
                    for r in conn.execute("SELECT session_id, role, team_id, status, config_json, created_at, updated_at FROM orca_sessions").fetchall():
                        nr = conn.execute("SELECT session_id, role, team_id, status, config_json, created_at, updated_at FROM simpul_sessions WHERE session_id = ?", (r["session_id"],)).fetchone()
                        if (
                            nr is None
                            or (nr["role"], nr["team_id"], nr["status"], nr["config_json"]) != (r["role"], r["team_id"], r["status"], r["config_json"])
                            or abs(nr["created_at"] - r["created_at"]) > 0.001
                            or abs(nr["updated_at"] - r["updated_at"]) > 0.001
                        ):
                            raise MigrationIntegrityError(f"Row equivalence verification failure for session {r['session_id']}")

            # 3. Queue (Comparing ALL columns: dispatch_id, team_id, from_session_id, to_session_id, task_id, payload_json, status, dedup_key, priority, steering_json, created_at, updated_at)
            if "orca_queue" in active_legacy_tables:
                cols = {r["name"] for r in conn.execute("PRAGMA table_info(orca_queue)").fetchall()}
                # Each optional column is handled independently; never discard a populated
                # legacy value merely because a different optional column is missing.
                optional_defaults = {
                    "dedup_key": "NULL",
                    "priority": "0",
                    "steering_json": "'[]'",
                }
                def legacy_expr(column: str) -> str:
                    return f"o.{column}" if column in cols else optional_defaults[column]

                dedup_expr = legacy_expr("dedup_key")
                priority_expr = legacy_expr("priority")
                steering_expr = legacy_expr("steering_json")
                conflicts = conn.execute(f"""  # nosec B608 - SQL fragments are fixed local identifiers from a closed allowlist
                    SELECT o.dispatch_id FROM orca_queue o
                    INNER JOIN simpul_queue s ON o.dispatch_id = s.dispatch_id
                    WHERE o.team_id IS NOT s.team_id
                       OR o.from_session_id IS NOT s.from_session_id
                       OR o.to_session_id IS NOT s.to_session_id
                       OR o.task_id IS NOT s.task_id
                       OR o.payload_json IS NOT s.payload_json
                       OR o.status IS NOT s.status
                       OR ({dedup_expr}) IS NOT s.dedup_key
                       OR ({priority_expr}) IS NOT s.priority
                       OR ({steering_expr}) IS NOT s.steering_json
                       OR o.created_at IS NOT s.created_at
                       OR o.updated_at IS NOT s.updated_at
                """).fetchall()
                if conflicts:
                    raise MigrationConflictError(
                        f"Conflicting primary keys between legacy orca_queue and simpul_queue: {[c[0] for c in conflicts]}"
                    )
                conn.execute(f"""  # nosec B608 - expressions selected solely from fixed schema-column allowlist
                    INSERT INTO simpul_queue (
                        dispatch_id, team_id, from_session_id, to_session_id,
                        task_id, payload_json, status, dedup_key, priority, steering_json,
                        created_at, updated_at
                    )
                    SELECT
                        o.dispatch_id, o.team_id, o.from_session_id, o.to_session_id,
                        o.task_id, o.payload_json, o.status,
                        {dedup_expr}, {priority_expr}, {steering_expr},
                        o.created_at, o.updated_at
                    FROM orca_queue o
                    WHERE o.dispatch_id NOT IN (SELECT dispatch_id FROM simpul_queue)
                """)
                for r in conn.execute("SELECT * FROM orca_queue").fetchall():
                    nr = conn.execute("SELECT * FROM simpul_queue WHERE dispatch_id = ?", (r["dispatch_id"],)).fetchone()
                    if nr is None:
                        raise MigrationIntegrityError(f"Row equivalence verification failure for dispatch {r['dispatch_id']}")
                    expected_dedup = r["dedup_key"] if "dedup_key" in cols else None
                    expected_priority = r["priority"] if "priority" in cols else 0
                    expected_steering = r["steering_json"] if "steering_json" in cols else "[]"
                    if (
                        nr["team_id"] != r["team_id"]
                        or nr["from_session_id"] != r["from_session_id"]
                        or nr["to_session_id"] != r["to_session_id"]
                        or nr["task_id"] != r["task_id"]
                        or nr["payload_json"] != r["payload_json"]
                        or nr["status"] != r["status"]
                        or nr["dedup_key"] != expected_dedup
                        or nr["priority"] != expected_priority
                        or nr["steering_json"] != expected_steering
                        or abs(nr["created_at"] - r["created_at"]) > 0.001
                        or abs(nr["updated_at"] - r["updated_at"]) > 0.001
                    ):
                        raise MigrationIntegrityError(f"Row equivalence verification failure for dispatch {r['dispatch_id']}")

            # 4. Worktrees (Comparing ALL columns: worker_id, team_id, worktree_path, branch_name, created_at)
            if "orca_worktrees" in active_legacy_tables:
                conflicts = conn.execute("""
                    SELECT o.worker_id FROM orca_worktrees o
                    INNER JOIN simpul_worktrees s ON o.worker_id = s.worker_id
                    WHERE o.team_id != s.team_id
                       OR o.worktree_path != s.worktree_path
                       OR o.branch_name != s.branch_name
                       OR ABS(o.created_at - s.created_at) > 0.001
                """).fetchall()
                if conflicts:
                    raise MigrationConflictError(
                        f"Conflicting primary keys between legacy orca_worktrees and simpul_worktrees: {[c[0] for c in conflicts]}"
                    )
                conn.execute("""
                    INSERT INTO simpul_worktrees (worker_id, team_id, worktree_path, branch_name, created_at)
                    SELECT worker_id, team_id, worktree_path, branch_name, created_at FROM orca_worktrees
                    WHERE worker_id NOT IN (SELECT worker_id FROM simpul_worktrees)
                """)
                for r in conn.execute("SELECT worker_id, team_id, worktree_path, branch_name, created_at FROM orca_worktrees").fetchall():
                    nr = conn.execute("SELECT worker_id, team_id, worktree_path, branch_name, created_at FROM simpul_worktrees WHERE worker_id = ?", (r["worker_id"],)).fetchone()
                    if (
                        nr is None
                        or (nr["team_id"], nr["worktree_path"], nr["branch_name"]) != (r["team_id"], r["worktree_path"], r["branch_name"])
                        or abs(nr["created_at"] - r["created_at"]) > 0.001
                    ):
                        raise MigrationIntegrityError(f"Row equivalence verification failure for worktree {r['worker_id']}")

            # 5. Handoffs (Comparing ALL columns: dispatch_id, team_id, from_worker_id, to_lead_id, status, summary, artifacts_json, metrics_json, submitted_at)
            if "orca_handoffs" in active_legacy_tables:
                conflicts = conn.execute("""
                    SELECT o.dispatch_id FROM orca_handoffs o
                    INNER JOIN simpul_handoffs s ON o.dispatch_id = s.dispatch_id
                    WHERE o.team_id != s.team_id
                       OR o.from_worker_id != s.from_worker_id
                       OR o.to_lead_id != s.to_lead_id
                       OR o.status != s.status
                       OR o.summary != s.summary
                       OR o.artifacts_json != s.artifacts_json
                       OR o.metrics_json != s.metrics_json
                       OR ABS(o.submitted_at - s.submitted_at) > 0.001
                """).fetchall()
                if conflicts:
                    raise MigrationConflictError(
                        f"Conflicting primary keys between legacy orca_handoffs and simpul_handoffs: {[c[0] for c in conflicts]}"
                    )
                conn.execute("""
                    INSERT INTO simpul_handoffs (
                        dispatch_id, team_id, from_worker_id, to_lead_id,
                        status, summary, artifacts_json, metrics_json, submitted_at
                    )
                    SELECT
                        dispatch_id, team_id, from_worker_id, to_lead_id,
                        status, summary, artifacts_json, metrics_json, submitted_at
                    FROM orca_handoffs
                    WHERE dispatch_id NOT IN (SELECT dispatch_id FROM simpul_handoffs)
                """)
                for r in conn.execute("SELECT dispatch_id, team_id, from_worker_id, to_lead_id, status, summary, artifacts_json, metrics_json, submitted_at FROM orca_handoffs").fetchall():
                    nr = conn.execute("SELECT dispatch_id, team_id, from_worker_id, to_lead_id, status, summary, artifacts_json, metrics_json, submitted_at FROM simpul_handoffs WHERE dispatch_id = ?", (r["dispatch_id"],)).fetchone()
                    if (
                        nr is None
                        or (nr["team_id"], nr["from_worker_id"], nr["to_lead_id"], nr["status"], nr["summary"], nr["artifacts_json"], nr["metrics_json"]) != (r["team_id"], r["from_worker_id"], r["to_lead_id"], r["status"], r["summary"], r["artifacts_json"], r["metrics_json"])
                        or abs(nr["submitted_at"] - r["submitted_at"]) > 0.001
                    ):
                        raise MigrationIntegrityError(f"Row equivalence verification failure for handoff {r['dispatch_id']}")

            # 6. Channel messages (Comparing ALL columns: message_id, team_id, from_session_id, to_session_id, content, role, created_at)
            if "orca_channel_messages" in active_legacy_tables:
                conflicts = conn.execute("""
                    SELECT o.message_id FROM orca_channel_messages o
                    INNER JOIN simpul_channel_messages s ON o.message_id = s.message_id
                    WHERE o.team_id != s.team_id
                       OR o.from_session_id != s.from_session_id
                       OR o.to_session_id != s.to_session_id
                       OR o.content != s.content
                       OR o.role != s.role
                       OR ABS(o.created_at - s.created_at) > 0.001
                """).fetchall()
                if conflicts:
                    raise MigrationConflictError(
                        f"Conflicting primary keys between legacy orca_channel_messages and simpul_channel_messages: {[c[0] for c in conflicts]}"
                    )
                conn.execute("""
                    INSERT INTO simpul_channel_messages (
                        message_id, team_id, from_session_id, to_session_id, content, role, created_at
                    )
                    SELECT message_id, team_id, from_session_id, to_session_id, content, role, created_at
                    FROM orca_channel_messages
                    WHERE message_id NOT IN (SELECT message_id FROM simpul_channel_messages)
                """)
                for r in conn.execute("SELECT message_id, team_id, from_session_id, to_session_id, content, role, created_at FROM orca_channel_messages").fetchall():
                    nr = conn.execute("SELECT message_id, team_id, from_session_id, to_session_id, content, role, created_at FROM simpul_channel_messages WHERE message_id = ?", (r["message_id"],)).fetchone()
                    if (
                        nr is None
                        or (nr["team_id"], nr["from_session_id"], nr["to_session_id"], nr["content"], nr["role"]) != (r["team_id"], r["from_session_id"], r["to_session_id"], r["content"], r["role"])
                        or abs(nr["created_at"] - r["created_at"]) > 0.001
                    ):
                        raise MigrationIntegrityError(f"Row equivalence verification failure for channel message {r['message_id']}")

            # 7. Checkpoints (Comparing ALL columns: checkpoint_id, worker_id, team_id, step_index, state_summary, tokens_consumed, context_json, created_at)
            if "orca_checkpoints" in active_legacy_tables:
                conflicts = conn.execute("""
                    SELECT o.checkpoint_id FROM orca_checkpoints o
                    INNER JOIN simpul_checkpoints s ON o.checkpoint_id = s.checkpoint_id
                    WHERE o.worker_id != s.worker_id
                       OR o.team_id != s.team_id
                       OR o.step_index != s.step_index
                       OR o.state_summary != s.state_summary
                       OR o.tokens_consumed != s.tokens_consumed
                       OR o.context_json != s.context_json
                       OR ABS(o.created_at - s.created_at) > 0.001
                """).fetchall()
                if conflicts:
                    raise MigrationConflictError(
                        f"Conflicting primary keys between legacy orca_checkpoints and simpul_checkpoints: {[c[0] for c in conflicts]}"
                    )
                conn.execute("""
                    INSERT INTO simpul_checkpoints (
                        checkpoint_id, worker_id, team_id, step_index,
                        state_summary, tokens_consumed, context_json, created_at
                    )
                    SELECT
                        checkpoint_id, worker_id, team_id, step_index,
                        state_summary, tokens_consumed, context_json, created_at
                    FROM orca_checkpoints
                    WHERE checkpoint_id NOT IN (SELECT checkpoint_id FROM simpul_checkpoints)
                """)
                for r in conn.execute("SELECT checkpoint_id, worker_id, team_id, step_index, state_summary, tokens_consumed, context_json, created_at FROM orca_checkpoints").fetchall():
                    nr = conn.execute("SELECT checkpoint_id, worker_id, team_id, step_index, state_summary, tokens_consumed, context_json, created_at FROM simpul_checkpoints WHERE checkpoint_id = ?", (r["checkpoint_id"],)).fetchone()
                    if (
                        nr is None
                        or (nr["worker_id"], nr["team_id"], nr["step_index"], nr["state_summary"], nr["tokens_consumed"], nr["context_json"]) != (r["worker_id"], r["team_id"], r["step_index"], r["state_summary"], r["tokens_consumed"], r["context_json"])
                        or abs(nr["created_at"] - r["created_at"]) > 0.001
                    ):
                        raise MigrationIntegrityError(f"Row equivalence verification failure for checkpoint {r['checkpoint_id']}")

            # Validate SQLite foreign keys
            fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if fk_violations:
                raise MigrationIntegrityError(f"Foreign key referential integrity violation during migration: {fk_violations}")

            # Validate application-level referential integrity across all entities
            _verify_application_referential_integrity(conn)

            # Drop legacy tables using static SQL statements
            LEGACY_DROP_MAP = {
                "orca_teams": "DROP TABLE IF EXISTS orca_teams",
                "orca_sessions": "DROP TABLE IF EXISTS orca_sessions",
                "orca_queue": "DROP TABLE IF EXISTS orca_queue",
                "orca_worktrees": "DROP TABLE IF EXISTS orca_worktrees",
                "orca_handoffs": "DROP TABLE IF EXISTS orca_handoffs",
                "orca_channel_messages": "DROP TABLE IF EXISTS orca_channel_messages",
                "orca_checkpoints": "DROP TABLE IF EXISTS orca_checkpoints",
            }
            for tbl in active_legacy_tables:
                if tbl in LEGACY_DROP_MAP:
                    conn.execute(LEGACY_DROP_MAP[tbl])

        # Establish compatibility views
        _execute_ddl_statements(conn, SIMPUL_COMPATIBILITY_VIEWS)

        # Record migration completion
        conn.execute(
            """
            INSERT OR REPLACE INTO simpul_schema_version (version, applied_at, description)
            VALUES (?, ?, ?)
            """,
            (2, time.time(), "Migrated legacy orca_* schema to simpul_* with zero data loss, row validation, and views"),
        )
        conn.execute("COMMIT")
        in_transaction = False
    except Exception:
        if in_transaction:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
        raise
    finally:
        conn.isolation_level = prev_isolation


class TeamStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        with self._lock:
            migrate_schema(self._conn, db_path=self.db_path)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> TeamStore:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # ---- Teams -----------------------------------------------------------

    def save_team(self, team: AgentTeam) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO simpul_teams (team_id, lead_session_id, title, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(team_id) DO UPDATE SET
                    lead_session_id = excluded.lead_session_id,
                    title = excluded.title
                """,
                (team.team_id, team.lead_session_id, team.title, team.created_at),
            )

    def load_team(self, team_id: str) -> AgentTeam | None:
        cur = self._conn.execute("SELECT * FROM simpul_teams WHERE team_id = ?", (team_id,))
        row = cur.fetchone()
        if not row:
            return None
        return AgentTeam(
            team_id=row["team_id"],
            lead_session_id=row["lead_session_id"],
            title=row["title"],
            created_at=row["created_at"],
        )

    # ---- Sessions --------------------------------------------------------

    def save_session(self, session: AgentSession) -> None:
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
                INSERT INTO simpul_sessions (session_id, role, team_id, status, config_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    status = excluded.status,
                    config_json = excluded.config_json,
                    updated_at = excluded.updated_at
                """,
                (
                    session.session_id,
                    session.role.value if isinstance(session.role, AgentRole) else str(session.role),
                    session.team_id,
                    session.status.value,
                    json.dumps(cfg_dict),
                    session.created_at,
                    session.updated_at,
                ),
            )

    def load_session(self, session_id: str) -> AgentSession | None:
        cur = self._conn.execute("SELECT * FROM simpul_sessions WHERE session_id = ?", (session_id,))
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_session(row)

    def list_all_sessions(self) -> list[AgentSession]:
        cur = self._conn.execute("SELECT * FROM simpul_sessions ORDER BY created_at ASC")
        return [self._row_to_session(row) for row in cur.fetchall()]

    def list_sessions_by_team(self, team_id: str) -> list[AgentSession]:
        cur = self._conn.execute(
            "SELECT * FROM simpul_sessions WHERE team_id = ? ORDER BY created_at ASC", (team_id,)
        )
        return [self._row_to_session(row) for row in cur.fetchall()]

    def _row_to_session(self, row: sqlite3.Row) -> AgentSession:
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
        keys = row.keys()
        raw_role = row["role"] if "role" in keys else row["orca_role"]
        return AgentSession(
            session_id=row["session_id"],
            role=AgentRole(raw_role),
            team_id=row["team_id"],
            status=WorkerStatus(row["status"]),
            config=cfg,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ---- Queue -----------------------------------------------------------

    def _row_to_queue_item(self, row: sqlite3.Row) -> QueueItem:
        keys = row.keys()
        steering = []
        if "steering_json" in keys and row["steering_json"]:
            try:
                steering = json.loads(row["steering_json"])
            except Exception:
                steering = []
        return QueueItem(
            dispatch_id=row["dispatch_id"],
            team_id=row["team_id"],
            from_session_id=row["from_session_id"],
            to_session_id=row["to_session_id"],
            task_id=row["task_id"],
            payload=json.loads(row["payload_json"]),
            status=QueueTaskStatus(row["status"]),
            dedup_key=row["dedup_key"] if "dedup_key" in keys else None,
            priority=row["priority"] if "priority" in keys else 0,
            steering_instructions=steering,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def save_queue_item(self, item: QueueItem) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO simpul_queue (
                    dispatch_id, team_id, from_session_id, to_session_id,
                    task_id, payload_json, status, dedup_key, priority, steering_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dispatch_id) DO UPDATE SET
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    dedup_key = excluded.dedup_key,
                    priority = excluded.priority,
                    steering_json = excluded.steering_json,
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
                    item.dedup_key,
                    item.priority,
                    json.dumps(item.steering_instructions),
                    item.created_at,
                    item.updated_at,
                ),
            )

    def load_queue_item(self, dispatch_id: str) -> QueueItem | None:
        cur = self._conn.execute("SELECT * FROM simpul_queue WHERE dispatch_id = ?", (dispatch_id,))
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_queue_item(row)

    def insert_queue_item_once(self, item: QueueItem) -> QueueItem:
        """Atomically deduplicate active/finished work across SQLite connections.

        Failed and cancelled attempts are retryable; completed work is not.
        BEGIN IMMEDIATE serializes competing writers across processes.
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                if item.dedup_key:
                    row = self._conn.execute(
                        """SELECT * FROM simpul_queue
                           WHERE team_id = ? AND dedup_key = ?
                             AND status NOT IN (?, ?)
                           ORDER BY created_at DESC LIMIT 1""",
                        (item.team_id, item.dedup_key,
                         QueueTaskStatus.FAILED.value, QueueTaskStatus.CANCELLED.value),
                    ).fetchone()
                    if row is not None:
                        self._conn.execute("COMMIT")
                        return self._row_to_queue_item(row)
                self._conn.execute(
                    """INSERT INTO simpul_queue
                       (dispatch_id, team_id, from_session_id, to_session_id,
                        task_id, payload_json, status, dedup_key, priority,
                        steering_json, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (item.dispatch_id, item.team_id, item.from_session_id,
                     item.to_session_id, item.task_id, json.dumps(item.payload),
                     item.status.value, item.dedup_key, item.priority,
                     json.dumps(item.steering_instructions),
                     item.created_at, item.updated_at),
                )
                self._conn.execute("COMMIT")
                return item
            except BaseException:
                if self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                raise

    def cancel_active_queue_item(self, dispatch_id: str, lead_session_id: str, reason: str) -> QueueItem:
        """Do not rewrite terminal completion, even if cancellation races handoff."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT * FROM simpul_queue WHERE dispatch_id = ?", (dispatch_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(dispatch_id)
                item = self._row_to_queue_item(row)
                if item.status not in (
                    QueueTaskStatus.PENDING, QueueTaskStatus.DISPATCHED,
                    QueueTaskStatus.RUNNING,
                ):
                    raise ValueError(f"Task cannot be cancelled from {item.status.value}")
                if reason:
                    item.steering_instructions.append({
                        "cancellation_reason": reason, "cancelled_by": lead_session_id,
                        "timestamp": time.time(),
                    })
                item.status = QueueTaskStatus.CANCELLED
                item.updated_at = time.time()
                cur = self._conn.execute(
                    """UPDATE simpul_queue SET status = ?, steering_json = ?, updated_at = ?
                       WHERE dispatch_id = ? AND status IN (?, ?, ?)""",
                    (item.status.value, json.dumps(item.steering_instructions),
                     item.updated_at, dispatch_id, QueueTaskStatus.PENDING.value,
                     QueueTaskStatus.DISPATCHED.value, QueueTaskStatus.RUNNING.value),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("Concurrent task finalization prevented cancellation")
                self._conn.execute("COMMIT")
                return item
            except BaseException:
                if self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                raise

    def find_queue_item_by_dedup(self, team_id: str, dedup_key: str) -> QueueItem | None:
        cur = self._conn.execute(
            """SELECT * FROM simpul_queue WHERE team_id = ? AND dedup_key = ?
               AND status NOT IN (?, ?) ORDER BY created_at DESC LIMIT 1""",
            (team_id, dedup_key, QueueTaskStatus.FAILED.value, QueueTaskStatus.CANCELLED.value)
        )
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_queue_item(row)

    def fetch_next_pending_task(self, team_id: str, worker_id: str) -> QueueItem | None:
        cur = self._conn.execute(
            """
            SELECT * FROM simpul_queue
            WHERE team_id = ? AND to_session_id = ? AND status = ?
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
            """,
            (team_id, worker_id, QueueTaskStatus.PENDING.value),
        )
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_queue_item(row)

    def list_queue_by_team(self, team_id: str) -> list[QueueItem]:
        cur = self._conn.execute(
            "SELECT * FROM simpul_queue WHERE team_id = ? ORDER BY created_at ASC", (team_id,)
        )
        return [self._row_to_queue_item(row) for row in cur.fetchall()]

    def mark_task_resuming(self, dispatch_id: str) -> QueueItem:
        with self._conn:
            cur = self._conn.execute(
                "SELECT * FROM simpul_queue WHERE dispatch_id = ?",
                (dispatch_id,),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError(f"queue item {dispatch_id!r} not found")
            status = row["status"]
            if status == QueueTaskStatus.RUNNING.value:
                raise RuntimeError(f"Concurrent resume rejected: task {dispatch_id!r} is already RUNNING")
            if status == QueueTaskStatus.COMPLETED.value:
                raise RuntimeError(f"Duplicate resume rejected: task {dispatch_id!r} is already COMPLETED")
            if status == QueueTaskStatus.CANCELLED.value:
                raise RuntimeError(f"Resume rejected: task {dispatch_id!r} is CANCELLED")

            now = time.time()
            self._conn.execute(
                "UPDATE simpul_queue SET status = ?, updated_at = ? WHERE dispatch_id = ?",
                (QueueTaskStatus.RUNNING.value, now, dispatch_id),
            )
            item = self._row_to_queue_item(row)
            item.status = QueueTaskStatus.RUNNING
            item.updated_at = now
            return item

    # ---- Channel Messages ------------------------------------------------

    def save_channel_message(self, msg: ChannelMessage) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO simpul_channel_messages (
                    message_id, team_id, from_session_id, to_session_id, content, role, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    content = excluded.content
                """,
                (
                    msg.message_id,
                    msg.team_id,
                    msg.from_session_id,
                    msg.to_session_id,
                    msg.content,
                    msg.role,
                    msg.created_at,
                ),
            )

    def list_channel_messages_by_team(self, team_id: str, limit: int = 100) -> list[ChannelMessage]:
        cur = self._conn.execute(
            """
            SELECT * FROM simpul_channel_messages
            WHERE team_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (team_id, limit),
        )
        messages = []
        for row in cur.fetchall():
            messages.append(
                ChannelMessage(
                    message_id=row["message_id"],
                    team_id=row["team_id"],
                    from_session_id=row["from_session_id"],
                    to_session_id=row["to_session_id"],
                    content=row["content"],
                    role=row["role"],
                    created_at=row["created_at"],
                )
            )
        return messages

    # ---- Worktrees -------------------------------------------------------

    def save_worktree(self, assignment: WorktreeAssignment) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO simpul_worktrees (worker_id, team_id, worktree_path, branch_name, created_at)
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
        cur = self._conn.execute("SELECT * FROM simpul_worktrees WHERE worker_id = ?", (worker_id,))
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
                INSERT INTO simpul_handoffs (
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

    def finalize_handoff_transaction(
        self,
        team_id: str,
        evidence: HandoffEvidence,
        new_queue_status: QueueTaskStatus | None = QueueTaskStatus.COMPLETED,
    ) -> None:
        """Atomically persists handoff, updates queue item status, and resets worker to IDLE.

        Guarantees transactional integrity and prevents duplicate finalization or replay across processes.
        """
        with self._conn:
            cur = self._conn.execute(
                "SELECT status, to_session_id FROM simpul_queue WHERE dispatch_id = ?",
                (evidence.dispatch_id,),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError(f"dispatch {evidence.dispatch_id!r} not found in queue")
            q_status = row["status"]
            worker_id = row["to_session_id"]
            if q_status in (QueueTaskStatus.COMPLETED.value, QueueTaskStatus.CANCELLED.value):
                raise ValueError(
                    f"Handoff already finalized for dispatch {evidence.dispatch_id!r} (queue status: {q_status})"
                )

            # Prevent duplicate handoffs in simpul_handoffs
            cur_h = self._conn.execute(
                "SELECT 1 FROM simpul_handoffs WHERE dispatch_id = ?",
                (evidence.dispatch_id,),
            )
            if cur_h.fetchone():
                raise ValueError(f"Handoff already finalized for dispatch {evidence.dispatch_id!r}")

            try:
                self._conn.execute(
                    """
                    INSERT INTO simpul_handoffs (
                        dispatch_id, team_id, from_worker_id, to_lead_id,
                        status, summary, artifacts_json, metrics_json, submitted_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            except sqlite3.IntegrityError as e:
                raise ValueError(f"Handoff already finalized for dispatch {evidence.dispatch_id!r}") from e

            now = time.time()
            if new_queue_status is not None:
                self._conn.execute(
                    "UPDATE simpul_queue SET status = ?, updated_at = ? WHERE dispatch_id = ?",
                    (new_queue_status.value, now, evidence.dispatch_id),
                )
            self._conn.execute(
                "UPDATE simpul_sessions SET status = ?, updated_at = ? WHERE session_id = ?",
                (WorkerStatus.IDLE.value, now, worker_id),
            )

    def list_handoffs_by_team(self, team_id: str) -> list[HandoffEvidence]:
        cur = self._conn.execute(
            "SELECT * FROM simpul_handoffs WHERE team_id = ? ORDER BY submitted_at ASC", (team_id,)
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

    def delete_worktree(self, worker_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM simpul_worktrees WHERE worker_id = ?", (worker_id,))

    # ---- Checkpoints -----------------------------------------------------

    def save_checkpoint(self, checkpoint: WorkerCheckpoint) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO simpul_checkpoints (
                    checkpoint_id, worker_id, team_id, step_index,
                    state_summary, tokens_consumed, context_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(checkpoint_id) DO UPDATE SET
                    step_index = excluded.step_index,
                    state_summary = excluded.state_summary,
                    tokens_consumed = excluded.tokens_consumed,
                    context_json = excluded.context_json
                """,
                (
                    checkpoint.checkpoint_id,
                    checkpoint.worker_id,
                    checkpoint.team_id,
                    checkpoint.step_index,
                    checkpoint.state_summary,
                    checkpoint.tokens_consumed,
                    json.dumps(checkpoint.context_snapshot),
                    checkpoint.created_at,
                ),
            )

    def load_latest_checkpoint(self, worker_id: str) -> WorkerCheckpoint | None:
        cur = self._conn.execute(
            """
            SELECT * FROM simpul_checkpoints
            WHERE worker_id = ?
            ORDER BY step_index DESC, created_at DESC
            LIMIT 1
            """,
            (worker_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return WorkerCheckpoint(
            checkpoint_id=row["checkpoint_id"],
            worker_id=row["worker_id"],
            team_id=row["team_id"],
            step_index=row["step_index"],
            state_summary=row["state_summary"],
            tokens_consumed=row["tokens_consumed"],
            context_snapshot=json.loads(row["context_json"]),
            created_at=row["created_at"],
        )

    def list_checkpoints(self, worker_id: str) -> list[WorkerCheckpoint]:
        cur = self._conn.execute(
            """
            SELECT * FROM simpul_checkpoints
            WHERE worker_id = ?
            ORDER BY step_index ASC, created_at ASC
            """,
            (worker_id,),
        )
        cps = []
        for row in cur.fetchall():
            cps.append(
                WorkerCheckpoint(
                    checkpoint_id=row["checkpoint_id"],
                    worker_id=row["worker_id"],
                    team_id=row["team_id"],
                    step_index=row["step_index"],
                    state_summary=row["state_summary"],
                    tokens_consumed=row["tokens_consumed"],
                    context_snapshot=json.loads(row["context_json"]),
                    created_at=row["created_at"],
                )
            )
        return cps


# Backward-compatibility alias
OrcaStore = TeamStore
