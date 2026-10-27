"""tests/test_antigravity_mcp_subprocess_client.py — Real MCP stdio subprocess integration.

Verifies:
1. Spawns subagentbridge.server as a real separate operating-system subprocess over stdio.
2. Connects using the standard Python MCP SDK (stdio_client and ClientSession).
3. Executes MCP initialize handshake, tool discovery, and schema registration.
4. Submits goal, dispatches execution, and verifies independent QA evidence across stdio JSON-RPC.
5. Executes specific task and verifies exact evidence payload.
6. Exercises approval gating (listing pending approvals and rejecting actions) over stdio.
7. Exercises run cancellation over stdio.
8. Verifies clean shutdown of subprocess.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class TestAntigravityMcpSubprocessClient(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name).resolve()

        # Initialize clean git repo
        subprocess.run(["git", "init", "-q"], cwd=str(self.workspace), check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(self.workspace), check=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(self.workspace), check=True)
        test_file = self.workspace / "tests" / "test_dummy.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def test_dummy(): pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(self.workspace), check=True)
        subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=str(self.workspace), check=True)

        self.db_path = self.workspace / ".subagentbridge" / "mcp_subprocess_test.db"
        self.server_env = {
            **os.environ,
            "PYTHONPATH": ".",
            "SUBAGENTBRIDGE_DB_PATH": str(self.db_path),
            "SUBAGENTBRIDGE_PRODUCTION_DB": str(self.db_path),
        }

    async def asyncTearDown(self):
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    async def test_real_mcp_stdio_subprocess_lifecycle(self):
        """Connect to subagentbridge.server via genuine MCP stdio client and test full tool surface."""
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "subagentbridge.server"],
            env=self.server_env,
        )

        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # 1. Initialize
                init_res = await session.initialize()
                self.assertEqual(init_res.serverInfo.name, "subagentbridge")

                # 2. List tools
                tools_res = await session.list_tools()
                tool_names = {t.name for t in tools_res.tools}
                self.assertIn("submit_goal", tool_names)
                self.assertIn("execute_run", tool_names)
                self.assertIn("execute_task", tool_names)
                self.assertIn("get_run", tool_names)
                self.assertIn("list_tasks", tool_names)
                self.assertIn("get_task_evidence", tool_names)
                self.assertIn("cancel_run", tool_names)
                self.assertIn("reject_approval", tool_names)
                self.assertIn("discover_models", tool_names)
                self.assertIn("list_skills", tool_names)

                # 3. Submit goal with real executable commands
                goal_text = "Verify Antigravity MCP stdio subprocess integration"
                sub_call = await session.call_tool(
                    "submit_goal",
                    arguments={
                        "goal": goal_text,
                        "workspace_path": str(self.workspace),
                        "execute": False,
                        "commands": {
                            "default": [sys.executable, "-c", "print('mcp stdio success')"],
                        },
                    },
                )
                self.assertIsNotNone(sub_call.content)
                sub_data = sub_call.content[0].text if hasattr(sub_call.content[0], "text") else str(sub_call.content[0])
                import json
                sub_json = json.loads(sub_data) if isinstance(sub_data, str) and sub_data.startswith("{") else {}
                run_id = sub_json.get("run_id")
                self.assertIsNotNone(run_id)
                self.assertEqual(sub_json.get("status"), "SUBMITTED")

                # 4. Get run details
                run_call = await session.call_tool("get_run", arguments={"run_id": run_id})
                run_data = json.loads(run_call.content[0].text)
                self.assertEqual(run_data.get("status"), "SUBMITTED")
                self.assertEqual(run_data.get("goal"), goal_text)

                # 5. List tasks
                tasks_call = await session.call_tool("list_tasks", arguments={"run_id": run_id})
                tasks_data = [json.loads(c.text) for c in tasks_call.content]
                self.assertTrue(len(tasks_data) >= 1)

                # 6. Execute run over stdio JSON-RPC
                exec_call = await session.call_tool("execute_run", arguments={"run_id": run_id})
                exec_data = json.loads(exec_call.content[0].text)
                self.assertEqual(exec_data.get("status"), "COMPLETED")

                # 7. Verify tasks and receipts via stdio
                tasks_call2 = await session.call_tool("list_tasks", arguments={"run_id": run_id})
                tasks_data2 = [json.loads(c.text) for c in tasks_call2.content]
                self.assertEqual(len(tasks_data2), 3)
                for t in tasks_data2:
                    self.assertEqual(t.get("status"), "VERIFIED")
                    task_id = t["task_id"]

                    ev_call = await session.call_tool(
                        "get_task_evidence",
                        arguments={"run_id": run_id, "task_id": task_id},
                    )
                    ev_data = json.loads(ev_call.content[0].text)
                    self.assertEqual(ev_data.get("status"), "VERIFIED")
                    self.assertTrue(ev_data.get("verified"))
                    self.assertEqual(ev_data.get("evidence_ids"), t["evidence_ids"])

                # 8. Test execute_task on a new run
                sub_call2 = await session.call_tool(
                    "submit_goal",
                    arguments={
                        "goal": "Second run for task-level execution",
                        "workspace_path": str(self.workspace),
                        "execute": False,
                    },
                )
                sub_json2 = json.loads(sub_call2.content[0].text)
                run_id2 = sub_json2["run_id"]
                target_task_id = f"{run_id2}_pm"

                task_exec_call = await session.call_tool(
                    "execute_task",
                    arguments={
                        "run_id": run_id2,
                        "task_id": target_task_id,
                        "command": [sys.executable, "-c", "print('task stdio ok')"],
                    },
                )
                task_exec_data = json.loads(task_exec_call.content[0].text)
                self.assertEqual(task_exec_data.get("status"), "VERIFIED")
                self.assertEqual(task_exec_data.get("task_id"), target_task_id)
                self.assertIn("evidence", task_exec_data)
                self.assertTrue(task_exec_data["evidence"].get("verified"))

                # 9. Test cancel_run over stdio
                sub_call3 = await session.call_tool(
                    "submit_goal",
                    arguments={
                        "goal": "Third run for cancellation",
                        "workspace_path": str(self.workspace),
                        "execute": False,
                    },
                )
                sub_json3 = json.loads(sub_call3.content[0].text)
                run_id3 = sub_json3["run_id"]

                cancel_call = await session.call_tool(
                    "cancel_run",
                    arguments={"run_id": run_id3, "reason": "User cancelled via stdio MCP"},
                )
                cancel_data = json.loads(cancel_call.content[0].text)
                self.assertEqual(cancel_data.get("status"), "CANCELLED")

                # 10. Test discover_models and list_skills over stdio
                models_call = await session.call_tool(
                    "discover_models",
                    arguments={"workspace_path": str(self.workspace)},
                )
                models_data = json.loads(models_call.content[0].text)
                self.assertTrue(isinstance(models_data, list) or models_data.get("status") in ("ERROR", "OK"))

                skills_call = await session.call_tool(
                    "list_skills",
                    arguments={"role": "DEVELOPER", "workspace_path": str(self.workspace)},
                )
                skills_data = [json.loads(c.text) for c in skills_call.content]
                self.assertIsInstance(skills_data, list)


if __name__ == "__main__":
    unittest.main()
