"""Backward compatibility shim for external integration adapter.

Imports all types from integration_adapter while preserving existing import paths.
"""
from __future__ import annotations

from subagentbridge.execution.integration_adapter import (
    IntegrationProbe,
    OptionalIntegrationBackend,
    OptionalOrcaBackend,
    OrcaProbe,
)

__all__ = [
    "IntegrationProbe",
    "OrcaProbe",
    "OptionalIntegrationBackend",
    "OptionalOrcaBackend",
]
