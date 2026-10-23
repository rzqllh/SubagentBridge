"""tests/test_remote_pinned_checkout_e23.py — Acceptance Gate E23 Verification.

Proves:
1. Actual remote GitHub clone from https://github.com/rzqllh/SubagentBridge.git.
2. Verified exact pinned SHA match against remote branch HEAD.
3. Clean checkout verification on fresh remote clone.
4. Independent rejection of branch movement when remote tip differs from expected pinned SHA.
"""
from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest

REMOTE_REPO_URL = "https://github.com/rzqllh/SubagentBridge.git"
PINNED_MAIN_SHA = "953c0f5a34c7ae8917d8febde92354eb8ed8a4ef"


def run_git(*args: str, cwd: pathlib.Path | None = None) -> str:
    res = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed (code {res.returncode}): {res.stderr.strip()}")
    return res.stdout.strip()


def verify_remote_pinned_checkout(
    remote_url: str,
    branch: str,
    expected_pinned_sha: str,
    target_dir: pathlib.Path,
) -> dict:
    """Independent verifier: fetches remote branch ref, checks against pinned SHA,

    and rejects branch movement.
    """
    # 1. Query remote ref directly without mutating local repository
    ls_output = run_git("ls-remote", remote_url, f"refs/heads/{branch}")
    lines = [line.strip() for line in ls_output.splitlines() if line.strip()]
    if not lines:
        return {"status": "BLOCKED", "reason": f"remote branch {branch} not found at {remote_url}"}

    actual_remote_sha = lines[0].split()[0]
    if actual_remote_sha != expected_pinned_sha:
        return {
            "status": "BLOCKED",
            "reason": f"remote branch movement detected: expected pinned SHA {expected_pinned_sha}, found {actual_remote_sha}",
            "actual_remote_sha": actual_remote_sha,
            "expected_pinned_sha": expected_pinned_sha,
        }

    # 2. Perform fresh shallow clone of the verified pinned branch
    clone_dir = target_dir / "remote_checkout"
    run_git("clone", "--quiet", "--depth", "1", "--single-branch", "--branch", branch, remote_url, str(clone_dir))

    # 3. Verify checked-out HEAD in fresh clone
    head_sha = run_git("rev-parse", "HEAD", cwd=clone_dir)
    if head_sha != expected_pinned_sha:
        return {
            "status": "BLOCKED",
            "reason": f"cloned HEAD SHA {head_sha} does not match expected pinned SHA {expected_pinned_sha}",
        }

    status_out = run_git("status", "--porcelain", cwd=clone_dir)
    if status_out:
        return {
            "status": "BLOCKED",
            "reason": "fresh remote checkout is not clean",
        }

    return {
        "status": "QA_VERIFIED",
        "remote_url": remote_url,
        "branch": branch,
        "pinned_sha": expected_pinned_sha,
        "checkout_clean": True,
    }


class TestRemotePinnedCheckoutE23(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name).resolve()

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_e23_01_actual_remote_pinned_checkout_passes(self):
        """Verify real remote GitHub checkout matches exact released main SHA."""
        result = verify_remote_pinned_checkout(
            remote_url=REMOTE_REPO_URL,
            branch="main",
            expected_pinned_sha=PINNED_MAIN_SHA,
            target_dir=self.root,
        )
        self.assertEqual(result["status"], "QA_VERIFIED")
        self.assertEqual(result["pinned_sha"], PINNED_MAIN_SHA)
        self.assertTrue(result["checkout_clean"])

    def test_e23_02_remote_branch_movement_rejected(self):
        """Verify that if the remote branch moves or does not match pinned SHA, verification is BLOCKED."""
        # Simulated stale or moved pin
        stale_sha = "8d2b019000000000000000000000000000000000"
        result = verify_remote_pinned_checkout(
            remote_url=REMOTE_REPO_URL,
            branch="main",
            expected_pinned_sha=stale_sha,
            target_dir=self.root,
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("branch movement detected", result["reason"])


if __name__ == "__main__":
    unittest.main()
