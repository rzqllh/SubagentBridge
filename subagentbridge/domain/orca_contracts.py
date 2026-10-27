"""Backward compatibility shim for domain contracts.

Imports all types from team_contracts while preserving existing import paths.
"""
from __future__ import annotations

from subagentbridge.domain.team_contracts import (
    AgentRole,
    OrcaRole,
    WorkerStatus,
    QueueTaskStatus,
    WorkerConfig,
    AgentTeam,
    OrcaTeam,
    AgentSession,
    OrcaSession,
    QueueItem,
    WorktreeAssignment,
    HandoffEvidence,
    ChannelMessage,
    WorkerCheckpoint,
)

__all__ = [
    "AgentRole",
    "OrcaRole",
    "WorkerStatus",
    "QueueTaskStatus",
    "WorkerConfig",
    "AgentTeam",
    "OrcaTeam",
    "AgentSession",
    "OrcaSession",
    "QueueItem",
    "WorktreeAssignment",
    "HandoffEvidence",
    "ChannelMessage",
    "WorkerCheckpoint",
]
