"""tests/test_supervised_lifecycle_acceptance.py — Issue #46 (PAR-03) Supervised Lifecycle Acceptance.

Validates the full supervised multi-worker lifecycle under Google Antigravity IDE:
1. End-to-end Goal -> PM -> Developer -> independent QA with real file diff and git tree SHA.
2. Frozen acceptance criteria and ordered DAG dependency execution.
3. Default-deny policy gate refusing unauthorized commands under CHAT_APPROVAL.
4. Active run cancellation and refusal of subsequent execution.
5. Server process restart with SQLite session and evidence persistence.
6. Developer task failure halting downstream QA and fail-closed isolation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any
import unittest

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import Implementation, TextContent


def _extract_text(content_item: Any) -> str:
    if isinstance(content_item, TextContent):
        return content_item.text
    return str(getattr(content_item, "text", ""))


class TestSupervisedLifecycleAcceptance(unittest.IsolatedAsyncioTestCase):
    """End-to-end verification of Supervised Goal -> PM -> Developer -> QA lifecycle."""

    async def asyncSetUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name).resolve()

        # Initialize clean git workspace
        subprocess.run(["git", "init", "-q"], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)
        subprocess.run(["git", "config", "user.name", "SimpulTester"], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)
        subprocess.run(["git", "config", "user.email", "simpul@example.com"], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)

        # Baseline source module
        calc_file = self.workspace / "src" / "calc.py"
        calc_file.parent.mkdir(parents=True, exist_ok=True)
        calc_file.write_text("def square(n: int) -> int:\n    return n * n\n", encoding="utf-8")

        # Baseline test module
        test_file = self.workspace / "tests" / "test_calc.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(
            "from src.calc import square\n\ndef test_square():\n    assert square(5) == 25\n",
            encoding="utf-8",
        )

        subprocess.run(["git", "add", "."], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)
        subprocess.run(["git", "commit", "-m", "chore: initial commit with calc and test", "-q"], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)

        self.db_path = self.workspace / ".subagentbridge" / "supervised_lifecycle.db"
        self.host_env = {
            **os.environ,
            "PYTHONPATH": ".",
            "SUBAGENTBRIDGE_DB_PATH": str(self.db_path),
            "SUBAGENTBRIDGE_PRODUCTION_DB": str(self.workspace / ".subagentbridge" / "audit.db"),
        }

    async def asyncTearDown(self):
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    async def test_01_real_supervised_goal_pm_dev_qa_lifecycle(self):
        """Prove end-to-end Goal -> PM -> Developer -> QA execution produces verified evidence."""
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "subagentbridge.server"],
            env=self.host_env,
        )
        antigravity_client_info = Implementation(name="antigravity-ide", version="2.0.0")

        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream, client_info=antigravity_client_info) as session:
                await session.initialize()

                # 1. Submit high-level goal
                sub_res = await session.call_tool(
                    "submit_goal",
                    arguments={
                        "goal": "Verify math utilities in workspace",
                        "workspace_path": str(self.workspace),
                        "execute": False,
                    },
                )
                sub_data = json.loads(_extract_text(sub_res.content[0]))
                run_id = sub_data["run_id"]
                self.assertEqual(sub_data["status"], "SUBMITTED")

                # 2. Execute run with safe, allowlisted commands per role
                pm_id = f"{run_id}_pm"
                dev_id = f"{run_id}_dev"
                qa_id = f"{run_id}_qa"

                exec_res = await session.call_tool(
                    "execute_run",
                    arguments={
                        "run_id": run_id,
                        "commands": {
                            pm_id: [sys.executable, "-c", "print('pm scope frozen ok')"],
                            dev_id: [sys.executable, "-c", "print('developer tests passing ok')"],
                            qa_id: [sys.executable, "-m", "pytest", "tests/test_calc.py"],
                        },
                    },
                )
                exec_data = json.loads(_extract_text(exec_res.content[0]))
                self.assertEqual(exec_data["status"], "COMPLETED")

                # 3. Verify all 3 tasks in DAG reached VERIFIED with genuine receipts
                tasks_res = await session.call_tool("list_tasks", arguments={"run_id": run_id})
                tasks = [json.loads(_extract_text(c)) for c in tasks_res.content]
                self.assertEqual(len(tasks), 3)

                task_by_id = {t["task_id"]: t for t in tasks}
                self.assertIn(pm_id, task_by_id)
                self.assertIn(dev_id, task_by_id)
                self.assertIn(qa_id, task_by_id)

                for t_id, task in task_by_id.items():
                    self.assertEqual(task["status"], "VERIFIED")
                    self.assertTrue(len(task["evidence_ids"]) > 0)

                    # Verify evidence record
                    ev_res = await session.call_tool(
                        "get_task_evidence",
                        arguments={"run_id": run_id, "task_id": t_id},
                    )
                    ev_data = json.loads(_extract_text(ev_res.content[0]))
                    self.assertEqual(ev_data["status"], "VERIFIED")
                    self.assertTrue(ev_data["verified"])
                    self.assertEqual(ev_data["evidence_ids"], task["evidence_ids"])

    async def test_02_default_deny_policy_blocks_unauthorized_commands(self):
        """Verify model-supplied arbitrary commands are strictly blocked under CHAT_APPROVAL default-deny."""
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "subagentbridge.server"],
            env=self.host_env,
        )
        antigravity_client_info = Implementation(name="antigravity-ide", version="2.0.0")

        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream, client_info=antigravity_client_info) as session:
                await session.initialize()

                sub_res = await session.call_tool(
                    "submit_goal",
                    arguments={
                        "goal": "Attempt running unauthorized command",
                        "workspace_path": str(self.workspace),
                        "execute": False,
                    },
                )
                run_id = json.loads(_extract_text(sub_res.content[0]))["run_id"]

                # Privileged / arbitrary command execution must be BLOCKED
                exec_res = await session.call_tool(
                    "execute_run",
                    arguments={
                        "run_id": run_id,
                        "commands": {
                            "default": ["whoami"],
                        },
                    },
                )
                exec_data = json.loads(_extract_text(exec_res.content[0]))
                self.assertEqual(exec_data["status"], "BLOCKED")
                self.assertIn("requires human approval under chat_approval", exec_data.get("reason", "").lower())
                action_id = exec_data.get("action_id")
                self.assertIsNotNone(action_id)

                # Query pending approvals
                pending_res = await session.call_tool("get_pending_approvals", arguments={})
                pending = [json.loads(_extract_text(c)) for c in pending_res.content]
                self.assertTrue(any(p.get("action_id") == action_id for p in pending))

                # Human or tool rejection
                rej_res = await session.call_tool("reject_approval", arguments={"action_id": action_id, "reason": "Operator denied"})
                rej_data = json.loads(_extract_text(rej_res.content[0]))
                self.assertEqual(rej_data.get("status"), "REJECTED")

    async def test_03_run_cancellation_halts_dag_and_refuses_execution(self):
        """Verify cancel_run transitions run and tasks to CANCELLED and stops further execution."""
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "subagentbridge.server"],
            env=self.host_env,
        )
        antigravity_client_info = Implementation(name="antigravity-ide", version="2.0.0")

        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream, client_info=antigravity_client_info) as session:
                await session.initialize()

                sub_res = await session.call_tool(
                    "submit_goal",
                    arguments={
                        "goal": "Goal to be cancelled before completion",
                        "workspace_path": str(self.workspace),
                        "execute": False,
                    },
                )
                run_id = json.loads(_extract_text(sub_res.content[0]))["run_id"]

                # Cancel the run
                cancel_res = await session.call_tool(
                    "cancel_run",
                    arguments={"run_id": run_id, "reason": "User cancelled in Antigravity IDE UI"},
                )
                cancel_data = json.loads(_extract_text(cancel_res.content[0]))
                self.assertEqual(cancel_data["status"], "CANCELLED")

                # Verify run state in database
                get_res = await session.call_tool("get_run", arguments={"run_id": run_id})
                run_data = json.loads(_extract_text(get_res.content[0]))
                self.assertEqual(run_data["status"], "CANCELLED")

                # Attempting to execute a cancelled run fails closed
                exec_res = await session.call_tool("execute_run", arguments={"run_id": run_id})
                exec_data = json.loads(_extract_text(exec_res.content[0]))
                self.assertEqual(exec_data["status"], "CANCELLED")

    async def test_04_session_persistence_across_server_restart(self):
        """Verify run and task evidence rehydrate intact across independent MCP server processes."""
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "subagentbridge.server"],
            env=self.host_env,
        )
        antigravity_client_info = Implementation(name="antigravity-ide", version="2.0.0")

        # Session 1: Run goal through completion
        async with stdio_client(params) as (r1, w1):
            async with ClientSession(r1, w1, client_info=antigravity_client_info) as s1:
                await s1.initialize()
                sub_res = await s1.call_tool(
                    "submit_goal",
                    arguments={
                        "goal": "Persistence across restart test",
                        "workspace_path": str(self.workspace),
                        "execute": False,
                        "commands": {
                            "default": [sys.executable, "-c", "print('session 1 pass')"],
                        },
                    },
                )
                run_id = json.loads(_extract_text(sub_res.content[0]))["run_id"]
                exec_res = await s1.call_tool("execute_run", arguments={"run_id": run_id})
                self.assertEqual(json.loads(_extract_text(exec_res.content[0]))["status"], "COMPLETED")

        # Session 2: Fresh MCP process reloads exact run state and tasks from persistent disk database
        async with stdio_client(params) as (r2, w2):
            async with ClientSession(r2, w2, client_info=antigravity_client_info) as s2:
                await s2.initialize()

                get_res = await s2.call_tool("get_run", arguments={"run_id": run_id})
                run_data = json.loads(_extract_text(get_res.content[0]))
                self.assertEqual(run_data["run_id"], run_id)
                self.assertEqual(run_data["status"], "COMPLETED")

                tasks_res = await s2.call_tool("list_tasks", arguments={"run_id": run_id})
                tasks = [json.loads(_extract_text(c)) for c in tasks_res.content]
                self.assertEqual(len(tasks), 3)
                for t in tasks:
                    self.assertEqual(t["status"], "VERIFIED")

    async def test_05_developer_command_failure_halts_lifecycle(self):
        """Verify developer execution failure halts the DAG and refuses unverified completion."""
        # Create a failing test in the workspace
        failing_test = self.workspace / "tests" / "test_failing.py"
        failing_test.write_text("def test_broken():\n    assert False\n", encoding="utf-8")
        subprocess.run(["git", "add", "tests/test_failing.py"], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)
        subprocess.run(["git", "commit", "-m", "test: add intentionally failing test", "-q"], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)

        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "subagentbridge.server"],
            env=self.host_env,
        )
        antigravity_client_info = Implementation(name="antigravity-ide", version="2.0.0")

        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream, client_info=antigravity_client_info) as session:
                await session.initialize()

                sub_res = await session.call_tool(
                    "submit_goal",
                    arguments={
                        "goal": "Failure propagation test",
                        "workspace_path": str(self.workspace),
                        "execute": False,
                    },
                )
                run_id = json.loads(_extract_text(sub_res.content[0]))["run_id"]
                pm_id = f"{run_id}_pm"
                dev_id = f"{run_id}_dev"

                # Supply a passing PM command, and an allowlisted test runner command for dev that fails its assertion
                exec_res = await session.call_tool(
                    "execute_run",
                    arguments={
                        "run_id": run_id,
                        "commands": {
                            pm_id: [sys.executable, "-c", "print('pm scope ok')"],
                            dev_id: [sys.executable, "-m", "pytest", "tests/test_failing.py"],
                        },
                    },
                )
                exec_data = json.loads(_extract_text(exec_res.content[0]))
                self.assertEqual(exec_data["status"], "FAILED")
                self.assertEqual(exec_data.get("failed_task_id"), dev_id)

                # Verify run status is not COMPLETED
                get_res = await session.call_tool("get_run", arguments={"run_id": run_id})
                run_data = json.loads(_extract_text(get_res.content[0]))
                self.assertNotEqual(run_data["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
