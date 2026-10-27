"""Trusted host-side worker execution boundary.

No child/model-controlled payload can select a privilege drop. Isolated mode is
Linux-only and fails closed unless the supervisor can launch the subprocess as a
different, dedicated non-root uid/gid. This is identity separation, NOT a full
sandbox: it does not confine network, syscalls, or permitted workspace content.
"""
from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Deliberately omit AI tokens, cloud credentials, GitHub tokens, SSH_AUTH_SOCK,
# PYTHONPATH/PYTHONHOME, arbitrary user profile variables, and secret-bearing env.
_WORKER_ENV_KEYS = (
    "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
    "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE",
    "LANG", "LC_ALL", "LC_CTYPE", "PYTHONIOENCODING", "PYTHONUTF8",
    "VIRTUAL_ENV",
)


@dataclass(frozen=True)
class WorkerIsolationPolicy:
    """Configured by the trusted supervisor, never from task or MCP input."""

    mode: str = "inherited"  # 'inherited' or 'dedicated_user'
    uid: int | None = None
    gid: int | None = None

    def __post_init__(self) -> None:
        if self.mode not in ("inherited", "dedicated_user"):
            raise ValueError(f"Unsupported isolation mode: {self.mode!r}")
        if self.mode == "inherited" and (self.uid is not None or self.gid is not None):
            raise ValueError("UID/GID cannot be set when isolation mode is inherited")
        if self.mode == "dedicated_user" and (
            isinstance(self.uid, bool) or not isinstance(self.uid, int) or self.uid <= 0
            or isinstance(self.gid, bool) or not isinstance(self.gid, int) or self.gid <= 0
        ):
            raise ValueError("Dedicated-user isolation requires explicit positive non-root UID/GID")


def _verify_trusted_code_path(code_root: Path, worker_uid: int, worker_gid: int) -> None:
    """A worker may read supervisor code but must not be able to rewrite it."""
    root = code_root.resolve(strict=True)
    # Parent writable components are checked as well: do not allow the worker
    # to swap a parent directory to replace the code module search path.
    for part in (root, *root.parents):
        meta = part.stat()
        mode = meta.st_mode
        owned_write = meta.st_uid == worker_uid and bool(mode & stat.S_IWUSR)
        group_write = meta.st_gid == worker_gid and bool(mode & stat.S_IWGRP)
        world_write = bool(mode & stat.S_IWOTH)
        # A sticky world-writable parent (/tmp) cannot replace a directory
        # owned by somebody else; treat all other writable parents as unsafe.
        sticky_protected = bool(mode & stat.S_ISVTX) and meta.st_uid != worker_uid
        if owned_write or group_write or (world_write and not sticky_protected):
            raise PermissionError(f"Worker UID/GID can modify trusted runtime path {part}")


def worker_launch_configuration(
    policy: WorkerIsolationPolicy,
    *,
    code_root: Path,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Return a scrubbed child environment and explicit Popen privilege kwargs.

    Environment scrubbing does not prevent a same-UID worker from reading the
    parent's files. Dedicated-user mode is an *optional* independently checked
    POSIX identity boundary; no silent fallback to same-user execution.
    """
    env = {key: value for key in _WORKER_ENV_KEYS if (value := os.environ.get(key))}
    # Never accept a model/user-injected PYTHONPATH. Only trusted package path.
    env["PYTHONPATH"] = str(code_root.resolve(strict=True))
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONSAFEPATH"] = "1"
    if policy.mode == "inherited":
        return env, {}

    if not sys.platform.startswith("linux") or not hasattr(os, "geteuid"):
        raise RuntimeError("DEDICATED_USER_UNAVAILABLE: Linux OS identity separation required")
    if os.geteuid() != 0:
        raise PermissionError("DEDICATED_USER_UNAVAILABLE: supervisor must have permission to set UID/GID")
    assert policy.uid is not None and policy.gid is not None
    import pwd

    try:
        account = pwd.getpwuid(policy.uid)
    except KeyError as exc:
        raise ValueError("DEDICATED_USER_UNAVAILABLE: UID has no dedicated Linux account") from exc
    if account.pw_gid != policy.gid:
        raise ValueError("Configured GID must be the dedicated worker account primary group")
    if account.pw_dir == os.environ.get("HOME"):
        raise ValueError("Dedicated worker HOME must not equal supervisor HOME")
    _verify_trusted_code_path(code_root, policy.uid, policy.gid)
    # Do not propagate interactive terminal, home, credential, or user site path.
    env = {
        "PATH": os.defpath,
        "HOME": account.pw_dir,
        "USER": account.pw_name,
        "LOGNAME": account.pw_name,
        "PYTHONPATH": str(code_root.resolve(strict=True)),
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
        "TMPDIR": "/tmp",
    }
    for key in ("LANG", "LC_ALL", "LC_CTYPE"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env, {"user": policy.uid, "group": policy.gid, "extra_groups": []}
