"""Independent authenticated human operator approval boundary (P0 / Issue #22).

Provides a **candidate** operator decision store; it does NOT itself authenticate
OIDC/WebAuthn tokens or integrate into the production command dispatcher.
The trusted host must supply an independently authenticated verifier, and the
boundary denies all operator decisions until one is supplied.
Decisions are cryptographically bound to:
1. Authenticated operator identity (OIDC/WebAuthn/console assertion)
2. Operator role (e.g. 'security_lead', 'operator', 'auditor')
3. Worker session ID and task ID
4. Canonical command and arguments
5. Canonical workspace path
6. Single-use cryptographic nonce
7. Bounded TTL expiration
8. Triad policy: ALLOW_ONCE, DENY, ANSWER_QUESTIONS
9. Durable tamper-evident audit trail via AuditLedger (SHA-256 hash chaining)
10. Safe pending-decision recovery across supervisor restarts without secret leakage.
"""
from __future__ import annotations

import hashlib
import hmac
from copy import deepcopy
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from secrets import token_hex
import sqlite3
import threading
import time
from typing import Any, Callable, Mapping

from subagentbridge.storage.audit_ledger import AuditLedger


class OperatorDecision(str, Enum):
    ALLOW_ONCE = "ALLOW_ONCE"
    DENY = "DENY"
    ANSWER_QUESTIONS = "ANSWER_QUESTIONS"


class ApprovalState(str, Enum):
    BLOCKED = "BLOCKED"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    QUESTION_PENDING = "QUESTION_PENDING"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"


@dataclass(frozen=True, slots=True)
class OperatorIdentity:
    """Unverified operator assertion. Construction does not prove authentication."""

    operator_id: str
    role: str
    channel: str  # e.g. "webauthn", "oidc", "operator_console"
    auth_token: str  # UNVERIFIED caller-supplied assertion; must be checked by an external verifier

    def __post_init__(self) -> None:
        if not self.operator_id or not self.role or not self.channel or not self.auth_token:
            raise ValueError("operator_id, role, channel, and auth_token are strictly required")
        if self.role in ("worker", "agent", "subagent", "untrusted"):
            raise PermissionError(f"Role {self.role!r} is not an authorized operator role")


@dataclass
class OperatorApprovalRequest:
    action_id: str
    session_id: str
    task_id: str
    command: list[str]
    workspace_path: str
    nonce: str
    created_at: float
    expires_at: float
    state: ApprovalState = ApprovalState.BLOCKED
    decision: OperatorDecision | None = None
    operator_id: str = ""
    operator_role: str = ""
    operator_channel: str = ""
    operator_notes: str = ""
    questions: list[str] = field(default_factory=list)
    answers: dict[str, str] = field(default_factory=dict)
    # False for all legacy rows; only a trusted host verifier can set True.
    operator_verified: bool = False


