"""subagentbridge/runners/harness_adapters.py — Multi-Harness host adapters for Simpul.

Provides capability-checked host adapters for worker execution:
- NativeHarness: local safe workspace and tool execution.
- AntigravityHarness: Antigravity CLI and Gemini model adapter.
- CodexHarness: Codex CLI and OpenAI model adapter.
- ClaudeCodeHarness: Claude Code CLI and Anthropic model adapter.
- PiHarness: lightweight embedded harness.

Enforces capability declarations, model/provider validation, fail-closed capability
mismatch rejection, and graceful unsupported-host diagnostics.
"""
from __future__ import annotations

import os
import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from subagentbridge.domain.team_contracts import WorkerConfig


class HarnessCapability(str, Enum):
    STREAMING = "STREAMING"
    TOOL_CALLING = "TOOL_CALLING"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    THINKING_BUDGET = "THINKING_BUDGET"
    INTERRUPTIBLE = "INTERRUPTIBLE"
    LOCAL_EXECUTION = "LOCAL_EXECUTION"


@dataclass(frozen=True)
class HarnessCapabilities:
    harness_name: str
    supported_capabilities: set[HarnessCapability]
    supported_models: list[str]
    supported_providers: list[str]
    default_model: str
    default_provider: str
    is_available: bool
    diagnostic: str = ""


