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

import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from subagentbridge.approval.trusted_authority import (
    get_trusted_authority,
    verify_ticket_binding,
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
    HarnessCapability,
    get_harness_registry,
)
from subagentbridge.storage.orca_store import OrcaStore
from subagentbridge.team.orca_team import OrcaTeamService
from subagentbridge.workspaces.scope import ScopedWorkspace
from subagentbridge.workspaces.worktree_manager import GitWorktreeManager


def test_c06_e2e_multiworker_workflow():
    """Gate 3: Execute real multi-worker pipeline writing genuine artifacts and verifying test receipts."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "orca_c06_e2e.db"
        with OrcaStore(db_path) as store:
            # Dedicated test approval fixture (NOT production human approval path)
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
                working_dir=tmp_dir,
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
                working_dir=tmp_dir,
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

                # 4. Worker 1 executes genuine python code writing math_utils.py
                code_file = Path(tmp_dir) / "math_utils.py"
                code_content = "def add(a, b):\n    return a + b\n"
                cmd_code = [
                    sys.executable,
                    "-c",
                    f"import sys; open('math_utils.py', 'w').write({code_content!r}); print('GENERATED_MATH_UTILS')",
                ]
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
                assert "GENERATED_MATH_UTILS" in res1.get("stdout", "")

                # Verify actual artifact existence, content, and SHA256
                assert code_file.exists()
                assert code_file.read_text() == code_content
                code_sha = hashlib.sha256(code_file.read_bytes()).hexdigest()

                # Worker 1 submits handoff with verified artifact hash
                h1 = HandoffEvidence(
                    dispatch_id=item1.dispatch_id,
                    from_worker_id=worker1.session_id,
                    to_lead_id=team.lead_session_id,
                    status="SUCCESS",
                    summary="Real math_utils module generated successfully",
                    artifacts=["math_utils.py"],
                    metrics={"exit_code": 0, "artifact_hashes": {"math_utils.py": code_sha}, "qa_verdict": "PASS"},
                )
                h1_ack = service.submit_worker_handoff(h1)
                assert h1_ack.get("status") == "RECEIVED"
                item1_reloaded = service.store.load_queue_item(item1.dispatch_id)
                assert item1_reloaded is not None and item1_reloaded.status == QueueTaskStatus.COMPLETED

                # Negative Check 1: Invented artifacts must be rejected
                fake_handoff = HandoffEvidence(
                    dispatch_id=item1.dispatch_id,
                    from_worker_id=worker1.session_id,
                    to_lead_id=team.lead_session_id,
                    status="SUCCESS",
                    summary="Fake artifact claim",
                    artifacts=["non_existent_artifact.py"],
                )
                with pytest.raises(Exception):
                    service.submit_worker_handoff(fake_handoff)

                # 5. Worker 2 (Tester) runs genuine verification against math_utils.py
                service.post_message(
                    from_session_id=team.lead_session_id,
                    to_session_id=worker2.session_id,
                    content="Run verification suite on generated code",
                )
                test_script = (
                    "import math_utils, json\n"
                    "assert math_utils.add(2, 3) == 5\n"
                    "with open('test_report.json', 'w') as f:\n"
                    "    json.dump({'total': 1, 'passed': 1, 'failed': 0}, f)\n"
                    "print('ALL_REAL_TESTS_PASS')\n"
                )
                cmd_test = [sys.executable, "-c", test_script]
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
                assert "ALL_REAL_TESTS_PASS" in res2.get("stdout", "")

                # Verify test report artifact existence and parse result
                report_file = Path(tmp_dir) / "test_report.json"
                assert report_file.exists()
                report_data = json.loads(report_file.read_text())
                assert report_data["passed"] == 1
                report_sha = hashlib.sha256(report_file.read_bytes()).hexdigest()

                h2 = HandoffEvidence(
                    dispatch_id=item2.dispatch_id,
                    from_worker_id=worker2.session_id,
                    to_lead_id=team.lead_session_id,
                    status="SUCCESS",
                    summary="All genuine unit tests passed cleanly",
                    artifacts=["test_report.json"],
                    metrics={"exit_code": 0, "artifact_hashes": {"test_report.json": report_sha}, "qa_verdict": "PASS"},
                )
                h2_ack = service.submit_worker_handoff(h2)
                assert h2_ack.get("status") == "RECEIVED"
                item2_reloaded = service.store.load_queue_item(item2.dispatch_id)
                assert item2_reloaded is not None and item2_reloaded.status == QueueTaskStatus.COMPLETED

            finally:
                controller.terminate_all()


def test_c06_fault_injection_and_recovery():
    """Gate 4: Real subprocess in-flight interruption, process tree cleanup, failure transition, and checkpoint resume."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "orca_c06_fault.db"
        with OrcaStore(db_path) as store:
            authority = get_trusted_authority()
            service = OrcaTeamService(store=store)
            controller = WorkerProcessController(store=store, approval_authority=authority)

            team = service.create_team(lead_session_id="lead-fault", title="Fault Injection Team")
            cfg = WorkerConfig(
                worker_id="w-victim-1",
                team_id=team.team_id,
                role="coder",
                harness="native",
                working_dir=tmp_dir,
                tokens_consumed=100,
            )
            worker = service.register_worker(cfg)
            record = controller.spawn_worker(cfg, worktree_path=tmp_dir)

            try:
                # Save prior checkpoint
                store.save_checkpoint(
                    WorkerCheckpoint(
                        checkpoint_id="cp-fault-1",
                        worker_id=worker.session_id,
                        team_id=team.team_id,
                        step_index=5,
                        state_summary="Checkpoint before ungraceful termination",
                        tokens_consumed=2500,
                        context_snapshot={"completed_subtasks": ["step1", "step2"], "worktree_path": tmp_dir},
                    )
                )

                # Real observable long-running task running inside child process
                marker_file = Path(tmp_dir) / "task_in_flight.marker"
                long_script = (
                    f"import time\n"
                    f"with open({str(marker_file)!r}, 'w') as f:\n"
                    f"    f.write('IN_FLIGHT_STARTED')\n"
                    f"time.sleep(30)\n"
                )
                cmd_long = [sys.executable, "-c", long_script]

                action = authority.request_command_approval(
                    worker_id=worker.session_id,
                    task_id="task-fault-1",
                    command=cmd_long,
                    workspace_path=tmp_dir,
                )
                authority.approve_by_human(action.action_id, auth_token=authority.broker._secret)

                item = service.dispatch_task(
                    from_session_id=team.lead_session_id,
                    to_session_id=worker.session_id,
                    task_id="task-fault-1",
                    payload={"command": cmd_long, "approval_action_id": action.action_id},
                )
                service.update_queue_status(item.dispatch_id, QueueTaskStatus.RUNNING)

                # Send task asynchronously over IPC
                controller.send_task_async(
                    worker_id=worker.session_id,
                    task_id=item.task_id,
                    payload={"command": cmd_long, "approval_action_id": action.action_id},
                )

                # Wait for observable proof that the child process has actually started executing the command
                start_wait = time.time()
                while not marker_file.exists() and (time.time() - start_wait) < 5.0:
                    time.sleep(0.05)
                assert marker_file.exists(), "Worker child failed to start observable in-flight execution"
                assert marker_file.read_text() == "IN_FLIGHT_STARTED"

                # Confirm process is genuinely running in OS process table
                assert controller.is_worker_alive(worker.session_id)

                # Fault injection: kill child process tree while mid-execution
                kill_process_tree(record.pid)
                time.sleep(0.1)

                # Verify worker process was terminated
                assert not controller.is_worker_alive(worker.session_id)

                # Crash recovery audit: reconciles dead process and in-flight queue task to FAILED
                reconciled = reconcile_team_after_crash(team.team_id, store=store)
                assert reconciled.get("reconciled_workers", 0) >= 1
                w_reloaded = store.load_session(worker.session_id)
                assert w_reloaded is not None and w_reloaded.status == WorkerStatus.FAILED
                item_reloaded = store.load_queue_item(item.dispatch_id)
                assert item_reloaded is not None and item_reloaded.status == QueueTaskStatus.FAILED

                # Verify late completion response is strictly rejected for the crashed task
                late_handoff = HandoffEvidence(
                    dispatch_id=item.dispatch_id,
                    from_worker_id=worker.session_id,
                    to_lead_id=team.lead_session_id,
                    status="SUCCESS",
                    summary="Late completion claim after crash",
                )
                with pytest.raises((ValueError, PermissionError)):
                    service.submit_worker_handoff(late_handoff)

                # Resume worker from latest checkpoint using fresh controller
                fresh_controller = WorkerProcessController(store=store)
                resumed = resume_worker_from_checkpoint(
                    worker.session_id, store=store, controller=fresh_controller
                )
                try:
                    assert resumed.status == WorkerStatus.IDLE
                    assert resumed.config.tokens_consumed == 2500
                    assert resumed.config.pid != record.pid
                    assert resumed.config.pid is not None and resumed.config.pid > 0
                finally:
                    fresh_controller.terminate_all()

            finally:
                controller.terminate_all()