def canonical_command_digest(command: list[str], workspace_path: str, task_id: str) -> str:
    payload = json.dumps({
        "command": [str(x) for x in command],
        "workspace_path": str(Path(workspace_path).resolve()),
        "task_id": str(task_id),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def operator_decision_challenge(
    request: OperatorApprovalRequest, decision: OperatorDecision,
) -> str:
    """Action-specific challenge digest supplied to a trusted RP/IdP verifier.

    This is a challenge, NOT an authenticated assertion or a signature.
    WebAuthn/OIDC validation, consent, role checks and replay prevention must
    be enforced by the trusted external relying party.
    """
    if not isinstance(request, OperatorApprovalRequest) or not isinstance(decision, OperatorDecision):
        raise TypeError("operator decision challenge requires a request and explicit decision")
    payload = json.dumps({
        "domain": "SIMPUL_OPERATOR_APPROVAL_V1",
        "action_id": request.action_id,
        "session_id": request.session_id,
        "task_id": request.task_id,
        "nonce": request.nonce,
        "command_digest": canonical_command_digest(
            request.command, request.workspace_path, request.task_id,
        ),
        "workspace_path": request.workspace_path,
        "created_at": request.created_at,
        "expires_at": request.expires_at,
        "decision": decision.value,
    }, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class IndependentOperatorApprovalBoundary:
    """Local decision store; requires externally verified operator assertions."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        ledger: AuditLedger | None = None,
        *,
        default_ttl_seconds: float = 900.0,
        signing_secret: str | None = None,
        operator_verifier: Callable[[OperatorIdentity], bool] | None = None,
        decision_verifier: Callable[
            [OperatorApprovalRequest, OperatorDecision, OperatorIdentity], bool
        ] | None = None,
    ) -> None:
        if not 0 < default_ttl_seconds <= 86400:
            raise ValueError("default_ttl_seconds must be within (0, 86400]")
        self.default_ttl = default_ttl_seconds
        # Production must inject a trusted out-of-process/OIDC/WebAuthn assertion
        # verifier. A caller-constructed OperatorIdentity is never authentication.
        # No verifier => ALLOW_ONCE, DENY and ANSWER_QUESTIONS all fail closed.
        self._operator_verifier = operator_verifier
        # Only a trusted host can verify a fresh, action-specific external
        # assertion. Identity-only checks are insufficient for worker dispatch.
        self._decision_verifier = decision_verifier
        self._secret = signing_secret or token_hex(32)
        self._lock = threading.RLock()
        self._requests: dict[str, OperatorApprovalRequest] = {}
        self._consumed_nonces: set[str] = set()

        self.db_path = Path(db_path) if db_path else None
        if self.db_path:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()

        self.ledger = ledger

    def _init_db(self) -> None:
        assert self.db_path is not None
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            # Concurrent Windows SQLite startups may raise SQLITE_BUSY while
            # another process switches journal mode. Journal mode is a
            # performance choice, not a prerequisite for serialized DDL.
            # A single-owner deployment may enable WAL separately.
            # Serialize schema inspection + ALTER across independent processes.
            # The test for a missing column must run under the same write lock
            # as the migration itself, or concurrent startups can both ALTER.
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS operator_approvals (
                    action_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    nonce TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    state TEXT NOT NULL,
                    decision TEXT,
                    operator_id TEXT,
                    operator_role TEXT,
                    operator_channel TEXT,
                    operator_notes TEXT,
                    questions_json TEXT,
                    answers_json TEXT,
                    operator_verified INTEGER NOT NULL DEFAULT 0
                )
            """)
            existing = {row[1] for row in conn.execute("PRAGMA table_info(operator_approvals)")}
            if "operator_verified" not in existing:
                # Existing approvals have no independent authentication evidence.
                # A default of 0 means they cannot be consumed after upgrade.
                conn.execute(
                    "ALTER TABLE operator_approvals "
                    "ADD COLUMN operator_verified INTEGER NOT NULL DEFAULT 0"
                )

    def _persist_request(
        self,
        req: OperatorApprovalRequest,
        *,
        expected: OperatorApprovalRequest | None = None,
    ) -> None:
        """Persist a new request or CAS one permitted state transition.

        Each supervisor owns a separate memory snapshot. Never allow a stale
        BLOCKED/QUESTION_PENDING/APPROVED snapshot to overwrite the winner in
        another process, including a still-unconsumed APPROVED row.
        """
        if not self.db_path:
            return

        with sqlite3.connect(self.db_path, timeout=5.0) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            if expected is None:
                try:
                    conn.execute("""
                        INSERT INTO operator_approvals (
                            action_id, session_id, task_id, command_json, workspace_path,
                            nonce, created_at, expires_at, state, decision,
                            operator_id, operator_role, operator_channel, operator_notes,
                            questions_json, answers_json, operator_verified
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        req.action_id, req.session_id, req.task_id,
                        json.dumps(req.command), req.workspace_path, req.nonce,
                        req.created_at, req.expires_at, req.state.value,
                        req.decision.value if req.decision else None,
                        req.operator_id, req.operator_role, req.operator_channel,
                        req.operator_notes, json.dumps(req.questions),
                        json.dumps(req.answers), int(req.operator_verified),
                    ))
                except sqlite3.IntegrityError as exc:
                    raise PermissionError(
                        "DENIED: stale or terminal approval cannot be inserted again"
                    ) from exc
                return

            # The original immutable command context and TTL must never change
            # when an operator decides or an active approval expires.
            if (
                req.action_id != expected.action_id
                or req.session_id != expected.session_id
                or req.task_id != expected.task_id
                or req.command != expected.command
                or req.workspace_path != expected.workspace_path
                or req.nonce != expected.nonce
                or req.created_at != expected.created_at
                or req.expires_at != expected.expires_at
            ):
                raise PermissionError("DENIED: approval context changed during transition")

            permitted = {
                ApprovalState.BLOCKED: {
                    ApprovalState.QUESTION_PENDING, ApprovalState.APPROVED,
                    ApprovalState.DENIED, ApprovalState.EXPIRED,
                },
                ApprovalState.QUESTION_PENDING: {
                    ApprovalState.QUESTION_PENDING, ApprovalState.APPROVED,
                    ApprovalState.DENIED, ApprovalState.EXPIRED,
                },
                ApprovalState.APPROVED: {ApprovalState.EXPIRED},
            }
            if req.state not in permitted.get(expected.state, set()):
                raise PermissionError("DENIED: stale or terminal approval state transition")

            # Expected answers and identity are checked as well as state. This
            # rejects two concurrent QUESTION_PENDING updates with the same
            # state but different human answers or operator provenance.
            cursor = conn.execute("""
                UPDATE operator_approvals SET
                    state=?, decision=?, operator_id=?, operator_role=?,
                    operator_channel=?, operator_notes=?, questions_json=?,
                    answers_json=?, operator_verified=?
                WHERE action_id=? AND nonce=? AND session_id=? AND task_id=?
                  AND command_json=? AND workspace_path=?
                  AND state=? AND COALESCE(decision, '')=?
                  AND COALESCE(operator_id, '')=?
                  AND COALESCE(operator_role, '')=?
                  AND COALESCE(operator_channel, '')=?
                  AND COALESCE(operator_notes, '')=?
                  AND COALESCE(questions_json, '[]')=?
                  AND COALESCE(answers_json, '{}')=?
                  AND operator_verified=?
            """, (
                req.state.value,
                req.decision.value if req.decision else None,
                req.operator_id, req.operator_role, req.operator_channel,
                req.operator_notes, json.dumps(req.questions),
                json.dumps(req.answers), int(req.operator_verified),
                expected.action_id, expected.nonce, expected.session_id,
                expected.task_id, json.dumps(expected.command),
                expected.workspace_path, expected.state.value,
                expected.decision.value if expected.decision else "",
                expected.operator_id, expected.operator_role,
                expected.operator_channel, expected.operator_notes,
                json.dumps(expected.questions), json.dumps(expected.answers),
                int(expected.operator_verified),
            ))
            if cursor.rowcount != 1:
                raise PermissionError(
                    "DENIED: stale operator decision or terminal approval changed in another process"
                )

    def rehydrate_from_disk(self) -> int:
        """Reloads pending/consumed approvals across orchestrator restart."""
        if not self.db_path or not self.db_path.exists():
            return 0
        now = time.time()
        rehydrated = 0
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM operator_approvals").fetchall()
            for r in rows:
                state_str = r["state"]
                state = ApprovalState(state_str)
                expires_at = float(r["expires_at"])
                if state in (ApprovalState.BLOCKED, ApprovalState.APPROVED, ApprovalState.QUESTION_PENDING) and now >= expires_at:
                    state = ApprovalState.EXPIRED

                decision = OperatorDecision(r["decision"]) if r["decision"] else None
                req = OperatorApprovalRequest(
                    action_id=r["action_id"],
                    session_id=r["session_id"],
                    task_id=r["task_id"],
                    command=json.loads(r["command_json"]),
                    workspace_path=r["workspace_path"],
                    nonce=r["nonce"],
                    created_at=float(r["created_at"]),
                    expires_at=expires_at,
                    state=state,
                    decision=decision,
                    operator_id=r["operator_id"] or "",
                    operator_role=r["operator_role"] or "",
                    operator_channel=r["operator_channel"] or "",
                    operator_notes=r["operator_notes"] or "",
                    questions=json.loads(r["questions_json"] or "[]"),
                    answers=json.loads(r["answers_json"] or "{}"),
                    operator_verified=bool(r["operator_verified"]),
                )
                self._requests[req.action_id] = req
                if state == ApprovalState.CONSUMED:
                    self._consumed_nonces.add(req.nonce)
                rehydrated += 1
        return rehydrated

    def create_request(
        self,
        *,
        session_id: str,
        task_id: str,
        command: list[str],
        workspace_path: str,
        questions: list[str] | None = None,
        ttl_seconds: float | None = None,
    ) -> OperatorApprovalRequest:
        if not session_id or not task_id or not command or not workspace_path:
            raise ValueError("session_id, task_id, command, and workspace_path are required")

        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        if not 0 < ttl <= 86400:
            raise ValueError("ttl_seconds must be in (0, 86400]")

        now = time.time()
        nonce = token_hex(16)
        c_digest = canonical_command_digest(command, workspace_path, task_id)
        raw_id = f"{session_id}:{task_id}:{c_digest}:{nonce}"
        action_id = f"act_{hashlib.sha256(raw_id.encode()).hexdigest()[:16]}"

        req = OperatorApprovalRequest(
            action_id=action_id,
            session_id=session_id,
            task_id=task_id,
            command=[str(x) for x in command],
            workspace_path=str(Path(workspace_path).resolve()),
            nonce=nonce,
            created_at=now,
            expires_at=now + ttl,
            state=ApprovalState.BLOCKED,
            questions=list(questions or []),
        )

        with self._lock:
            self._requests[action_id] = req
            self._persist_request(req)

        if self.ledger:
            self.ledger.append(
                stream="operator_approvals",
                idempotency_key=action_id,
                event_type="REQUEST_CREATED",
                payload={
                    "action_id": action_id,
                    "session_id": session_id,
                    "task_id": task_id,
                    "command_digest": c_digest,
                    "nonce": nonce,
                    "expires_at": req.expires_at,
                },
            )

        return deepcopy(req)

    def _expire_if_due(self, req: OperatorApprovalRequest, now: float) -> OperatorApprovalRequest:
        """Expire active actions without overwriting a terminal row in another process.

        Caller holds the local RLock. A stale supervisor rehydrates its view
        if a concurrent terminal transition won in the durable store.
        """
        if now < req.expires_at or req.state not in (
            ApprovalState.BLOCKED, ApprovalState.QUESTION_PENDING, ApprovalState.APPROVED,
        ):
            return req
        expired = deepcopy(req)
        expired.state = ApprovalState.EXPIRED
        try:
            self._persist_request(expired, expected=req)
        except PermissionError:
            if self.db_path is not None:
                self.rehydrate_from_disk()
                return self._requests.get(req.action_id, expired)
            return expired
        self._requests[req.action_id] = expired
        return expired

    def resolve_by_operator(
        self,
        action_id: str,
        *,
        decision: OperatorDecision,
        operator: OperatorIdentity,
        notes: str = "",
        answers: Mapping[str, str] | None = None,
    ) -> OperatorApprovalRequest:
        """Resolve only after a trusted external verifier authenticates the assertion."""
        if not isinstance(decision, OperatorDecision):
            raise TypeError("decision must be an instance of OperatorDecision")
        if not isinstance(operator, OperatorIdentity):
            raise TypeError("operator must be an instance of OperatorIdentity")
        if self._operator_verifier is None:
            raise PermissionError("DENIED: independently authenticated operator verifier is not configured")
        try:
            verified = self._operator_verifier(operator)
        except Exception as exc:
            raise PermissionError("DENIED: operator identity verification failed") from exc
        if verified is not True:
            raise PermissionError("DENIED: operator identity has not been authenticated")
        if operator.role not in ("security_lead", "security_admin", "operator"):
            raise PermissionError("DENIED: authenticated operator role cannot resolve approvals")

        now = time.time()
        with self._lock:
            req = self._requests.get(action_id)
            if not req:
                raise KeyError(f"unknown action_id {action_id!r}")

            if req.state in (ApprovalState.BLOCKED, ApprovalState.QUESTION_PENDING) and now >= req.expires_at:
                self._expire_if_due(req, now)
                raise PermissionError("Approval request has expired")

            if req.state != ApprovalState.BLOCKED and req.state != ApprovalState.QUESTION_PENDING:
                raise PermissionError(f"Action {action_id!r} cannot be resolved in state {req.state.value}")

            if req.nonce in self._consumed_nonces:
                raise PermissionError("Action nonce already consumed (replay prevented)")

            if self._decision_verifier is not None:
                # Recompute challenge inside the trusted state lock. A signed
                # login bearer token from a different action/decision cannot
                # serve as transaction authorization for this request.
                try:
                    authorized = self._decision_verifier(deepcopy(req), decision, operator)
                except Exception as exc:
                    raise PermissionError("DENIED: action-bound decision verification failed") from exc
                if authorized is not True:
                    raise PermissionError("DENIED: action-specific operator proof invalid")

            # Copy-on-write: never expose APPROVED in memory before both the
            # audit append and durable state persistence succeed. These stores
            # are not atomically coupled, so a failed later step stays BLOCKED.
            updated = deepcopy(req)
            updated.decision = decision
            updated.operator_id = operator.operator_id
            updated.operator_role = operator.role
            updated.operator_channel = operator.channel
            updated.operator_notes = notes
            updated.operator_verified = True

            if decision == OperatorDecision.ALLOW_ONCE:
                updated.state = ApprovalState.APPROVED
            elif decision == OperatorDecision.DENY:
                updated.state = ApprovalState.DENIED
            elif decision == OperatorDecision.ANSWER_QUESTIONS:
                updated.state = ApprovalState.QUESTION_PENDING
                if answers:
                    updated.answers.update(dict(answers))

            if self.ledger:
                idemp_key = f"{action_id}:decision:{decision.value}:{len(updated.answers)}"
                self.ledger.append(
                    stream="operator_approvals",
                    idempotency_key=idemp_key,
                    event_type="OPERATOR_DECISION",
                    payload={
                        "action_id": action_id,
                        "decision": decision.value,
                        "operator_id": operator.operator_id,
                        "operator_role": operator.role,
                        "operator_channel": operator.channel,
                        "state": updated.state.value,
                        "notes": notes,
                        "answers": dict(updated.answers),
                    },
                )

            self._persist_request(updated, expected=req)
            self._requests[action_id] = updated

        return deepcopy(updated)

    def consume_for_execution(
        self,
        action_id: str,
        *,
        session_id: str,
        task_id: str,
        command: list[str],
        workspace_path: str,
        ticket_ttl_seconds: float = 60.0,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """Atomically consumes one-time approval and issues HMAC ticket for IPC."""
        if not 0 < ticket_ttl_seconds <= 60:
            return False, "DENIED: ticket TTL must be within (0, 60] seconds", None

        now = time.time()
        with self._lock:
            req = self._requests.get(action_id)
            if not req:
                return False, f"DENIED: unknown action {action_id!r}", None

            if now >= req.expires_at:
                self._expire_if_due(req, now)
                return False, "DENIED: approval expired", None

            if req.state != ApprovalState.APPROVED:
                return False, f"DENIED: action is in state {req.state.value}, not APPROVED", None
            if not req.operator_verified:
                return False, "DENIED: approval has no verified operator provenance", None
            if self._operator_verifier is None:
                return False, "DENIED: operator authentication boundary is unavailable", None

            if req.nonce in self._consumed_nonces:
                return False, "DENIED: approval already consumed (replay prevented)", None

            if req.session_id != session_id:
                return False, f"DENIED: session {req.session_id!r} mismatch with {session_id!r}", None

            if req.task_id != task_id:
                return False, f"DENIED: task {req.task_id!r} mismatch with {task_id!r}", None

            expected_digest = canonical_command_digest(req.command, req.workspace_path, req.task_id)
            actual_digest = canonical_command_digest(command, workspace_path, task_id)
            if expected_digest != actual_digest:
                return False, "DENIED: command or workspace mismatch with approved action", None

            # Cross-process single-use consumption must be asserted by the
            # database, not just this instance's RLock/in-memory nonce set.
            # A stale supervisor may hold its own APPROVED snapshot.
            if self.db_path is not None:
                try:
                    with sqlite3.connect(self.db_path, timeout=5.0) as conn:
                        conn.execute("PRAGMA busy_timeout=5000")
                        conn.execute("BEGIN IMMEDIATE")
                        result = conn.execute(
                            "UPDATE operator_approvals SET state=? "
                            "WHERE action_id=? AND state=? AND nonce=? "
                            "AND operator_verified=1 AND expires_at>?",
                            (
                                ApprovalState.CONSUMED.value,
                                req.action_id,
                                ApprovalState.APPROVED.value,
                                req.nonce,
                                now,
                            ),
                        )
                        if result.rowcount != 1:
                            return False, "DENIED: durable approval already consumed or changed", None
                except sqlite3.Error:
                    return False, "DENIED: durable approval store unavailable", None

            req.state = ApprovalState.CONSUMED
            self._consumed_nonces.add(req.nonce)

        # Issue single-use HMAC ticket
        expiry = now + ticket_ttl_seconds
        payload_str = f"{action_id}:{session_id}:{task_id}:{actual_digest}:{req.nonce}:{expiry:.3f}"
        sig = hmac.new(self._secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()

        ticket = {
            "action_id": action_id,
            "session_id": session_id,
            "task_id": task_id,
            "command_digest": actual_digest,
            "nonce": req.nonce,
            "expiry": expiry,
            "signature": sig,
        }

        if self.ledger:
            self.ledger.append(
                stream="operator_approvals",
                idempotency_key=f"{action_id}:consume",
                event_type="APPROVAL_CONSUMED",
                payload={
                    "action_id": action_id,
                    "session_id": session_id,
                    "task_id": task_id,
                    "nonce": req.nonce,
                },
            )

        return True, "APPROVED", ticket

    def get_request(self, action_id: str) -> OperatorApprovalRequest | None:
        with self._lock:
            req = self._requests.get(action_id)
            if req is not None:
                req = self._expire_if_due(req, time.time())
            return deepcopy(req) if req is not None else None

    def list_pending(self) -> list[OperatorApprovalRequest]:
        now = time.time()
        with self._lock:
            pending: list[OperatorApprovalRequest] = []
            for req in list(self._requests.values()):
                current = self._expire_if_due(req, now)
                if current.state in (ApprovalState.BLOCKED, ApprovalState.QUESTION_PENDING):
                    pending.append(deepcopy(current))
            return pending
