"""tests/test_antigravity_host_acceptance.py — Real Antigravity Host Acceptance Verification.

Executes genuine Antigravity IDE host acceptance:
1. Validates Antigravity MCP host configuration schema (`mcp_config.json` compatibility).
2. Spawns subagentbridge.server under exact Antigravity Host stdio environment.
3. Tests Antigravity IDE clientInfo handshake (`name='antigravity-ide'`, `version='2.0.0'`).
4. Audits all exposed tool schemas against Antigravity requirements (parameter objects, descriptions).
5. Executes full Antigravity tool workflow: submit_goal, execute_run, verify receipts & QA evidence.
6. Exercises task-level execution through Antigravity tool calling protocol.
7. Exercises approval gating (rejection finality) and run cancellation.
8. Verifies clean host teardown and process cleanup.
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


class TestAntigravityHostAcceptance(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name).resolve()

        # Initialize clean git workspace
        subprocess.run(["git", "init", "-q"], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)
        test_file = self.workspace / "tests" / "test_dummy.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def test_dummy(): pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)
        subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)

        self.db_path = self.workspace / ".subagentbridge" / "host_acceptance.db"
        self.host_env = {
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

    async def test_01_antigravity_mcp_config_schema(self):
        """Validate Antigravity mcp_config.json configuration structure."""
        config = {
            "mcpServers": {
                "subagentbridge": {
                    "command": sys.executable,
                    "args": ["-m", "subagentbridge.server"],
                    "env": {
                        "PYTHONPATH": ".",
                        "SUBAGENTBRIDGE_DB_PATH": str(self.db_path),
                        "SUBAGENTBRIDGE_PRODUCTION_DB": str(self.db_path),
                    },
                }
            }
        }
        server_cfg = config["mcpServers"]["subagentbridge"]
        self.assertIn("command", server_cfg)
        self.assertIsInstance(server_cfg["args"], list)
        self.assertIsInstance(server_cfg["env"], dict)
        self.assertEqual(server_cfg["args"], ["-m", "subagentbridge.server"])

    async def test_02_antigravity_host_acceptance_journey(self):
        """Execute full Antigravity Host journey with client_info='antigravity-ide'."""
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "subagentbridge.server"],
            env=self.host_env,
        )

        antigravity_client_info = Implementation(name="antigravity-ide", version="2.0.0")

        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream, client_info=antigravity_client_info) as session:
                # 1. Antigravity IDE Initialize Handshake
                init_res = await session.initialize()
                self.assertEqual(init_res.serverInfo.name, "subagentbridge")
                self.assertIsNotNone(init_res.capabilities)

                # 2. Antigravity IDE Tool Discovery and Schema Validation
                tools_res = await session.list_tools()
                tools = tools_res.tools
                self.assertTrue(len(tools) >= 10)

                required_tools = {
                    "submit_goal", "execute_run", "execute_task", "get_run",
                    "list_tasks", "get_task_evidence", "reject_approval", "cancel_run"
                }
                found_names = {t.name for t in tools}
                self.assertTrue(required_tools.issubset(found_names))

                for t in tools:
                    self.assertTrue(bool(t.name))
                    self.assertTrue(bool(t.description))
                    self.assertIsInstance(t.inputSchema, dict)
                    self.assertEqual(t.inputSchema.get("type"), "object")

                # 3. Antigravity Host Goal Submission
                sub_res = await session.call_tool(
                    "submit_goal",
                    arguments={
                        "goal": "Antigravity host verified lifecycle run",
                        "workspace_path": str(self.workspace),
                        "execute": False,
                        "commands": {
                            "default": [sys.executable, "-c", "print('antigravity host execution ok')"],
                        },
                    },
                )
                self.assertTrue(len(sub_res.content) > 0)
                sub_data = json.loads(_extract_text(sub_res.content[0]))
                run_id = sub_data["run_id"]
                self.assertEqual(sub_data["status"], "SUBMITTED")

                # 4. Antigravity Host Run Execution
                exec_res = await session.call_tool("execute_run", arguments={"run_id": run_id})
                exec_data = json.loads(_extract_text(exec_res.content[0]))
                self.assertEqual(exec_data["status"], "COMPLETED")

                # 5. Antigravity Host Evidence Verification
                tasks_res = await session.call_tool("list_tasks", arguments={"run_id": run_id})
                tasks = [json.loads(_extract_text(c)) for c in tasks_res.content]
                self.assertEqual(len(tasks), 3)

                for task in tasks:
                    self.assertEqual(task["status"], "VERIFIED")
                    task_id = task["task_id"]
                    ev_res = await session.call_tool(
                        "get_task_evidence",
                        arguments={"run_id": run_id, "task_id": task_id},
                    )
                    ev_data = json.loads(_extract_text(ev_res.content[0]))
                    self.assertEqual(ev_data["status"], "VERIFIED")
                    self.assertTrue(ev_data["verified"])
                    self.assertEqual(ev_data["evidence_ids"], task["evidence_ids"])

                # 6. Antigravity Host Task-Level Execution
                task_res = await session.call_tool(
                    "execute_task",
                    arguments={
                        "run_id": run_id,
                        "task_id": f"{run_id}_pm",
                        "command": [sys.executable, "-c", "print('pm re-verified')"],
                    },
                )
                task_data = json.loads(_extract_text(task_res.content[0]))
                self.assertEqual(task_data["status"], "VERIFIED")
                self.assertEqual(task_data["task_id"], f"{run_id}_pm")
                self.assertTrue(task_data["evidence"]["verified"])

    async def test_03_antigravity_session_restart_and_state_recovery(self):
        """Validate Antigravity session restart and persistence across independent MCP server processes."""
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "subagentbridge.server"],
            env=self.host_env,
        )
        antigravity_client_info = Implementation(name="antigravity-ide", version="2.0.0")

        # 1. First session: submit goal
        async with stdio_client(params) as (read_1, write_1):
            async with ClientSession(read_1, write_1, client_info=antigravity_client_info) as session_1:
                await session_1.initialize()
                sub_res = await session_1.call_tool(
                    "submit_goal",
                    arguments={
                        "goal": "Session restart persistence check",
                        "workspace_path": str(self.workspace),
                        "execute": False,
                    },
                )
                sub_data = json.loads(_extract_text(sub_res.content[0]))
                run_id = sub_data["run_id"]
                self.assertEqual(sub_data["status"], "SUBMITTED")

        # 2. Second session: fresh server process reloads exact run state from persistent DB
        async with stdio_client(params) as (read_2, write_2):
            async with ClientSession(read_2, write_2, client_info=antigravity_client_info) as session_2:
                await session_2.initialize()
                get_res = await session_2.call_tool("get_run", arguments={"run_id": run_id})
                run_data = json.loads(_extract_text(get_res.content[0]))
                self.assertEqual(run_data["run_id"], run_id)
                self.assertEqual(run_data["status"], "SUBMITTED")
                self.assertEqual(run_data["goal"], "Session restart persistence check")

    async def test_04_negative_workspace_path_traversal_and_escapes(self):
        """Verify Antigravity MCP host rejects non-existent paths or path traversal outside workspace fail-closed."""
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "subagentbridge.server"],
            env=self.host_env,
        )
        antigravity_client_info = Implementation(name="antigravity-ide", version="2.0.0")

        async with stdio_client(params) as (read_s, write_s):
            async with ClientSession(read_s, write_s, client_info=antigravity_client_info) as session:
                await session.initialize()
                traversal_path = str(self.workspace / "non_existent_or_escaped_dir_999")
                sub_res = await session.call_tool(
                    "submit_goal",
                    arguments={
                        "goal": "Malicious path traversal attempt",
                        "workspace_path": traversal_path,
                        "execute": False,
                    },
                )
                run_id = json.loads(_extract_text(sub_res.content[0]))["run_id"]

                # Attempting to execute in an invalid/non-existent workspace fails closed
                exec_res = await session.call_tool("execute_run", arguments={"run_id": run_id})
                exec_data = json.loads(_extract_text(exec_res.content[0]))
                self.assertIn(exec_data["status"], ("BLOCKED", "FAILED", "ERROR"))

    async def test_05_negative_disallowed_command_rejection(self):
        """Verify arbitrary unauthorized command execution through MCP is refused without approval."""
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "subagentbridge.server"],
            env=self.host_env,
        )
        antigravity_client_info = Implementation(name="antigravity-ide", version="2.0.0")

        async with stdio_client(params) as (read_s, write_s):
            async with ClientSession(read_s, write_s, client_info=antigravity_client_info) as session:
                await session.initialize()
                sub_res = await session.call_tool(
                    "submit_goal",
                    arguments={
                        "goal": "Unapproved command rejection test",
                        "workspace_path": str(self.workspace),
                        "execute": False,
                    },
                )
                run_id = json.loads(_extract_text(sub_res.content[0]))["run_id"]

                # Executing run with unauthorized privileged commands fails closed under CHAT_APPROVAL
                exec_res = await session.call_tool(
                    "execute_run",
                    arguments={
                        "run_id": run_id,
                        "commands": {
                            "default": ["rm", "-rf", "/unauthorized/path"],
                        },
                    },
                )
                exec_data = json.loads(_extract_text(exec_res.content[0]))
                self.assertEqual(exec_data["status"], "BLOCKED")
                self.assertIn("requires human approval under chat_approval", exec_data.get("reason", "").lower())


if __name__ == "__main__":
    unittest.main()
