"""PR-02 candidate: application-enforced, versioned append-only SQLite ledger.

This is *not* an authenticated, OS-isolated, tamper-proof audit system.
An administrator able to rewrite the SQLite file and its chain anchors can forge data.
No existing runtime path is enabled by importing this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Mapping

GENESIS = "0" * 64
SCHEMA_VERSION = 1
_PRIVATE_KEYS = frozenset({"api_key", "authorization", "access_token", "refresh_token", "secret", "password", "credential", "credentials", "private_key"})
_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_schema (component TEXT PRIMARY KEY, version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  stream TEXT NOT NULL,
  seq INTEGER NOT NULL CHECK (seq > 0),
  idempotency_key TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  prev_sha TEXT NOT NULL,
  event_sha TEXT NOT NULL,
  created_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (stream, seq), UNIQUE (stream, idempotency_key)
);
CREATE INDEX IF NOT EXISTS audit_stream_order ON audit_events(stream, seq);
CREATE TABLE IF NOT EXISTS recovery_state (
  stream TEXT NOT NULL,
  session_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('RECOVERY_REQUIRED', 'RECONCILED_CLOSED')),
  cause TEXT NOT NULL,
  PRIMARY KEY (stream, session_id)
);
"""


class LedgerIntegrityError(RuntimeError):
    pass


class ReplayConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AuditEvent:
    stream: str
    seq: int
    idempotency_key: str
    event_type: str
    payload: dict[str, Any]
    prev_sha: str
    event_sha: str


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _scrub(value: Any) -> Any:
    """Best-effort key redaction; callers must keep opaque secrets out of free text."""
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("event mapping keys must be strings")
            result[key] = "[REDACTED]" if key.lower().replace("-", "_") in _PRIVATE_KEYS else _scrub(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_scrub(x) for x in value]
    if value is None or type(value) in (str, bool, int, float):
        return value
    raise ValueError("event payload contains a non-JSON type")


def _digest(stream: str, seq: int, key: str, kind: str, payload_json: str, prev_sha: str) -> str:
    return sha256(_canonical([SCHEMA_VERSION, stream, seq, key, kind, payload_json, prev_sha]).encode()).hexdigest()


