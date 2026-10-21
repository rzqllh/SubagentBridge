"""PR-01 candidate: versioned, dependency-free domain data contracts.

These values are pure application-domain contracts. They do not provide OS
confinement, trusted human approval, or permission enforcement by themselves.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet

SCHEMA_VERSION = 1


class Role(str, Enum):
    PM = "PM"
    DEVELOPER = "DEVELOPER"
    QA = "QA"
    SPECIALIST = "SPECIALIST"
    EXECUTOR = "EXECUTOR"


class TaskState(str, Enum):
    CREATED = "CREATED"
    FROZEN = "FROZEN"
    DISPATCHED = "DISPATCHED"
    PROCESS_SUCCEEDED = "PROCESS_SUCCEEDED"
    QA_VERIFIED = "QA_VERIFIED"
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


@dataclass(frozen=True, slots=True)
class Run:
    run_id: str
    project_id: str
    policy_revision: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self):
        if not self.run_id or not self.project_id or not self.policy_revision:
            raise ValueError("run ID, project ID and policy revision are required")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported schema version")


@dataclass(frozen=True, slots=True)
class Task:
    task_id: str
    run_id: str
    acceptance_criteria: tuple[str, ...]
    tree_sha: str
    policy_revision: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self):
        if not self.task_id or not self.run_id or not self.policy_revision:
            raise ValueError("task IDs and policy revision must be nonempty")
        criteria = self.acceptance_criteria
        if (not isinstance(criteria, (list, tuple)) or not criteria
            or any(not isinstance(x, str) or not x.strip() for x in criteria)):
            raise ValueError("nonempty, frozen acceptance criteria are required")
        object.__setattr__(self, "acceptance_criteria", tuple(criteria))
        if not self.tree_sha:
            raise ValueError("tree SHA is required")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported schema version")


@dataclass(frozen=True, slots=True)
class Dispatch:
    dispatch_id: str
    task_id: str
    attempt: int
    idempotency_key: str
    tree_sha: str
    policy_revision: str

    def __post_init__(self):
        if not self.dispatch_id or not self.task_id or not self.idempotency_key or not self.tree_sha:
            raise ValueError("dispatch correlation IDs and tree identity required")
        if self.attempt < 1 or not self.policy_revision:
            raise ValueError("attempt must be positive and policy revision nonempty")


@dataclass(frozen=True, slots=True)
class Message:
    message_id: str
    from_principal: str
    to_principal: str
    task_id: str
    dispatch_id: str
    payload: str

    def __post_init__(self):
        if not all((self.message_id, self.from_principal, self.to_principal, self.task_id, self.dispatch_id)):
            raise ValueError("targeted messages require sender, recipient, task and dispatch identity")


@dataclass(frozen=True, slots=True)
class Approval:
    decision_id: str
    operation_fingerprint: str
    policy_revision: str
    human_principal_id: str | None = None
    # A data record only; never authorizes execution without a trusted broker.
    approved: bool | None = None

    def __post_init__(self):
        if not all((self.decision_id, self.operation_fingerprint, self.policy_revision)):
            raise ValueError("approval must bind an operation and policy revision")


@dataclass(frozen=True, slots=True)
class Capability:
    name: str
    allowed_roles: FrozenSet[Role]
    enforcement_class: str = "UNSUPPORTED_ENFORCEMENT"

    def __post_init__(self):
        if (not self.name or not isinstance(self.allowed_roles, (set, frozenset))
            or not self.allowed_roles or not all(isinstance(x, Role) for x in self.allowed_roles)):
            raise ValueError("capability and roles required")
        object.__setattr__(self, "allowed_roles", frozenset(self.allowed_roles))


@dataclass(frozen=True, slots=True)
class Budget:
    max_tokens: int
    max_attempts: int
    max_cost_microunits: int

    def __post_init__(self):
        if self.max_tokens < 0 or self.max_cost_microunits < 0 or self.max_attempts < 1:
            raise ValueError("budget ceilings must be nonnegative; attempts >= 1")


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    receipt_id: str
    task_id: str
    dispatch_id: str
    tree_sha: str
    # Only a registered registry constructs verified Evidence; this dataclass
    # is transport/storage representation, not an unforgeable runtime proof.
