"""Fail-closed adversarial tests for bootstrap verification helper.

The original helper fails two tests because it only checks cwd, not checkout root.
"""
from __future__ import annotations
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

TOOL = pathlib.Path(__file__).resolve().parents[1] / "candidate" / "bve_tool.py"


class CheckoutBoundaryTests(unittest.TestCase):
    def _invoke(self, *, cwd: pathlib.Path, log_dir: pathlib.Path, checkout_root=None):
        cmd = [sys.executable, str(TOOL), "run", "--cwd", str(cwd), "--log-dir", str(log_dir), "--label", "negative"]
        if checkout_root is not None:
            cmd += ["--checkout-root", str(checkout_root)]
        cmd += ["--", sys.executable, "-c", "print('ok')"]
        return subprocess.run(cmd, capture_output=True, text=True)

    def test_explicit_checkout_root_blocks_log_in_sibling_directory(self):
        with tempfile.TemporaryDirectory() as td:
            checkout = pathlib.Path(td) / "checkout"
            (checkout / "src").mkdir(parents=True)
            r = self._invoke(cwd=checkout / "src", log_dir=checkout / "logs", checkout_root=checkout)
            self.assertEqual(r.returncode, 125, r.stdout + r.stderr)
            self.assertFalse((checkout / "logs").exists())

    def test_autodetected_git_root_blocks_log_in_sibling_directory(self):
        with tempfile.TemporaryDirectory() as td:
            checkout = pathlib.Path(td) / "checkout"
            checkout.mkdir()
            init = subprocess.run(["git", "init", "-q", str(checkout)], capture_output=True, text=True)
            if init.returncode != 0:
                self.skipTest("git not available")
            (checkout / "src").mkdir()
            r = self._invoke(cwd=checkout / "src", log_dir=checkout / "logs")
            self.assertEqual(r.returncode, 125, r.stdout + r.stderr)
            self.assertFalse((checkout / "logs").exists())

    def test_outside_git_checkout_is_allowed_with_complete_boundary_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            checkout = pathlib.Path(td) / "checkout"
            checkout.mkdir()
            init = subprocess.run(["git", "init", "-q", str(checkout)], capture_output=True, text=True)
            if init.returncode != 0:
                self.skipTest("git not available")
            (checkout / "src").mkdir()
            logs = pathlib.Path(td) / "logs"
            r = self._invoke(cwd=checkout / "src", log_dir=logs)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            record = json.loads((logs / "records.jsonl").read_text().splitlines()[-1])
            self.assertEqual(pathlib.Path(record["checkout_root"]).resolve(), checkout.resolve())
            self.assertTrue(record["log_outside_checkout"])
            self.assertEqual(record["boundary_source"], "git")

    def test_git_status_failure_is_unknown_not_clean(self):
        with tempfile.TemporaryDirectory() as td:
            checkout = pathlib.Path(td) / "non_git_checkout"
            checkout.mkdir()
            logs = pathlib.Path(td) / "logs"
            r = self._invoke(cwd=checkout, log_dir=logs, checkout_root=checkout)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            record = json.loads((logs / "records.jsonl").read_text().splitlines()[-1])
            self.assertIsNone(record["git_dirty"])
            self.assertFalse(record["git_status_known"])
            self.assertEqual(record["boundary_source"], "explicit")

    def test_explicit_checkout_root_must_enclose_working_directory(self):
        with tempfile.TemporaryDirectory() as td:
            checkout = pathlib.Path(td) / "checkout"
            checkout.mkdir()
            unrelated = pathlib.Path(td) / "unrelated"
            unrelated.mkdir()
            r = self._invoke(cwd=unrelated, log_dir=pathlib.Path(td) / "logs", checkout_root=checkout)
            self.assertEqual(r.returncode, 125, r.stdout + r.stderr)

    def test_relative_executable_resolution_from_cwd(self):
        with tempfile.TemporaryDirectory() as td:
            checkout = pathlib.Path(td) / "checkout"
            checkout.mkdir()
            logs = pathlib.Path(td) / "logs"
            script_name = "test_run.bat" if sys.platform == "win32" else "test_run.sh"
            script_file = checkout / script_name
            if sys.platform == "win32":
                script_file.write_text("@echo off\necho RELATIVE_OK\n", encoding="utf-8")
            else:
                script_file.write_text("#!/bin/sh\necho RELATIVE_OK\n", encoding="utf-8")
                script_file.chmod(0o755)
            cmd = [sys.executable, str(TOOL), "run", "--cwd", str(checkout), "--log-dir", str(logs), "--label", "rel", "--", f"./{script_name}"]
            r = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("RELATIVE_OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