class AuditLedger:
    """Scoped append/replay/verification interface; caller controls trusted stream IDs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            existing = self._conn.execute("SELECT version FROM audit_schema WHERE component='ledger'").fetchone()
            if existing is None:
                self._conn.execute("INSERT INTO audit_schema VALUES ('ledger', ?)", (SCHEMA_VERSION,))
            elif existing[0] != SCHEMA_VERSION:
                self._conn.close()
                raise LedgerIntegrityError("unsupported audit ledger schema version")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def append(self, *, stream: str, idempotency_key: str, event_type: str, payload: Mapping[str, Any]) -> AuditEvent:
        if not isinstance(stream, str) or not stream.strip() or not isinstance(idempotency_key, str) or not idempotency_key.strip() or not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("nonempty stream, key and event type required")
        if not isinstance(payload, Mapping):
            raise ValueError("payload must be a mapping")
        data = _scrub(payload)
        payload_json = _canonical(data)
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                # Fail closed if the existing chain is broken before appending.
                existing = self._read_rows(stream)
                self._check_rows(stream, existing)
                replay = self._conn.execute("SELECT seq, event_type, payload_json, prev_sha, event_sha FROM audit_events WHERE stream=? AND idempotency_key=?", (stream, idempotency_key)).fetchone()
                if replay:
                    seq, old_type, old_payload, prior, digest = replay
                    if old_type != event_type or old_payload != payload_json:
                        raise ReplayConflict("idempotency key reused for a different event")
                    self._conn.execute("COMMIT")
                    return AuditEvent(stream, seq, idempotency_key, event_type, data, prior, digest)
                seq = len(existing) + 1
                prev = existing[-1][4] if existing else GENESIS
                digest = _digest(stream, seq, idempotency_key, event_type, payload_json, prev)
                self._conn.execute("INSERT INTO audit_events (stream, seq, idempotency_key, event_type, payload_json, prev_sha, event_sha) VALUES (?, ?, ?, ?, ?, ?, ?)", (stream, seq, idempotency_key, event_type, payload_json, prev, digest))
                self._conn.execute("COMMIT")
                return AuditEvent(stream, seq, idempotency_key, event_type, data, prev, digest)
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

    def _read_rows(self, stream: str) -> list[tuple]:
        return self._conn.execute("SELECT seq, idempotency_key, event_type, payload_json, event_sha, prev_sha FROM audit_events WHERE stream=? ORDER BY seq", (stream,)).fetchall()

    @staticmethod
    def _check_rows(stream: str, rows: list[tuple]) -> str:
        prev = GENESIS
        for expected_seq, (seq, key, kind, payload_json, event_sha, prev_sha) in enumerate(rows, 1):
            if seq != expected_seq or prev_sha != prev or _digest(stream, seq, key, kind, payload_json, prev) != event_sha:
                raise LedgerIntegrityError("audit chain integrity mismatch")
            prev = event_sha
        return prev

    def verify(self, *, stream: str, expected_tail: str | None = None) -> str:
        with self._lock:
            tail = self._check_rows(stream, self._read_rows(stream))
            if expected_tail is not None and tail != expected_tail:
                raise LedgerIntegrityError("stream tail no longer matches external checkpoint")
            return tail

    def read(self, *, stream: str, reader_stream: str) -> list[AuditEvent]:
        if stream != reader_stream:
            raise PermissionError("cross-stream audit read denied")
        with self._lock:
            rows = self._read_rows(stream)
            self._check_rows(stream, rows)
            return [AuditEvent(stream, seq, key, kind, json.loads(body), prev_sha, event_sha) for seq, key, kind, body, event_sha, prev_sha in rows]

    def backup_to(self, destination: str | Path) -> None:
        destination = Path(destination)
        if destination.resolve() == self.path.resolve():
            raise ValueError("backup cannot overwrite its source")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, closing(sqlite3.connect(destination)) as dest:
            self._conn.backup(dest)

    def note_unreconciled(self, *, stream: str, session_id: str, cause: str) -> None:
        if not (stream and session_id and cause):
            raise ValueError("recovery identity and cause required")
        with self._lock:
            self._conn.execute("INSERT INTO recovery_state VALUES (?, ?, 'RECOVERY_REQUIRED', ?) ON CONFLICT(stream, session_id) DO UPDATE SET state='RECOVERY_REQUIRED', cause=excluded.cause", (stream, session_id, cause))

    def recovery_state(self, *, stream: str, session_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT state FROM recovery_state WHERE stream=? AND session_id=?", (stream, session_id)).fetchone()
            return row[0] if row else None

    def reconcile_closed(self, *, stream: str, session_id: str, evidence_key: str) -> None:
        """Atomically append reconciliation proof and close recovery state.

        The old implementation committed the event before updating the
        recovery row. A failed update could leave an apparent reconciliation
        receipt but an unresolved session. Both operations now share one
        SQLite IMMEDIATE transaction. This does not establish OS ownership
        or genuine process termination; evidence_key is still caller-claimed.
        """
        if not (stream and session_id and evidence_key):
            raise ValueError("reconciliation needs scoped stream/session/evidence")
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT state FROM recovery_state WHERE stream=? AND session_id=?",
                    (stream, session_id)).fetchone()
                if row is None or row[0] != "RECOVERY_REQUIRED":
                    raise ValueError("no unresolved recovery checkpoint")
                existing = self._read_rows(stream)
                self._check_rows(stream, existing)
                key = "recovery:" + session_id + ":" + evidence_key
                if self._conn.execute(
                    "SELECT 1 FROM audit_events WHERE stream=? AND idempotency_key=?",
                    (stream, key)).fetchone():
                    raise ReplayConflict("reconciliation key already used")
                data = {"session_id": session_id, "evidence_key": evidence_key}
                payload_json = _canonical(data)
                seq = len(existing) + 1
                prev = existing[-1][4] if existing else GENESIS
                digest = _digest(stream, seq, key, "RECOVERY_RECONCILED", payload_json, prev)
                self._conn.execute(
                    "INSERT INTO audit_events (stream, seq, idempotency_key, event_type, "
                    "payload_json, prev_sha, event_sha) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (stream, seq, key, "RECOVERY_RECONCILED", payload_json, prev, digest))
                self._conn.execute(
                    "UPDATE recovery_state SET state='RECONCILED_CLOSED' "
                    "WHERE stream=? AND session_id=?", (stream, session_id))
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
