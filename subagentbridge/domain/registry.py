"""PR-01 receipt and role-registry contracts (in-process proof of wiring only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from secrets import token_bytes
from hmac import compare_digest
from uuid import uuid4
from threading import Lock

from .contracts import Message

from .contracts import Role, Evidence


@dataclass(frozen=True, slots=True)
class Principal:
    principal_id: str
    role: Role
    _registry_secret: bytes = field(default=b"", repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class ExecutorReceipt:
    receipt_id: str
    issuer_id: str
    task_id: str
    dispatch_id: str
    tree_sha: str
    exit_code: int
    # This record is a *contract* only. PR-04b must issue operational receipts
    # using a Bridge-owned executor and record argv, env, logs and provenance.


@dataclass(frozen=True, slots=True)
class QaVerdict:
    verdict_id: str
    qa_principal_id: str
    task_id: str
    dispatch_id: str
    tree_sha: str
    receipt_ids: tuple[str, ...]
    accepted: bool


class IdentityRegistry:
    """Trusted composition root registers identities; not an OS authorization boundary."""

    def __init__(self):
        self._members: dict[str, tuple[Role, bytes]] = {}

    def register(self, principal_id: str, role: Role) -> Principal:
        if not principal_id or not isinstance(role, Role):
            raise ValueError("valid principal identity and role required")
        if principal_id in self._members:
            raise ValueError("principal cannot be re-registered or change roles")
        secret = token_bytes(32)
        self._members[principal_id] = (role, secret)
        return Principal(principal_id, role, secret)

    def require(self, principal: Principal, role: Role):
        entry = self._members.get(principal.principal_id) if isinstance(principal, Principal) else None
        if (entry is None or entry[0] is not role or principal.role is not role
            or not compare_digest(principal._registry_secret, entry[1])):
            raise PermissionError(f"registered {role.value} identity is required")


class ReceiptIssuerRegistry:
    """Registry validates receipt provenance in tests; no security boundary yet.

    PR-04b must replace in-process issuance with real Bridge-owned tool executor
    and bind output hashes and a clean Git tree; never trust LLM-supplied claims.
    """

    def __init__(self, identities: IdentityRegistry):
        self._identities = identities
        self._receipts: dict[str, ExecutorReceipt] = {}
        self._evidence: dict[str, Evidence] = {}
        self._verdicts: dict[str, QaVerdict] = {}

    def issue(self, executor: Principal, *, task_id: str, dispatch_id: str,
              tree_sha: str, exit_code: int) -> ExecutorReceipt:
        self._identities.require(executor, Role.EXECUTOR)
        if not all((task_id, dispatch_id, tree_sha)) or type(exit_code) is not int:
            raise ValueError("receipt requires task/dispatch/tree identity and exit code")
        record = ExecutorReceipt(str(uuid4()), executor.principal_id, task_id, dispatch_id, tree_sha, exit_code)
        self._receipts[record.receipt_id] = record
        return record

    def create_evidence(self, receipt_id: str, *, task_id: str, dispatch_id: str, tree_sha: str) -> Evidence:
        receipt = self._receipts.get(receipt_id)
        if receipt is None:
            raise PermissionError("unissued receipt is not evidence")
        if (receipt.task_id, receipt.dispatch_id, receipt.tree_sha) != (task_id, dispatch_id, tree_sha):
            raise PermissionError("receipt does not match task, dispatch, and tree")
        if receipt.exit_code != 0:
            raise PermissionError("failed execution cannot serve as success evidence")
        record = Evidence(str(uuid4()), receipt_id, task_id, dispatch_id, tree_sha)
        self._evidence[record.evidence_id] = record
        return record

    def create_qa_verdict(self, qa: Principal, *, evidence: tuple[Evidence, ...],
                          task_id: str, dispatch_id: str, tree_sha: str,
                          accepted: bool) -> QaVerdict:
        self._identities.require(qa, Role.QA)
        if type(accepted) is not bool:
            raise ValueError("QA verdict accepted must be a boolean")
        if not evidence:
            raise PermissionError("QA verdict requires executor-issued receipt evidence")
        if len({item.evidence_id for item in evidence}) != len(evidence):
            raise PermissionError("duplicate evidence cannot be counted twice")
        for item in evidence:
            registered_evidence = self._evidence.get(item.evidence_id)
            if registered_evidence is None or registered_evidence != item:
                raise PermissionError("unregistered or mutated evidence object")
            if (item.task_id, item.dispatch_id, item.tree_sha) != (task_id, dispatch_id, tree_sha):
                raise PermissionError("cross-task, stale dispatch or wrong-tree evidence")
            # Evidence objects are not trusted: validate against registry.
            r = self._receipts.get(item.receipt_id)
            if r is None or (r.task_id, r.dispatch_id, r.tree_sha) != (task_id, dispatch_id, tree_sha) or r.exit_code != 0:
                raise PermissionError("unissued or mismatched receipt")
        verdict = QaVerdict(str(uuid4()), qa.principal_id, task_id, dispatch_id, tree_sha,
                             tuple(item.receipt_id for item in evidence), accepted)
        self._verdicts[verdict.verdict_id] = verdict
        return verdict

    def require_verdict(self, verdict: QaVerdict, *, task_id: str, dispatch_id: str, tree_sha: str):
        registered = self._verdicts.get(verdict.verdict_id)
        if registered is None or registered != verdict:
            raise PermissionError("QA verdict is not from a registered issuer")
        if (verdict.task_id, verdict.dispatch_id, verdict.tree_sha) != (task_id, dispatch_id, tree_sha):
            raise PermissionError("QA verdict does not bind this dispatch and tree")
        if not verdict.accepted:
            raise PermissionError("QA rejected the change")
        if not verdict.receipt_ids or any(self._receipts.get(i) is None for i in verdict.receipt_ids):
            raise PermissionError("missing executor-issued receipt")


class MessageRegistry:
    """In-memory idempotent message admission, not authenticated transport.

    PR-02 must persist deduplication with transactions before network workers
    can rely on it across crashes. This registry never grants permissions.
    """

    def __init__(self):
        self._recorded: dict[str, Message] = {}
        self._lock = Lock()

    def record(self, message: Message, *, task_id: str, dispatch_id: str) -> bool:
        if not isinstance(message, Message):
            raise ValueError("Message contract required")
        if (message.task_id, message.dispatch_id) != (task_id, dispatch_id):
            raise PermissionError("stale or cross-task message denied")
        if message.to_principal == "*" or message.from_principal == "*":
            raise PermissionError("no implicit broadcast")
        with self._lock:
            if message.message_id in self._recorded:
                if self._recorded[message.message_id] != message:
                    raise ValueError("conflicting message id cannot be replayed")
                return False
            self._recorded[message.message_id] = message
            return True

    @property
    def recorded_count(self) -> int:
        with self._lock:
            return len(self._recorded)
