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

    mode: str = "inherited"  # 'inherited', 'dedicated_user', or 'windows_job_restricted'
    uid: int | None = None
    gid: int | None = None

    def __post_init__(self) -> None:
        if self.mode not in ("inherited", "dedicated_user", "windows_job_restricted"):
            raise ValueError(f"Unsupported isolation mode: {self.mode!r}")
        if self.mode in ("inherited", "windows_job_restricted") and (self.uid is not None or self.gid is not None):
            raise ValueError("UID/GID cannot be set when isolation mode is not dedicated_user")
        if self.mode == "dedicated_user" and (
            isinstance(self.uid, bool) or not isinstance(self.uid, int) or self.uid <= 0
            or isinstance(self.gid, bool) or not isinstance(self.gid, int) or self.gid <= 0
        ):
            raise ValueError("Dedicated-user isolation requires explicit positive non-root UID/GID")


def assign_windows_job_restrictions(process_handle: int) -> int:
    """Create a Windows Job Object with UI restrictions and assign process handle."""
    if sys.platform != "win32":
        raise RuntimeError("Windows Job Object is only available on win32")
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32

    class JOBOBJECT_BASIC_UI_RESTRICTIONS(ctypes.Structure):
        _fields_ = [("UIRestrictionsClass", wintypes.DWORD)]

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError("CreateJobObjectW failed")

    # Limit UI handles, clipboard read/write, global atoms, desktop, exit windows
    ui_flags = 0x00000001 | 0x00000002 | 0x00000004 | 0x00000020 | 0x00000040 | 0x00000080
    ui_limits = JOBOBJECT_BASIC_UI_RESTRICTIONS(ui_flags)
    res = kernel32.SetInformationJobObject(
        job,
        4,  # JobObjectBasicUIRestrictions
        ctypes.byref(ui_limits),
        ctypes.sizeof(ui_limits),
    )
    if not res:
        kernel32.CloseHandle(job)
        raise OSError("SetInformationJobObject for JobObjectBasicUIRestrictions failed")

    assign_res = kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(process_handle))
    if not assign_res:
        kernel32.CloseHandle(job)
        raise OSError("AssignProcessToJobObject failed")

    return int(job)


def _verify_trusted_code_path(code_root: Path, worker_uid: int, worker_gid: int) -> None:
    """A worker may read supervisor code but must not be able to rewrite it."""
    root = code_root.resolve(strict=True)
    # Parent writable components are checked as well: do not allow the worker
    # to swap a parent directory to replace the code module search path.
    # Directories alone are not enough: a writable module inside a protected
    # directory can replace trusted code; a worker-owned read-only file can
    # be chmod'd to writable without changing the directory permissions.
    package_root = root / "subagentbridge"
    if not package_root.is_dir() or package_root.is_symlink():
        raise PermissionError("Trusted Simpul package directory is missing or a symlink")
    candidates = [root, *root.parents, package_root, *package_root.rglob("*"), *root.glob("*.py")]
    for part in candidates:
        if part.is_symlink():
            raise PermissionError(f"Trusted runtime contains a symlink: {part}")
        meta = part.lstat()
        mode = meta.st_mode
        worker_owned = meta.st_uid == worker_uid
        group_write = meta.st_gid == worker_gid and bool(mode & stat.S_IWGRP)
        world_write = bool(mode & stat.S_IWOTH)
        # A sticky world-writable parent (such as /tmp) does not allow a
        # different UID to unlink supervisor-owned child entries.
        sticky_protected = part in root.parents and bool(mode & stat.S_ISVTX) and not worker_owned
        if worker_owned or group_write or (world_write and not sticky_protected):
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

    if policy.mode == "inherited":
        return env, {}

    if policy.mode == "windows_job_restricted":
        if sys.platform != "win32":
            raise RuntimeError("WINDOWS_JOB_RESTRICTED_UNAVAILABLE: Windows Job Object is only available on win32")
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
    }
    for key in ("LANG", "LC_ALL", "LC_CTYPE"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env, {"user": policy.uid, "group": policy.gid, "extra_groups": []}
