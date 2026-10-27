"""Tests for zero-data-loss schema migration from legacy orca_* to native simpul_*.

Verifies:
- Fresh database initialization with simpul_* schema, version 2, and compatibility views.
- Full lossless migration of pre-existing legacy orca_* tables with real records.
- Row-by-row equivalence, row identity, and column-by-column equality validation.
- Physical pre-migration byte backup creation and preservation (.pre_migration.bak).
- Fail-closed transactional rollback on corrupted data or injected failures.
- Rejection of conflicting primary keys against destination tables.
- Idempotent recovery from interrupted / partial migrations.
- Multi-connection concurrency and busy timeout resilience.
- Full consumer compatibility for legacy class and module aliases.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from subagentbridge.domain.team_contracts import (
    AgentRole,
    AgentSession,
    AgentTeam,
    OrcaRole,
    OrcaSession,
    OrcaTeam,
    QueueTaskStatus,
    WorkerConfig,
    WorkerStatus,
)
from subagentbridge.storage.team_store import (
    MigrationConflictError,
    MigrationIntegrityError,
    OrcaStore,
    TeamStore,
    migrate_schema,
)
from subagentbridge.team.team_manager import OrcaTeamManager, OrcaTeamService, TeamManager
from subagentbridge.execution.integration_adapter import (
    IntegrationProbe,
    OptionalIntegrationBackend,
    OptionalOrcaBackend,
    OrcaProbe,
)

LEGACY_ORCA_DDL = """
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
    dedup_key TEXT,
    priority INTEGER NOT NULL DEFAULT 0,
    steering_json TEXT NOT NULL DEFAULT '[]',
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

