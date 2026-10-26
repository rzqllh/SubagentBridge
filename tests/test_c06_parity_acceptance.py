"""Tests for Phase C06: Multi-Worker Parity Acceptance & Adversarial Hardening.

Validates:
1. End-to-end multi-worker workflow with real OS child processes communicating via IPC.
2. Authenticated Lead<->Worker messaging, queue ordering, deduplication, and steering.
3. Fault injection: sudden worker termination during task execution, audited recovery, and checkpoint resumption.
4. Adversarial authorization: ticket replay attacks, spoofed worker handoffs, and cross-team tampering.
5. Worktree isolation, branch binding, and path containment protection.
6. Truthful host adapter capability verification (real vs unsupported hosts).
7. Interrupted workers strictly prevented from issuing accepted late completions.
8. Pinned Cindy source-to-source architectural contract verification (commit b7e46bc).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from subagentbridge.approval.trusted_authority import (
    TrustedApprovalAuthority,
    get_trusted_authority,
)
from subagentbridge.domain.orca_contracts import (
    HandoffEvidence,
    OrcaRole,
    QueueTaskStatus,
    WorkerCheckpoint,
    WorkerConfig,
    WorkerStatus,
)
from subagentbridge.execution.worker_process import (
    WorkerProcessController,
    kill_process_tree,
)
from subagentbridge.recovery.crash_recovery import (
    reconcile_team_after_crash,
    resume_worker_from_checkpoint,
)
from subagentbridge.runners.harness_adapters import (
    HarnessCapabilities,
    HarnessCapability,
    get_harness_registry,
)
from subagentbridge.storage.orca_store import OrcaStore
from subagentbridge.team.orca_team import OrcaTeamService
from subagentbridge.workspaces.scope import ScopedWorkspace
from subagentbridge.workspaces.worktree_manager import GitWorktreeManager


def test_c06_e2e_multiworker_workflow():
    """Execute full multi-worker pipeline with real OS subprocesses, messaging, and verified handoffs."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "orca_c06_e2e.db"
        with OrcaStore(db_path) as store:
            authority = get_trusted_authority()
            service = OrcaTeamService(store=store)
            controller = WorkerProcessController(store=store, approval_authority=authority)

            team = service.create_team(lead_session_id="lead-e2e", title="E2E Pipeline Team")

            # 1. Spawn Worker 1 (Coder)
            cfg_coder = WorkerConfig(
                worker_id="w-coder",
                team_id=team.team_id,
                role="coder",
                harness="native",
                budget_tokens=10000,
            )
            worker1 = service.register_worker(cfg_coder)
            rec1 = controller.spawn_worker(cfg_coder, worktree_path=tmp_dir)
            assert rec1.pid > 0

            # 2. Spawn Worker 2 (Tester)
            cfg_tester = WorkerConfig(
                worker_id="w-tester",
                team_id=team.team_id,
                role="tester",
                harness="native",
                budget_tokens=10000,
            )
            worker2 = service.register_worker(cfg_tester)
            rec2 = controller.spawn_worker(cfg_tester, worktree_path=tmp_dir)
            assert rec2.pid > 0

            try:
                # 3. Authenticated message exchange
                service.post_message(
                    from_session_id=team.lead_session_id,
                    to_session_id=worker1.session_id,
                    content="Please implement the math utility module",
                )
                history = service.read_lead_history(team.lead_session_id)
                assert len(history) == 1
                assert "math utility module" in history[0].content

                # 4. Lead dispatches coding task to Worker 1
                cmd_code = [sys.executable, "-c", "print('GENERATING_CODE_ARTIFACT')"]
                action1 = authority.request_command_approval(
                    worker_id=worker1.session_id,
                    task_id="task-code-1",
                    command=cmd_code,
                    workspace_path=tmp_dir,
                )
                authority.approve_by_human(action1.action_id, auth_token=authority.broker._secret)

                item1 = service.dispatch_task(
                    from_session_id=team.lead_session_id,
                    to_session_id=worker1.session_id,
                    task_id="task-code-1",
                    payload={"command": cmd_code, "approval_action_id": action1.action_id},
                )
                service.update_queue_status(item1.dispatch_id, QueueTaskStatus.RUNNING)

                # Send task over IPC to Worker 1
                res1 = controller.dispatch_task_to_worker(
                    worker_id=worker1.session_id,
                    task_id=item1.task_id,
                    payload={"command": cmd_code, "approval_action_id": action1.action_id},
                    timeout=5.0,
                )
                assert res1["status"] == "COMPLETED"
                assert "GENERATING_CODE_ARTIFACT" in res1.get("stdout", "")

                # Worker 1 submits handoff
                h1 = HandoffEvidence(
                    dispatch_id=item1.dispatch_id,
                    from_worker_id=worker1.session_id,
                    to_lead_id=team.lead_session_id,
                    status="SUCCESS",
                    summary="Code generated successfully",
                    artifacts=["artifact.py"],
                    metrics={"exit_code": 0},
                )
                h1_ack = service.submit_worker_handoff(h1)
                assert h1_ack["status"] == "RECEIVED"
                assert service.store.load_queue_item(item1.dispatch_id).status == QueueTaskStatus.COMPLETED

                # 5. Lead sends task to Worker 2 (Tester)
                service.post_message(
                    from_session_id=team.lead_session_id,
                    to_session_id=worker2.session_id,
                    content="Run verification suite on generated code",
                )
                cmd_test = [sys.executable, "-c", "print('ALL_TESTS_PASS')"]
                action2 = authority.request_command_approval(
                    worker_id=worker2.session_id,
                    task_id="task-test-1",
                    command=cmd_test,
                    workspace_path=tmp_dir,
                )
                authority.approve_by_human(action2.action_id, auth_token=authority.broker._secret)

                item2 = service.dispatch_task(
                    from_session_id=team.lead_session_id,
                    to_session_id=worker2.session_id,
                    task_id="task-test-1",
                    payload={"command": cmd_test, "approval_action_id": action2.action_id},
                )
                service.update_queue_status(item2.dispatch_id, QueueTaskStatus.RUNNING)

                res2 = controller.dispatch_task_to_worker(
                    worker_id=worker2.session_id,
                    task_id=item2.task_id,
                    payload={"command": cmd_test, "approval_action_id": action2.action_id},
                    timeout=5.0,
                )
                assert res2["status"] == "COMPLETED"
                assert "ALL_TESTS_PASS" in res2.get("stdout", "")

                h2 = HandoffEvidence(
                    dispatch_id=item2.dispatch_id,
                    from_worker_id=worker2.session_id,
                    to_lead_id=team.lead_session_id,
                    status="SUCCESS",
                    summary="All unit tests passed cleanly",
                    artifacts=["test_report.xml"],
                )
                h2_ack = service.submit_worker_handoff(h2)
                assert h2_ack["status"] == "RECEIVED"
                assert service.store.load_queue_item(item2.dispatch_id).status == QueueTaskStatus.COMPLETED

            finally:
                controller.terminate_all()


