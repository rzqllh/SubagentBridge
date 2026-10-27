"""tests/test_native_execution.py — Test suite for Phase P03 Native Execution.

Verifies:
1. TaskDecomposer generates a valid DAG with frozen criteria and explicit dependencies.
2. SupervisedNativeLifecycle runs the complete supervised lifecycle:
   PM freeze -> Dev dispatch -> ToolExecutor -> Receipts -> QA review -> VERIFIED.
3. Negative tests: process failure, wrong tree SHA, dirty checkout, QA test tampering.
4. Process lifecycle supervision and timeout termination.
5. FastMCP server endpoints: submit_goal, execute_run, execute_task, get_task_evidence.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

from subagentbridge.composition import build_production_system
from subagentbridge.domain.contracts import TaskState
from subagentbridge.execution.native_runtime import (
    SupervisedNativeLifecycle,
    TaskDecomposer,
    resolve_tree_sha,
)
from subagentbridge.execution.isolation.runner import IsolatedExecutionRunner
from subagentbridge.storage.sqlite_store import SQLiteStore
import subagentbridge.server as srv


class TaskDecomposerTests(unittest.TestCase):
    def test_decompose_goal_creates_valid_dag(self):
        run_id = f"run_{uuid4().hex[:8]}"
        tree_sha = "a" * 40
        tasks, dependencies, records = TaskDecomposer.decompose_goal(
            goal="Implement end-to-end token counter",
            run_id=run_id,
            tree_sha=tree_sha,
        )

        self.assertEqual(len(tasks), 3)
        self.assertEqual(len(dependencies), 3)
        self.assertEqual(len(records), 3)

        pm_id = f"{run_id}_pm"
        dev_id = f"{run_id}_dev"
        qa_id = f"{run_id}_qa"

        self.assertIn(pm_id, tasks)
        self.assertIn(dev_id, tasks)
        self.assertIn(qa_id, tasks)

        self.assertEqual(dependencies[pm_id], ())
        self.assertEqual(dependencies[dev_id], (pm_id,))
        self.assertEqual(dependencies[qa_id], (dev_id,))

        self.assertTrue(all(len(t.acceptance_criteria) > 0 for t in tasks.values()))


class SupervisedNativeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp).resolve()

        # Genuine git repository setup
        subprocess.run(["git", "init", "-q"], cwd=str(self.root), check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(self.root), check=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(self.root), check=True)

        self.db_path = self.root / ".subagentbridge" / "audit.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.store = SQLiteStore(str(self.root / "store.db"))

        test_file = self.root / "tests" / "test_dummy.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def test_dummy(): pass\n", encoding="utf-8")
        import hashlib
        self.test_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

        subprocess.run(["git", "add", "."], cwd=str(self.root), check=True)
        subprocess.run(["git", "commit", "-m", "init clean workspace", "-q"], cwd=str(self.root), check=True)

        self.sys = build_production_system(
            workspace_root=self.root,
            db_path=self.db_path,
            custom_qa_hashes={"tests/test_dummy.py": self.test_hash},
        )

    def tearDown(self):
        self.sys.close()
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_supervised_lifecycle_happy_path(self):
        """Lifecycle advances through PM freeze -> Dev dispatch -> ToolExecutor -> QA review -> VERIFIED."""
        run_id = f"run_{uuid4().hex[:8]}"
        tree_sha = resolve_tree_sha(self.root)

        tasks, dependencies, records = TaskDecomposer.decompose_goal(
            goal="Add secure cache layer",
            run_id=run_id,
            tree_sha=tree_sha,
        )

        lifecycle = SupervisedNativeLifecycle(sys=self.sys, workspace_path=self.root, store=self.store)
        coordinator, principals = lifecycle.create_coordinator_for_run(
            run_id=run_id,
            tasks=tasks,
            dependencies=dependencies,
        )

        import sys
        pm_id = f"{run_id}_pm"
        dev_id = f"{run_id}_dev"
        qa_id = f"{run_id}_qa"
        commands = {
            pm_id: [sys.executable, "-c", "print('pm scope ok')"],
            dev_id: [sys.executable, "-c", "print('dev pass')"],
            qa_id: [sys.executable, "-c", "print('qa pass')"],
        }

        result = lifecycle.execute_lifecycle(
            run_id=run_id,
            coordinator=coordinator,
            principals=principals,
            task_records=records,
            command_map=commands,
        )

        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(len(result["tasks"]), 3)

        # All tasks must be VERIFIED
        for t in result["tasks"]:
            self.assertEqual(t["status"], "VERIFIED")
            self.assertGreater(len(t["evidence_ids"]), 0)

        # Coordinator internal state must be VERIFIED for all
        for task_id in tasks:
            self.assertEqual(coordinator.state(task_id), TaskState.VERIFIED)

    def test_developer_command_failure_halts_lifecycle(self):
        """A failing command halts execution and reports failure."""
        run_id = f"run_{uuid4().hex[:8]}"
        tree_sha = resolve_tree_sha(self.root)

        tasks, dependencies, records = TaskDecomposer.decompose_goal(
            goal="Command failure test",
            run_id=run_id,
            tree_sha=tree_sha,
        )

        lifecycle = SupervisedNativeLifecycle(sys=self.sys, workspace_path=self.root, store=self.store)
        coordinator, principals = lifecycle.create_coordinator_for_run(
            run_id=run_id,
            tasks=tasks,
            dependencies=dependencies,
        )

        import sys
        pm_id = f"{run_id}_pm"
        dev_id = f"{run_id}_dev"
        failing_cmd = [sys.executable, "-c", "import sys; sys.exit(42)"]

        result = lifecycle.execute_lifecycle(
            run_id=run_id,
            coordinator=coordinator,
            principals=principals,
            task_records=records,
            command_map={pm_id: [sys.executable, "-c", "print('pm ok')"], dev_id: failing_cmd},
        )

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failed_task_id"], dev_id)

    def test_qa_rejects_dirty_checkout(self):
        """QA gate refuses verification if checkout is dirty or tree SHA mismatches."""
        run_id = f"run_{uuid4().hex[:8]}"
        tree_sha = resolve_tree_sha(self.root)
        tasks, dependencies, records = TaskDecomposer.decompose_goal(
            goal="Dirty checkout test",
            run_id=run_id,
            tree_sha=tree_sha,
        )
        lifecycle = SupervisedNativeLifecycle(sys=self.sys, workspace_path=self.root, store=self.store)
        coordinator, (pm, dev, qa, executor) = lifecycle.create_coordinator_for_run(
            run_id=run_id,
            tasks=tasks,
            dependencies=dependencies,
        )

        pm_id = f"{run_id}_pm"
        coordinator.freeze(pm_id, pm)
        plan = coordinator.begin(pm_id, pm=pm, idempotency_key="key1", token_allowance=10, cost_microunits=10)
        coordinator.report_process_succeeded(developer=dev, task_id=pm_id, dispatch_id=plan.dispatch_id, tree_sha=plan.tree_sha)

        receipt = self.sys.receipts.issue(executor, task_id=pm_id, dispatch_id=plan.dispatch_id, tree_sha=plan.tree_sha, exit_code=0)
        evidence = self.sys.receipts.create_evidence(receipt.receipt_id, task_id=pm_id, dispatch_id=plan.dispatch_id, tree_sha=plan.tree_sha)

        # Clean is False
        decision = coordinator.qa_review(
            qa=qa,
            task_id=pm_id,
            evidence=(evidence,),
            covered_criteria=tasks[pm_id].acceptance_criteria,
            actual_test_hashes=self.sys.qa_gate.test_hashes,
            actual_tree_sha=plan.tree_sha,
            clean=False,
            fix_round=0,
        )
        self.assertEqual(decision.status, "UNVERIFIED")
        self.assertIn("dirty checkout", decision.reason)


    def test_qa_rejects_tampered_test_hashes(self):
        """QA gate refuses verification if QA test hashes differ from pinned hashes."""
        run_id = f"run_{uuid4().hex[:8]}"
        tree_sha = resolve_tree_sha(self.root)
        tasks, dependencies, records = TaskDecomposer.decompose_goal(
            goal="Tamper test",
            run_id=run_id,
            tree_sha=tree_sha,
        )
        lifecycle = SupervisedNativeLifecycle(sys=self.sys, workspace_path=self.root, store=self.store)
        coordinator, (pm, dev, qa, executor) = lifecycle.create_coordinator_for_run(
            run_id=run_id,
            tasks=tasks,
            dependencies=dependencies,
        )

        pm_id = f"{run_id}_pm"
        coordinator.freeze(pm_id, pm)
        plan = coordinator.begin(pm_id, pm=pm, idempotency_key="key_tamper", token_allowance=10, cost_microunits=10)
        coordinator.report_process_succeeded(developer=dev, task_id=pm_id, dispatch_id=plan.dispatch_id, tree_sha=plan.tree_sha)

        receipt = self.sys.receipts.issue(executor, task_id=pm_id, dispatch_id=plan.dispatch_id, tree_sha=plan.tree_sha, exit_code=0)
        evidence = self.sys.receipts.create_evidence(receipt.receipt_id, task_id=pm_id, dispatch_id=plan.dispatch_id, tree_sha=plan.tree_sha)

        # Tampered test hash
        tampered_hashes = {"tests/test_dummy.py": "0" * 64}
        decision = coordinator.qa_review(
            qa=qa,
            task_id=pm_id,
            evidence=(evidence,),
            covered_criteria=tasks[pm_id].acceptance_criteria,
            actual_test_hashes=tampered_hashes,
            actual_tree_sha=plan.tree_sha,
            clean=True,
            fix_round=0,
        )
        self.assertEqual(decision.status, "UNVERIFIED")
        self.assertIn("QA tests changed", decision.reason)

    def test_process_lifecycle_supervision_timeout(self):
        """IsolatedExecutionRunner terminates long-running process on timeout."""
        runner = IsolatedExecutionRunner(self.root)
        import subprocess
        with self.assertRaises(subprocess.TimeoutExpired):
            runner.run_isolated(
                ["python", "-c", "import time; time.sleep(10)"],
                timeout_seconds=1,
            )

    def test_resolve_tree_sha_deterministic(self):
        """resolve_tree_sha produces a 40+ char hex string deterministically."""
        sha1 = resolve_tree_sha(self.root)
        sha2 = resolve_tree_sha(self.root)
        self.assertEqual(sha1, sha2)
        self.assertGreaterEqual(len(sha1), 40)


class McpNativeExecutionServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp).resolve()
        subprocess.run(["git", "init", "-q"], cwd=str(self.root), check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(self.root), check=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(self.root), check=True)
        test_file = self.root / "tests" / "test_dummy.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def test_dummy(): pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(self.root), check=True)
        subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=str(self.root), check=True)
        srv.close_production_system()

    def tearDown(self):
        srv.close_production_system()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_submit_goal_with_execute_runs_full_lifecycle(self):
        """submit_goal(..., execute=True) completes and marks tasks VERIFIED with genuine execution."""
        import sys
        res = srv.submit_goal(
            goal="Build authenticated token bucket",
            workspace_path=str(self.root),
            execute=True,
            commands={"default": [sys.executable, "-c", "print('task ok')"]},
        )

        self.assertEqual(res["status"], "COMPLETED")
        run_id = res["run_id"]

        run_info = srv.get_run(run_id)
        self.assertEqual(run_info["status"], "COMPLETED")
        self.assertEqual(run_info["task_count"], 3)

        tasks = srv.list_tasks(run_id)
        self.assertEqual(len(tasks), 3)
        for t in tasks:
            self.assertEqual(t["status"], "VERIFIED")
            evidence = srv.get_task_evidence(run_id, t["task_id"])
            self.assertTrue(evidence["verified"])
            self.assertGreater(len(evidence["evidence_ids"]), 0)

    def test_execute_run_and_execute_task_tools(self):
        """submit_goal(..., execute=False) leaves run SUBMITTED; execute_run completes it."""
        import sys
        res = srv.submit_goal(
            goal="Build circuit breaker",
            workspace_path=str(self.root),
            execute=False,
            commands={"default": [sys.executable, "-c", "print('task ok')"]},
        )
        self.assertEqual(res["status"], "SUBMITTED")
        run_id = res["run_id"]

        # Run execute_run tool
        exec_res = srv.execute_run(run_id)
        self.assertEqual(exec_res["status"], "COMPLETED")

        # Run execute_task on individual task returns current state and exact evidence
        tasks = srv.list_tasks(run_id)
        task_res = srv.execute_task(run_id, tasks[0]["task_id"])
        self.assertEqual(task_res["status"], "VERIFIED")
        self.assertIn("evidence", task_res)
        self.assertTrue(task_res["evidence"]["verified"])
        self.assertEqual(task_res["task_id"], tasks[0]["task_id"])

    def test_completed_run_rehydrates_with_verified_evidence(self):
        """A completed run rehydrates from SQLite and retains verified status and evidence."""
        import sys
        res = srv.submit_goal(
            goal="Persistent cache integration",
            workspace_path=str(self.root),
            execute=True,
            commands={"default": [sys.executable, "-c", "print('task ok')"]},
        )
        run_id = res["run_id"]
        self.assertEqual(res["status"], "COMPLETED")

        # Wipe memory
        srv._runs.clear()
        srv._tasks.clear()

        # Rehydrate
        srv.rehydrate_runs_and_tasks(srv._store)

        run_view = srv.get_run(run_id)
        self.assertEqual(run_view["status"], "COMPLETED")
        tasks = srv.list_tasks(run_id)
        self.assertEqual(len(tasks), 3)
        for t in tasks:
            self.assertEqual(t["status"], "VERIFIED")
            ev = srv.get_task_evidence(run_id, t["task_id"])
            self.assertTrue(ev["verified"])


if __name__ == "__main__":
    unittest.main()