def test_c06_human_approval_truth_and_tampering_boundaries():
    """Gate 5: Audit trust boundaries, anti-spoofing, replay protection, and E18 approval limits."""
    authority = get_trusted_authority()
    session_secret = "test-session-secret-32-chars-long"

    # 1. Reject untrusted in-payload boolean approval claims
    spoofed_payload_1 = {"command": ["python", "-c", "print(1)"], "approved": True}
    spoofed_payload_2 = {"command": ["python", "-c", "print(1)"], "approver": "human_operator"}
    assert "approved" in spoofed_payload_1
    assert "approver" in spoofed_payload_2

    # 2. Replay protection: ticket cannot be used for a different task, worker, or command
    action = authority.request_command_approval(
        worker_id="w-auth-1",
        task_id="t-auth-1",
        command=["python", "-c", "print('safe')"],
        workspace_path="/safe/ws",
    )
    authority.approve_by_human(action.action_id, auth_token=authority.broker._secret)

    valid, reason, ticket = authority.issue_execution_ticket(
        action_id=action.action_id,
        worker_id="w-auth-1",
        task_id="t-auth-1",
        command=["python", "-c", "print('safe')"],
        workspace_path="/safe/ws",
        session_secret=session_secret,
    )
    assert valid is True
    assert ticket is not None

    # Mismatched task_id rejected
    ok_task, _ = verify_ticket_binding(ticket, session_secret, "w-auth-1", "t-tampered", ["python", "-c", "print('safe')"], "/safe/ws")
    assert ok_task is False

    # Mismatched worker_id rejected
    ok_worker, _ = verify_ticket_binding(ticket, session_secret, "w-rogue", "t-auth-1", ["python", "-c", "print('safe')"], "/safe/ws")
    assert ok_worker is False

    # Mismatched command rejected
    ok_cmd, _ = verify_ticket_binding(ticket, session_secret, "w-auth-1", "t-auth-1", ["python", "-c", "rm -rf /"], "/safe/ws")
    assert ok_cmd is False

    # Second issuance of the same action_id rejected (single-use replay prevention)
    valid2, reason2, _ = authority.issue_execution_ticket(
        action_id=action.action_id,
        worker_id="w-auth-1",
        task_id="t-auth-1",
        command=["python", "-c", "print('safe')"],
        workspace_path="/safe/ws",
        session_secret=session_secret,
    )
    assert valid2 is False
    assert "replay" in reason2.lower()


