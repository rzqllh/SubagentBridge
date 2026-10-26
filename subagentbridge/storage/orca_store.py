"""Backward compatibility shim for persistence store.

Imports all types and functions from team_store while preserving existing import paths.
"""
from __future__ import annotations

from subagentbridge.storage.team_store import (
    TeamStore,
    OrcaStore,
    migrate_schema,
    SIMPUL_SCHEMA,
    SIMPUL_COMPATIBILITY_VIEWS,
)

# Legacy alias for schema constant
ORCA_SCHEMA = SIMPUL_SCHEMA

__all__ = [
    "TeamStore",
    "OrcaStore",
    "migrate_schema",
    "SIMPUL_SCHEMA",
    "ORCA_SCHEMA",
    "SIMPUL_COMPATIBILITY_VIEWS",
]
