"""Unit tests for Phase C01: Cindy/Orca Parity Foundation.

Covers the 8 baseline acceptance requirements:
1. Distinct Lead and Worker sessions with real identity and lifecycle.
2. Per-worker model, harness, provider, and effort configuration.
3. Dispatch returning a durable queue handle with state tracking.
4. Worker interrupt preemption setting INTERRUPTED status.
5. Structured Worker-to-Lead handoff with evidence payload.
6. Process restart reconstruction from durable SQLite persistence.
7. Per-worker worktree assignment and isolation tracking.
8. Default-deny command authorization enforcement at worker execution boundary.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from subagentbridge.domain.orca_contracts import (
    OrcaRole,
    WorkerStatus,
    QueueTaskStatus,
    WorkerConfig,
    QueueItem,
    HandoffEvidence,
)
from subagentbridge.team.orca_team import OrcaTeamManager
from subagentbridge.storage.orca_store import OrcaStore


def test_c01_lead_worker_distinct_sessions():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca.db") as store:
            manager = OrcaTeamManager(store=store)

            team = manager.create_team(team_id="team-alpha", lead_session_id="lead-001", title="Alpha Team")
            assert team.team_id == "team-alpha"
            assert team.lead_session_id == "lead-001"

            lead_session = manager.get_session("lead-001")
            assert lead_session is not None
            assert lead_session.orca_role == OrcaRole.LEAD
            assert lead_session.status == WorkerStatus.IDLE

            w1_cfg = WorkerConfig(
                worker_id="worker-dev-1",
                team_id="team-alpha",
                role="coder",
                harness="native",
                model="claude-3-5-sonnet",
            )
            w1_session = manager.create_worker("team-alpha", w1_cfg)

            assert w1_session.session_id == "worker-dev-1"
            assert w1_session.orca_role == OrcaRole.WORKER
            assert w1_session.session_id != lead_session.session_id
            assert w1_session.status == WorkerStatus.IDLE

            # Status transition is independent
            manager.set_worker_status("worker-dev-1", WorkerStatus.RUNNING)
            assert manager.get_session("worker-dev-1").status == WorkerStatus.RUNNING
            assert manager.get_session("lead-001").status == WorkerStatus.IDLE


def test_c01_worker_has_own_model_config():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca.db") as store:
            manager = OrcaTeamManager(store=store)
            manager.create_team("team-multi", "lead-root", "Multi-Agent Team")

            cfg_sonnet = WorkerConfig(
                worker_id="worker-sonnet",
                team_id="team-multi",
                role="architect",
                harness="antigravity",
                model="claude-3-5-sonnet-20241022",
                provider="anthropic",
                effort="high",
                budget_tokens=50000,
            )
            cfg_gpt = WorkerConfig(
                worker_id="worker-gpt",
                team_id="team-multi",
                role="tester",
                harness="codex",
                model="gpt-4o",
                provider="openai",
                effort="medium",
                budget_tokens=20000,
            )

            w_sonnet = manager.create_worker("team-multi", cfg_sonnet)
            w_gpt = manager.create_worker("team-multi", cfg_gpt)

            assert w_sonnet.config.model == "claude-3-5-sonnet-20241022"
            assert w_sonnet.config.harness == "antigravity"
            assert w_sonnet.config.effort == "high"
            assert w_sonnet.config.budget_tokens == 50000

            assert w_gpt.config.model == "gpt-4o"
            assert w_gpt.config.harness == "codex"
            assert w_gpt.config.effort == "medium"
            assert w_gpt.config.budget_tokens == 20000


def test_c01_dispatch_returns_queue_handle():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca.db") as store:
            manager = OrcaTeamManager(store=store)
            manager.create_team("team-dispatch", "lead-d", "Dispatch Team")
            w_cfg = WorkerConfig(worker_id="worker-d1", team_id="team-dispatch", role="dev", harness="native")
            manager.create_worker("team-dispatch", w_cfg)

            payload = {"instruction": "Implement module X", "files": ["module_x.py"]}
            queue_item = manager.dispatch_task(
                from_session_id="lead-d",
                to_session_id="worker-d1",
                task_id="task-101",
                payload=payload,
            )

            assert isinstance(queue_item, QueueItem)
            assert queue_item.dispatch_id.startswith("dsp-")
            assert queue_item.task_id == "task-101"
            assert queue_item.to_session_id == "worker-d1"
            assert queue_item.status == QueueTaskStatus.PENDING
            assert queue_item.payload == payload

            # Advance queue state
            updated = manager.update_queue_status(queue_item.dispatch_id, QueueTaskStatus.RUNNING)
            assert updated.status == QueueTaskStatus.RUNNING


def test_c01_interrupt_preempts_worker():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca.db") as store:
            manager = OrcaTeamManager(store=store)
            manager.create_team("team-int", "lead-i", "Interrupt Team")
            w_cfg = WorkerConfig(worker_id="worker-i1", team_id="team-int", role="worker", harness="native")
            manager.create_worker("team-int", w_cfg)

            queue_item = manager.dispatch_task("lead-i", "worker-i1", "task-heavy", {"goal": "long running"})
            manager.update_queue_status(queue_item.dispatch_id, QueueTaskStatus.RUNNING)
            manager.set_worker_status("worker-i1", WorkerStatus.RUNNING)

            # Preempt the worker
            interrupted = manager.interrupt_worker("worker-i1")
            assert interrupted is True

            # Task and worker reflect interrupt
            w_after = manager.get_session("worker-i1")
            assert w_after.status == WorkerStatus.INTERRUPTED

            item_after = manager.get_queue_item(queue_item.dispatch_id)
            assert item_after.status == QueueTaskStatus.INTERRUPTED


def test_c01_worker_to_lead_handoff():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca.db") as store:
            manager = OrcaTeamManager(store=store)
            manager.create_team("team-handoff", "lead-h", "Handoff Team")
            w_cfg = WorkerConfig(worker_id="worker-h1", team_id="team-handoff", role="qa", harness="native")
            manager.create_worker("team-handoff", w_cfg)

            q_item = manager.dispatch_task("lead-h", "worker-h1", "task-verify", {"target": "unit tests"})

            evidence = HandoffEvidence(
                dispatch_id=q_item.dispatch_id,
                from_worker_id="worker-h1",
                to_lead_id="lead-h",
                status="PASSED",
                summary="All 10 tests passed without errors",
                artifacts=["test_report.xml", "coverage.json"],
                metrics={"passed": 10, "failed": 0, "duration_s": 1.25},
            )

            receipt = manager.submit_worker_handoff(evidence)
            assert receipt["status"] == "RECEIVED"
            assert receipt["dispatch_id"] == q_item.dispatch_id

            # Queue item is marked COMPLETED
            item = manager.get_queue_item(q_item.dispatch_id)
            assert item.status == QueueTaskStatus.COMPLETED

            # Lead can retrieve handoffs for the team
            handoffs = manager.list_team_handoffs("team-handoff")
            assert len(handoffs) == 1
            assert handoffs[0].summary == "All 10 tests passed without errors"
            assert "test_report.xml" in handoffs[0].artifacts


def test_c01_restart_reconstructs_sessions():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "durable_orca.db"

        # Session 1: Create team, workers, and pending tasks
        with OrcaStore(db_path) as store1:
            mgr1 = OrcaTeamManager(store=store1)
            mgr1.create_team("team-durable", "lead-durable", "Persistence Team")
            w_cfg = WorkerConfig(
                worker_id="worker-persist",
                team_id="team-durable",
                role="database-engineer",
                harness="native",
                model="claude-3-opus",
                provider="anthropic",
                effort="high",
                budget_tokens=100000,
            )
            mgr1.create_worker("team-durable", w_cfg)
            mgr1.dispatch_task("lead-durable", "worker-persist", "task-d1", {"query": "SELECT 1"})

        # Session 2: Fresh instance (simulating crash / restart)
        with OrcaStore(db_path) as store2:
            mgr2 = OrcaTeamManager(store=store2)

            # Rehydrate team
            rehydrated_team = mgr2.load_team("team-durable")
            assert rehydrated_team is not None
            assert rehydrated_team.lead_session_id == "lead-durable"

            workers = mgr2.list_workers("team-durable")
            assert len(workers) == 1
            assert workers[0].session_id == "worker-persist"
            assert workers[0].config.model == "claude-3-opus"
            assert workers[0].config.budget_tokens == 100000

            pending_items = mgr2.list_team_queue("team-durable")
            assert len(pending_items) == 1
            assert pending_items[0].task_id == "task-d1"
            assert pending_items[0].status == QueueTaskStatus.PENDING


def test_c01_worktree_assignment_per_worker():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca.db") as store:
            manager = OrcaTeamManager(store=store)
            manager.create_team("team-wt", "lead-wt", "Worktree Team")

            wt1 = str(Path(tmp_dir) / "wt-worker-1")
            wt2 = str(Path(tmp_dir) / "wt-worker-2")

            cfg1 = WorkerConfig(worker_id="w-wt-1", team_id="team-wt", role="frontend", harness="native")
            cfg2 = WorkerConfig(worker_id="w-wt-2", team_id="team-wt", role="backend", harness="native")

            manager.create_worker("team-wt", cfg1, worktree_path=wt1, branch_name="feature/fe")
            manager.create_worker("team-wt", cfg2, worktree_path=wt2, branch_name="feature/be")

            assignment1 = manager.get_worktree_assignment("w-wt-1")
            assignment2 = manager.get_worktree_assignment("w-wt-2")

            assert assignment1 is not None
            assert assignment1.worktree_path == wt1
            assert assignment1.branch_name == "feature/fe"

            assert assignment2 is not None
            assert assignment2.worktree_path == wt2
            assert assignment2.branch_name == "feature/be"

            assert assignment1.worktree_path != assignment2.worktree_path


def test_c01_unapproved_command_blocked():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca.db") as store:
            manager = OrcaTeamManager(store=store)
            manager.create_team("team-sec", "lead-sec", "Security Team")
            cfg = WorkerConfig(worker_id="w-sec", team_id="team-sec", role="worker", harness="native")
            manager.create_worker("team-sec", cfg)

            # Worker attempts unapproved command execution through policy gate
            result = manager.execute_worker_command(
                worker_id="w-sec",
                command=["rm", "-rf", "/"],
                approver=None,
            )
            assert result["status"] == "DENIED"
            assert "default-deny" in result["reason"].lower()

            # Valid approved command can execute when approval token / approver is explicitly provided
            approved_result = manager.execute_worker_command(
                worker_id="w-sec",
                command=["echo", "safe"],
                approver="human",
                approved=True,
            )
            assert approved_result["status"] == "APPROVED"
            assert approved_result["command"] == ["echo", "safe"]