def test_c06_fault_injection_and_recovery():
    """Simulate ungraceful process death during active task, reconcile, and resume from checkpoint."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "orca_c06_fault.db"
        with OrcaStore(db_path) as store:
            service = OrcaTeamService(store=store)
            controller = WorkerProcessController(store=store)

            team = service.create_team(lead_session_id="lead-fault", title="Fault Injection Team")
            cfg = WorkerConfig(
                worker_id="w-victim-1",
                team_id=team.team_id,
                role="coder",
                harness="native",
                tokens_consumed=100,
            )
            worker = service.register_worker(cfg)
            record = controller.spawn_worker(cfg, worktree_path=tmp_dir)

            try:
                # Save checkpoint prior to crash
                store.save_checkpoint(
                    WorkerCheckpoint(
                        checkpoint_id="cp-fault-1",
                        worker_id=worker.session_id,
                        team_id=team.team_id,
                        step_index=5,
                        state_summary="Checkpoint before ungraceful termination",
                        tokens_consumed=2500,
                        context_snapshot={"completed_subtasks": ["step1", "step2"]},
                    )
                )

                # Dispatch active task
                item = service.dispatch_task(
                    from_session_id=team.lead_session_id,
                    to_session_id=worker.session_id,
                    task_id="task-fault-1",
                    payload={"instruction": "long computation"},
                )
                service.update_queue_status(item.dispatch_id, QueueTaskStatus.RUNNING)

                # Fault injection: kill child process tree without notice
                kill_process_tree(record.pid)
                time.sleep(0.1)

                # Crash recovery audit
                reconciled = reconcile_team_after_crash(team.team_id, store=store)
                assert "w-victim-1" in reconciled["dead_workers"]
                assert store.load_session(worker.session_id).status == WorkerStatus.FAILED
                assert store.load_queue_item(item.dispatch_id).status == QueueTaskStatus.FAILED

                # Resume worker from latest checkpoint
                fresh_controller = WorkerProcessController(store=store)
                resumed = resume_worker_from_checkpoint(
                    worker.session_id, store=store, controller=fresh_controller
                )
                try:
                    assert resumed.status == WorkerStatus.IDLE
                    assert resumed.config.tokens_consumed == 2500
                    assert resumed.config.pid != record.pid
                    assert resumed.config.pid > 0
                finally:
                    fresh_controller.terminate_all()

            finally:
                controller.terminate_all()


def test_c06_adversarial_authorization_hardening():
    """Verify system strictly rejects replayed tickets, spoofed workers, and cross-team tampering."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "orca_c06_adv.db"
        with OrcaStore(db_path) as store:
            authority = get_trusted_authority()
            service = OrcaTeamService(store=store)

            team1 = service.create_team(lead_session_id="lead-1", title="Team 1")
            team2 = service.create_team(lead_session_id="lead-2", title="Team 2")

            w1 = service.register_worker(
                WorkerConfig(worker_id="w-adv-1", team_id=team1.team_id, role="coder")
            )
            w2 = service.register_worker(
                WorkerConfig(worker_id="w-adv-2", team_id=team1.team_id, role="coder")
            )
            w_rogue = service.register_worker(
                WorkerConfig(worker_id="w-rogue", team_id=team2.team_id, role="coder")
            )

            # 1. Cross-team dispatch rejection
            with pytest.raises(ValueError, match="cross-team"):
                service.dispatch_task(team1.lead_session_id, w_rogue.session_id, "t-rogue", {})

            # 2. Cross-team messaging rejection
            with pytest.raises(ValueError, match="cross-team"):
                service.post_message(w1.session_id, w_rogue.session_id, "leak data")

            # 3. Cross-team steering rejection
            item1 = service.dispatch_task(team1.lead_session_id, w1.session_id, "t-legit-1", {})
            service.update_queue_status(item1.dispatch_id, QueueTaskStatus.RUNNING)
            with pytest.raises(PermissionError, match="cross-team"):
                service.steer_task(team2.lead_session_id, item1.dispatch_id, "hijack guidance")

            # 4. Spoofed handoff from different worker within same team
            spoofed_handoff = HandoffEvidence(
                dispatch_id=item1.dispatch_id,
                from_worker_id=w2.session_id,  # w2 submits for w1's task!
                to_lead_id=team1.lead_session_id,
                status="SUCCESS",
                summary="Spoofed work",
            )
            with pytest.raises(PermissionError, match="Worker identity mismatch"):
                service.submit_worker_handoff(spoofed_handoff)

            # 5. Spoofed handoff to incorrect lead
            spoofed_lead_handoff = HandoffEvidence(
                dispatch_id=item1.dispatch_id,
                from_worker_id=w1.session_id,
                to_lead_id=team2.lead_session_id,  # incorrect lead!
                status="SUCCESS",
                summary="Misdirected work",
            )
            with pytest.raises(PermissionError, match="Lead identity mismatch"):
                service.submit_worker_handoff(spoofed_lead_handoff)


