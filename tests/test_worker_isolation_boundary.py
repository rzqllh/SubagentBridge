"""Release security regression: worker environment and opt-in OS identity boundary.

These tests do NOT certify hostile-worker confinement. A dedicated OS identity
is available only on supported Linux deployments under a privileged trusted
supervisor; Windows and unprivileged Linux fail closed.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from subagentbridge.approval.trusted_authority import TrustedApprovalAuthority
from subagentbridge.domain.team_contracts import WorkerConfig
from subagentbridge.execution.worker_isolation import (
    WorkerIsolationPolicy,
    _verify_trusted_code_path,
    worker_launch_configuration,
)
from subagentbridge.execution.worker_process import WorkerProcessController
from subagentbridge.storage.team_store import TeamStore


@pytest.mark.parametrize("kwargs", [
    {"mode": "untrusted"},
    {"mode": "inherited", "uid": 1234},
    {"mode": "dedicated_user"},
    {"mode": "dedicated_user", "uid": 0, "gid": 1000},
    {"mode": "dedicated_user", "uid": 1000, "gid": 0},
    {"mode": "dedicated_user", "uid": True, "gid": 1000},
])
def test_worker_identity_policy_rejects_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        WorkerIsolationPolicy(**kwargs)


def test_worker_environment_does_not_inherit_secrets_or_attacker_pythonpath(tmp_path):
    values = {
        "OPENAI_API_KEY": "should-not-be-in-child",
        "ANTHROPIC_API_KEY": "should-not-be-in-child",
        "GEMINI_API_KEY": "should-not-be-in-child",
        "GITHUB_TOKEN": "should-not-be-in-child",
        "AWS_SECRET_ACCESS_KEY": "should-not-be-in-child",
        "SIMPUL_WORKER_SECRET": "should-not-be-in-child",
        "SSH_AUTH_SOCK": "/tmp/secret-agent",
        "PYTHONPATH": "/untrusted/shadow/path",
        "PATH": os.environ.get("PATH", ""),
    }
    with patch.dict(os.environ, values, clear=True):
        env, privileges = worker_launch_configuration(WorkerIsolationPolicy(), code_root=tmp_path)
    assert privileges == {}
    assert env["PYTHONPATH"] == str(tmp_path.resolve())
    assert env["PYTHONNOUSERSITE"] == "1"
    for secret in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
                   "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "SIMPUL_WORKER_SECRET",
                   "SSH_AUTH_SOCK"):
        assert secret not in env


def test_spawned_worker_cannot_read_inherited_credential_environment():
    with tempfile.TemporaryDirectory() as root, TeamStore(Path(root) / "env.db") as store:
        authority = TrustedApprovalAuthority()
        controller = WorkerProcessController(store, approval_authority=authority)
        cfg = WorkerConfig(worker_id="env-test", team_id="env-team",
                           role="worker", working_dir=root)
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "OPENAI_SECRET_MARKER",
            "GITHUB_TOKEN": "GH_SECRET_MARKER",
            "PYTHONPATH": "/attacker/path",
        }):
            controller.spawn_worker(cfg)
        try:
            command = [sys.executable, "-c",
                       "import os;print(os.environ.get('OPENAI_API_KEY','ABSENT'),"
                       "os.environ.get('GITHUB_TOKEN','ABSENT'))"]
            action = authority.request_command_approval(
                worker_id=cfg.worker_id, task_id="check-env",
                command=command, workspace_path=root,
            )
            authority.approve_by_human(action.action_id, auth_token=authority.broker._secret)
            result = controller.dispatch_task_to_worker(cfg.worker_id, "check-env", {
                "command": command, "approval_action_id": action.action_id,
            })
            assert result["status"] == "COMPLETED", result
            assert result["stdout"].strip() == "ABSENT ABSENT"
        finally:
            controller.terminate_all()


def test_dedicated_identity_fails_closed_without_privileged_os_support(tmp_path):
    policy = WorkerIsolationPolicy(mode="dedicated_user", uid=65432, gid=65432)
    if sys.platform.startswith("linux"):
        with patch("subagentbridge.execution.worker_isolation.os.geteuid", return_value=1000):
            with pytest.raises(PermissionError, match="supervisor"):
                worker_launch_configuration(policy, code_root=tmp_path)
    else:
        with pytest.raises(RuntimeError, match="Linux OS identity"):
            worker_launch_configuration(policy, code_root=tmp_path)


@pytest.mark.skipif(os.name != "posix", reason="Requires POSIX permission bits")
def test_dedicated_identity_rejects_worker_writable_supervisor_code(tmp_path):
    root = tmp_path / "runtime_code"
    root.mkdir()
    root.chmod(0o777)
    try:
        with pytest.raises(PermissionError, match="trusted runtime"):
            _verify_trusted_code_path(root, worker_uid=9876, worker_gid=9876)
    finally:
        root.chmod(0o755)


def test_inherited_mode_is_never_advertised_as_dedicated_identity(tmp_path):
    with TeamStore(tmp_path / "state.db") as store:
        ctrl = WorkerProcessController(store)
        assert ctrl.isolation_policy.mode == "inherited"
        assert ctrl.isolation_policy.uid is None
