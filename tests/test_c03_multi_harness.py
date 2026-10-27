"""Unit tests for Phase C03: Multi-Harness Host Adapters & Capability Checking.

Validates:
1. Harness registration and discovery (`native`, `antigravity`, `codex`, `claude_code`, `pi`).
2. Capability checking (`STREAMING`, `TOOL_CALLING`, `STRUCTURED_OUTPUT`, `THINKING_BUDGET`).
3. Model and provider resolution and validation per harness.
4. Graceful handling of unavailable / unsupported hosts (fail-closed, diagnostic evidence).
5. Native harness execution with real observable results.
6. Rejection of capability mismatches (fail-closed policy).
7. End-to-end worker process routing to harness adapters over IPC.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from subagentbridge.domain.orca_contracts import (
    WorkerConfig,
)
from subagentbridge.runners.harness_adapters import (
    HarnessCapability,
    HarnessCapabilities,
    BaseHarnessAdapter,
    NativeHarness,
    AntigravityHarness,
    CodexHarness,
    ClaudeCodeHarness,
    PiHarness,
    HarnessRegistry,
    get_harness_registry,
)
from subagentbridge.storage.orca_store import OrcaStore
from subagentbridge.execution.worker_process import WorkerProcessController


def test_c03_harness_registry_and_discovery():
    registry = HarnessRegistry()
    available = registry.list_available()
    assert "native" in available
    assert "antigravity" in available
    assert "codex" in available
    assert "claude_code" in available
    assert "pi" in available

    native = registry.get("native")
    assert isinstance(native, NativeHarness)
    assert native.name == "native"


def test_c03_harness_capability_contracts():
    registry = get_harness_registry()

    for name in ["native", "antigravity", "codex", "claude_code", "pi"]:
        adapter = registry.get(name)
        assert isinstance(adapter, BaseHarnessAdapter)
        caps = adapter.get_capabilities()
        assert isinstance(caps, HarnessCapabilities)
        assert isinstance(caps.supported_capabilities, set)
        assert isinstance(caps.supported_models, list)
        assert isinstance(caps.is_available, bool)


def test_c03_model_and_provider_selection():
    registry = get_harness_registry()

    antigravity = registry.get("antigravity")
    assert antigravity.validate_model("gemini-2.5-pro") is True
    assert antigravity.validate_model("unsupported-xyz-model") is False
    assert antigravity.validate_provider("google") is True
    assert antigravity.validate_provider("unsupported-provider") is False

    claude = registry.get("claude_code")
    assert claude.validate_model("claude-3-7-sonnet") is True
    assert claude.validate_provider("anthropic") is True


def test_c03_unsupported_host_graceful_handling():
    """Prove that an unavailable host CLI returns UNSUPPORTED_HOST with explicit diagnostic."""
    with patch("shutil.which", return_value=None):
        with patch.dict(os.environ, {}, clear=True):
            claude = ClaudeCodeHarness()
            caps = claude.get_capabilities()
            assert caps.is_available is False
            assert "not found" in caps.diagnostic.lower() or "missing" in caps.diagnostic.lower()

            # Execution attempt on unavailable host
            result = claude.execute(
                task_id="t-unavail",
                instruction="write tests",
                config=WorkerConfig(worker_id="w-u", team_id="t", harness="claude_code"),
                workspace_path="",
            )
            assert result["status"] == "UNSUPPORTED_HOST"
            assert "claude" in result["error"].lower()
            assert "diagnostic" in result


def test_c03_capability_mismatch_rejection():
    """Prove that requesting a capability not supported by the harness fails closed."""
    pi = PiHarness()
    # Pi harness does not support THINKING_BUDGET
    result = pi.execute(
        task_id="t-mismatch",
        instruction="deep reasoning task",
        config=WorkerConfig(worker_id="w-pi", team_id="t", harness="pi", effort="max"),
        workspace_path="",
        required_capabilities={HarnessCapability.THINKING_BUDGET},
    )
    assert result["status"] == "DENIED"
    assert "capabilitymismatch" in result.get("error", "").lower()


def test_c03_native_harness_real_execution():
    """Prove native harness execution performs real task execution in workspace."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = Path(tmp_dir) / "test_artifact.txt"
        native = NativeHarness()

        result = native.execute(
            task_id="t-native-1",
            instruction=f"create_file:{test_file.name}:real content generated",
            config=WorkerConfig(worker_id="w-nat", team_id="t", harness="native"),
            workspace_path=tmp_dir,
        )
        assert result["status"] == "COMPLETED"
        assert result["task_id"] == "t-native-1"
        assert test_file.exists()
        assert test_file.read_text().strip() == "real content generated"
        assert result["metered_tokens"] > 0


def test_c03_worker_process_harness_routing():
    """Prove worker process entrypoint routes instruction to harness adapter over IPC."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c03.db") as store:
            controller = WorkerProcessController(store=store)
            cfg = WorkerConfig(
                worker_id="w-harness-1",
                team_id="team-harness",
                role="worker",
                harness="native",
            )

            controller.spawn_worker(cfg, worktree_path=tmp_dir)
            try:
                target_file = Path(tmp_dir) / "harness_output.txt"
                payload = {
                    "instruction": f"create_file:{target_file.name}:hello from harness IPC",
                }
                result = controller.dispatch_task_to_worker(
                    worker_id="w-harness-1",
                    task_id="task-c03-harness",
                    payload=payload,
                    timeout=5.0,
                )

                assert result["status"] == "COMPLETED"
                assert result["task_id"] == "task-c03-harness"
                assert target_file.exists()
                assert target_file.read_text().strip() == "hello from harness IPC"
            finally:
                controller.terminate_worker("w-harness-1")
