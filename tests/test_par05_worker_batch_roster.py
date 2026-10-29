"""PAR-05: bounded atomic worker roster, no implicit subprocess execution."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from subagentbridge.domain.team_contracts import AgentRole, WorkerConfig, WorkerStatus
from subagentbridge.storage.team_store import TeamStore
from subagentbridge.team.team_manager import TeamManager


def _cfg(wid: str, team: str = "alpha", role: str = "developer") -> WorkerConfig:
    return WorkerConfig(
        worker_id=wid, team_id=team, role=role, harness="native",
        model="native", provider="local", fallback_to_native=False,
    )


def test_atomic_batch_preserves_roles_models_and_does_not_launch_workers():
    with TemporaryDirectory() as td, TeamStore(Path(td) / "teams.db") as store:
        manager = TeamManager(store)
        manager.create_team("alpha", "lead-a", "Test team")
        new = manager.create_workers_batch(
            "lead-a", "alpha", [_cfg("dev-a"), _cfg("qa-a", role="qa")],
            max_workers=2,
        )
        assert [s.session_id for s in new] == ["dev-a", "qa-a"]
        assert all(s.role == AgentRole.WORKER and s.status == WorkerStatus.IDLE for s in new)
        assert all(s.config.pid is None for s in new)
        assert [s.config.role for s in manager.list_workers("alpha")] == ["developer", "qa"]
        assert store.load_session("qa-a").config.model == "native"
        assert store.load_session("qa-a").config.provider == "local"


def test_batch_rejects_cross_team_spoof_duplicate_and_over_capacity_without_partial_write():
    with TemporaryDirectory() as td, TeamStore(Path(td) / "teams.db") as store:
        manager = TeamManager(store)
        manager.create_team("alpha", "lead-a", "Alpha")
        manager.create_team("beta", "lead-b", "Beta")
        with pytest.raises(PermissionError, match="lead"):
            manager.create_workers_batch("lead-b", "alpha", [_cfg("unauthorized")])
        with pytest.raises(ValueError, match="team binding"):
            manager.create_workers_batch("lead-a", "alpha", [_cfg("foreign", "beta")])
        with pytest.raises(ValueError, match="duplicate"):
            manager.create_workers_batch("lead-a", "alpha", [_cfg("duplicate"), _cfg("duplicate")])
        with pytest.raises(PermissionError, match="unverified live process"):
            manager.create_workers_batch(
                "lead-a", "alpha",
                [WorkerConfig(worker_id="adopted", team_id="alpha", pid=1234)],
            )
        assert manager.list_workers("alpha") == []
        manager.create_workers_batch("lead-a", "alpha", [_cfg("first")], max_workers=2)
        with pytest.raises(ValueError, match="capacity"):
            manager.create_workers_batch(
                "lead-a", "alpha", [_cfg("second"), _cfg("third")], max_workers=2,
            )
        assert [s.session_id for s in manager.list_workers("alpha")] == ["first"]
        with pytest.raises(ValueError, match="already registered"):
            manager.create_workers_batch("lead-a", "alpha", [_cfg("first")], max_workers=2)
        assert store.load_session("first").config.role == "developer"
        assert store.load_session("lead-a").role == AgentRole.LEAD


def test_two_supervisor_connections_cannot_overbook_worker_capacity():
    with TemporaryDirectory() as td:
        db = Path(td) / "teams.db"
        with TeamStore(db) as bootstrap:
            TeamManager(bootstrap).create_team("alpha", "lead-a", "Alpha")
        with TeamStore(db) as one, TeamStore(db) as two:
            m1, m2 = TeamManager(one), TeamManager(two)

            def enroll(manager: TeamManager, worker_id: str) -> str:
                try:
                    manager.create_workers_batch(
                        "lead-a", "alpha", [_cfg(worker_id)], max_workers=1,
                    )
                    return "ACCEPTED"
                except ValueError as exc:
                    assert "capacity" in str(exc)
                    return "CAPACITY_BLOCKED"

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = [
                    pool.submit(enroll, m1, "w1"),
                    pool.submit(enroll, m2, "w2"),
                ]
                values = [x.result(timeout=10) for x in results]
            assert sorted(values) == ["ACCEPTED", "CAPACITY_BLOCKED"]
            assert len(one.list_sessions_by_team("alpha")) == 2  # lead + one worker


def test_legacy_single_worker_registration_does_not_gain_batch_permissions():
    with TemporaryDirectory() as td, TeamStore(Path(td) / "teams.db") as store:
        manager = TeamManager(store)
        manager.create_team("alpha", "lead-a", "Alpha")
        with pytest.raises(ValueError, match="worker role"):
            manager.create_workers_batch("lead-a", "alpha", [_cfg("lead-spoof", role="lead")])
        assert manager.list_workers("alpha") == []