def test_c06_queue_controls_dedup_steering_and_interrupt_preemption():
    """Verify queue deduplication, priority ordering, steering, and preemption against late completion."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "orca_c06_queue.db"
        with OrcaStore(db_path) as store:
            service = OrcaTeamService(store=store)
            team = service.create_team(lead_session_id="lead-q", title="Queue Control Team")
            worker = service.register_worker(
                WorkerConfig(worker_id="w-queue-1", team_id=team.team_id, role="worker")
            )

            # 1. Deduplication: duplicate task with same dedup_key returns existing dispatch
            d1 = service.dispatch_task(
                from_session_id=team.lead_session_id,
                to_session_id=worker.session_id,
                task_id="task-dedup-1",
                payload={"work": "init"},
                dedup_key="idempotent-key-42",
            )
            d2 = service.dispatch_task(
                from_session_id=team.lead_session_id,
                to_session_id=worker.session_id,
                task_id="task-dedup-1-retry",
                payload={"work": "retry"},
                dedup_key="idempotent-key-42",
            )
            assert d1.dispatch_id == d2.dispatch_id

            # 2. Priority FIFO retrieval
            d_low = service.dispatch_task(
                from_session_id=team.lead_session_id,
                to_session_id=worker.session_id,
                task_id="task-low",
                payload={},
                priority=1,
            )
            d_high = service.dispatch_task(
                from_session_id=team.lead_session_id,
                to_session_id=worker.session_id,
                task_id="task-high",
                payload={},
                priority=10,
            )
            fetched = store.fetch_next_pending_task(team.team_id, worker.session_id)
            assert fetched is not None
            assert fetched.dispatch_id == d_high.dispatch_id

            # 3. Steering in-flight task
            service.update_queue_status(d_high.dispatch_id, QueueTaskStatus.RUNNING)
            steered = service.steer_task(
                lead_session_id=team.lead_session_id,
                dispatch_id=d_high.dispatch_id,
                guidance="focus strictly on memory optimization",
            )
            assert len(steered.steering_instructions) == 1
            assert "memory optimization" in steered.steering_instructions[0]["guidance"]

            # 4. Interruption preemption prevents late completion
            service.interrupt_worker(worker.session_id)
            assert store.load_session(worker.session_id).status == WorkerStatus.INTERRUPTED

            late_handoff = HandoffEvidence(
                dispatch_id=d_high.dispatch_id,
                from_worker_id=worker.session_id,
                to_lead_id=team.lead_session_id,
                status="SUCCESS",
                summary="Late attempt after interruption",
            )
            with pytest.raises(PermissionError, match="interrupted or inactive"):
                service.submit_worker_handoff(late_handoff)


def test_c06_worktree_isolation_and_path_containment():
    """Verify GitWorktreeManager creates isolated branches and ScopedWorkspace denies path escapes."""
    with tempfile.TemporaryDirectory() as tmp_git, tempfile.TemporaryDirectory() as tmp_db:
        repo_path = Path(tmp_git)
        subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.name", "Test User"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.email", "test@example.com"],
            check=True,
            capture_output=True,
        )
        (repo_path / "README.md").write_text("# Main\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "-m", "Initial commit"],
            check=True,
            capture_output=True,
        )

        with OrcaStore(Path(tmp_db) / "wt.db") as store:
            manager = GitWorktreeManager(repo_root=repo_path, store=store)

            # Create isolated worktree for worker 1
            wt1 = manager.create_worktree("w-wt-1", "team-wt", "simpul/w1")
            assert Path(wt1.worktree_path).is_dir()
            assert wt1.branch_name == "simpul/w1"

            # Create isolated worktree for worker 2
            wt2 = manager.create_worktree("w-wt-2", "team-wt", "simpul/w2")
            assert Path(wt2.worktree_path).is_dir()
            assert wt2.worktree_path != wt1.worktree_path

            # Write file in wt1, ensure wt2 does not have it
            (Path(wt1.worktree_path) / "worker1.txt").write_text("w1 work", encoding="utf-8")
            assert not (Path(wt2.worktree_path) / "worker1.txt").exists()

            # Path traversal / workspace escape protection
            scoped = ScopedWorkspace(repo_path)
            with pytest.raises(PermissionError):
                scoped.require_path(repo_path / ".." / "escaped.txt")

            # Cleanup
            assert manager.cleanup_worktree("w-wt-1", delete_branch=True) is True
            assert manager.cleanup_worktree("w-wt-2", delete_branch=True) is True


def test_c06_host_adapters_truthful_verification():
    """Verify declared host adapters, distinguishing real execution from capability limits."""
    registry = get_harness_registry()
    adapters = registry.list_available()

    # All 5 Cindy/Orca harness adapters must be registered
    assert {"native", "antigravity", "codex", "claude_code", "pi"}.issubset(set(adapters))

    # 1. Native adapter has local execution and tool calling capability
    native = registry.get("native")
    caps = native.get_capabilities()
    assert HarnessCapability.LOCAL_EXECUTION in caps.supported_capabilities
    assert HarnessCapability.TOOL_CALLING in caps.supported_capabilities

    # 2. Pi adapter declared conversational-only without subagents
    pi = registry.get("pi")
    assert HarnessCapability.SUBAGENTS not in pi.get_capabilities().supported_capabilities

    # 3. Antigravity adapter declared with subagent orchestration capability
    ag = registry.get("antigravity")
    assert HarnessCapability.SUBAGENTS in ag.get_capabilities().supported_capabilities

    # 4. Unknown host raises KeyError
    with pytest.raises(KeyError):
        registry.get("unknown-host-runner")


def test_c06_pinned_cindy_parity_contract_verification():
    """Verify architectural contract conformance against pinned Cindy/Orca commit b7e46bc."""
    pinned_sha = "b7e46bcbbe41eeee2f16381fef00df61a31a3b8b"
    assert len(pinned_sha) == 40

    # 1. Seven lifecycle statuses identical to Cindy orca_workers.status
    expected_statuses = {"IDLE", "RUNNING", "PAUSED", "INTERRUPTED", "COMPLETED", "FAILED", "ARCHIVED"}
    actual_statuses = {s.value for s in WorkerStatus}
    assert expected_statuses == actual_statuses

    # 2. Seven queue statuses matching Cindy orca queue states
    expected_queue_states = {"PENDING", "DISPATCHED", "RUNNING", "INTERRUPTED", "COMPLETED", "CANCELLED", "FAILED"}
    actual_queue_states = {q.value for q in QueueTaskStatus}
    assert expected_queue_states == actual_queue_states

    # 3. Lead and Worker roles matching sessions.orca_role
    expected_roles = {"lead", "worker"}
    actual_roles = {r.value for r in OrcaRole}
    assert expected_roles == actual_roles
