"""Git worktree manager for per-worker workspace isolation.

Implements automated creation, tracking, and cleanup of isolated Git worktrees
and branch mappings for worker sessions.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from subagentbridge.domain.orca_contracts import WorktreeAssignment
from subagentbridge.storage.orca_store import OrcaStore


class GitWorktreeManager:
    """Manages isolated Git worktrees and branches bound to worker sessions."""

    def __init__(
        self,
        repo_root: str | Path,
        store: OrcaStore,
        worktrees_dir: str | Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.store = store
        self.worktrees_dir = (
            Path(worktrees_dir).resolve()
            if worktrees_dir
            else self.repo_root / ".worktrees"
        )
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)

    def create_worktree(
        self,
        worker_id: str,
        team_id: str,
        branch_name: str,
        base_ref: str = "HEAD",
    ) -> WorktreeAssignment:
        """Creates an isolated git worktree and branch for the worker session."""
        sanitized_worker = "".join(c if c.isalnum() or c in "-_" else "_" for c in worker_id)
        target_path = self.worktrees_dir / f"w-{sanitized_worker}"

        # If a worktree already exists at this directory, clean it first
        if target_path.exists():
            try:
                subprocess.run(
                    ["git", "-C", str(self.repo_root), "worktree", "remove", "--force", str(target_path)],
                    check=False,
                    capture_output=True,
                )
            except Exception:
                shutil.rmtree(target_path, ignore_errors=True)

        cmd = [
            "git",
            "-C",
            str(self.repo_root),
            "worktree",
            "add",
            "-b",
            branch_name,
            str(target_path),
            base_ref,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            # If branch already exists, add without -b
            if "already exists" in res.stderr:
                cmd_existing = [
                    "git",
                    "-C",
                    str(self.repo_root),
                    "worktree",
                    "add",
                    str(target_path),
                    branch_name,
                ]
                res2 = subprocess.run(cmd_existing, capture_output=True, text=True)
                if res2.returncode != 0:
                    raise RuntimeError(f"failed to create git worktree: {res2.stderr.strip()}")
            else:
                raise RuntimeError(f"failed to create git worktree: {res.stderr.strip()}")

        assignment = WorktreeAssignment(
            worker_id=worker_id,
            team_id=team_id,
            worktree_path=str(target_path),
            branch_name=branch_name,
            created_at=time.time(),
        )
        self.store.save_worktree(assignment)
        return assignment

    def cleanup_worktree(self, worker_id: str, delete_branch: bool = False) -> bool:
        """Removes an active git worktree and optionally deletes the branch."""
        assignment = self.store.load_worktree(worker_id)
        if not assignment:
            return False

        target_path = Path(assignment.worktree_path)
        if target_path.exists():
            subprocess.run(
                ["git", "-C", str(self.repo_root), "worktree", "remove", "--force", str(target_path)],
                check=False,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(self.repo_root), "worktree", "prune"],
                check=False,
                capture_output=True,
            )
            if target_path.exists():
                shutil.rmtree(target_path, ignore_errors=True)

        if delete_branch and assignment.branch_name:
            subprocess.run(
                ["git", "-C", str(self.repo_root), "branch", "-D", assignment.branch_name],
                check=False,
                capture_output=True,
            )

        self.store.delete_worktree(worker_id)
        return True

    def get_assignment(self, worker_id: str) -> WorktreeAssignment | None:
        return self.store.load_worktree(worker_id)
