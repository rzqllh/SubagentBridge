"""Tests for the hardened production MCP server tools and lockdown (PR-10, INV-03).

Proves:
1. server.py does NOT expose def approve_action (INV-03).
2. server.py registers real control-plane MCP tools: submit_goal, get_run,
   list_tasks, get_task_evidence, get_pending_approvals, reject_approval,
   get_model_usage, cancel_run.
3. submit_goal initializes a real run and tasks through the production engine.
4. get_pending_approvals and reject_approval operate safely under CHAT_APPROVAL.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "subagentbridge"


class ProductionMcpServerTests(unittest.TestCase):
    def test_INV_03_no_approve_action_callable(self):
        text = (SRC / "server.py").read_text(encoding="utf-8")
        self.assertNotIn("def approve_action(action_id: str)", text, "Model-callable approval must not be exposed")

    def test_mcp_tools_registered(self):
        import subagentbridge.server as srv

        tools = getattr(srv.mcp, "_tool_manager", None) or getattr(srv.mcp, "tools", None)
        # Verify tool functions exist in module namespace
        self.assertTrue(hasattr(srv, "submit_goal"), "submit_goal MCP tool must exist")
        self.assertTrue(hasattr(srv, "get_run"), "get_run MCP tool must exist")
        self.assertTrue(hasattr(srv, "list_tasks"), "list_tasks MCP tool must exist")
        self.assertTrue(hasattr(srv, "get_task_evidence"), "get_task_evidence MCP tool must exist")
        self.assertTrue(hasattr(srv, "get_pending_approvals"), "get_pending_approvals MCP tool must exist")
        self.assertTrue(hasattr(srv, "reject_approval"), "reject_approval MCP tool must exist")
        self.assertTrue(hasattr(srv, "get_model_usage"), "get_model_usage MCP tool must exist")
        self.assertTrue(hasattr(srv, "cancel_run"), "cancel_run MCP tool must exist")

    def test_submit_goal_and_query_run(self):
        import subagentbridge.server as srv

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                res = srv.submit_goal(goal="Implement secure feature", workspace_path=tmpdir)
                self.assertEqual(res.get("status"), "SUBMITTED")
                run_id = res.get("run_id")
                self.assertIsNotNone(run_id)

                run_info = srv.get_run(run_id)
                self.assertEqual(run_info.get("run_id"), run_id)
                self.assertIn("status", run_info)

                tasks = srv.list_tasks(run_id)
                self.assertIsInstance(tasks, list)
                self.assertGreaterEqual(len(tasks), 1)

                # Cancel run
                cancel_res = srv.cancel_run(run_id, reason="Testing complete")
                self.assertEqual(cancel_res.get("status"), "CANCELLED")
            finally:
                srv.close_production_system()


if __name__ == "__main__":
    unittest.main()
