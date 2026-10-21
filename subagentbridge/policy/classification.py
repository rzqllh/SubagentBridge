"""PR-03 candidate: conservative classification, NOT an execution authorizer.

Never interpret a worker's 'approved' argument as human authorization.
This only classifies operations; PR-03 isolated broker and PR-04b proxy are REQUIRED
before a side effect can be permitted. No network, shell or filesystem writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json


class GateCategory(str, Enum):
    AUTH = "AUTH_OR_SECRET"
    DEPENDENCY = "DEPENDENCY"
    CI_DEPLOY = "CI_OR_DEPLOY"
    DESTRUCTIVE = "DESTRUCTIVE"
    PUSH = "GIT_PUSH_OR_REWRITE"
    EGRESS = "NETWORK_EGRESS"
    OUTSIDE_WORKSPACE = "OUTSIDE_WORKSPACE_WRITE"
    QA_CHANGE = "QA_OR_ACCEPTANCE_CHANGE"
    WAIVER = "QA_WAIVER"
    BUDGET = "BUDGET_OR_RETRY_OVERRIDE"
    TRADEOFF = "MATERIAL_TRADEOFF"
    READ = "READ_ONLY_REQUEST"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class OperationRequest:
    task_id: str
    dispatch_id: str
    policy_revision: str
    operation: str
    argv: tuple[str, ...]
    resource: str

    def __post_init__(self) -> None:
        for label, value, limit in (
            ('task_id', self.task_id, 256), ('dispatch_id', self.dispatch_id, 256),
            ('policy_revision', self.policy_revision, 256),
            ('operation', self.operation, 256), ('resource', self.resource, 4096),
        ):
            if (type(value) is not str or not value.strip() or len(value) > limit
                    or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
                raise ValueError(f'{label} must be bounded printable text')
        if (type(self.argv) not in (list, tuple) or len(self.argv) > 64
                or not all(type(x) is str and x and len(x) <= 4096
                           and not any(ord(ch) < 32 or ord(ch) == 127 for ch in x)
                           for x in self.argv)):
            raise ValueError('argv must be bounded printable argument strings')
        object.__setattr__(self, 'argv', tuple(self.argv))


@dataclass(frozen=True, slots=True)
class GateDecision:
    category: GateCategory
    human_gate_required: bool
    execution_authorized: bool = False
    reason: str = "No broker/ToolExecutor installed: operation NOT authorized"


def fingerprint(request: OperationRequest) -> str:
    """Stable operation identity; never a capability or approval credential."""
    body = [1, request.task_id, request.dispatch_id, request.policy_revision,
            request.operation, list(request.argv), request.resource]
    return sha256(json.dumps(body, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


_RULES = {
    "auth.change": GateCategory.AUTH,
    "secret.read": GateCategory.AUTH,
    "credential.write": GateCategory.AUTH,
    "dependency.install": GateCategory.DEPENDENCY,
    "dependency.change": GateCategory.DEPENDENCY,
    "ci.modify": GateCategory.CI_DEPLOY,
    "deploy": GateCategory.CI_DEPLOY,
    "file.delete": GateCategory.DESTRUCTIVE,
    "branch.delete": GateCategory.DESTRUCTIVE,
    "data.migrate": GateCategory.DESTRUCTIVE,
    "git.push": GateCategory.PUSH,
    "git.force_push": GateCategory.PUSH,
    "git.rewrite": GateCategory.PUSH,
    "network.new_host": GateCategory.EGRESS,
    "file.write_outside_workspace": GateCategory.OUTSIDE_WORKSPACE,
    "qa.tests.modify": GateCategory.QA_CHANGE,
    "qa.criteria.modify": GateCategory.QA_CHANGE,
    "qa.waive": GateCategory.WAIVER,
    "budget.override": GateCategory.BUDGET,
    "retry.limit_exceeded": GateCategory.BUDGET,
    "tradeoff.material": GateCategory.TRADEOFF,
    "file.read": GateCategory.READ,
    "task.inspect": GateCategory.READ,
}


# Only these exact, inspect-only argv spellings may accompany task.inspect.
# A file.read request identifies the file in `resource`, never executable argv.
# This conservative table is classification, NOT permission to execute any argv.
_INSPECTION_ARGV = frozenset({
    ('git', 'status', '--porcelain'),
    ('git', 'rev-parse', 'HEAD'),
    ('git', 'rev-parse', 'HEAD^{tree}'),
})


def classify(request: OperationRequest) -> GateDecision:
    """Fail closed on an operation/argv mismatch, even for claimed reads.

    An adversary can label `git push` as `file.read`. No unknown or mismatched
    intent may evade the human gate. Even valid reads remain unauthorized here;
    a separate scoped executor and identity boundary are mandatory.
    """
    if not isinstance(request, OperationRequest):
        raise TypeError("OperationRequest required")
    cat = _RULES.get(request.operation, GateCategory.UNKNOWN)
    if cat is GateCategory.READ:
        if request.operation == 'file.read' and request.argv:
            return GateDecision(GateCategory.UNKNOWN, True, reason='file.read cannot execute argv')
        if (request.operation == 'task.inspect' and request.argv
                and request.argv not in _INSPECTION_ARGV):
            return GateDecision(GateCategory.UNKNOWN, True, reason='inspection argv is not allowlisted')
    return GateDecision(cat, cat is not GateCategory.READ)
