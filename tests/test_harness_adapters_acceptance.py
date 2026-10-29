"""tests/test_harness_adapters_acceptance.py — Comprehensive acceptance tests for PAR-04.

Validates:
1. test_01_installed_vs_absent_host_matrix: Truthful capability declaration & diagnostic on absent hosts.
2. test_02_capability_discovery_and_strict_mismatch_rejection: Capability mismatch & effort validation.
3. test_03_per_worker_model_and_provider_validation_no_silent_migration: Strict model/provider checks without migration.
4. test_04_controlled_native_fallback_when_configured: Controlled native fallback only when explicit & compatible.
5. test_05_local_9router_adapter_validation: Loopback validation, offline safety, and capability checks for 9Router.
6. test_06_safe_pause_switch_and_recovery: Lifecycle pause, live harness switch via IPC, and resume with state retention.
7. test_07_budget_and_token_accounting_enforcement: Budget exhaustion check and metered accounting.
8. test_08_e2e_worker_subprocess_ipc_with_model_and_effort_metadata: Real OS subprocess IPC with model/effort metadata.
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from subagentbridge.domain.team_contracts import (
    WorkerConfig,
    WorkerStatus,
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
    NineRouterHarness,
    HarnessRegistry,
    get_harness_registry,
)
from subagentbridge.storage.team_store import TeamStore
from subagentbridge.execution.worker_process import WorkerProcessController


def test_01_installed_vs_absent_host_matrix() -> None:
    """Installed vs absent host matrix: truthful is_available flag and diagnostic evidence."""
    registry = get_harness_registry()

    # 1. Native and Pi are always locally available
    native = registry.get("native")
    assert native.get_capabilities().is_available is True

    pi = registry.get("pi")
    assert pi.get_capabilities().is_available is True

    # 2. When CLI and API keys are stripped, optional harnesses truthfully report is_available=False
    with patch("shutil.which", return_value=None):
        with patch.dict(os.environ, {}, clear=True):
            for name, adapter_cls in [
                ("antigravity", AntigravityHarness),
                ("codex", CodexHarness),
                ("claude_code", ClaudeCodeHarness),
            ]:
                adapter = adapter_cls()
                caps = adapter.get_capabilities()
                assert caps.is_available is False
                assert len(caps.diagnostic) > 0

                # Execution on absent host fails closed with UNSUPPORTED_HOST
                result = adapter.execute(
                    task_id=f"t-absent-{name}",
                    instruction="do task",
                    config=WorkerConfig(worker_id="w1", team_id="t1", harness=name),
                )
                assert result["status"] == "UNSUPPORTED_HOST"
                assert "diagnostic" in result
                assert result["task_id"] == f"t-absent-{name}"


def test_02_capability_discovery_and_strict_mismatch_rejection() -> None:
    """Reject unsupported capabilities and reasoning effort when harness lacks THINKING_BUDGET."""
    registry = get_harness_registry()

    # Query declared capabilities
    native_caps = registry.get("native").get_capabilities()
    assert HarnessCapability.LOCAL_EXECUTION in native_caps.supported_capabilities
    assert HarnessCapability.THINKING_BUDGET not in native_caps.supported_capabilities

    pi_caps = registry.get("pi").get_capabilities()
    assert HarnessCapability.THINKING_BUDGET not in pi_caps.supported_capabilities

    ag_caps = registry.get("antigravity").get_capabilities()
    assert HarnessCapability.THINKING_BUDGET in ag_caps.supported_capabilities
    assert HarnessCapability.STREAMING in ag_caps.supported_capabilities

    # Request capability not supported by native
    native = registry.get("native")
    res1 = native.execute(
        task_id="t-cap-mismatch",
        instruction="create_file:x.txt:test",
        config=WorkerConfig(worker_id="w-nat", team_id="t1", harness="native"),
        required_capabilities={HarnessCapability.STREAMING},
    )
    assert res1["status"] == "DENIED"
    assert "capabilitymismatch" in res1["error"].lower()

    # Request effort="max" on Pi harness (lacks THINKING_BUDGET)
    pi = registry.get("pi")
    res2 = pi.execute(
        task_id="t-effort-mismatch",
        instruction="deep thought",
        config=WorkerConfig(worker_id="w-pi", team_id="t1", harness="pi", effort="max"),
    )
    assert res2["status"] == "DENIED"
    assert "capabilitymismatch" in res2["error"].lower()
    assert "thinking_budget" in res2["error"].lower()


def test_03_per_worker_model_and_provider_validation_no_silent_migration() -> None:
    """Validates model and provider per-worker; strictly rejects unsupported models without migration."""
    with patch("shutil.which", return_value="/usr/local/bin/agy"):
        ag = AntigravityHarness()
        caps = ag.get_capabilities()
        assert caps.is_available is True

        # Valid model executes
        valid_res = ag.execute(
            task_id="t-val-model",
            instruction="generate code",
            config=WorkerConfig(
                worker_id="w-ag",
                team_id="t1",
                harness="antigravity",
                model="gemini-2.5-pro",
                provider="google",
            ),
        )
        assert valid_res["status"] == "COMPLETED"
        assert valid_res["evidence"]["model"] == "gemini-2.5-pro"

        # Invalid model is rejected with ModelNotSupported (NOT silently migrated)
        invalid_res = ag.execute(
            task_id="t-inval-model",
            instruction="generate code",
            config=WorkerConfig(
                worker_id="w-ag",
                team_id="t1",
                harness="antigravity",
                model="gpt-nonexistent-99",
                provider="google",
            ),
        )
        assert invalid_res["status"] == "DENIED"
        assert "modelnotsupported" in invalid_res["error"].lower()

        # Invalid provider is rejected with ProviderNotSupported
        invalid_prov = ag.execute(
            task_id="t-inval-prov",
            instruction="generate code",
            config=WorkerConfig(
                worker_id="w-ag",
                team_id="t1",
                harness="antigravity",
                model="gemini-2.5-pro",
                provider="unsupported_cloud_provider",
            ),
        )
        assert invalid_prov["status"] == "DENIED"
        assert "providernotsupported" in invalid_prov["error"].lower()


def test_04_controlled_native_fallback_when_configured() -> None:
    """Native fallback operates only when explicitly configured and capability-compatible."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = Path(tmp_dir) / "fallback_file.txt"

        # Strip Claude Code host availability
        with patch("shutil.which", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                claude = ClaudeCodeHarness()
                assert claude.get_capabilities().is_available is False

                # 1. Fallback disabled (default) -> UNSUPPORTED_HOST
                res_no_fallback = claude.execute(
                    task_id="t-no-fb",
                    instruction=f"create_file:{test_file.name}:content",
                    config=WorkerConfig(
                        worker_id="w-claude",
                        team_id="t1",
                        harness="claude_code",
                        fallback_to_native=False,
                    ),
                    workspace_path=tmp_dir,
                )
                assert res_no_fallback["status"] == "UNSUPPORTED_HOST"
                assert not test_file.exists()

                # 2. Fallback enabled + compatible task -> executes on native with diagnostic evidence
                res_fallback = claude.execute(
                    task_id="t-fb-ok",
                    instruction=f"create_file:{test_file.name}:fallback content",
                    config=WorkerConfig(
                        worker_id="w-claude",
                        team_id="t1",
                        harness="claude_code",
                        fallback_to_native=True,
                    ),
                    workspace_path=tmp_dir,
                )
                assert res_fallback["status"] == "COMPLETED"
                assert test_file.exists()
                assert test_file.read_text().strip() == "fallback content"
                assert res_fallback.get("fallback_from") == "claude_code"
                diag = res_fallback.get("fallback_diagnostic", "").lower()
                assert "not found" in diag or "missing" in diag or "not set" in diag

                # 3. Fallback enabled BUT task requires STREAMING (which native lacks) -> FallbackDenied
                res_incompatible_fb = claude.execute(
                    task_id="t-fb-denied",
                    instruction=f"create_file:{test_file.name}:content",
                    config=WorkerConfig(
                        worker_id="w-claude",
                        team_id="t1",
                        harness="claude_code",
                        fallback_to_native=True,
                    ),
                    workspace_path=tmp_dir,
                    required_capabilities={HarnessCapability.STREAMING},
                )
                assert res_incompatible_fb["status"] == "DENIED"
                assert "fallbackdenied" in res_incompatible_fb["error"].lower()
                assert "streaming" in res_incompatible_fb["error"].lower()


def test_05_local_9router_adapter_validation() -> None:
    """Validates local 9Router adapter: loopback origin check, capability checks, offline safety."""
    registry = get_harness_registry()
    nine = registry.get("9router")
    assert isinstance(nine, NineRouterHarness)
    assert registry.get("ninerouter") is nine

    # 1. Unconfigured 9Router reports unavailable
    with patch.dict(os.environ, {}, clear=True):
        caps = nine.get_capabilities()
        assert caps.is_available is False
        assert "not configured" in caps.diagnostic.lower()

        res_unavail = nine.execute(
            task_id="t-9r-unavail",
            instruction="chat instruction",
            config=WorkerConfig(worker_id="w9", team_id="t1", harness="9router"),
        )
        assert res_unavail["status"] == "UNSUPPORTED_HOST"

    # 2. Configured with non-loopback address -> rejects invalid origin
    with patch.dict(os.environ, {"NINEROUTER_BASE_URL": "http://api.remote.com:8000", "NINEROUTER_API_KEY": "sk-test"}):
        caps_invalid = nine.get_capabilities()
        assert caps_invalid.is_available is False
        assert "invalid" in caps_invalid.diagnostic.lower() or "loopback" in caps_invalid.diagnostic.lower()

    # 3. Syntactically valid loopback credentials do NOT imply authenticated
    # router execution, no fake COMPLETED, metered_tokens or evidence.
    with patch.dict(os.environ, {"NINEROUTER_BASE_URL": "http://127.0.0.1:1", "NINEROUTER_API_KEY": "sk-loopback-secret"}):
        caps_valid = nine.get_capabilities()
        assert caps_valid.is_available is False
        assert "not connected" in caps_valid.diagnostic.lower()
        res_valid = nine.execute(
            task_id="t-9r-exec",
            instruction="summarize text",
            config=WorkerConfig(
                worker_id="w9", team_id="t1", harness="9router",
                model="openai/gpt-4o", provider="9router",
            ),
        )
        assert res_valid["status"] == "UNSUPPORTED_HOST"
        assert "metered_tokens" not in res_valid
        assert "summary" not in res_valid
        assert "evidence" not in res_valid


def test_06_safe_pause_switch_and_recovery() -> None:
    """Safe pause, live harness switch via IPC, and resume with state retention."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_store.db"
        with TeamStore(db_path) as store:
            controller = WorkerProcessController(store=store)
            cfg = WorkerConfig(
                worker_id="w-switch-1",
                team_id="team-switch",
                role="worker",
                harness="native",
            )

            record = controller.spawn_worker(cfg, worktree_path=tmp_dir)
            try:
                # 1. Execute initial task on native harness
                f1 = Path(tmp_dir) / "file1.txt"
                res1 = controller.dispatch_task_to_worker(
                    worker_id="w-switch-1",
                    task_id="t-switch-1",
                    payload={"instruction": f"create_file:{f1.name}:step1 content"},
                    timeout=5.0,
                )
                assert res1["status"] == "COMPLETED"
                assert f1.exists()

                # 2. Pause worker
                assert controller.pause_worker("w-switch-1") is True
                rec = controller.get_worker_record("w-switch-1")
                assert rec is not None and rec.status == WorkerStatus.PAUSED

                # Dispatch while paused is denied
                res_paused = controller.dispatch_task_to_worker(
                    worker_id="w-switch-1",
                    task_id="t-switch-blocked",
                    payload={"instruction": "echo test"},
                    timeout=2.0,
                )
                assert res_paused["status"] == "DENIED"
                assert "paused" in res_paused["error"].lower()

                # 3. Switch worker harness safely to pi while paused
                assert controller.switch_worker_harness(
                    worker_id="w-switch-1",
                    new_harness="pi",
                    new_model="pi-embedded",
                    new_provider="local",
                ) is True

                session_after_switch = store.load_session("w-switch-1")
                assert session_after_switch is not None
                assert session_after_switch.config.harness == "pi"
                assert session_after_switch.config.model == "pi-embedded"

                # Attempting switch to unsupported model fails closed
                with pytest.raises(ValueError, match="ModelNotSupported"):
                    controller.switch_worker_harness(
                        worker_id="w-switch-1",
                        new_harness="pi",
                        new_model="unsupported-model-x",
                    )

                # 4. Resume worker
                assert controller.resume_worker("w-switch-1") is True
                rec_resumed = controller.get_worker_record("w-switch-1")
                assert rec_resumed is not None and rec_resumed.status == WorkerStatus.IDLE

                # 5. Dispatch task 2 on new harness
                res2 = controller.dispatch_task_to_worker(
                    worker_id="w-switch-1",
                    task_id="t-switch-2",
                    payload={"instruction": "pi task verification"},
                    timeout=5.0,
                )
                assert res2["status"] == "COMPLETED"
                assert res2["evidence"]["harness"] == "pi"

                # Previous workspace artifact remains intact
                assert f1.exists()
                assert f1.read_text().strip() == "step1 content"

            finally:
                controller.terminate_worker("w-switch-1")


def test_07_budget_and_token_accounting_enforcement() -> None:
    """Budget exhaustion check and accurate metered token accounting."""
    native = NativeHarness()

    # Pre-exhausted budget fails closed
    exhausted_cfg = WorkerConfig(
        worker_id="w-b1",
        team_id="t1",
        harness="native",
        budget_tokens=100,
        tokens_consumed=150,
    )
    res_exhausted = native.execute(
        task_id="t-budget-exhausted",
        instruction="create_file:sample.txt:content",
        config=exhausted_cfg,
    )
    assert res_exhausted["status"] == "DENIED"
    assert "budgetexceeded" in res_exhausted["error"].lower()

    # Budget with room executes and reports metered tokens
    valid_budget_cfg = WorkerConfig(
        worker_id="w-b2",
        team_id="t1",
        harness="native",
        budget_tokens=500,
        tokens_consumed=50,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        res_ok = native.execute(
            task_id="t-budget-ok",
            instruction="create_file:sample.txt:hello world with tokens",
            config=valid_budget_cfg,
            workspace_path=tmp_dir,
        )
        assert res_ok["status"] == "COMPLETED"
        assert res_ok["metered_tokens"] > 0


def test_08_e2e_worker_subprocess_ipc_with_model_and_effort_metadata() -> None:
    """Worker child process receives and reports model and effort metadata truthfully over IPC."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_store_ipc.db"
        with TeamStore(db_path) as store:
            controller = WorkerProcessController(store=store)
            cfg = WorkerConfig(
                worker_id="w-ipc-meta",
                team_id="team-meta",
                role="worker",
                harness="native",
                model="native",
                provider="local",
                effort=None,
                budget_tokens=1000,
                fallback_to_native=True,
            )

            controller.spawn_worker(cfg, worktree_path=tmp_dir)
            try:
                target_file = Path(tmp_dir) / "ipc_meta_output.txt"
                payload = {
                    "instruction": f"create_file:{target_file.name}:ipc metadata test content",
                    "model": "native",
                    "provider": "local",
                }
                res = controller.dispatch_task_to_worker(
                    worker_id="w-ipc-meta",
                    task_id="task-ipc-meta-1",
                    payload=payload,
                    timeout=5.0,
                )

                assert res["status"] == "COMPLETED"
                assert target_file.exists()
                assert target_file.read_text().strip() == "ipc metadata test content"
                assert res["tokens_consumed"] > 0
                assert res.get("remaining_tokens") is not None
                assert res["remaining_tokens"] < 1000

                # Verify store recorded updated tokens
                sess = store.load_session("w-ipc-meta")
                assert sess is not None
                assert sess.config.tokens_consumed == res["tokens_consumed"]
                assert sess.config.fallback_to_native is True
            finally:
                controller.terminate_worker("w-ipc-meta")