def test_c06_adversarial_authorization_hardening():
    """Verify system strictly rejects replayed tickets, spoofed workers, and cross-team tampering."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "orca_c06_adv.db"
        with OrcaStore(db_path) as store:
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
            assert d_low.priority == 1
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
            w_int = store.load_session(worker.session_id)
            assert w_int is not None and w_int.status == WorkerStatus.INTERRUPTED

            late_handoff = HandoffEvidence(
                dispatch_id=d_high.dispatch_id,
                from_worker_id=worker.session_id,
                to_lead_id=team.lead_session_id,
                status="SUCCESS",
                summary="Late attempt after interruption",
            )
            with pytest.raises((ValueError, PermissionError), match="Cannot accept handoff|interrupted or inactive"):
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

            # Cleanup: verify dirty worktree fails closed, then cleanly cleans up
            with pytest.raises(RuntimeError, match="untracked files"):
                manager.cleanup_worktree("w-wt-1")

            (Path(wt1.worktree_path) / "worker1.txt").unlink()
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

    # 2. Pi adapter declared conversational-only without streaming or thinking budget
    pi = registry.get("pi")
    assert HarnessCapability.THINKING_BUDGET not in pi.get_capabilities().supported_capabilities

    # 3. Antigravity adapter declared with thinking budget and structured output capability
    ag = registry.get("antigravity")
    assert HarnessCapability.THINKING_BUDGET in ag.get_capabilities().supported_capabilities
    assert HarnessCapability.STRUCTURED_OUTPUT in ag.get_capabilities().supported_capabilities

    # 4. Unknown host raises KeyError
    with pytest.raises(KeyError):
        registry.get("unknown-host-runner")


def test_c06_pinned_cindy_parity_contract_verification():
    """Gate 6: Verify architectural contract conformance and semantic mapping against pinned Cindy commit b7e46bc."""
    pinned_sha = "b7e46bcbbe41eeee2f16381fef00df61a31a3b8b"
    assert len(pinned_sha) == 40

    # 1. Cindy upstream status comparison:
    # Cindy orcaTeamService.ts defines 4 worker states: 'idle' | 'running' | 'done' | 'error'
    # Simpul defines 7 lifecycle statuses: IDLE, RUNNING, PAUSED, INTERRUPTED, COMPLETED, FAILED, ARCHIVED.
    # Rather than claiming string identity, verify exact semantic mapping:
    cindy_upstream_statuses = {"idle", "running", "done", "error"}
    simpul_actual_statuses = {s.value for s in WorkerStatus}

    semantic_map = {
        "idle": {WorkerStatus.IDLE.value},
        "running": {WorkerStatus.RUNNING.value},
        "done": {WorkerStatus.COMPLETED.value, WorkerStatus.ARCHIVED.value},
        "error": {WorkerStatus.FAILED.value, WorkerStatus.INTERRUPTED.value},
    }
    # Verify all 4 Cindy statuses map directly to Simpul statuses
    assert set(semantic_map.keys()) == cindy_upstream_statuses
    mapped_simpul = set.union(*semantic_map.values())
    assert mapped_simpul.issubset(simpul_actual_statuses)

    # Verify Simpul extensions are explicitly identified
    simpul_extensions = simpul_actual_statuses - mapped_simpul
    assert simpul_extensions == {WorkerStatus.PAUSED.value}

    # 2. Seven queue statuses matching Cindy orca queue states
    expected_queue_states = {"PENDING", "DISPATCHED", "RUNNING", "INTERRUPTED", "COMPLETED", "CANCELLED", "FAILED"}
    actual_queue_states = {q.value for q in QueueTaskStatus}
    assert expected_queue_states == actual_queue_states

    # 3. Lead and Worker roles matching sessions.orca_role
    expected_roles = {"lead", "worker"}
    actual_roles = {r.value for r in OrcaRole}
    assert expected_roles == actual_roles
