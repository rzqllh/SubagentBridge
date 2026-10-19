"""Baseline security probes for the ORIGINAL implementation, not production QA.

These intentionally failing assertions are labelled expectedFailure until the
corresponding enforcement PR has been independently verified. They document
what must not be reported as secure just because a legacy test suite is green.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from subagentbridge.manager import AgentManager, PendingActionQueue, WorkspaceBoundaryError


class ExistingBehaviorTests(unittest.TestCase):
    def test_no_registered_workspace_must_deny_writes(self):
        manager = AgentManager()
        with self.assertRaises(WorkspaceBoundaryError):
            manager.check_path_in_workspace("/tmp/outside")

    def test_outside_workspace_must_be_rejected(self):
        manager = AgentManager()
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as outside:
            class NoopRunner:
                name = "noop"

            manager.spawn("d1", first, NoopRunner())
            with self.assertRaises(WorkspaceBoundaryError):
                manager.check_path_in_workspace(str(Path(outside) / "escape.txt"))

    def test_no_approval_request_starts_resolved(self):
        q = PendingActionQueue()
        action = q.enqueue("session-x", {"command": "rm -rf /a"})
        self.assertFalse(action.resolved)
        self.assertIsNone(action.approved)


class KnownUnmetGuarantees(unittest.TestCase):
    @unittest.expectedFailure
    def test_agent_cannot_self_approve_by_calling_queue(self):
        # Legacy API accepts approved=True with no authenticated human actor.
        queue = PendingActionQueue()
        action = queue.enqueue("s", {"command": "rm -rf /a"})
        # A secure queue would reject an untrusted caller, not mark approved.
        with self.assertRaises(PermissionError):
            queue.resolve(action.action_id, approved=True)

    @unittest.expectedFailure
    def test_per_dispatch_workspace_boundaries(self):
        # Legacy manager allows ANY registered workspace, not task-scoped ones.
        manager = AgentManager()
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            class NoopRunner:
                name = "noop"

            manager.spawn("dispatch-a", a, NoopRunner())
            manager.spawn("dispatch-b", b, NoopRunner())
            # This negative assertion requires a per-dispatch API in PR-03/04b.
            with self.assertRaises(WorkspaceBoundaryError):
                manager.check_path_in_workspace(str(Path(b) / "secret.py"))


if __name__ == "__main__":
    unittest.main()
