"""P0 regression: deny all legacy execution until a trusted tool executor exists.

Tests cover security-denial behavior, not proof of OS isolation or an
authenticated human broker. No test modifies global MCP or process state.
"""
from __future__ import annotations

import ast
from pathlib import Path
import tempfile
import unittest

from subagentbridge.manager import AgentManager, PendingActionQueue, Session

ROOT = Path(__file__).resolve().parents[1]


class CountingRunner:
    name = "unsafe-legacy-cli"

    def __init__(self):
        self.launch_requests = 0

    def build_command(self, *args, **kwargs):
        self.launch_requests += 1
        raise AssertionError("legacy subprocess runner must never be invoked")


class P0PermissionDefaults(unittest.TestCase):
    def test_default_session_does_not_skip_permissions(self):
        from dataclasses import fields
        field = next(f for f in fields(Session) if f.name == "skip_permissions")
        self.assertIs(field.default, False)

    def test_spawn_refuses_explicit_permission_bypass(self):
        manager = AgentManager()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(PermissionError):
                manager.spawn("bypass", root, CountingRunner(), skip_permissions=True)
        self.assertNotIn("bypass", manager.sessions)

    def test_spawn_refuses_disabled_hitl(self):
        manager = AgentManager()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(PermissionError):
                manager.spawn("hitl-off", root, CountingRunner(), hitl_enabled=False)
        self.assertNotIn("hitl-off", manager.sessions)

    def test_mcp_approval_is_not_registered(self):
        tree = ast.parse((ROOT / "subagentbridge/server.py").read_text(encoding="utf-8"))
        functions = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertIn("approve_action", functions, "Preserve deprecated callable as denied API")
        def is_mcp_tool(decorator):
            return (isinstance(decorator, ast.Call) and
                    isinstance(decorator.func, ast.Attribute) and
                    decorator.func.attr == "tool" and
                    isinstance(decorator.func.value, ast.Name) and
                    decorator.func.value.id == "mcp")
        self.assertFalse(any(is_mcp_tool(d) for d in functions["approve_action"].decorator_list))
        self.assertFalse(any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "resolve"
            and any(k.arg == "approved" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords)
            for node in ast.walk(functions["approve_action"])
        ))

    def test_mcp_spawn_permission_default_is_false(self):
        tree = ast.parse((ROOT / "subagentbridge/server.py").read_text(encoding="utf-8"))
        spawn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "spawn_agent")
        defaults = {arg.arg: value for arg, value in zip(spawn.args.args[-len(spawn.args.defaults):], spawn.args.defaults)}
        self.assertIn("skip_permissions", defaults)
        self.assertIs(defaults["skip_permissions"].value, False)

    def test_queue_refuses_unauthenticated_approval(self):
        queue = PendingActionQueue()
        action = queue.enqueue("s", {"command": "dangerous"})
        with self.assertRaises(PermissionError):
            queue.resolve(action.action_id, approved=True)
        self.assertFalse(action.resolved)
        self.assertIsNone(action.approved)

    def test_denied_action_cannot_be_upgraded(self):
        queue = PendingActionQueue()
        action = queue.enqueue("s", {"command": "dangerous"})
        queue.resolve(action.action_id, approved=False, reason="denied")
        with self.assertRaises(PermissionError):
            queue.resolve(action.action_id, approved=True)
        self.assertFalse(action.approved)


class P0ExecutionLockdown(unittest.IsolatedAsyncioTestCase):
    async def test_public_send_message_rejects_before_working(self):
        runner = CountingRunner()
        manager = AgentManager()
        with tempfile.TemporaryDirectory() as root:
            manager.spawn("session", root, runner)
            with self.assertRaises(PermissionError):
                await manager.send_message("session", "run arbitrary code")
            self.assertEqual(runner.launch_requests, 0)
            self.assertEqual(manager.get_session("session").status, "blocked")

    async def test_direct_internal_run_refuses_before_build_command(self):
        runner = CountingRunner()
        manager = AgentManager()
        with tempfile.TemporaryDirectory() as root:
            session = manager.spawn("session", root, runner)
            with self.assertRaises(PermissionError):
                await manager._run_once(session, "side effect", is_retry=False)
            self.assertEqual(runner.launch_requests, 0)


if __name__ == "__main__":
    unittest.main()
