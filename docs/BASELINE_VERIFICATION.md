# Baseline implementation status (PR-00 candidate)

This is a **source-level assessment**, not verified runtime safety, release approval, or a security claim.

Observed baseline on GitHub main `2a467bd4a82c65a30931554acef879fda9794a5f`:
- FastMCP tool surface exists (`subagentbridge/server.py`).
- Manager and SQLite persistence exist (`subagentbridge/manager.py`, `subagentbridge/storage/sqlite_store.py`).
- Concrete runner registry is empty (`subagentbridge/runners/__init__.py`).
- Team Rules v2, approval origin, role-scoped filesystem isolation, deterministic test receipts, and QA VERIFIED engine were **not** implemented or proven at baseline.
- Git branch `hardening/m2.5-runtime-safety` exists with 9 commits ahead of main (observed 2026-10-19); do not silently discard its changes or enable its bypass-permissions mode.

Known dangerous assumptions requiring verified fixes:
1. MCP `approve_action` exposed as an agent tool is not proof of human origin.
2. Stdout `tool_call` processing after a CLI executes is not an interception boundary.
3. Worktree, Python subprocess kill, Windows Job Object and command allowlist alone do not provide full filesystem/network sandboxing.
4. SQLite WAL alone is not tamper resistance against a same-user process.
5. An LLM-produced command output or hash is a claim, not executor-owned receipt.
6. A no-op/verifier-fake must never be available in production to generate VERIFIED.

Until the relevant code, negative tests and independent verdict exist, each guarantee above remains **UNVERIFIED**.
