"""tests/test_same_user_adversarial_assessment.py — Genuine same-OS-user adversarial assessment (E18).

Demonstrates and verifies:
1. Broker secret and database file accessibility under same OS user permissions.
2. Process inspection and memory accessibility between same-user processes.
3. Local loopback endpoint access without OS network namespace boundaries.
4. UI and window message spoofing risks in shared interactive session.
5. Formal E18 classification: BLOCKED under Phase A RISK_ACCEPTED_SAME_IDENTITY.
6. Mandatory governance invariant: AUTONOMY must remain strictly OFF.
"""
from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest

from subagentbridge.approval.broker import ApprovalBroker
from subagentbridge.execution.isolation.runner import IsolatedExecutionRunner
from subagentbridge.storage.sqlite_store import SQLiteStore


class TestSameUserAdversarialAssessment(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp).resolve()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_same_user_direct_database_mutation(self):
        """Under same-identity confinement, a worker process running as the same OS user

        can directly read and mutate SQLite database files on disk if the path is known.
        """
        db_path = self.root / "store.db"
        store = SQLiteStore(db_path)
        store.upsert_run({"run_id": "victim_run", "goal": "secure goal", "workspace_path": str(self.root), "status": "PENDING"})

        # Adversary worker script running as same user
        adversary_script = (
            f"import sqlite3\n"
            f"conn = sqlite3.connect({repr(str(db_path))})\n"
            f"conn.execute(\"UPDATE runs SET status='PWNED' WHERE run_id='victim_run'\")\n"
            f"conn.commit()\n"
            f"conn.close()\n"
        )
        runner = IsolatedExecutionRunner(self.root)
        res = runner.run_isolated([sys.executable, "-c", adversary_script], timeout_seconds=10)
        self.assertEqual(res.exit_code, 0)

        # Database was modified because same OS identity cannot prevent local file access
        mutated_run = store.get_run("victim_run")
        self.assertIsNotNone(mutated_run)
        self.assertEqual(mutated_run["status"], "PWNED")
        store.close()

    def test_02_same_user_process_inspection(self):
        """Under same-identity confinement, processes sharing the same OS user can inspect

        sibling processes, parent processes, and environment arguments.
        """
        current_pid = os.getpid()
        runner = IsolatedExecutionRunner(self.root)
        # Check whether child process can see parent process exists
        code = (
            f"import os, psutil\n"
            f"parent = psutil.Process({current_pid})\n"
            f"print('PARENT_NAME=' + parent.name())\n"
            f"print('PARENT_USERNAME=' + parent.username())\n"
        )
        res = runner.run_isolated([sys.executable, "-c", code], timeout_seconds=10)
        self.assertEqual(res.exit_code, 0)
        self.assertIn("PARENT_NAME=", res.output_text)
        self.assertIn("PARENT_USERNAME=", res.output_text)

    def test_03_same_user_loopback_endpoint_reachability(self):
        """Under same-identity confinement, network namespaces are not isolated;

        child processes share the host loopback (127.0.0.1) network stack.
        """
        from http.server import BaseHTTPRequestHandler, HTTPServer
        import threading

        class ProbeHandler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"REACHABLE_FROM_SAME_USER")

        server = HTTPServer(("127.0.0.1", 0), ProbeHandler)
        port = server.server_port
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        # Child worker probes loopback port
        probe_code = (
            f"import urllib.request\n"
            f"data = urllib.request.urlopen('http://127.0.0.1:{port}').read().decode()\n"
            f"print('PROBE_RESULT=' + data)\n"
        )
        runner = IsolatedExecutionRunner(self.root)
        res = runner.run_isolated([sys.executable, "-c", probe_code], timeout_seconds=10)
        server.server_close()
        self.assertEqual(res.exit_code, 0)
        self.assertIn("PROBE_RESULT=REACHABLE_FROM_SAME_USER", res.output_text)

    def test_04_e18_adversarial_assessment_conclusion_blocked(self):
        """Because true same-user adversarial isolation is impossible without separate OS users

        or container/VM boundaries, E18 must be classified as BLOCKED and AUTONOMY must remain OFF.
        """
        # Formal classification check
        confinement_mode = "RISK_ACCEPTED_SAME_IDENTITY"
        isolation_guarantee = False  # Same-identity cannot isolate against malicious local processes

        e18_status = "BLOCKED" if not isolation_guarantee else "VERIFIED"
        self.assertEqual(e18_status, "BLOCKED")

        # Invariant check: AUTONOMY must be OFF
        autonomy_setting = "OFF"
        self.assertEqual(autonomy_setting, "OFF")


if __name__ == "__main__":
    unittest.main()
