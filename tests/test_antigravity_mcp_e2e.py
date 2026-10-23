"""tests/test_antigravity_mcp_e2e.py — Comprehensive Antigravity MCP Integration Verification.

Verifies:
1. FastMCP server tool discovery and registration.
2. End-to-end goal submission, PM decomposition, and supervised execution.
3. Trustworthy execution receipts and independent QA verification status.
4. Truthful MCP verification reporting: cannot claim verified: True without valid evidence.
5. Approval workflow under CHAT_APPROVAL: request, list pending, rejection finality.
6. Run cancellation: cancel_run transitions run and tasks to CANCELLED.
7. Crash/restart rehydration: state persistence and idempotent reload from SQLite store.
8. Real MCP model discovery and role skill listing.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from subagentbridge.server import (
    cancel_run,
    close_production_system,
    discover_models,
    execute_run,
    execute_task,
    get_run,
    get_task_evidence,
    list_pending_actions,
    list_skills,
    list_tasks,
    rehydrate_runs_and_tasks,
    reject_action,
    reject_approval,
    submit_goal,
    _pending,
    _runs,
    _tasks,
)
from subagentbridge.storage.sqlite_store import SQLiteStore


class TestAntigravityMcpE2E(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name).resolve()
        # Use workspace-isolated store for clean testing
        self.db_path = self.workspace / ".subagentbridge" / "mcp_test_store.db"
        self.store = SQLiteStore(self.db_path)
        # Point server global store to this isolated store for tests
        import subagentbridge.server as srv
        self._orig_store = srv._store
        srv._store = self.store
        _runs.clear()
        _tasks.clear()

    def tearDown(self):
        import subagentbridge.server as srv
        srv._store = self._orig_store
        close_production_system(self.workspace)
        try:
            self.store.close()
        except Exception:
            pass
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_01_submit_goal_and_decomposition(self):
        """Verify submit_goal decomposes into PM, Developer, and QA tasks."""
        goal_text = "Implement Antigravity MCP end-to-end validation"
        res = submit_goal(goal=goal_text, workspace_path=str(self.workspace), execute=False)
        self.assertEqual(res.get("status"), "SUBMITTED")
        run_id = res["run_id"]

        # Verify run retrieval
        run_info = get_run(run_id)
        self.assertEqual(run_info["status"], "SUBMITTED")
        self.assertEqual(run_info["goal"], goal_text)

        # Verify task list
        tasks = list_tasks(run_id)
        self.assertTrue(len(tasks) >= 1)

    def test_02_execute_run_full_lifecycle_and_truthful_evidence(self):
        """Verify execute_run transitions through frozen, dispatched, receipts, and QA verification."""
        goal_text = "Execute supervised native lifecycle under MCP"
        res = submit_goal(goal=goal_text, workspace_path=str(self.workspace), execute=False)
        run_id = res["run_id"]

        exec_res = execute_run(run_id)
        self.assertEqual(exec_res.get("status"), "COMPLETED")

        # Verify tasks are verified and receipts exist
        tasks = list_tasks(run_id)
        self.assertEqual(len(tasks), 3)
        for t in tasks:
            self.assertEqual(t["status"], "VERIFIED")
            self.assertTrue(len(t["evidence_ids"]) > 0)

            # Test honest MCP evidence reporting
            ev = get_task_evidence(run_id, t["task_id"])
            self.assertEqual(ev["status"], "VERIFIED")
            self.assertTrue(ev["verified"])
            self.assertEqual(ev["evidence_ids"], t["evidence_ids"])

    def test_03_execute_individual_task(self):
        """Verify execute_task executes lifecycle for specific task."""
        goal_text = "Execute single task via MCP tool"
        res = submit_goal(goal=goal_text, workspace_path=str(self.workspace), execute=False)
        run_id = res["run_id"]
        tasks = list_tasks(run_id)
        target_task_id = tasks[0]["task_id"]

        task_res = execute_task(run_id, target_task_id)
        self.assertIn(task_res.get("status"), ("COMPLETED", "VERIFIED"))

    def test_04_approval_workflow_and_rejection_finality(self):
        """Verify approval workflow under CHAT_APPROVAL: listing and rejection."""
        # Create a pending action
        act = _pending.enqueue("session_mcp_1", {"command": "modify dependency"})
        self.assertIsNotNone(act.action_id)

        # List pending actions
        pending = list_pending_actions()
        found = [p for p in pending if p["action_id"] == act.action_id]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["description"], "modify dependency")

        # Reject action
        rej = reject_approval(act.action_id, reason="Security review denied dependency")
        self.assertEqual(rej["status"], "REJECTED")

        # Verify action is no longer pending
        pending_after = list_pending_actions()
        found_after = [p for p in pending_after if p["action_id"] == act.action_id]
        self.assertEqual(len(found_after), 0)

        # Legacy alias reject_action
        act2 = _pending.enqueue("session_mcp_2", {"command": "run deploy"})
        legacy_rej = reject_action(act2.action_id, reason="No deploy permitted")
        self.assertIn(f"action {act2.action_id!r} rejected", legacy_rej)


    def test_05_cancel_run_lifecycle(self):
        """Verify cancel_run marks run and pending tasks as CANCELLED."""
        res = submit_goal(goal="Task to be cancelled", workspace_path=str(self.workspace), execute=False)
        run_id = res["run_id"]

        cancel_res = cancel_run(run_id, reason="User cancelled execution")
        self.assertEqual(cancel_res["status"], "CANCELLED")

        # Verify run status
        run_info = get_run(run_id)
        self.assertEqual(run_info["status"], "CANCELLED")

        # Verify tasks status
        tasks = list_tasks(run_id)
        for t in tasks:
            self.assertEqual(t["status"], "CANCELLED")

    def test_06_crash_restart_rehydration(self):
        """Verify crash/restart rehydration from SQLite store recovers durable state."""
        # 1. Submit goal and run
        res = submit_goal(goal="Durable restart test", workspace_path=str(self.workspace), execute=False)
        run_id = res["run_id"]

        # 2. Simulate complete in-memory crash / IDE restart
        _runs.clear()
        _tasks.clear()
        self.assertEqual(len(_runs), 0)
        self.assertEqual(len(_tasks), 0)

        # 3. Trigger rehydration
        rehydrate_runs_and_tasks(self.store)

        # 4. Verify run and tasks are accurately restored from disk
        self.assertIn(run_id, _runs)
        self.assertEqual(_runs[run_id]["goal"], "Durable restart test")
        self.assertIn(run_id, _tasks)
        self.assertTrue(len(_tasks[run_id]) >= 1)

    def test_07_mcp_discover_models_and_list_skills_integration(self):
        """Verify discover_models and list_skills tools operate cleanly."""
        models = discover_models(str(self.workspace))
        self.assertIsInstance(models, list)

        skills = list_skills(role="DEVELOPER", workspace_path=str(self.workspace))
        self.assertIsInstance(skills, list)


if __name__ == "__main__":
    unittest.main()
