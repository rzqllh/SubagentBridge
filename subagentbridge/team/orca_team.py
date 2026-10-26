"""Backward compatibility shim for team manager.

Imports all types and functions from team_manager while preserving existing import paths.
"""
from __future__ import annotations

from subagentbridge.team.team_manager import (
    TeamManager,
    OrcaTeamManager,
    OrcaTeamService,
)

__all__ = [
    "TeamManager",
    "OrcaTeamManager",
    "OrcaTeamService",
]
