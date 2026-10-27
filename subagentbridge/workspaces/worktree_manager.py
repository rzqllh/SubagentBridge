"""Git worktree manager for per-worker workspace isolation.

Implements safe creation, tracking, validation, and verified cleanup of isolated
Git worktrees and branch mappings for worker sessions.
Enforces strict path containment, no forceful routine removals, pre-cleanup dirty
checks, ownership provenance, concurrency locking, and fail-closed safety.
"""
from __future__ import annotations

import re
import subprocess
import threading
import time
from pathlib import Path

from subagentbridge.domain.team_contracts import WorktreeAssignment
from subagentbridge.storage.team_store import TeamStore


class GitWorktreeManager:
    """Manages isolated Git worktrees and branches bound to worker sessions."""

    def __init__(
        self,
        repo_root: str | Path,
        store: TeamStore,
        worktrees_dir: str | Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        if not self.repo_root.is_dir() or not (self.repo_root / ".git").exists():
            raise ValueError(f"repo_root {self.repo_root} is not a valid git repository")

        self.store = store
        self.worktrees_dir = (
            Path(worktrees_dir).resolve()
            if worktrees_dir
            else (self.repo_root / ".worktrees").resolve()
        )
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _validate_worker_id(self, worker_id: str) -> None:
        if not worker_id or not re.fullmatch(r"[A-Za-z0-9_-]+", worker_id):
            raise ValueError(
                f"Invalid worker_id {worker_id!r}: must contain only alphanumeric characters, dashes, and underscores"
            )

    def _resolve_and_validate_path(self, worker_id: str) -> Path:
        self._validate_worker_id(worker_id)
        target = (self.worktrees_dir / f"w-{worker_id}").resolve()
        try:
            target.relative_to(self.worktrees_dir)
        except ValueError:
            raise ValueError(f"Path traversal detected: {target} is outside {self.worktrees_dir}")

        if target.is_symlink():
            raise ValueError(f"Target path {target} is a symlink or junction, refusing to use")

        return target

    def create_worktree(
        self,
        worker_id: str,
        team_id: str,
        branch_name: str,
        base_ref: str = "HEAD",
    ) -> WorktreeAssignment:
        """Creates an isolated git worktree and branch for the worker session.

        Fails closed if the target directory already exists, has uncommitted changes,
        or belongs to another worker. Never forcefully deletes or wipes existing directories.
        """
        with self._lock:
            target_path = self._resolve_and_validate_path(worker_id)

            # Prevent overwriting existing paths or worktrees
            if target_path.exists():
                raise FileExistsError(
                    f"Target worktree path {target_path} already exists. Automatic removal is forbidden."
                )

            # Verify no active assignment in store for this worker
            existing = self.store.load_worktree(worker_id)
            if existing is not None:
                raise RuntimeError(
                    f"Worker {worker_id!r} already has active worktree assignment at {existing.worktree_path}"
                )

            # Validate branch name
            if not branch_name or not re.fullmatch(r"[A-Za-z0-9/_.-]+", branch_name):
                raise ValueError(f"Invalid branch_name: {branch_name!r}")

            # Check if branch already exists in repo to prevent conflicts
            chk_branch = subprocess.run(
                ["git", "-C", str(self.repo_root), "rev-parse", "--verify", f"refs/heads/{branch_name}"],
                capture_output=True,
                text=True,
            )
            if chk_branch.returncode == 0:
                raise RuntimeError(
                    f"Branch {branch_name!r} already exists in repository; ambiguous overwrite rejected"
                )

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

    def cleanup_worktree(
        self,
        worker_id: str,
        delete_branch: bool = False,
        force: bool = False,
    ) -> bool:
        """Removes an active git worktree safely and optionally deletes the branch.

        Refuses cleanup if dirty tracked files, untracked files, ignored user files, or locks
        are detected. Recursive rmtree, forceful deletions, and routine worktree prune are strictly forbidden.
        Fails closed on any git status/list inspection error.
        Preserves store ownership records if any cleanup step fails.
        """
        if force:
            raise ValueError(
                "force=True is forbidden: destructive or forceful worktree cleanup is disabled by data safety policy"
            )

        with self._lock:
            assignment = self.store.load_worktree(worker_id)
            if not assignment:
                return False

            raw_target = Path(assignment.worktree_path)
            if raw_target.is_symlink():
                raise ValueError(f"Worktree path {raw_target} is a symlink or junction, refusing cleanup")

            target_path = raw_target.resolve()
            try:
                target_path.relative_to(self.worktrees_dir)
            except ValueError:
                raise ValueError(
                    f"Path traversal detected: {target_path} is outside managed {self.worktrees_dir}"
                )

            if target_path.is_symlink():
                raise ValueError(f"Worktree path {target_path} is a symlink, refusing cleanup")

            if target_path.exists():
                # Fail-closed check: verify actual git worktree identity from git metadata
                wt_list = subprocess.run(
                    ["git", "-C", str(self.repo_root), "worktree", "list", "--porcelain"],
                    capture_output=True,
                    text=True,
                )
                if wt_list.returncode != 0:
                    raise RuntimeError(
                        f"git worktree list failed: {wt_list.stderr.strip()}; fail-closed"
                    )

                norm_target = str(target_path).replace("\\", "/").lower()
                entries = wt_list.stdout.strip().split("\n\n")
                matched_entry = None
                for entry in entries:
                    lines = entry.splitlines()
                    for line in lines:
                        if line.startswith("worktree ") and line.split(" ", 1)[1].strip().replace("\\", "/").lower() == norm_target:
                            matched_entry = entry
                            break
                    if matched_entry:
                        break

                if not matched_entry:
                    raise RuntimeError(
                        f"Target path {target_path} is not recognized by git as an active worktree; ambiguous cleanup rejected"
                    )

                # Verify worktree branch identity matches assigned branch
                if assignment.branch_name:
                    expected_branch_ref = f"refs/heads/{assignment.branch_name}"
                    branch_matched = any(
                        line.strip() == f"branch {expected_branch_ref}"
                        for line in matched_entry.splitlines()
                    )
                    if not branch_matched:
                        raise RuntimeError(
                            f"Worktree branch mismatch: expected {expected_branch_ref!r} in git worktree list; cleanup rejected"
                        )

                if "locked" in matched_entry:
                    raise RuntimeError(f"Worktree at {target_path} is locked; cleanup rejected")

                # Check for uncommitted, untracked, and ignored files (fail-closed)
                status_res = subprocess.run(
                    ["git", "-C", str(target_path), "status", "--porcelain", "-uall", "--ignored=matching"],
                    capture_output=True,
                    text=True,
                )
                if status_res.returncode != 0:
                    raise RuntimeError(
                        f"git status inspection failed on {target_path}: {status_res.stderr.strip()}; fail-closed"
                    )

                if status_res.stdout.strip():
                    raise RuntimeError(
                        f"Cannot cleanup dirty worktree at {target_path}: uncommitted changes, untracked files, or user modifications present: {status_res.stdout.strip()[:200]}"
                    )

                # Remove worktree safely via git worktree remove (no rmtree fallback)
                cmd = ["git", "-C", str(self.repo_root), "worktree", "remove", str(target_path)]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode != 0:
                    raise RuntimeError(f"git worktree remove failed: {res.stderr.strip()}")

                if target_path.exists():
                    raise RuntimeError(
                        f"Worktree path {target_path} still exists after git worktree remove; destructive rmtree forbidden"
                    )

            if delete_branch and assignment.branch_name:
                # Safe branch deletion only (-d, never forceful -D)
                cmd_b = ["git", "-C", str(self.repo_root), "branch", "-d", assignment.branch_name]
                res_b = subprocess.run(cmd_b, capture_output=True, text=True)
                if res_b.returncode != 0:
                    raise RuntimeError(f"Safe git branch delete failed (unmerged?): {res_b.stderr.strip()}")

            # Delete ownership record ONLY after all git operations succeed
            self.store.delete_worktree(worker_id)
            return True

    def get_assignment(self, worker_id: str) -> WorktreeAssignment | None:
        return self.store.load_worktree(worker_id)
