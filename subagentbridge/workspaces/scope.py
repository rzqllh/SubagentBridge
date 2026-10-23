"""PR-04a partial: conservative path checks; no worktree/process isolation claim.

These checks do NOT eliminate path-swap TOCTOU, Windows junction races,
case normalization edge cases, or imply that a child process is confined.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import os


def dispatch_folder_name(task_id: str, dispatch_id: str) -> str:
    if not task_id or not dispatch_id:
        raise ValueError('task and dispatch required')
    return 'dispatch-' + sha256((task_id + '\x00' + dispatch_id).encode('utf8')).hexdigest()[:24]


class ScopedWorkspace:
    def __init__(self, root: str | Path):
        p = Path(root).absolute()
        if not p.is_dir() or p.is_symlink() or getattr(p, 'is_junction', lambda: False)():
            raise ValueError('workspace root must exist and not be a link/junction')
        self.root = p.resolve(strict=True)

    def require_path(self, user_path: str | Path, *, must_exist: bool = False) -> Path:
        p = Path(user_path)
        if not p.is_absolute():
            p = self.root / p
        candidate = p.absolute()
        # Disallow links/junctions at every existing ancestor in the request path.
        node = candidate
        while True:
            if node.is_symlink() or getattr(node, 'is_junction', lambda: False)():
                raise PermissionError('linked path/junction is denied')
            if node == node.parent:
                break
            node = node.parent
        resolved = candidate.resolve(strict=must_exist)
        try:
            if os.path.commonpath((str(self.root), str(resolved))) != str(self.root):
                raise PermissionError('path outside bound workspace')
        except ValueError as exc:
            raise PermissionError('different drive or outside workspace') from exc
        return resolved
