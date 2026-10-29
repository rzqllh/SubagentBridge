"""Identity integrity: team lead and worker IDs must never be silently upserted."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from subagentbridge.domain.team_contracts import AgentRole, WorkerConfig
from subagentbridge.storage.team_store import TeamStore
from subagentbridge.team.team_manager import TeamManager


def test_exact_team_registration_is_idempotent_but_lead_takeover_is_denied():
    with TemporaryDirectory() as td, TeamStore(Path(td) / "team.db") as store:
        manager = TeamManager(store)
        first = manager.create_team("alpha", "lead-a", "Alpha")
        again = manager.create_team("alpha", "lead-a", "Alpha")
        assert first.created_at == again.created_at
        with pytest.raises(PermissionError, match="owner"):
            manager.create_team("alpha", "lead-evil", "Alpha")
        with pytest.raises(PermissionError, match="title"):
            manager.create_team("alpha", "lead-a", "Hijacked title")
        with pytest.raises(PermissionError, match="lead session identity"):
            manager.create_team("evil", "lead-a", "Another team")
        assert store.load_team("evil") is None
        assert store.load_team("alpha").lead_session_id == "lead-a"
        assert store.load_session("lead-a").role == AgentRole.LEAD


def test_single_worker_never_overwrites_lead_or_another_team_worker():
    with TemporaryDirectory() as td, TeamStore(Path(td) / "team.db") as store:
        manager = TeamManager(store)
        manager.create_team("alpha", "lead-a", "Alpha")
        manager.create_team("beta", "lead-b", "Beta")
        first = manager.register_worker(WorkerConfig(
            worker_id="worker-a", team_id="alpha", role="coder",
            model="native", provider="local",
        ))
        assert first.config.role == "coder"
        with pytest.raises(ValueError, match="already registered"):
            manager.register_worker(WorkerConfig(
                worker_id="worker-a", team_id="alpha", role="qa",
                model="hijacked",
            ))
        with pytest.raises(ValueError, match="already registered"):
            manager.register_worker(WorkerConfig(
                worker_id="worker-a", team_id="beta", role="qa",
            ))
        with pytest.raises(ValueError, match="team binding"):
            manager.create_worker("alpha", WorkerConfig(worker_id="foreign", team_id="beta"))
        with pytest.raises(PermissionError, match="lead identity"):
            manager.register_worker(WorkerConfig(worker_id="lead-a", team_id="alpha"))
        with pytest.raises(ValueError, match="role"):
            manager.register_worker(WorkerConfig(worker_id="spoof", team_id="alpha", role="lead"))
        with pytest.raises(PermissionError, match="unverified OS process"):
            manager.register_worker(WorkerConfig(worker_id="pid", team_id="alpha", pid=1234))
        assert store.load_session("worker-a").config.model == "native"
        assert store.load_session("lead-a").role == AgentRole.LEAD
        assert store.load_session("spoof") is None
        assert store.load_session("foreign") is None


def test_atomic_worker_with_worktree_records_preserve_binding():
    with TemporaryDirectory() as td, TeamStore(Path(td) / "team.db") as store:
        manager = TeamManager(store)
        manager.create_team("alpha", "lead-a", "Alpha")
        session = manager.create_worker(
            "alpha", WorkerConfig(worker_id="w", team_id="alpha"),
            worktree_path=str(Path(td) / "workspace"), branch_name="feat/w",
        )
        assert session.role == AgentRole.WORKER
        wt = store.load_worktree("w")
        assert wt is not None and wt.team_id == "alpha" and wt.branch_name == "feat/w"
        with pytest.raises(ValueError, match="already registered"):
            manager.create_worker(
                "alpha", WorkerConfig(worker_id="w", team_id="alpha"),
                worktree_path=str(Path(td) / "evil"), branch_name="feat/evil",
            )
        assert store.load_worktree("w").branch_name == "feat/w"


def test_two_supervisor_connections_cannot_claim_same_worker_identity():
    with TemporaryDirectory() as td:
        db = Path(td) / "team.db"
        with TeamStore(db) as root:
            manager = TeamManager(root)
            manager.create_team("alpha", "lead-a", "Alpha")
            manager.create_team("beta", "lead-b", "Beta")
        with TeamStore(db) as a, TeamStore(db) as b:
            def claim(store: TeamStore, team_id: str) -> str:
                try:
                    TeamManager(store).register_worker(
                        WorkerConfig(worker_id="shared-id", team_id=team_id),
                    )
                    return "ADMITTED"
                except ValueError as exc:
                    assert "already registered" in str(exc)
                    return "BLOCKED"
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(claim, a, "alpha"), pool.submit(claim, b, "beta")]
                assert sorted(f.result(timeout=10) for f in futures) == ["ADMITTED", "BLOCKED"]
            owners = [a.load_session("shared-id")]
            assert len(owners) == 1 and owners[0].team_id in ("alpha", "beta")
