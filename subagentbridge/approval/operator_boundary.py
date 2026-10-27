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
    ) -> None:
        if not 0 < default_ttl_seconds <= 86400:
            raise ValueError("default_ttl_seconds must be within (0, 86400]")
        self.default_ttl = default_ttl_seconds
        # Production must inject a trusted out-of-process/OIDC/WebAuthn assertion
        # verifier. A caller-constructed OperatorIdentity is never authentication.
        # No verifier => ALLOW_ONCE, DENY and ANSWER_QUESTIONS all fail closed.
        self._operator_verifier = operator_verifier
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
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
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

    def _persist_request(self, req: OperatorApprovalRequest) -> None:
        if not self.db_path:
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO operator_approvals (
                    action_id, session_id, task_id, command_json, workspace_path,
                    nonce, created_at, expires_at, state, decision,
                    operator_id, operator_role, operator_channel, operator_notes,
                    questions_json, answers_json, operator_verified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                req.action_id,
                req.session_id,
                req.task_id,
                json.dumps(req.command),
                req.workspace_path,
                req.nonce,
                req.created_at,
                req.expires_at,
                req.state.value,
                req.decision.value if req.decision else None,
                req.operator_id,
                req.operator_role,
                req.operator_channel,
                req.operator_notes,
                json.dumps(req.questions),
                json.dumps(req.answers),
                int(req.operator_verified),
            ))

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
                req.state = ApprovalState.EXPIRED
                self._persist_request(req)
                raise PermissionError("Approval request has expired")

            if req.state != ApprovalState.BLOCKED and req.state != ApprovalState.QUESTION_PENDING:
                raise PermissionError(f"Action {action_id!r} cannot be resolved in state {req.state.value}")

            if req.nonce in self._consumed_nonces:
                raise PermissionError("Action nonce already consumed (replay prevented)")

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

            self._persist_request(updated)
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
                req.state = ApprovalState.EXPIRED
                self._persist_request(req)
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

            # Mark consumed
            req.state = ApprovalState.CONSUMED
            self._consumed_nonces.add(req.nonce)
            self._persist_request(req)

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
            if req and req.state in (ApprovalState.BLOCKED, ApprovalState.APPROVED, ApprovalState.QUESTION_PENDING):
                if time.time() >= req.expires_at:
                    req.state = ApprovalState.EXPIRED
                    self._persist_request(req)
            return deepcopy(req) if req is not None else None

    def list_pending(self) -> list[OperatorApprovalRequest]:
        now = time.time()
        with self._lock:
            pending: list[OperatorApprovalRequest] = []
            for req in self._requests.values():
                if req.state in (ApprovalState.BLOCKED, ApprovalState.QUESTION_PENDING):
                    if now >= req.expires_at:
                        req.state = ApprovalState.EXPIRED
                        self._persist_request(req)
                    else:
                        pending.append(deepcopy(req))
            return pending
