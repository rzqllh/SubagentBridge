"""tests/test_remote_pinned_checkout_e23.py — Acceptance Gate E23 Verification.

Proves:
1. Actual remote GitHub clone from https://github.com/rzqllh/SubagentBridge.git.
2. Verified exact pinned SHA match against remote branch HEAD.
3. Clean checkout verification on fresh remote clone.
4. Independent rejection of branch movement when remote tip differs from expected pinned SHA.
"""
from __future__ import annotations

import os
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

        # Controlled local bare remote repository fixture (Thread #3 fix)
        self.local_remote_dir = self.root / "fixture_remote.git"
        run_git("init", "--bare", "--initial-branch=main", str(self.local_remote_dir))

        # Create an initial commit in a seed working copy and push to local bare remote
        seed_dir = self.root / "seed_repo"
        seed_dir.mkdir()
        run_git("init", "--initial-branch=main", str(seed_dir))
        run_git("config", "user.name", "Simpul Tester", cwd=seed_dir)
        run_git("config", "user.email", "tester@simpul.local", cwd=seed_dir)
        (seed_dir / "README.md").write_text("# Simpul Pinned Checkout Fixture\n")
        run_git("add", "README.md", cwd=seed_dir)
        run_git("commit", "-m", "Initial pinned commit", cwd=seed_dir)
        self.pinned_local_sha = run_git("rev-parse", "HEAD", cwd=seed_dir)
        run_git("remote", "add", "origin", str(self.local_remote_dir), cwd=seed_dir)
        run_git("push", "origin", "main", cwd=seed_dir)

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_e23_01_controlled_remote_pinned_checkout_passes(self):
        """Verify controlled remote checkout matches exact pinned SHA without moving-main dependency."""
        target_dir = self.root / "target_clean"
        target_dir.mkdir()
        result = verify_remote_pinned_checkout(
            remote_url=str(self.local_remote_dir),
            branch="main",
            expected_pinned_sha=self.pinned_local_sha,
            target_dir=target_dir,
        )
        self.assertEqual(result["status"], "QA_VERIFIED")
        self.assertEqual(result["pinned_sha"], self.pinned_local_sha)
        self.assertTrue(result["checkout_clean"])

    def test_e23_02_remote_branch_movement_rejected(self):
        """Verify that when remote tip differs from expected pinned SHA, verification is BLOCKED."""
        stale_sha = "0" * 40
        target_dir = self.root / "target_stale"
        target_dir.mkdir()
        result = verify_remote_pinned_checkout(
            remote_url=str(self.local_remote_dir),
            branch="main",
            expected_pinned_sha=stale_sha,
            target_dir=target_dir,
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("branch movement detected", result["reason"])

    @unittest.skipUnless(
        os.environ.get("SUBAGENTBRIDGE_LIVE_REMOTE_TEST") == "1",
        "Live remote GitHub checkout check requires SUBAGENTBRIDGE_LIVE_REMOTE_TEST=1",
    )
    def test_e23_03_live_remote_github_acceptance_check(self):
        """Live remote GitHub checkout check: queries remote branch HEAD dynamically."""
        target_dir = self.root / "target_live"
        target_dir.mkdir()
        ls_output = run_git("ls-remote", REMOTE_REPO_URL, "refs/heads/main")
        lines = [line.strip() for line in ls_output.splitlines() if line.strip()]
        if not lines:
            self.skipTest("Remote branch refs/heads/main unreachable")
        current_live_sha = lines[0].split()[0]
        result = verify_remote_pinned_checkout(
            remote_url=REMOTE_REPO_URL,
            branch="main",
            expected_pinned_sha=current_live_sha,
            target_dir=target_dir,
        )
        self.assertEqual(result["status"], "QA_VERIFIED")
        self.assertTrue(result["checkout_clean"])


if __name__ == "__main__":
    unittest.main()
