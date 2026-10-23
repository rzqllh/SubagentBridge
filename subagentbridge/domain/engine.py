"""PR-01 task aggregate — formal stage separation and stale-dispatch rejection."""
from __future__ import annotations

from uuid import uuid4

from .contracts import Dispatch, Task, TaskState, Role
from .registry import Principal, IdentityRegistry, ReceiptIssuerRegistry, QaVerdict


class InvalidTransition(ValueError):
    pass


class StaleDispatch(ValueError):
    pass


class TaskAggregate:
    def __init__(self, task: Task, identities: IdentityRegistry, receipts: ReceiptIssuerRegistry):
        self.task = task
        self.identities = identities
        self.receipts = receipts
        self._state = TaskState.CREATED
        self.active_dispatch: Dispatch | None = None
        self.verified_tree_sha: str | None = None
        self.qa_verdict: QaVerdict | None = None
        self._used_keys: set[str] = set()
        self._attempt = 0

    @property
    def state(self) -> TaskState:
        return self._state

    def freeze(self, pm: Principal):
        self.identities.require(pm, Role.PM)
        if self.state not in (TaskState.CREATED, TaskState.BLOCKED):
            raise InvalidTransition("freeze requires CREATED or BLOCKED")
        self._state = TaskState.FROZEN

    def dispatch(self, pm: Principal, *, idempotency_key: str) -> Dispatch:
        self.identities.require(pm, Role.PM)
        if self.state is not TaskState.FROZEN:
            raise InvalidTransition("a frozen task is required")
        if not idempotency_key or idempotency_key in self._used_keys:
            raise InvalidTransition("duplicate or missing idempotency key")
        self._used_keys.add(idempotency_key)
        self._attempt += 1
        self.active_dispatch = Dispatch(str(uuid4()), self.task.task_id, self._attempt,
                                        idempotency_key, self.task.tree_sha, self.task.policy_revision)
        self._state = TaskState.DISPATCHED
        return self.active_dispatch

    def process_succeeded(self, dispatch_id: str, tree_sha: str):
        self._require_current(dispatch_id, tree_sha)
        if self.state is not TaskState.DISPATCHED:
            raise InvalidTransition("PROCESS_SUCCEEDED requires DISPATCHED")
        self._state = TaskState.PROCESS_SUCCEEDED

    def qa_verified(self, qa: Principal, verdict: QaVerdict):
        self.identities.require(qa, Role.QA)
        if self.state is not TaskState.PROCESS_SUCCEEDED or self.active_dispatch is None:
            raise InvalidTransition("QA_VERIFIED requires PROCESS_SUCCEEDED")
        self.receipts.require_verdict(verdict, task_id=self.task.task_id,
                                      dispatch_id=self.active_dispatch.dispatch_id,
                                      tree_sha=self.task.tree_sha)
        if verdict.qa_principal_id != qa.principal_id:
            raise PermissionError("QA verdict cannot be presented by a different principal")
        self.qa_verdict = verdict
        self._state = TaskState.QA_VERIFIED

    def mark_verified(self, qa: Principal):
        self.identities.require(qa, Role.QA)
        if self.state is not TaskState.QA_VERIFIED or self.qa_verdict is None:
            raise InvalidTransition("VERIFIED requires QA_VERIFIED plus verdict")
        if self.qa_verdict.qa_principal_id != qa.principal_id:
            raise PermissionError("only verdict-issuing QA can finalize")
        self._state = TaskState.VERIFIED
        self.verified_tree_sha = self.task.tree_sha

    def change_tree(self, new_tree_sha: str):
        if not new_tree_sha:
            raise ValueError("new tree cannot be empty")
        if new_tree_sha == self.task.tree_sha:
            return
        if self._state is TaskState.RECOVERY_REQUIRED:
            raise InvalidTransition("cannot change tree while task is in RECOVERY_REQUIRED; reconciliation required")
        self.task = Task(self.task.task_id, self.task.run_id, self.task.acceptance_criteria,
                         new_tree_sha, self.task.policy_revision)
        self._state = TaskState.FROZEN
        self.verified_tree_sha = None
        self.qa_verdict = None
        self.active_dispatch = None

    def reconcile(self, pm: Principal, *, new_tree_sha: str | None = None) -> None:
        self.identities.require(pm, Role.PM)
        if self._state is not TaskState.RECOVERY_REQUIRED:
            raise InvalidTransition("reconcile requires RECOVERY_REQUIRED")
        tree = new_tree_sha or self.task.tree_sha
        self.task = Task(self.task.task_id, self.task.run_id, self.task.acceptance_criteria,
                         tree, self.task.policy_revision)
        self._state = TaskState.FROZEN
        self.active_dispatch = None
        self.verified_tree_sha = None
        self.qa_verdict = None

    def block(self):
        self._state = TaskState.BLOCKED
        self.qa_verdict = None
        self.verified_tree_sha = None

    def recover_unknown(self):
        self._state = TaskState.RECOVERY_REQUIRED
        self.qa_verdict = None
        self.verified_tree_sha = None

    def _require_current(self, dispatch_id: str, tree_sha: str):
        d = self.active_dispatch
        if d is None or d.dispatch_id != dispatch_id or d.tree_sha != tree_sha or tree_sha != self.task.tree_sha:
            raise StaleDispatch("stale or cross-tree dispatch ignored")
