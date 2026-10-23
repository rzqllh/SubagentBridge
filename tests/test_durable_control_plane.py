"""Phase P02 verification: Durable control plane persistence, rehydration, crash recovery, and honest evidence."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from subagentbridge.server import (
    close_production_system,
    submit_goal,
    get_run,
    list_tasks,
    get_task_evidence,
    cancel_run,
    rehydrate_runs_and_tasks,
    _runs,
    _tasks,
)
from subagentbridge.storage.sqlite_store import SQLiteStore


class DurableControlPlaneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        self.db_path = self.root / "control_plane.db"
        self.store = SQLiteStore(self.db_path)
        import subagentbridge.server as srv
        self._orig_store = srv._store
        srv._store = self.store
        _runs.clear()
        _tasks.clear()

    def tearDown(self):
        close_production_system()
        import subagentbridge.server as srv
        srv._store = self._orig_store
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_and_task_persistence_survives_restart(self):
        """Runs and tasks persist to SQLite and rehydrate after server restart."""
        # 1. Submit goal
        res = submit_goal("Implement durable scheduler", workspace_path=str(self.root))
        self.assertEqual(res["status"], "SUBMITTED")
        run_id = res["run_id"]
        task_id = res["initial_task_id"]

        # 2. Verify stored in store
        run = self.store.get_run(run_id)
        self.assertIsNotNone(run)
        self.assertEqual(run["goal"], "Implement durable scheduler")
        self.assertEqual(run["status"], "SUBMITTED")

        tasks = self.store.load_tasks_for_run(run_id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], task_id)
        self.assertEqual(tasks[0]["status"], "PENDING")

        # 3. Simulate process crash / memory wipe
        _runs.clear()
        _tasks.clear()

        # 4. Rehydrate from store
        rehydrate_runs_and_tasks(self.store)
        self.assertIn(run_id, _runs)
        self.assertIn(run_id, _tasks)

        # 5. MCP tools retrieve persisted state
        run_view = get_run(run_id)
        self.assertEqual(run_view["status"], "SUBMITTED")
        self.assertEqual(run_view["task_count"], 1)

        task_list = list_tasks(run_id)
        self.assertEqual(len(task_list), 1)
        self.assertEqual(task_list[0]["task_id"], task_id)

    def test_crash_recovery_resets_stale_active_tasks_to_recovery_required(self):
        """Active dispatches whose processes died on crash are recovered to RECOVERY_REQUIRED."""
        res = submit_goal("Build distributed cache", workspace_path=str(self.root))
        run_id = res["run_id"]
        task_id = res["initial_task_id"]

        # Simulate task advancing to DISPATCHED before crash
        self.store.upsert_task({
            "task_id": task_id,
            "run_id": run_id,
            "title": "Task in flight",
            "status": "DISPATCHED",
            "role": "DEVELOPER",
            "tree_sha": "abc123",
        })

        # Crash happens: server restarts and runs rehydration
        _runs.clear()
        _tasks.clear()
        rehydrate_runs_and_tasks(self.store)

        # Task must be marked RECOVERY_REQUIRED, not left in phantom DISPATCHED
        t = self.store.get_task(task_id)
        self.assertEqual(t["status"], "RECOVERY_REQUIRED")
        self.assertEqual(_tasks[run_id][0]["status"], "RECOVERY_REQUIRED")

    def test_cancel_run_persists_cancellation_and_cancels_tasks(self):
        """cancel_run updates run and all active tasks to CANCELLED durably."""
        res = submit_goal("Experimental pipeline", workspace_path=str(self.root))
        run_id = res["run_id"]
        task_id = res["initial_task_id"]

        # Cancel run
        cancel_res = cancel_run(run_id, reason="User requested abort")
        self.assertEqual(cancel_res["status"], "CANCELLED")

        # Check in-memory
        self.assertEqual(_runs[run_id]["status"], "CANCELLED")
        self.assertEqual(_tasks[run_id][0]["status"], "CANCELLED")

        # Check durable store
        persisted_run = self.store.get_run(run_id)
        self.assertEqual(persisted_run["status"], "CANCELLED")

        persisted_task = self.store.get_task(task_id)
        self.assertEqual(persisted_task["status"], "CANCELLED")

    def test_honest_mcp_evidence_refuses_forged_verified(self):
        """get_task_evidence refuses to claim verified: True without evidence."""
        res = submit_goal("Honest status check", workspace_path=str(self.root))
        run_id = res["run_id"]
        task_id = res["initial_task_id"]

        # 1. When status is PENDING, verified is False
        ev = get_task_evidence(run_id, task_id)
        self.assertFalse(ev["verified"])

        # 2. If status is forged to VERIFIED but evidence_ids is empty
        _tasks[run_id][0]["status"] = "VERIFIED"
        _tasks[run_id][0]["evidence_ids"] = []
        ev_forged = get_task_evidence(run_id, task_id)
        self.assertFalse(ev_forged["verified"], "Honest MCP must reject VERIFIED claim with empty evidence")

        # 3. With actual evidence_ids present
        _tasks[run_id][0]["evidence_ids"] = ["ev_receipt_001"]
        ev_legit = get_task_evidence(run_id, task_id)
        self.assertTrue(ev_legit["verified"])


if __name__ == "__main__":
    unittest.main()