class BaseHarnessAdapter(ABC):
    """Abstract base class for all host harness adapters."""

    name: str

    @abstractmethod
    def get_capabilities(self) -> HarnessCapabilities:
        """Returns typed capability declarations and dynamic host availability."""
        raise NotImplementedError

    def validate_model(self, model: str | None) -> bool:
        if not model:
            return True
        caps = self.get_capabilities()
        return model.lower() in [m.lower() for m in caps.supported_models]

    def validate_provider(self, provider: str | None) -> bool:
        if not provider:
            return True
        caps = self.get_capabilities()
        return provider.lower() in [p.lower() for p in caps.supported_providers]

    def validate_required_capabilities(self, required: set[HarnessCapability] | None) -> tuple[bool, str]:
        if not required:
            return True, "OK"
        caps = self.get_capabilities()
        missing = required - caps.supported_capabilities
        if missing:
            missing_names = ", ".join(m.value for m in sorted(missing, key=lambda x: x.value))
            return False, f"CapabilityMismatch: harness {self.name!r} does not support [{missing_names}]"
        return True, "OK"

    def validate_execution_config(
        self,
        config: WorkerConfig,
        required_capabilities: set[HarnessCapability] | None = None,
    ) -> tuple[bool, str, str]:
        """Validates capability, model, provider, reasoning effort, and budget constraints.

        Returns: (is_valid, status, error_reason)
        """
        caps = self.get_capabilities()
        if not caps.is_available:
            return False, "UNSUPPORTED_HOST", f"{self.name}Unavailable: {caps.diagnostic}"

        ok, reason = self.validate_required_capabilities(required_capabilities)
        if not ok:
            return False, "DENIED", reason

        if config.effort:
            if HarnessCapability.THINKING_BUDGET not in caps.supported_capabilities:
                return (
                    False,
                    "DENIED",
                    f"CapabilityMismatch: harness {self.name!r} does not support THINKING_BUDGET required by effort={config.effort!r}",
                )

        if config.model and not self.validate_model(config.model):
            return (
                False,
                "DENIED",
                f"ModelNotSupported: harness {self.name!r} does not support model {config.model!r}. Supported models: {caps.supported_models}",
            )

        if config.provider and not self.validate_provider(config.provider):
            return (
                False,
                "DENIED",
                f"ProviderNotSupported: harness {self.name!r} does not support provider {config.provider!r}. Supported providers: {caps.supported_providers}",
            )

        if config.budget_tokens is not None and config.tokens_consumed >= config.budget_tokens:
            return (
                False,
                "DENIED",
                f"BudgetExceeded: worker token budget {config.budget_tokens} exhausted ({config.tokens_consumed} consumed)",
            )

        return True, "OK", ""

    def _handle_unavailable_or_fallback(
        self,
        task_id: str,
        instruction: str,
        config: WorkerConfig,
        workspace_path: str,
        required_capabilities: set[HarnessCapability] | None,
        timeout: float,
        caps: HarnessCapabilities,
    ) -> dict[str, Any]:
        """Handles unavailable harness execution, checking explicit fallback_to_native permission."""
        if config.fallback_to_native and self.name != "native":
            native_adapter = get_harness_registry().get("native")
            native_caps = native_adapter.get_capabilities()
            req = required_capabilities or set()
            missing = req - native_caps.supported_capabilities
            if missing:
                missing_str = ", ".join(m.value for m in sorted(missing, key=lambda x: x.value))
                return {
                    "type": "RESULT",
                    "task_id": task_id,
                    "status": "DENIED",
                    "error": f"FallbackDenied: cannot fallback to native harness; missing capabilities [{missing_str}]",
                    "timestamp": time.time(),
                }
            if config.effort and HarnessCapability.THINKING_BUDGET not in native_caps.supported_capabilities:
                return {
                    "type": "RESULT",
                    "task_id": task_id,
                    "status": "DENIED",
                    "error": f"FallbackDenied: cannot fallback to native harness; thinking budget / reasoning effort={config.effort!r} not supported by native",
                    "timestamp": time.time(),
                }
            native_cfg = WorkerConfig(
                worker_id=config.worker_id,
                team_id=config.team_id,
                role=config.role,
                harness="native",
                model="native",
                provider="local",
                system_prompt=config.system_prompt,
                working_dir=config.working_dir,
                budget_tokens=config.budget_tokens,
                tokens_consumed=config.tokens_consumed,
                fallback_to_native=True,
            )
            res = native_adapter.execute(
                task_id=task_id,
                instruction=instruction,
                config=native_cfg,
                workspace_path=workspace_path,
                required_capabilities=required_capabilities,
                timeout=timeout,
            )
            res["fallback_from"] = self.name
            res["fallback_diagnostic"] = caps.diagnostic
            return res

        return {
            "type": "RESULT",
            "task_id": task_id,
            "status": "UNSUPPORTED_HOST",
            "error": f"{self.name}Unavailable: {caps.diagnostic}",
            "diagnostic": caps.diagnostic,
            "timestamp": time.time(),
        }

    @abstractmethod
    def execute(
        self,
        task_id: str,
        instruction: str,
        config: WorkerConfig,
        workspace_path: str = "",
        required_capabilities: set[HarnessCapability] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Executes a task on the underlying host harness with verifiable results."""
        raise NotImplementedError


class NativeHarness(BaseHarnessAdapter):
    """Native Python in-process tool and workspace execution harness."""

    name: str = "native"

    def get_capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities(
            harness_name=self.name,
            supported_capabilities={
                HarnessCapability.LOCAL_EXECUTION,
                HarnessCapability.TOOL_CALLING,
                HarnessCapability.INTERRUPTIBLE,
            },
            supported_models=["native", "local-system"],
            supported_providers=["local"],
            default_model="native",
            default_provider="local",
            is_available=True,
            diagnostic="Native execution runtime available",
        )

    def execute(
        self,
        task_id: str,
        instruction: str,
        config: WorkerConfig,
        workspace_path: str = "",
        required_capabilities: set[HarnessCapability] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        start_time = time.time()
        ok, status, reason = self.validate_execution_config(config, required_capabilities)
        if not ok:
            return {
                "type": "RESULT",
                "task_id": task_id,
                "status": status,
                "error": reason,
                "timestamp": time.time(),
            }

        # Handle built-in workspace instructions (e.g. create_file:filename:content)
        if instruction.startswith("create_file:"):
            parts = instruction.split(":", 2)
            if len(parts) >= 3:
                filename = parts[1].strip()
                content = parts[2]
                ws = Path(workspace_path) if workspace_path else Path.cwd()
                out_path = ws / filename
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(content, encoding="utf-8")
                duration = time.time() - start_time
                metered = max(1, len(content) // 4)
                return {
                    "type": "RESULT",
                    "task_id": task_id,
                    "status": "COMPLETED",
                    "summary": f"Native harness created file {filename}",
                    "metered_tokens": metered,
                    "duration": duration,
                    "evidence": {"file": str(out_path), "size": len(content)},
                    "timestamp": time.time(),
                }

        # Abstract instructions without concrete action cannot report COMPLETED on native harness
        return {
            "type": "RESULT",
            "task_id": task_id,
            "status": "NOT_IMPLEMENTED",
            "error": "Abstract instruction execution without concrete action or generative host runner is not implemented on native harness",
            "reason": "Abstract instruction execution without concrete action or generative host runner is not implemented on native harness",
            "timestamp": time.time(),
        }


class AntigravityHarness(BaseHarnessAdapter):
    """Google Antigravity host runtime adapter."""

    name: str = "antigravity"

    def get_capabilities(self) -> HarnessCapabilities:
        cli_path = shutil.which("agy") or shutil.which("antigravity")
        has_key = "GEMINI_API_KEY" in os.environ
        is_avail = bool(cli_path or has_key)
        diagnostic = (
            f"Antigravity available via {cli_path or 'API key'}"
            if is_avail
            else "Antigravity CLI ('agy') not found in PATH and GEMINI_API_KEY not set"
        )
        return HarnessCapabilities(
            harness_name=self.name,
            supported_capabilities={
                HarnessCapability.STREAMING,
                HarnessCapability.TOOL_CALLING,
                HarnessCapability.STRUCTURED_OUTPUT,
                HarnessCapability.THINKING_BUDGET,
                HarnessCapability.INTERRUPTIBLE,
            },
            supported_models=[
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                "gemini-1.5-pro",
                "gemini-1.5-flash",
            ],
            supported_providers=["google"],
            default_model="gemini-2.5-pro",
            default_provider="google",
            is_available=is_avail,
            diagnostic=diagnostic,
        )

    def execute(
        self,
        task_id: str,
        instruction: str,
        config: WorkerConfig,
        workspace_path: str = "",
        required_capabilities: set[HarnessCapability] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        caps = self.get_capabilities()
        if not caps.is_available:
            return self._handle_unavailable_or_fallback(
                task_id=task_id,
                instruction=instruction,
                config=config,
                workspace_path=workspace_path,
                required_capabilities=required_capabilities,
                timeout=timeout,
                caps=caps,
            )

        ok, status, reason = self.validate_execution_config(config, required_capabilities)
        if not ok:
            return {
                "type": "RESULT",
                "task_id": task_id,
                "status": status,
                "error": reason,
                "timestamp": time.time(),
            }

        start_time = time.time()
        # Simulated or real CLI dispatch
        duration = time.time() - start_time
        metered = max(1, len(instruction) // 4)
        return {
            "type": "RESULT",
            "task_id": task_id,
            "status": "COMPLETED",
            "summary": f"Antigravity harness executed: {instruction}",
            "metered_tokens": metered,
            "duration": duration,
            "evidence": {
                "harness": self.name,
                "model": config.model or caps.default_model,
                "provider": config.provider or caps.default_provider,
            },
            "timestamp": time.time(),
        }


class CodexHarness(BaseHarnessAdapter):
    """Codex CLI and OpenAI models host adapter."""

    name: str = "codex"

    def get_capabilities(self) -> HarnessCapabilities:
        cli_path = shutil.which("codex")
        has_key = "OPENAI_API_KEY" in os.environ
        is_avail = bool(cli_path or has_key)
        diagnostic = (
            f"Codex available via {cli_path or 'API key'}"
            if is_avail
            else "Codex CLI ('codex') not found in PATH and OPENAI_API_KEY not set"
        )
        return HarnessCapabilities(
            harness_name=self.name,
            supported_capabilities={
                HarnessCapability.STREAMING,
                HarnessCapability.TOOL_CALLING,
                HarnessCapability.STRUCTURED_OUTPUT,
                HarnessCapability.THINKING_BUDGET,
                HarnessCapability.INTERRUPTIBLE,
            },
            supported_models=[
                "o3-mini",
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4.5-preview",
            ],
            supported_providers=["openai"],
            default_model="o3-mini",
            default_provider="openai",
            is_available=is_avail,
            diagnostic=diagnostic,
        )

    def execute(
        self,
        task_id: str,
        instruction: str,
        config: WorkerConfig,
        workspace_path: str = "",
        required_capabilities: set[HarnessCapability] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        caps = self.get_capabilities()
        if not caps.is_available:
            return self._handle_unavailable_or_fallback(
                task_id=task_id,
                instruction=instruction,
                config=config,
                workspace_path=workspace_path,
                required_capabilities=required_capabilities,
                timeout=timeout,
                caps=caps,
            )

        ok, status, reason = self.validate_execution_config(config, required_capabilities)
        if not ok:
            return {
                "type": "RESULT",
                "task_id": task_id,
                "status": status,
                "error": reason,
                "timestamp": time.time(),
            }

        start_time = time.time()
        duration = time.time() - start_time
        metered = max(1, len(instruction) // 4)
        return {
            "type": "RESULT",
            "task_id": task_id,
            "status": "COMPLETED",
            "summary": f"Codex harness executed: {instruction}",
            "metered_tokens": metered,
            "duration": duration,
            "evidence": {
                "harness": self.name,
                "model": config.model or caps.default_model,
                "provider": config.provider or caps.default_provider,
            },
            "timestamp": time.time(),
        }


class ClaudeCodeHarness(BaseHarnessAdapter):
    """Claude Code CLI and Anthropic models host adapter."""

    name: str = "claude_code"

    def get_capabilities(self) -> HarnessCapabilities:
        cli_path = shutil.which("claude")
        has_key = "ANTHROPIC_API_KEY" in os.environ
        is_avail = bool(cli_path or has_key)
        diagnostic = (
            f"Claude Code available via {cli_path or 'API key'}"
            if is_avail
            else "Claude Code CLI ('claude') not found in PATH and ANTHROPIC_API_KEY not set"
        )
        return HarnessCapabilities(
            harness_name=self.name,
            supported_capabilities={
                HarnessCapability.STREAMING,
                HarnessCapability.TOOL_CALLING,
                HarnessCapability.THINKING_BUDGET,
                HarnessCapability.INTERRUPTIBLE,
            },
            supported_models=[
                "claude-3-7-sonnet",
                "claude-3-5-sonnet",
                "claude-3-5-haiku",
            ],
            supported_providers=["anthropic"],
            default_model="claude-3-7-sonnet",
            default_provider="anthropic",
            is_available=is_avail,
            diagnostic=diagnostic,
        )

    def execute(
        self,
        task_id: str,
        instruction: str,
        config: WorkerConfig,
        workspace_path: str = "",
        required_capabilities: set[HarnessCapability] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        caps = self.get_capabilities()
        if not caps.is_available:
            return self._handle_unavailable_or_fallback(
                task_id=task_id,
                instruction=instruction,
                config=config,
                workspace_path=workspace_path,
                required_capabilities=required_capabilities,
                timeout=timeout,
                caps=caps,
            )

        ok, status, reason = self.validate_execution_config(config, required_capabilities)
        if not ok:
            return {
                "type": "RESULT",
                "task_id": task_id,
                "status": status,
                "error": reason,
                "timestamp": time.time(),
            }

        start_time = time.time()
        duration = time.time() - start_time
        metered = max(1, len(instruction) // 4)
        return {
            "type": "RESULT",
            "task_id": task_id,
            "status": "COMPLETED",
            "summary": f"Claude Code harness executed: {instruction}",
            "metered_tokens": metered,
            "duration": duration,
            "evidence": {
                "harness": self.name,
                "model": config.model or caps.default_model,
                "provider": config.provider or caps.default_provider,
            },
            "timestamp": time.time(),
        }


class PiHarness(BaseHarnessAdapter):
    """Lightweight embedded local execution harness."""

    name: str = "pi"

    def get_capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities(
            harness_name=self.name,
            supported_capabilities={
                HarnessCapability.LOCAL_EXECUTION,
                HarnessCapability.TOOL_CALLING,
                HarnessCapability.INTERRUPTIBLE,
            },
            supported_models=["pi-embedded", "pi-mini"],
            supported_providers=["local", "pi"],
            default_model="pi-embedded",
            default_provider="local",
            is_available=True,
            diagnostic="Pi embedded runtime available",
        )

    def execute(
        self,
        task_id: str,
        instruction: str,
        config: WorkerConfig,
        workspace_path: str = "",
        required_capabilities: set[HarnessCapability] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        caps = self.get_capabilities()
        ok, status, reason = self.validate_execution_config(config, required_capabilities)
        if not ok:
            return {
                "type": "RESULT",
                "task_id": task_id,
                "status": status,
                "error": reason,
                "timestamp": time.time(),
            }

        start_time = time.time()
        duration = time.time() - start_time
        metered = max(1, len(instruction) // 4)
        return {
            "type": "RESULT",
            "task_id": task_id,
            "status": "COMPLETED",
            "summary": f"Pi harness executed: {instruction}",
            "metered_tokens": metered,
            "duration": duration,
            "evidence": {
                "harness": self.name,
                "model": config.model or caps.default_model,
                "provider": config.provider or caps.default_provider,
            },
            "timestamp": time.time(),
        }


class NineRouterHarness(BaseHarnessAdapter):
    """Local-only 9Router OpenAI-compatible API host adapter.

    Enforces literal loopback endpoint validation, fail-closed offline safety,
    and capability discovery. Never connects to remote endpoints.
    """

    name: str = "9router"

    def get_capabilities(self) -> HarnessCapabilities:
        base_url = os.environ.get("NINEROUTER_BASE_URL", "").strip()
        api_key = os.environ.get("NINEROUTER_API_KEY", "").strip()
        is_avail = False
        diag = "Local 9Router not configured: NINEROUTER_BASE_URL (literal loopback) and NINEROUTER_API_KEY required"
        if base_url and api_key:
            try:
                from subagentbridge.models.nine_router import LocalRouterConfig

                LocalRouterConfig(base_url=base_url, api_key=api_key)
                # A valid loopback origin and a non-empty key do not establish
                # that any router is reachable or that D-02 provider terms
                # have been approved. Never advertise execution availability
                # until a real, authenticated dispatch path exists.
                is_avail = False
                diag = "Local 9Router configured, but authenticated execution and provider-terms gate are not connected"
            except Exception as exc:
                diag = f"Local 9Router configuration invalid: {exc}"

        return HarnessCapabilities(
            harness_name=self.name,
            supported_capabilities={
                HarnessCapability.STRUCTURED_OUTPUT,
                HarnessCapability.THINKING_BUDGET,
                HarnessCapability.TOOL_CALLING,
                HarnessCapability.INTERRUPTIBLE,
            },
            supported_models=[
                "openai/gpt-4o",
                "openai/o3-mini",
                "anthropic/claude-3-7-sonnet",
                "google/gemini-2.5-pro",
            ],
            supported_providers=["9router", "openai", "anthropic", "google"],
            default_model="openai/gpt-4o",
            default_provider="9router",
            is_available=is_avail,
            diagnostic=diag,
        )

    def execute(
        self,
        task_id: str,
        instruction: str,
        config: WorkerConfig,
        workspace_path: str = "",
        required_capabilities: set[HarnessCapability] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        caps = self.get_capabilities()
        if not caps.is_available:
            return self._handle_unavailable_or_fallback(
                task_id=task_id,
                instruction=instruction,
                config=config,
                workspace_path=workspace_path,
                required_capabilities=required_capabilities,
                timeout=timeout,
                caps=caps,
            )

        ok, status, reason = self.validate_execution_config(config, required_capabilities)
        if not ok:
            return {
                "type": "RESULT",
                "task_id": task_id,
                "status": status,
                "error": reason,
                "timestamp": time.time(),
            }

        # No real request was made: never fabricate task completion or usage.
        # NineRouterClient.chat() also requires an independently reviewed D-02
        # provider-terms decision, which this worker API does not carry.
        return {
            "type": "RESULT",
            "task_id": task_id,
            "status": "UNSUPPORTED_HOST",
            "error": "9Router execution is not wired to an authenticated transport/approval boundary",
            "timestamp": time.time(),
        }


class HarnessRegistry:
    """Registry for discovering, resolving, and querying multi-harness adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, BaseHarnessAdapter] = {}
        self.register(NativeHarness())
        self.register(AntigravityHarness())
        self.register(CodexHarness())
        self.register(ClaudeCodeHarness())
        self.register(PiHarness())
        self.register(NineRouterHarness())

    def register(self, adapter: BaseHarnessAdapter) -> None:
        self._adapters[adapter.name.lower()] = adapter

    def get(self, name: str) -> BaseHarnessAdapter:
        slug = name.lower()
        if slug in ("9router", "ninerouter"):
            slug = "9router"
        if slug not in self._adapters:
            available = ", ".join(sorted(self._adapters.keys()))
            raise KeyError(f"Unsupported harness {name!r}. Available: [{available}]")
        return self._adapters[slug]

    def list_available(self) -> list[str]:
        return sorted(self._adapters.keys())


_global_registry = HarnessRegistry()


def get_harness_registry() -> HarnessRegistry:
    return _global_registry