CREATE TABLE IF NOT EXISTS orca_channel_messages (
    message_id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    from_session_id TEXT NOT NULL,
    to_session_id TEXT NOT NULL,
    content TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS orca_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    state_summary TEXT NOT NULL,
    tokens_consumed INTEGER NOT NULL,
    context_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


def test_fresh_db_initialization():
    """Verify fresh DB initializes with simpul_* schema, version 2, and compatibility views."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "fresh.db"
        with TeamStore(db_path) as store:
            conn = store._conn
            # Verify version
            ver_row = conn.execute("SELECT MAX(version) FROM simpul_schema_version").fetchone()
            assert ver_row[0] == 2

            # Verify simpul tables exist
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            assert "simpul_teams" in tables
            assert "simpul_sessions" in tables
            assert "simpul_queue" in tables
            assert "simpul_worktrees" in tables
            assert "simpul_handoffs" in tables
            assert "simpul_channel_messages" in tables
            assert "simpul_checkpoints" in tables
            assert "simpul_schema_version" in tables

            # Verify orca compatibility views exist
            views = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()}
            assert "orca_teams" in views
            assert "orca_sessions" in views
            assert "orca_queue" in views
            assert "orca_worktrees" in views
            assert "orca_handoffs" in views
            assert "orca_channel_messages" in views
            assert "orca_checkpoints" in views

            # Write and read data via TeamStore
            team = AgentTeam(team_id="team-alpha", lead_session_id="lead-1", title="Alpha Team")
            store.save_team(team)
            loaded_team = store.load_team("team-alpha")
            assert loaded_team is not None
            assert loaded_team.title == "Alpha Team"

            # Verify data is visible through compatibility view
            v_row = conn.execute("SELECT title FROM orca_teams WHERE team_id = 'team-alpha'").fetchone()
            assert v_row[0] == "Alpha Team"


def test_legacy_orca_db_zero_data_loss_migration():
    """Verify lossless migration from pre-existing orca_* database with row equivalence."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "legacy_migration.db"

        # 1. Manually populate legacy SQLite database with old orca schema
        legacy_conn = sqlite3.connect(str(db_path))
        legacy_conn.executescript(LEGACY_ORCA_DDL)

        now = 1700000000.0

        # Insert 2 teams
        legacy_conn.execute(
            "INSERT INTO orca_teams VALUES (?, ?, ?, ?)",
            ("team-legacy-1", "lead-leg-1", "Legacy Team 1", now),
        )
        legacy_conn.execute(
            "INSERT INTO orca_teams VALUES (?, ?, ?, ?)",
            ("team-legacy-2", "lead-leg-2", "Legacy Team 2", now + 10),
        )

        # Insert 3 sessions (1 lead, 2 workers)
        cfg1 = {"worker_id": "lead-leg-1", "team_id": "team-legacy-1", "role": "lead"}
        cfg2 = {"worker_id": "worker-leg-1", "team_id": "team-legacy-1", "role": "worker", "pid": 1234}
        cfg3 = {"worker_id": "worker-leg-2", "team_id": "team-legacy-2", "role": "worker", "pid": 5678}
        legacy_conn.execute(
            "INSERT INTO orca_sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("lead-leg-1", "lead", "team-legacy-1", "IDLE", json.dumps(cfg1), now, now),
        )
        legacy_conn.execute(
            "INSERT INTO orca_sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("worker-leg-1", "worker", "team-legacy-1", "RUNNING", json.dumps(cfg2), now, now + 5),
        )
        legacy_conn.execute(
            "INSERT INTO orca_sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("worker-leg-2", "worker", "team-legacy-2", "COMPLETED", json.dumps(cfg3), now, now + 8),
        )

        # Insert 2 queue items
        legacy_conn.execute(
            "INSERT INTO orca_queue VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("dsp-001", "team-legacy-1", "lead-leg-1", "worker-leg-1", "task-1", '{"work":"build"}', "RUNNING", "dedup-1", 5, '[]', now, now + 5),
        )
        legacy_conn.execute(
            "INSERT INTO orca_queue VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("dsp-002", "team-legacy-2", "lead-leg-2", "worker-leg-2", "task-2", '{"work":"test"}', "COMPLETED", "dedup-2", 1, '[]', now, now + 10),
        )

        # Insert worktree
        legacy_conn.execute(
            "INSERT INTO orca_worktrees VALUES (?, ?, ?, ?, ?)",
            ("worker-leg-1", "team-legacy-1", "/worktrees/w1", "branch-w1", now),
        )

        # Insert handoff with metrics & hashes
        metrics = {"exit_code": 0, "receipt_id": "rcpt-leg-001", "qa_verdict": "PASS", "artifact_hashes": {"res.txt": "a" * 64}}
        legacy_conn.execute(
            "INSERT INTO orca_handoffs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("dsp-002", "team-legacy-2", "worker-leg-2", "lead-leg-2", "SUCCESS", "Completed cleanly", '["res.txt"]', json.dumps(metrics), now + 12),
        )

        # Insert channel message
        legacy_conn.execute(
            "INSERT INTO orca_channel_messages VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("msg-leg-01", "team-legacy-1", "lead-leg-1", "worker-leg-1", "Start coding", "lead", now),
        )

        # Insert checkpoint
        legacy_conn.execute(
            "INSERT INTO orca_checkpoints VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("cp-leg-01", "worker-leg-1", "team-legacy-1", 1, "Finished init", 1500, '{"commit_hash":"abc1234"}', now + 2),
        )

        legacy_conn.commit()
        legacy_conn.close()

        # 2. Open with TeamStore - triggers automatic lossless migration with backup and row validation
        with TeamStore(db_path) as store:
            # Check version
            ver_row = store._conn.execute("SELECT MAX(version) FROM simpul_schema_version").fetchone()
            assert ver_row[0] == 2

            # Check teams
            t1 = store.load_team("team-legacy-1")
            assert t1 is not None
            assert t1.title == "Legacy Team 1"
            assert t1.lead_session_id == "lead-leg-1"

            t2 = store.load_team("team-legacy-2")
            assert t2 is not None
            assert t2.title == "Legacy Team 2"

            # Check sessions
            s1 = store.load_session("worker-leg-1")
            assert s1 is not None
            assert s1.role == AgentRole.WORKER
            assert s1.orca_role == AgentRole.WORKER
            assert s1.status == WorkerStatus.RUNNING
            assert s1.config.pid == 1234

            # Check queue items
            q1 = store.load_queue_item("dsp-001")
            assert q1 is not None
            assert q1.status == QueueTaskStatus.RUNNING
            assert q1.priority == 5
            assert q1.dedup_key == "dedup-1"
            assert q1.payload == {"work": "build"}

            # Check worktrees
            wt = store.load_worktree("worker-leg-1")
            assert wt is not None
            assert wt.worktree_path == "/worktrees/w1"
            assert wt.branch_name == "branch-w1"

            # Check handoffs
            h = store.list_handoffs_by_team("team-legacy-2")
            assert len(h) == 1
            assert h[0].dispatch_id == "dsp-002"
            assert h[0].metrics["receipt_id"] == "rcpt-leg-001"
            assert h[0].artifacts == ["res.txt"]

            # Check channel messages
            msgs = store.list_channel_messages_by_team("team-legacy-1")
            assert len(msgs) == 1
            assert msgs[0].content == "Start coding"

            # Check checkpoints
            cp = store.load_latest_checkpoint("worker-leg-1")
            assert cp is not None
            assert cp.step_index == 1
            assert cp.tokens_consumed == 1500
            assert cp.context_snapshot == {"commit_hash": "abc1234"}

            # Verify legacy views queryable directly
            v_cur = store._conn.execute("SELECT session_id, orca_role FROM orca_sessions WHERE session_id = 'worker-leg-1'")
            row = v_cur.fetchone()
            assert row["session_id"] == "worker-leg-1"
            assert row["orca_role"] == "worker"


def test_pre_migration_backup_creation_and_preservation():
    """Verify that a disk-based legacy database creates a verified pre-migration backup."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "with_backup.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(LEGACY_ORCA_DDL)
        conn.execute("INSERT INTO orca_teams VALUES ('t-bk', 'l-bk', 'Backup Team', 100.0)")
        conn.commit()
        conn.close()

        # Run migration
        with TeamStore(db_path):
            pass

        # Verify pre-migration backup exists on disk and contains legacy tables intact
        bak_path = Path(str(db_path) + ".pre_migration.bak")
        assert bak_path.exists()
        assert bak_path.stat().st_size > 0

        bak_conn = sqlite3.connect(str(bak_path))
        bak_cur = bak_conn.execute("SELECT title FROM orca_teams WHERE team_id = 't-bk'")
        assert bak_cur.fetchone()[0] == "Backup Team"
        bak_conn.close()


def test_migration_rollback_on_injected_failure_preserves_tables():
    """Verify that an error during migration cleanly rolls back without dropping legacy tables."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "rollback_test.db"
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript(LEGACY_ORCA_DDL)
        conn.execute("INSERT INTO orca_teams VALUES ('t1', 'l1', 'Original Team', 100.0)")
        conn.execute("INSERT INTO orca_sessions VALUES ('s1', 'worker', 't1', 'IDLE', '{}', 100.0, 100.0)")

        # Corrupt migration by introducing a table with an incompatible schema before migrate_schema runs
        conn.execute("CREATE TABLE simpul_sessions (session_id INT PRIMARY KEY, broken_col TEXT NOT NULL)")

        with pytest.raises(Exception):
            migrate_schema(conn, db_path=db_path)

        # Verify that rollback restored legacy tables intact
        t_row = conn.execute("SELECT title FROM orca_teams WHERE team_id = 't1'").fetchone()
        assert t_row is not None
        assert t_row["title"] == "Original Team"

        s_row = conn.execute("SELECT orca_role FROM orca_sessions WHERE session_id = 's1'").fetchone()
        assert s_row is not None
        assert s_row["orca_role"] == "worker"

        conn.close()


def test_migration_rejects_conflicting_primary_keys():
    """Verify that pre-existing conflicting records in destination tables raise MigrationConflictError."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "conflict_test.db"
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript(LEGACY_ORCA_DDL)
        conn.execute("INSERT INTO orca_teams VALUES ('t-conflict', 'l-old', 'Legacy Title', 100.0)")

        # Pre-create simpul_teams with conflicting data for same primary key
        conn.execute("CREATE TABLE simpul_teams (team_id TEXT PRIMARY KEY, lead_session_id TEXT NOT NULL, title TEXT NOT NULL, created_at REAL NOT NULL)")
        conn.execute("INSERT INTO simpul_teams VALUES ('t-conflict', 'l-new', 'Different Title', 200.0)")

        with pytest.raises(MigrationConflictError) as exc_info:
            migrate_schema(conn, db_path=db_path)

        assert "Conflicting primary keys" in str(exc_info.value)

        # Legacy table must not be dropped
        tbl = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orca_teams'").fetchone()
        assert tbl is not None

        conn.close()


def test_migration_partial_recovery():
    """Verify that an interrupted migration where some identical rows exist can resume cleanly."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "partial_recovery.db"
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript(LEGACY_ORCA_DDL)

        now = 100.0
        conn.execute("INSERT INTO orca_teams VALUES ('t-part-1', 'l-1', 'Team 1', ?)", (now,))
        conn.execute("INSERT INTO orca_teams VALUES ('t-part-2', 'l-2', 'Team 2', ?)", (now + 10,))

        # Simulate partial migration: destination simpul_teams already has t-part-1 (matching)
        conn.execute("CREATE TABLE simpul_teams (team_id TEXT PRIMARY KEY, lead_session_id TEXT NOT NULL, title TEXT NOT NULL, created_at REAL NOT NULL)")
        conn.execute("INSERT INTO simpul_teams VALUES ('t-part-1', 'l-1', 'Team 1', ?)", (now,))

        # Run migration - should detect t-part-1 is identical, insert t-part-2, verify, and complete
        migrate_schema(conn, db_path=db_path)

        rows = conn.execute("SELECT team_id, title FROM simpul_teams ORDER BY team_id").fetchall()
        assert len(rows) == 2
        assert rows[0]["team_id"] == "t-part-1"
        assert rows[1]["team_id"] == "t-part-2"

        # Verify orca_teams converted to view
        view_row = conn.execute("SELECT type FROM sqlite_master WHERE name='orca_teams'").fetchone()
        assert view_row["type"] == "view"

        conn.close()


def test_idempotent_repeated_migration():
    """Verify repeated store openings or migration runs cause no errors or duplicate data."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "idempotent.db"

        # Create team and data in run 1
        with TeamStore(db_path) as s:
            s.save_team(AgentTeam("team-1", "lead-1", "Initial Team"))
            s.save_session(AgentSession("worker-1", AgentRole.WORKER, "team-1"))

        # Reopen 5 times in succession
        for _ in range(5):
            with TeamStore(db_path) as s:
                t = s.load_team("team-1")
                assert t is not None
                assert t.title == "Initial Team"
                w = s.load_session("worker-1")
                assert w is not None
                assert w.role == AgentRole.WORKER
                # Total count remains exactly 1
                assert len(s.list_sessions_by_team("team-1")) == 1


def test_multi_process_concurrency_busy_timeout():
    """Verify busy_timeout allows concurrent access without immediate database locked error."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "concurrent.db"

        # Initialize store
        with TeamStore(db_path) as s:
            s.save_team(AgentTeam("t-conc", "l-conc", "Concurrent Team"))

        # Open connection in worker thread
        def hold_lock():
            c1 = sqlite3.connect(str(db_path), timeout=5.0)
            c1.execute("PRAGMA busy_timeout=5000")
            with c1:
                c1.execute("UPDATE simpul_teams SET title='Updated Title' WHERE team_id='t-conc'")
                time.sleep(0.1)
            c1.close()

        t = threading.Thread(target=hold_lock)
        t.start()

        # Thread 2 reads concurrently with busy_timeout - must succeed
        time.sleep(0.02)
        conn2 = sqlite3.connect(str(db_path), timeout=5.0)
        conn2.execute("PRAGMA busy_timeout=5000")
        row = conn2.execute("SELECT title FROM simpul_teams WHERE team_id='t-conc'").fetchone()
        t.join()

        assert row is not None
        conn2.close()


def test_backward_compatibility_aliases_and_view_read_only():
    """Verify all legacy aliases (OrcaStore, OrcaTeamManager, OrcaTeamService, OrcaRole, etc.) behave identically."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "compat.db"

        # OrcaStore alias
        with OrcaStore(db_path) as store:
            service = OrcaTeamService(store=store)
            assert isinstance(service, TeamManager)
            assert isinstance(service, OrcaTeamManager)

            # OrcaTeam creation via service
            team = service.create_team(team_id="team-c", lead_session_id="lead-c", title="Compat Team")
            assert isinstance(team, AgentTeam)
            assert isinstance(team, OrcaTeam)

            # Worker registration with OrcaRole
            cfg = WorkerConfig(worker_id="w-compat-1", team_id="team-c", role="worker")
            session = service.register_worker(cfg)
            assert isinstance(session, AgentSession)
            assert isinstance(session, OrcaSession)
            assert session.orca_role == OrcaRole.WORKER
            assert session.role == AgentRole.WORKER

            # IntegrationProbe / OrcaProbe / OptionalOrcaBackend
            probe = OrcaProbe(available=True, enforcement_class="CLASS_A", details="Ready")
            assert isinstance(probe, IntegrationProbe)
            assert probe.available is True

            backend = OptionalOrcaBackend(enabled=False)
            assert isinstance(backend, OptionalIntegrationBackend)
            p = backend.probe()
            assert p.available is False

            # Verify view is readable
            cur = store._conn.execute("SELECT title FROM orca_teams WHERE team_id = 'team-c'")
            assert cur.fetchone()[0] == "Compat Team"


def test_omitted_column_conflicts_sessions_updated_at():
    """Verify conflict in sessions.updated_at alone fails closed with MigrationConflictError."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "sess_conflict.db"
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript(LEGACY_ORCA_DDL)
        now = 1000.0
        conn.execute("INSERT INTO orca_teams VALUES ('t1', 'l1', 'Team 1', ?)", (now,))
        conn.execute(
            "INSERT INTO orca_sessions VALUES ('s1', 'worker', 't1', 'IDLE', '{}', ?, ?)",
            (now, now),
        )

        # Pre-populate destination simpul_teams and simpul_sessions with differing updated_at
        conn.execute("CREATE TABLE simpul_teams (team_id TEXT PRIMARY KEY, lead_session_id TEXT NOT NULL, title TEXT NOT NULL, created_at REAL NOT NULL)")
        conn.execute("INSERT INTO simpul_teams VALUES ('t1', 'l1', 'Team 1', ?)", (now,))
        conn.execute("CREATE TABLE simpul_sessions (session_id TEXT PRIMARY KEY, role TEXT NOT NULL, team_id TEXT NOT NULL, status TEXT NOT NULL, config_json TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL)")
        conn.execute(
            "INSERT INTO simpul_sessions VALUES ('s1', 'worker', 't1', 'IDLE', '{}', ?, ?)",
            (now, now + 999.0),  # Differing updated_at ONLY
        )

        with pytest.raises(MigrationConflictError) as exc_info:
            migrate_schema(conn, db_path=db_path)

        assert "simpul_sessions" in str(exc_info.value)
        assert "s1" in str(exc_info.value)
        # Legacy table must remain intact
        tbl = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orca_sessions'").fetchone()
        assert tbl is not None
        conn.close()


def test_omitted_column_conflicts_queue_columns():
    """Verify conflicts exclusively in queue columns (from/to_session_id, dedup_key, priority, steering_json, timestamps)."""
    cases = [
        ("from_session_id", "from-diff", "to1", "dedup1", 1, "[]", 100.0, 100.0),
        ("to_session_id", "from1", "to-diff", "dedup1", 1, "[]", 100.0, 100.0),
        ("dedup_key", "from1", "to1", "dedup-diff", 1, "[]", 100.0, 100.0),
        ("priority", "from1", "to1", "dedup1", 99, "[]", 100.0, 100.0),
        ("steering_json", "from1", "to1", "dedup1", 1, '["diff"]', 100.0, 100.0),
        ("updated_at", "from1", "to1", "dedup1", 1, "[]", 100.0, 200.0),
        ("created_at", "from1", "to1", "dedup1", 1, "[]", 200.0, 100.0),
    ]

    for label, from_id, to_id, dedup, prio, steer, cr_at, up_at in cases:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / f"q_conflict_{label}.db"
            conn = sqlite3.connect(str(db_path), isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.executescript(LEGACY_ORCA_DDL)
            now = 100.0
            conn.execute("INSERT INTO orca_teams VALUES ('t1', 'l1', 'Team 1', ?)", (now,))
            conn.execute(
                "INSERT INTO orca_queue VALUES ('dsp-1', 't1', 'from1', 'to1', 'task1', '{}', 'PENDING', 'dedup1', 1, '[]', ?, ?)",
                (now, now),
            )

            # Pre-populate matching team in destination
            conn.execute("CREATE TABLE simpul_teams (team_id TEXT PRIMARY KEY, lead_session_id TEXT NOT NULL, title TEXT NOT NULL, created_at REAL NOT NULL)")
            conn.execute("INSERT INTO simpul_teams VALUES ('t1', 'l1', 'Team 1', ?)", (now,))

            # Destination queue with conflict ONLY in the test column
            conn.execute("""
                CREATE TABLE simpul_queue (
                    dispatch_id TEXT PRIMARY KEY, team_id TEXT NOT NULL, from_session_id TEXT NOT NULL,
                    to_session_id TEXT NOT NULL, task_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                    status TEXT NOT NULL, dedup_key TEXT, priority INTEGER NOT NULL DEFAULT 0,
                    steering_json TEXT NOT NULL DEFAULT '[]', created_at REAL NOT NULL, updated_at REAL NOT NULL
                )
            """)
            conn.execute(
                "INSERT INTO simpul_queue VALUES ('dsp-1', 't1', ?, ?, 'task1', '{}', 'PENDING', ?, ?, ?, ?, ?)",
                (from_id, to_id, dedup, prio, steer, cr_at, up_at),
            )

            with pytest.raises(MigrationConflictError) as exc_info:
                migrate_schema(conn, db_path=db_path)

            assert "simpul_queue" in str(exc_info.value), f"Failed for column {label}"
            assert "dsp-1" in str(exc_info.value), f"Failed for column {label}"
            conn.close()


def test_omitted_column_conflicts_checkpoints_columns():
    """Verify conflicts exclusively in checkpoints columns (team_id, tokens_consumed, context_json, created_at)."""
    cases = [
        ("team_id", "t-diff", 1, "summary", 10, "{}", 100.0),
        ("tokens_consumed", "t1", 1, "summary", 9999, "{}", 100.0),
        ("context_json", "t1", 1, "summary", 10, '{"diff": true}', 100.0),
        ("created_at", "t1", 1, "summary", 10, "{}", 200.0),
    ]

    for label, team_id, step, summary, tokens, ctx, cr_at in cases:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / f"cp_conflict_{label}.db"
            conn = sqlite3.connect(str(db_path), isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.executescript(LEGACY_ORCA_DDL)
            now = 100.0
            conn.execute("INSERT INTO orca_teams VALUES ('t1', 'l1', 'Team 1', ?)", (now,))
            conn.execute("INSERT INTO orca_sessions VALUES ('w1', 'worker', 't1', 'RUNNING', '{}', ?, ?)", (now, now))
            conn.execute(
                "INSERT INTO orca_checkpoints VALUES ('cp-1', 'w1', 't1', 1, 'summary', 10, '{}', ?)",
                (now,),
            )

            # Destination matching teams and sessions
            conn.execute("CREATE TABLE simpul_teams (team_id TEXT PRIMARY KEY, lead_session_id TEXT NOT NULL, title TEXT NOT NULL, created_at REAL NOT NULL)")
            conn.execute("INSERT INTO simpul_teams VALUES ('t1', 'l1', 'Team 1', ?)", (now,))
            conn.execute("CREATE TABLE simpul_sessions (session_id TEXT PRIMARY KEY, role TEXT NOT NULL, team_id TEXT NOT NULL, status TEXT NOT NULL, config_json TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL)")
            conn.execute("INSERT INTO simpul_sessions VALUES ('w1', 'worker', 't1', 'RUNNING', '{}', ?, ?)", (now, now))

            # Destination checkpoints with conflict ONLY in the tested column
            conn.execute("""
                CREATE TABLE simpul_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY, worker_id TEXT NOT NULL, team_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL, state_summary TEXT NOT NULL, tokens_consumed INTEGER NOT NULL,
                    context_json TEXT NOT NULL, created_at REAL NOT NULL
                )
            """)
            conn.execute(
                "INSERT INTO simpul_checkpoints VALUES ('cp-1', 'w1', ?, ?, ?, ?, ?, ?)",
                (team_id, step, summary, tokens, ctx, cr_at),
            )

            with pytest.raises(MigrationConflictError) as exc_info:
                migrate_schema(conn, db_path=db_path)

            assert "simpul_checkpoints" in str(exc_info.value), f"Failed for checkpoint column {label}"
            assert "cp-1" in str(exc_info.value), f"Failed for checkpoint column {label}"
            conn.close()


def test_omitted_column_conflicts_channel_messages_and_handoffs():
    """Verify conflicts exclusively in channel messages and handoffs columns."""
    # Channel message conflict in created_at
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "msg_conflict.db"
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript(LEGACY_ORCA_DDL)
        now = 100.0
        conn.execute("INSERT INTO orca_teams VALUES ('t1', 'l1', 'Team 1', ?)", (now,))
        conn.execute(
            "INSERT INTO orca_channel_messages VALUES ('m1', 't1', 's1', 's2', 'hello', 'lead', ?)",
            (now,),
        )
        conn.execute("CREATE TABLE simpul_teams (team_id TEXT PRIMARY KEY, lead_session_id TEXT NOT NULL, title TEXT NOT NULL, created_at REAL NOT NULL)")
        conn.execute("INSERT INTO simpul_teams VALUES ('t1', 'l1', 'Team 1', ?)", (now,))
        conn.execute("""
            CREATE TABLE simpul_channel_messages (
                message_id TEXT PRIMARY KEY, team_id TEXT NOT NULL, from_session_id TEXT NOT NULL,
                to_session_id TEXT NOT NULL, content TEXT NOT NULL, role TEXT NOT NULL, created_at REAL NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO simpul_channel_messages VALUES ('m1', 't1', 's1', 's2', 'hello', 'lead', ?)",
            (now + 50.0,),
        )
        with pytest.raises(MigrationConflictError) as exc_info:
            migrate_schema(conn, db_path=db_path)
        assert "simpul_channel_messages" in str(exc_info.value)
        conn.close()

    # Handoff conflict in metrics_json
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "handoff_conflict.db"
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript(LEGACY_ORCA_DDL)
        now = 100.0
        conn.execute("INSERT INTO orca_teams VALUES ('t1', 'l1', 'Team 1', ?)", (now,))
        conn.execute(
            "INSERT INTO orca_handoffs VALUES ('d1', 't1', 'w1', 'l1', 'SUCCESS', 'Done', '[]', '{\"code\": 0}', ?)",
            (now,),
        )
        conn.execute("CREATE TABLE simpul_teams (team_id TEXT PRIMARY KEY, lead_session_id TEXT NOT NULL, title TEXT NOT NULL, created_at REAL NOT NULL)")
        conn.execute("INSERT INTO simpul_teams VALUES ('t1', 'l1', 'Team 1', ?)", (now,))
        conn.execute("""
            CREATE TABLE simpul_handoffs (
                dispatch_id TEXT PRIMARY KEY, team_id TEXT NOT NULL, from_worker_id TEXT NOT NULL,
                to_lead_id TEXT NOT NULL, status TEXT NOT NULL, summary TEXT NOT NULL,
                artifacts_json TEXT NOT NULL, metrics_json TEXT NOT NULL, submitted_at REAL NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO simpul_handoffs VALUES ('d1', 't1', 'w1', 'l1', 'SUCCESS', 'Done', '[]', '{\"code\": 1}', ?)",
            (now,),
        )
        with pytest.raises(MigrationConflictError) as exc_info:
            migrate_schema(conn, db_path=db_path)
        assert "simpul_handoffs" in str(exc_info.value)
        conn.close()


def test_simultaneous_partial_migration_with_matching_and_conflicting_rows():
    """Verify simultaneous partial migration handles matching rows and rejects omitted-column conflicts."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "partial_multi.db"
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript(LEGACY_ORCA_DDL)
        now = 100.0

        # Legacy data: 2 teams, 2 sessions, 2 queue dispatches
        conn.execute("INSERT INTO orca_teams VALUES ('t1', 'l1', 'Team 1', ?)", (now,))
        conn.execute("INSERT INTO orca_teams VALUES ('t2', 'l2', 'Team 2', ?)", (now + 5,))
        conn.execute("INSERT INTO orca_sessions VALUES ('s1', 'lead', 't1', 'IDLE', '{}', ?, ?)", (now, now))
        conn.execute("INSERT INTO orca_sessions VALUES ('s2', 'worker', 't2', 'RUNNING', '{}', ?, ?)", (now, now))
        conn.execute("INSERT INTO orca_queue VALUES ('q1', 't1', 'l1', 's1', 'task-1', '{}', 'COMPLETED', 'k1', 1, '[]', ?, ?)", (now, now))
        conn.execute("INSERT INTO orca_queue VALUES ('q2', 't2', 'l2', 's2', 'task-2', '{}', 'PENDING', 'k2', 5, '[\"steer-orig\"]', ?, ?)", (now, now))

        # Destination has partial data:
        # t1 matches
        # s1 matches
        # q1 matches
        # q2 has conflict EXCLUSIVELY in steering_json
        conn.execute("CREATE TABLE simpul_teams (team_id TEXT PRIMARY KEY, lead_session_id TEXT NOT NULL, title TEXT NOT NULL, created_at REAL NOT NULL)")
        conn.execute("INSERT INTO simpul_teams VALUES ('t1', 'l1', 'Team 1', ?)", (now,))
        conn.execute("CREATE TABLE simpul_sessions (session_id TEXT PRIMARY KEY, role TEXT NOT NULL, team_id TEXT NOT NULL, status TEXT NOT NULL, config_json TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL)")
        conn.execute("INSERT INTO simpul_sessions VALUES ('s1', 'lead', 't1', 'IDLE', '{}', ?, ?)", (now, now))
        conn.execute("""
            CREATE TABLE simpul_queue (
                dispatch_id TEXT PRIMARY KEY, team_id TEXT NOT NULL, from_session_id TEXT NOT NULL,
                to_session_id TEXT NOT NULL, task_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                status TEXT NOT NULL, dedup_key TEXT, priority INTEGER NOT NULL DEFAULT 0,
                steering_json TEXT NOT NULL DEFAULT '[]', created_at REAL NOT NULL, updated_at REAL NOT NULL
            )
        """)
        conn.execute("INSERT INTO simpul_queue VALUES ('q1', 't1', 'l1', 's1', 'task-1', '{}', 'COMPLETED', 'k1', 1, '[]', ?, ?)", (now, now))
        conn.execute("INSERT INTO simpul_queue VALUES ('q2', 't2', 'l2', 's2', 'task-2', '{}', 'PENDING', 'k2', 5, '[\"steer-conflicting\"]', ?, ?)", (now, now))

        # Attempt migration -> must fail closed on q2 conflict
        with pytest.raises(MigrationConflictError) as exc_info:
            migrate_schema(conn, db_path=db_path)
        assert "simpul_queue" in str(exc_info.value)
        assert "q2" in str(exc_info.value)

        # Verify rollback: destination t2 and s2 were NOT committed
        t_row = conn.execute("SELECT team_id FROM simpul_teams WHERE team_id = 't2'").fetchone()
        assert t_row is None
        s_row = conn.execute("SELECT session_id FROM simpul_sessions WHERE session_id = 's2'").fetchone()
        assert s_row is None

        # Fix q2 conflict in destination to match legacy exactly
        conn.execute("UPDATE simpul_queue SET steering_json = '[\"steer-orig\"]' WHERE dispatch_id = 'q2'")

        # Re-run migration -> should cleanly succeed
        migrate_schema(conn, db_path=db_path)

        # Verify all records present and legacy tables converted to views
        assert len(conn.execute("SELECT * FROM simpul_teams").fetchall()) == 2
        assert len(conn.execute("SELECT * FROM simpul_sessions").fetchall()) == 2
        assert len(conn.execute("SELECT * FROM simpul_queue").fetchall()) == 2
        view_check = conn.execute("SELECT type FROM sqlite_master WHERE name = 'orca_queue'").fetchone()
        assert view_check["type"] == "view"
        conn.close()


def test_backup_readability_integrity_check_and_no_silent_overwrite():
    """Verify backup readability, PRAGMA integrity_check, and that prior backups are never overwritten."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "backup_safety.db"
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript(LEGACY_ORCA_DDL)
        conn.execute("INSERT INTO orca_teams VALUES ('t-bk-1', 'l1', 'Backup Team 1', 100.0)")
        conn.close()

        # Run migration 1 -> creates primary .pre_migration.bak
        with TeamStore(db_path):
            pass

        primary_bak = Path(f"{db_path}.pre_migration.bak")
        assert primary_bak.exists()
        bak_size = primary_bak.stat().st_size
        assert bak_size > 0

        # Verify readability and PRAGMA integrity_check on the logical snapshot backup
        b_conn = sqlite3.connect(str(primary_bak))
        chk = b_conn.execute("PRAGMA integrity_check").fetchone()
        assert chk[0] == "ok"
        t_row = b_conn.execute("SELECT title FROM orca_teams WHERE team_id = 't-bk-1'").fetchone()
        assert t_row[0] == "Backup Team 1"
        b_conn.close()

        # Record primary backup bytes to ensure it is never overwritten
        with open(primary_bak, "rb") as f:
            primary_bytes = f.read()

        # Create another legacy database with the same base name to test backup non-overwriting
        Path(db_path).unlink()
        conn2 = sqlite3.connect(str(db_path), isolation_level=None)
        conn2.row_factory = sqlite3.Row
        conn2.executescript(LEGACY_ORCA_DDL)
        conn2.execute("INSERT INTO orca_teams VALUES ('t-bk-2', 'l2', 'Backup Team 2', 200.0)")
        conn2.close()

        # Run migration 2 -> primary .pre_migration.bak already exists!
        with TeamStore(db_path):
            pass

        # Primary backup bytes must remain completely unchanged
        with open(primary_bak, "rb") as f:
            assert f.read() == primary_bytes

        # A new timestamped backup must have been created
        new_backups = list(Path(tmp_dir).glob("backup_safety.db.pre_migration.*.bak"))
        assert len(new_backups) == 1
        new_bak = new_backups[0]
        assert new_bak.exists()

        # Verify readability and integrity of the second backup
        b2_conn = sqlite3.connect(str(new_bak))
        chk2 = b2_conn.execute("PRAGMA integrity_check").fetchone()
        assert chk2[0] == "ok"
        t2_row = b2_conn.execute("SELECT title FROM orca_teams WHERE team_id = 't-bk-2'").fetchone()
        assert t2_row[0] == "Backup Team 2"
        b2_conn.close()


def test_application_level_referential_integrity():
    """Verify application-level referential integrity rejects orphaned entities without FK DDL."""
    # 1. Orphaned session (referencing non-existent team)
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "orphan_sess.db"
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript(LEGACY_ORCA_DDL)
        conn.execute("INSERT INTO orca_sessions VALUES ('s-orphan', 'worker', 'non-existent-team', 'IDLE', '{}', 100.0, 100.0)")
        with pytest.raises(MigrationIntegrityError) as exc_info:
            migrate_schema(conn, db_path=db_path)
        assert "referencing non-existent teams" in str(exc_info.value)
        conn.close()

    # 2. Orphaned queue item (referencing non-existent team)
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "orphan_queue.db"
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript(LEGACY_ORCA_DDL)
        conn.execute("INSERT INTO orca_queue VALUES ('q-orphan', 'non-existent-team', 'l1', 'w1', 't1', '{}', 'PENDING', NULL, 0, '[]', 100.0, 100.0)")
        with pytest.raises(MigrationIntegrityError) as exc_info:
            migrate_schema(conn, db_path=db_path)
        assert "referencing non-existent teams" in str(exc_info.value)
        conn.close()

    # 3. Orphaned checkpoint (referencing non-existent worker session)
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "orphan_cp.db"
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript(LEGACY_ORCA_DDL)
        conn.execute("INSERT INTO orca_teams VALUES ('t1', 'l1', 'Team 1', 100.0)")
        conn.execute("INSERT INTO orca_checkpoints VALUES ('cp-orphan', 'non-existent-worker', 't1', 1, 'summary', 0, '{}', 100.0)")
        with pytest.raises(MigrationIntegrityError) as exc_info:
            migrate_schema(conn, db_path=db_path)
        assert "referencing non-existent worker sessions" in str(exc_info.value)
        conn.close()


def test_injected_failure_after_copy_before_drop_restores_state(monkeypatch):
    """Verify an injected failure after data copying but before legacy DROP cleanly rolls back and restores state."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "injected_fail.db"
        conn = sqlite3.connect(str(db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(LEGACY_ORCA_DDL)
            now = 100.0
            conn.execute("INSERT INTO orca_teams VALUES ('t-inj', 'l-inj', 'Team Injected', ?)", (now,))
            conn.execute("INSERT INTO orca_sessions VALUES ('s-inj', 'worker', 't-inj', 'IDLE', '{}', ?, ?)", (now, now))

            from subagentbridge.storage import team_store

            def fake_integrity(c):
                raise RuntimeError("Injected failure after copying all tables, immediately before legacy table DROP")

            monkeypatch.setattr(team_store, "_verify_application_referential_integrity", fake_integrity)

            with pytest.raises(RuntimeError) as exc_info:
                migrate_schema(conn, db_path=db_path)
            assert "Injected failure after copying" in str(exc_info.value)

            # Legacy tables MUST remain intact as regular tables with all rows
            t_row = conn.execute("SELECT title FROM orca_teams WHERE team_id = 't-inj'").fetchone()
            assert t_row is not None
            assert t_row["title"] == "Team Injected"

            s_row = conn.execute("SELECT orca_role FROM orca_sessions WHERE session_id = 's-inj'").fetchone()
            assert s_row is not None
            assert s_row["orca_role"] == "worker"

            # Simpul tables must have rolled back completely (DDL/data rolled back)
            simpul_tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "simpul_teams" in simpul_tables:
                simpul_t = conn.execute("SELECT * FROM simpul_teams WHERE team_id = 't-inj'").fetchone()
                assert simpul_t is None
            else:
                assert "simpul_teams" not in simpul_tables
        finally:
            conn.close()


def test_deterministic_two_connection_concurrent_migration_race(monkeypatch):
    """Verify deterministic two-connection concurrency where both initializers observe legacy tables before migration completes.

    Addresses Codex review comment 4375020701:
    Ensures the second connection re-queries active legacy tables after acquiring BEGIN IMMEDIATE,
    avoiding stale pre-lock table metadata and avoiding DROP TABLE against compatibility views.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "race_det.db"
        conn_init = sqlite3.connect(str(db_path), isolation_level=None)
        conn_init.row_factory = sqlite3.Row
        conn_init.executescript(LEGACY_ORCA_DDL)
        now = 123.45
        conn_init.execute("INSERT INTO orca_teams VALUES ('t-race', 'l-race', 'Race Team', ?)", (now,))
        conn_init.execute("INSERT INTO orca_sessions VALUES ('s-race', 'worker', 't-race', 'IDLE', '{}', ?, ?)", (now, now))
        conn_init.close()

        t1_in_lock = threading.Event()
        t2_competing = threading.Event()
        errors: list[tuple[str, Exception]] = []

        from subagentbridge.storage import team_store
        orig_integrity = team_store._verify_application_referential_integrity

        def synchronized_integrity(c):
            # Signal that connection 1 holds BEGIN IMMEDIATE
            t1_in_lock.set()
            # Wait until connection 2 has started competing for the lock
            t2_competing.wait(timeout=5.0)
            # Brief pause to ensure connection 2 is actively blocked on BEGIN IMMEDIATE
            time.sleep(0.08)
            return orig_integrity(c)

        monkeypatch.setattr(team_store, "_verify_application_referential_integrity", synchronized_integrity)

        def worker1():
            try:
                c1 = sqlite3.connect(str(db_path), check_same_thread=False)
                c1.row_factory = sqlite3.Row
                c1.execute("PRAGMA journal_mode=WAL")
                c1.execute("PRAGMA busy_timeout=5000")
                migrate_schema(c1, db_path=db_path)
                c1.close()
            except Exception as e:
                errors.append(("w1", e))

        def worker2():
            try:
                # Wait until connection 1 has acquired BEGIN IMMEDIATE
                assert t1_in_lock.wait(timeout=5.0)
                c2 = sqlite3.connect(str(db_path), check_same_thread=False)
                c2.row_factory = sqlite3.Row
                c2.execute("PRAGMA journal_mode=WAL")
                c2.execute("PRAGMA busy_timeout=5000")

                # Connection 2 explicitly observes legacy database before competing for write lock
                pre_tables = {r[0] for r in c2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                assert "orca_teams" in pre_tables
                assert "orca_sessions" in pre_tables

                # Signal connection 1 that connection 2 is now competing for the write lock
                t2_competing.set()

                # Connection 2 attempts migration: will block until Connection 1 commits
                migrate_schema(c2, db_path=db_path)
                c2.close()
            except Exception as e:
                errors.append(("w2", e))

        th1 = threading.Thread(target=worker1, name="Init-Thread-1")
        th2 = threading.Thread(target=worker2, name="Init-Thread-2")
        th1.start()
        th2.start()
        th1.join(timeout=10.0)
        th2.join(timeout=10.0)

        assert not errors, f"Concurrent initializers encountered errors: {errors}"

        # Verify final database state
        verify_conn = sqlite3.connect(str(db_path))
        verify_conn.row_factory = sqlite3.Row
        try:
            ver = verify_conn.execute("SELECT MAX(version) FROM simpul_schema_version").fetchone()[0]
            assert ver == 2

            # All original rows intact in simpul_* tables
            team_row = verify_conn.execute("SELECT * FROM simpul_teams WHERE team_id='t-race'").fetchone()
            assert team_row is not None
            assert team_row["title"] == "Race Team"

            sess_row = verify_conn.execute("SELECT * FROM simpul_sessions WHERE session_id='s-race'").fetchone()
            assert sess_row is not None
            assert sess_row["role"] == "worker"

            # Compatibility views valid and return exact rows
            v_team = verify_conn.execute("SELECT * FROM orca_teams WHERE team_id='t-race'").fetchone()
            assert v_team is not None
            assert v_team["title"] == "Race Team"

            v_sess = verify_conn.execute("SELECT * FROM orca_sessions WHERE session_id='s-race'").fetchone()
            assert v_sess is not None
            assert v_sess["orca_role"] == "worker"

            # Master table objects must be views, NOT tables
            master_entry = verify_conn.execute("SELECT type FROM sqlite_master WHERE name='orca_teams'").fetchone()
            assert master_entry[0] == "view"

            # Pre-migration backup is collision-safe and verified
            backups = list(Path(tmp_dir).glob("race_det.db.pre_migration*.bak"))
            assert len(backups) == 1
        finally:
            verify_conn.close()


def test_deterministic_two_process_concurrent_migration_race():
    """Verify concurrent initialization across two independent operating system processes."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "race_proc.db"
        conn_init = sqlite3.connect(str(db_path))
        conn_init.execute("PRAGMA journal_mode=WAL")
        conn_init.executescript(LEGACY_ORCA_DDL)
        conn_init.execute("INSERT INTO orca_teams VALUES ('t-proc', 'l-proc', 'Process Team', 150.0)")
        conn_init.commit()
        conn_init.close()

        worker_script = f"""
import sys
sys.path.insert(0, r"{Path.cwd()}")
import sqlite3
from pathlib import Path
from subagentbridge.storage.team_store import TeamStore

db_file = Path(r"{db_path}")

# Under real OS scheduling, either legacy tables OR migrated tables may
# already be visible. Both states are legal; final persisted data must match.
pre_conn = sqlite3.connect(str(db_file))
pre_tables = {{r[0] for r in pre_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}}
pre_conn.close()
assert "orca_teams" in pre_tables or "simpul_teams" in pre_tables

# Compete for migration write lock and team access
with TeamStore(db_file) as store:
    t = store.load_team("t-proc")
    assert t is not None
    assert t.title == "Process Team"

print("PROC_MIGRATION_OK")
"""

        p1 = subprocess.Popen([sys.executable, "-c", worker_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        p2 = subprocess.Popen([sys.executable, "-c", worker_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        out1, err1 = p1.communicate(timeout=20)
        out2, err2 = p2.communicate(timeout=20)

        assert p1.returncode == 0, f"Process 1 failed with error: {err1}"
        assert p2.returncode == 0, f"Process 2 failed with error: {err2}"
        assert "PROC_MIGRATION_OK" in out1
        assert "PROC_MIGRATION_OK" in out2

        # Verify database
        c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        try:
            ver = c.execute("SELECT MAX(version) FROM simpul_schema_version").fetchone()[0]
            assert ver == 2
            row = c.execute("SELECT * FROM simpul_teams WHERE team_id='t-proc'").fetchone()
            assert row is not None
            assert row["title"] == "Process Team"
            v_type = c.execute("SELECT type FROM sqlite_master WHERE name='orca_teams'").fetchone()[0]
            assert v_type == "view"
        finally:
            c.close()


def test_concurrent_multi_thread_stress_initialization():
    """Verify repeated concurrency stress with 10 threads competing simultaneously for migration."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "stress.db"
        conn_init = sqlite3.connect(str(db_path))
        conn_init.execute("PRAGMA journal_mode=WAL")
        conn_init.executescript(LEGACY_ORCA_DDL)
        conn_init.execute("INSERT INTO orca_teams VALUES ('t-stress', 'l-stress', 'Stress Team', 200.0)")
        conn_init.commit()
        conn_init.close()

        num_threads = 10
        barrier = threading.Barrier(num_threads)
        errors: list[tuple[int, Exception]] = []

        def stress_worker(worker_idx: int):
            try:
                barrier.wait()
                with TeamStore(db_path) as store:
                    team = store.load_team("t-stress")
                    assert team is not None
                    assert team.title == "Stress Team"
            except Exception as e:
                errors.append((worker_idx, e))

        threads = [threading.Thread(target=stress_worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

        assert not errors, f"Errors occurred during 10-thread stress: {errors}"

        # Verify only a single valid pre-migration backup is created
        backups = list(Path(tmp_dir).glob("stress.db.pre_migration*.bak"))
        assert len(backups) == 1
        bak_conn = sqlite3.connect(str(backups[0]))
        chk = bak_conn.execute("PRAGMA integrity_check").fetchone()
        assert chk[0] == "ok"
        bak_conn.close()


def test_concurrency_failure_injection_and_competing_initializer_recovery(monkeypatch):
    """Verify when an initializer fails and rolls back, a competing waiting initializer recovers cleanly."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "fail_compete.db"
        conn_init = sqlite3.connect(str(db_path))
        conn_init.execute("PRAGMA journal_mode=WAL")
        conn_init.executescript(LEGACY_ORCA_DDL)
        conn_init.execute("INSERT INTO orca_teams VALUES ('t-inj-fail', 'l-fail', 'Failure Recovery Team', 300.0)")
        conn_init.commit()
        conn_init.close()

        t1_in_lock = threading.Event()
        t2_competing = threading.Event()

        from subagentbridge.storage import team_store
        orig_integrity = team_store._verify_application_referential_integrity

        def failing_integrity(c):
            if threading.current_thread().name == "Failing-Thread-1":
                t1_in_lock.set()
                t2_competing.wait(timeout=5.0)
                time.sleep(0.05)
                raise RuntimeError("Injected transaction failure in Thread 1")
            return orig_integrity(c)

        monkeypatch.setattr(team_store, "_verify_application_referential_integrity", failing_integrity)

        thread_errors: dict[str, Exception] = {}

        def worker1():
            c1 = sqlite3.connect(str(db_path), check_same_thread=False)
            c1.row_factory = sqlite3.Row
            c1.execute("PRAGMA journal_mode=WAL")
            c1.execute("PRAGMA busy_timeout=5000")
            try:
                migrate_schema(c1, db_path=db_path)
            except Exception as e:
                thread_errors["t1"] = e
            finally:
                c1.close()

        def worker2():
            # Wait for thread 1 to hold the lock
            assert t1_in_lock.wait(timeout=5.0)
            c2 = sqlite3.connect(str(db_path), check_same_thread=False)
            c2.row_factory = sqlite3.Row
            c2.execute("PRAGMA journal_mode=WAL")
            c2.execute("PRAGMA busy_timeout=5000")
            t2_competing.set()
            try:
                migrate_schema(c2, db_path=db_path)
            except Exception as e:
                thread_errors["t2"] = e
            finally:
                c2.close()

        th1 = threading.Thread(target=worker1, name="Failing-Thread-1")
        th2 = threading.Thread(target=worker2, name="Recovering-Thread-2")
        th1.start()
        th2.start()
        th1.join(timeout=10.0)
        th2.join(timeout=10.0)

        # Thread 1 must have failed with injected error and rolled back
        assert "t1" in thread_errors
        assert "Injected transaction failure in Thread 1" in str(thread_errors["t1"])

        # Thread 2 must have succeeded after acquiring lock
        assert "t2" not in thread_errors, f"Thread 2 failed unexpectedly: {thread_errors.get('t2')}"

        # Verify database successfully migrated to version 2 by Thread 2
        c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        try:
            ver = c.execute("SELECT MAX(version) FROM simpul_schema_version").fetchone()[0]
            assert ver == 2
            row = c.execute("SELECT * FROM simpul_teams WHERE team_id='t-inj-fail'").fetchone()
            assert row is not None
            assert row["title"] == "Failure Recovery Team"
        finally:
            c.close()


def test_failed_begin_immediate_does_not_mask_original_error():
    """Verify that a failed BEGIN IMMEDIATE raises the original sqlite3.OperationalError without masking."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "lock_mask.db"
        conn_holder = sqlite3.connect(str(db_path), isolation_level=None)
        conn_holder.execute("PRAGMA journal_mode=WAL")
        conn_holder.execute("CREATE TABLE orca_teams (team_id TEXT PRIMARY KEY, lead_session_id TEXT, title TEXT, created_at REAL)")
        conn_holder.execute("INSERT INTO orca_teams VALUES ('t-mask', 'l-mask', 'Mask Team', 100.0)")

        # Hold exclusive transaction lock
        conn_holder.execute("BEGIN EXCLUSIVE")

        conn_competing = sqlite3.connect(str(db_path), isolation_level=None)
        conn_competing.execute("PRAGMA busy_timeout=50")

        raised_exc: Exception | None = None
        try:
            migrate_schema(conn_competing, db_path=db_path)
        except Exception as e:
            raised_exc = e

        assert raised_exc is not None
        assert isinstance(raised_exc, sqlite3.OperationalError)
        msg = str(raised_exc).lower()
        assert "database is locked" in msg or "busy" in msg
        assert "cannot rollback" not in msg

        conn_holder.execute("ROLLBACK")
        conn_holder.close()
        conn_competing.close()


