"""Optional compatibility integration adapter seam for external CLI probing.

Isolated boundary for upstream compatibility probing; disabled by default.
No external subprocess calls occur unless explicitly enabled and configured.
Simpul runtime does not require or depend on external CLI tools.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class IntegrationProbe:
    available: bool
    enforcement_class: str
    details: str


# Backward-compatibility alias
OrcaProbe = IntegrationProbe


class OptionalIntegrationBackend:
    def __init__(self, *, enabled: bool = False, status_runner: Callable[[], dict] | None = None):
        self.enabled = enabled
        self._status_runner = status_runner
        self._owned: set[str] = set()

    def probe(self) -> IntegrationProbe:
        if not self.enabled:
            return IntegrationProbe(False, "UNSUPPORTED_ENFORCEMENT", "Integration probe disabled, no CLI calls")
        if self._status_runner is None:
            return IntegrationProbe(False, "UNSUPPORTED_ENFORCEMENT", "No verified external CLI adapter configured")
        try:
            details = self._status_runner()
        except (OSError, ValueError, RuntimeError) as exc:
            return IntegrationProbe(False, "UNSUPPORTED_ENFORCEMENT", type(exc).__name__)
        if not isinstance(details, dict) or type(details.get("available")) is not bool:
            return IntegrationProbe(False, "UNSUPPORTED_ENFORCEMENT", "Malformed status response")
        return IntegrationProbe(
            details["available"],
            "UNSUPPORTED_ENFORCEMENT",
            "CLI detected; isolation and dispatch support NOT VERIFIED",
        )

    def dispatch(self, task_id: str, dispatch_id: str):
        raise PermissionError("External dispatch unsupported until CLI and isolation verified")

    def cancel(self, dispatch_id: str):
        raise PermissionError("External cancellation unsupported; never use global reset")

    @staticmethod
    def normalize_worker_done(data: dict) -> dict:
        if not isinstance(data, dict) or not data.get("dispatch_id") or data.get("status") != "worker_done":
            raise ValueError("invalid worker completion signal")
        return {"dispatch_id": data["dispatch_id"], "status": "WAITING_QA", "verified": False}


# Backward-compatibility alias
OptionalOrcaBackend = OptionalIntegrationBackend
