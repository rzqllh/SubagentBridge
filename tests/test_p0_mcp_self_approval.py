"""P0: MCP callers must NEVER self-approve privileged execution."""
from __future__ import annotations

import ast
from pathlib import Path

from subagentbridge import server


def test_model_callable_approval_is_not_registered():
    names = {t.name for t in server.mcp._tool_manager.list_tools()}
    assert "approve_command" not in names
    assert "approve_action" not in names


def test_mcp_source_contains_no_approval_registration():
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "subagentbridge" / "server.py").read_text(encoding="utf-8"))
    funcs = {x.name: x for x in tree.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))}
    legacy = funcs["approve_command"]
    assert not any(ast.unparse(dec).startswith("mcp.tool") for dec in legacy.decorator_list)


def test_arbitrary_human_name_or_token_cannot_grant_mcp_approval():
    action = server._pending.enqueue("session-p0", {
        "operation": "UNAUTHORIZED_COMMAND",
        "command_list": ["python", "-c", "print('untrusted')"],
        "fingerprint": "bad-request-not-a-secret",
    })
    try:
        before = server._pending.list_pending()
        assert any(a.action_id == action.action_id for a in before)
        for claimed_identity, credential in (
            ("human", None), ("security_officer", None),
            ("administrator", "guess"),
            ("human", "human"),
            ("system", "any-model-supplied-string"),
        ):
            res = server.approve_command(
                action.action_id, approver=claimed_identity, auth_token=credential,
            )
            assert res["status"] == "BLOCKED"
            assert action.action_id not in [p.get("action_id") for p in server._approved_commands.values()]
            assert any(a.action_id == action.action_id for a in server._pending.list_pending())
    finally:
        # Rejection remains possible as a conservative fail-closed transition.
        server._pending.resolve(action.action_id, approved=False, reason="test cleanup")


def test_legacy_approval_function_never_records_approval():
    original = dict(server._approved_commands)
    response = server.approve_command("made-up", auth_token="fake-token")
    assert response["status"] == "BLOCKED"
    assert server._approved_commands == original
