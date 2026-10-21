"""PR-01 candidate: versioned, dependency-free domain data contracts.

These values are pure application-domain contracts. They do not provide OS
confinement, trusted human approval, or permission enforcement by themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet

SCHEMA_VERSION = 1


def _identity(value: object, *, label: str) -> None:
    if (type(value) is not str or not value.strip() or len(value) > 4096
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError(f'{label} must be bounded printable text')


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
        for key in ('run_id', 'project_id', 'policy_revision'):
            _identity(getattr(self, key), label=key)
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
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
        for key in ('task_id', 'run_id', 'tree_sha', 'policy_revision'):
            _identity(getattr(self, key), label=key)
        criteria = self.acceptance_criteria
        if (not isinstance(criteria, (list, tuple)) or not criteria
                or any(type(x) is not str or not x.strip() or len(x) > 4096
                       for x in criteria) or len(set(criteria)) != len(criteria)):
            raise ValueError("nonempty, unique frozen acceptance criteria required")
        object.__setattr__(self, "acceptance_criteria", tuple(criteria))
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
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
        for key in ('dispatch_id', 'task_id', 'idempotency_key', 'tree_sha', 'policy_revision'):
            _identity(getattr(self, key), label=key)
        if type(self.attempt) is not int or self.attempt < 1:
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
        for key in ('message_id', 'from_principal', 'to_principal', 'task_id', 'dispatch_id'):
            _identity(getattr(self, key), label=key)
        if type(self.payload) is not str:
            raise ValueError('message payload must be text')


@dataclass(frozen=True, slots=True)
class Approval:
    decision_id: str
    operation_fingerprint: str
    policy_revision: str
    human_principal_id: str | None = None
    # A data record only; never authorizes execution without a trusted broker.
    approved: bool | None = None

    def __post_init__(self):
        for key in ('decision_id', 'operation_fingerprint', 'policy_revision'):
            _identity(getattr(self, key), label=key)
        if self.human_principal_id is not None:
            _identity(self.human_principal_id, label='human_principal_id')
        if self.approved is not None and type(self.approved) is not bool:
            raise ValueError('approval state must be tri-state boolean')


@dataclass(frozen=True, slots=True)
class Capability:
    name: str
    allowed_roles: FrozenSet[Role]
    enforcement_class: str = "UNSUPPORTED_ENFORCEMENT"

    def __post_init__(self):
        if (type(self.name) is not str or not self.name.strip()
            or not isinstance(self.allowed_roles, (set, frozenset))
            or not self.allowed_roles or not all(isinstance(x, Role) for x in self.allowed_roles)):
            raise ValueError("capability and roles required")
        object.__setattr__(self, "allowed_roles", frozenset(self.allowed_roles))


@dataclass(frozen=True, slots=True)
class Budget:
    max_tokens: int
    max_attempts: int
    max_cost_microunits: int

    def __post_init__(self):
        if (any(type(v) is not int for v in
                (self.max_tokens, self.max_cost_microunits, self.max_attempts))
                or self.max_tokens < 0 or self.max_cost_microunits < 0 or self.max_attempts < 1):
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
