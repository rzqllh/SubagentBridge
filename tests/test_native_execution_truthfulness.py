"""tests/test_native_execution_truthfulness.py — TDD verification against false-success vulnerability.

Enforces:
1. Prevent COMPLETED/VERIFIED when no actual developer command occurred.
2. Never synthesize successful exit code 0.
3. Never synthesize clean-checkout status; inspect genuine git status.
4. Never synthesize QA acceptance coverage; execute qualifying QA tests.
5. Never issue executor receipts without actual execution.
6. Verify execute_task returns evidence for the exact requested task.
"""
from __future__ import annotations

import hashlib
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
    check_clean_checkout,
)
from subagentbridge.storage.sqlite_store import SQLiteStore
import subagentbridge.server as srv


class TestNativeExecutionTruthfulness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp).resolve()

        # Initialize a genuine Git repository in the workspace
        subprocess.run(["git", "init", "-q"], cwd=str(self.root), check=True)
        subprocess.run(["git", "config", "user.name", "TestAuditor"], cwd=str(self.root), check=True)
        subprocess.run(["git", "config", "user.email", "auditor@example.com"], cwd=str(self.root), check=True)

        self.db_path = self.root / ".subagentbridge" / "audit.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.store = SQLiteStore(str(self.root / "store.db"))

        # Create a genuine QA test file
        test_file = self.root / "tests" / "test_contract.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def test_ok(): assert True\n", encoding="utf-8")
        self.test_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

        # Initial commit to have a clean git tree
        subprocess.run(["git", "add", "."], cwd=str(self.root), check=True)
        subprocess.run(["git", "commit", "-m", "initial clean checkout", "-q"], cwd=str(self.root), check=True)

        self.sys = build_production_system(
            workspace_root=self.root,
            db_path=self.db_path,
            custom_qa_hashes={"tests/test_contract.py": self.test_hash},
        )

    def tearDown(self):
        self.sys.close()
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_prevents_completed_and_verified_without_developer_command(self):
        """Native execution must reject COMPLETED/VERIFIED when no developer command is executed."""
        run_id = f"run_{uuid4().hex[:8]}"
        tree_sha = resolve_tree_sha(self.root)

        tasks, dependencies, records = TaskDecomposer.decompose_goal(
            goal="Implement verified token ledger",
            run_id=run_id,
            tree_sha=tree_sha,
        )

        lifecycle = SupervisedNativeLifecycle(sys=self.sys, workspace_path=self.root, store=self.store)
        coordinator, principals = lifecycle.create_coordinator_for_run(
            run_id=run_id,
            tasks=tasks,
            dependencies=dependencies,
        )

        # Execute with NO command_map provided (empty / None)
        result = lifecycle.execute_lifecycle(
            run_id=run_id,
            coordinator=coordinator,
            principals=principals,
            task_records=records,
            command_map={},
        )

        self.assertEqual(result["status"], "FAILED")
        self.assertIn("no developer command provided", result.get("reason", "").lower())

        # No task should have reached VERIFIED
        for task_id in tasks:
            self.assertNotEqual(coordinator.state(task_id), TaskState.VERIFIED)

        # No task record in store or result should be VERIFIED
        for r in result.get("tasks", records):
            self.assertNotEqual(r.get("status"), "VERIFIED")

    def test_02_prevents_verified_when_checkout_is_dirty(self):
        """Native execution must detect dirty working tree and reject QA verification."""
        run_id = f"run_{uuid4().hex[:8]}"
        tree_sha = resolve_tree_sha(self.root)

        tasks, dependencies, records = TaskDecomposer.decompose_goal(
            goal="Test dirty checkout prevention",
            run_id=run_id,
            tree_sha=tree_sha,
        )

        lifecycle = SupervisedNativeLifecycle(sys=self.sys, workspace_path=self.root, store=self.store)
        coordinator, principals = lifecycle.create_coordinator_for_run(
            run_id=run_id,
            tasks=tasks,
            dependencies=dependencies,
        )

        pm_id = f"{run_id}_pm"
        # Command leaves an uncommitted dirty file
        dirty_cmd = [sys.executable, "-c", "import pathlib; pathlib.Path('dirty_untracked.txt').write_text('dirty')"]

        result = lifecycle.execute_lifecycle(
            run_id=run_id,
            coordinator=coordinator,
            principals=principals,
            task_records=records,
            command_map={pm_id: dirty_cmd},
        )

        self.assertEqual(result["status"], "FAILED")
        self.assertIn("checkout", result.get("reason", "").lower())
        self.assertNotEqual(coordinator.state(pm_id), TaskState.VERIFIED)

    def test_03_prevents_verified_when_qa_test_tampered(self):
        """Native execution reads actual QA test files from disk; tampered hashes fail QA review."""
        run_id = f"run_{uuid4().hex[:8]}"

        # Tamper the QA test on disk
        test_file = self.root / "tests" / "test_contract.py"
        test_file.write_text("def test_ok(): assert False # tampered\n", encoding="utf-8")
        subprocess.run(["git", "commit", "-am", "tamper QA test", "-q"], cwd=str(self.root), check=True)

        tree_sha = resolve_tree_sha(self.root)

        tasks, dependencies, records = TaskDecomposer.decompose_goal(
            goal="Test tampered QA test detection",
            run_id=run_id,
            tree_sha=tree_sha,
        )

        lifecycle = SupervisedNativeLifecycle(sys=self.sys, workspace_path=self.root, store=self.store)
        coordinator, principals = lifecycle.create_coordinator_for_run(
            run_id=run_id,
            tasks=tasks,
            dependencies=dependencies,
        )

        pm_id = f"{run_id}_pm"
        clean_cmd = [sys.executable, "-c", "print('pm pass')"]

        result = lifecycle.execute_lifecycle(
            run_id=run_id,
            coordinator=coordinator,
            principals=principals,
            task_records=records,
            command_map={pm_id: clean_cmd},
        )

        self.assertEqual(result["status"], "FAILED")
        self.assertIn("qa tests changed", result.get("reason", "").lower())

    def test_04_prevents_verified_when_qualifying_qa_fails(self):
        """Acceptance criteria coverage requires qualifying QA tests to pass."""
        run_id = f"run_{uuid4().hex[:8]}"
        tree_sha = resolve_tree_sha(self.root)

        # Make the QA test fail assert
        test_file = self.root / "tests" / "test_contract.py"
        test_file.write_text("def test_ok(): assert False, 'QA test failed'\n", encoding="utf-8")
        new_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()
        subprocess.run(["git", "commit", "-am", "failing QA test", "-q"], cwd=str(self.root), check=True)

        # Re-register system with the new hash so hash check passes, but execution fails
        self.sys.close()
        self.sys = build_production_system(
            workspace_root=self.root,
            db_path=self.db_path,
            custom_qa_hashes={"tests/test_contract.py": new_hash},
        )

        tasks, dependencies, records = TaskDecomposer.decompose_goal(
            goal="Test failing QA execution",
            run_id=run_id,
            tree_sha=resolve_tree_sha(self.root),
        )

        lifecycle = SupervisedNativeLifecycle(sys=self.sys, workspace_path=self.root, store=self.store)
        coordinator, principals = lifecycle.create_coordinator_for_run(
            run_id=run_id,
            tasks=tasks,
            dependencies=dependencies,
        )

        pm_id = f"{run_id}_pm"
        clean_cmd = [sys.executable, "-c", "print('pm pass')"]

        result = lifecycle.execute_lifecycle(
            run_id=run_id,
            coordinator=coordinator,
            principals=principals,
            task_records=records,
            command_map={pm_id: clean_cmd},
        )

        self.assertEqual(result["status"], "FAILED")
        self.assertIn("criteria", result.get("reason", "").lower())

    def test_05_genuine_execution_with_real_command_and_passing_qa_verifies(self):
        """With real commands, clean checkout, matching test hashes, and passing QA tests, task qualifies."""
        run_id = f"run_{uuid4().hex[:8]}"
        tree_sha = resolve_tree_sha(self.root)

        tasks, dependencies, records = TaskDecomposer.decompose_goal(
            goal="Build secure cache",
            run_id=run_id,
            tree_sha=tree_sha,
        )

        lifecycle = SupervisedNativeLifecycle(sys=self.sys, workspace_path=self.root, store=self.store)
        coordinator, principals = lifecycle.create_coordinator_for_run(
            run_id=run_id,
            tasks=tasks,
            dependencies=dependencies,
        )

        pm_id = f"{run_id}_pm"
        dev_id = f"{run_id}_dev"
        qa_id = f"{run_id}_qa"

        commands = {
            pm_id: [sys.executable, "-c", "print('PM scope analysis ok')"],
            dev_id: [sys.executable, "-c", "print('Dev implementation pass')"],
            qa_id: [sys.executable, "-c", "print('QA inspection pass')"],
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
        for t in result["tasks"]:
            self.assertEqual(t["status"], "VERIFIED")
            self.assertGreater(len(t["evidence_ids"]), 0)


if __name__ == "__main__":
    unittest.main()
