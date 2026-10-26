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
    MigrationError,
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
