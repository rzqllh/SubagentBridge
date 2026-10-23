"""tests/test_nine_router_authenticated_completion.py — Real Authenticated 9Router Completion Evidence.

Proves:
1. Genuine HTTP client-server communication over local IPv4 loopback (127.0.0.1).
2. Strict Bearer token authentication: requests without or with invalid token receive HTTP 401.
3. Authenticated completion returns real HTTP 200, parses assistant content and token usage.
4. Exact request evidence (method, path, Authorization header, payload) and response evidence.
5. End-to-end integration with SupervisedNativeLifecycle under D-02 approved terms.
6. Fail-closed rejection when D-02 terms are unapproved.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from subagentbridge.composition import build_production_system
from subagentbridge.execution.native_runtime import (
    SupervisedNativeLifecycle,
    TaskDecomposer,
    resolve_tree_sha,
)
from subagentbridge.models.capability import ModelCapabilities, ModelRoutingTable
from subagentbridge.models.nine_router import (
    CallBudget,
    LocalRouterConfig,
    NineRouterClient,
    RouterProtocolError,
    RouterUnavailable,
)
from subagentbridge.storage.sqlite_store import SQLiteStore

VALID_API_KEY = "simpul-authenticated-test-key-xyz"


class Authenticated9RouterHandler(BaseHTTPRequestHandler):
    requests_log: list[dict] = []

    def log_message(self, format, *args):
        pass  # Suppress default server logging

    def do_GET(self):
        auth_header = self.headers.get("Authorization", "")
        self.__class__.requests_log.append({
            "method": "GET",
            "path": self.path,
            "auth": auth_header,
        })

        if auth_header != f"Bearer {VALID_API_KEY}":
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Unauthorized: invalid router token"}')
            return

        if self.path == "/v1/models":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            payload = {
                "data": [
                    {
                        "id": "qwen2.5-coder-32b",
                        "supported_parameters": ["tools", "response_format", "stream"],
                    }
                ]
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        auth_header = self.headers.get("Authorization", "")
        content_len = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_len) if content_len > 0 else b""
        body_json = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}

        self.__class__.requests_log.append({
            "method": "POST",
            "path": self.path,
            "auth": auth_header,
            "body": body_json,
        })

        if auth_header != f"Bearer {VALID_API_KEY}":
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Unauthorized: invalid router token"}')
            return

        if self.path == "/v1/chat/completions":
            model = body_json.get("model", "qwen2.5-coder-32b")
            resp_payload = {
                "id": "chatcmpl-auth-test-001",
                "object": "chat.completion",
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Authenticated completion verified with valid Bearer token",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 42,
                    "completion_tokens": 18,
                    "total_tokens": 60,
                },
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp_payload).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


class TestNineRouterAuthenticatedCompletion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Authenticated9RouterHandler)
        cls.port = cls.server.server_port
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Authenticated9RouterHandler.requests_log.clear()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name).resolve()

        subprocess.run(["git", "init", "-q"], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)
        test_file = self.workspace / "tests" / "test_dummy.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def test_dummy(): pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)
        subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=str(self.workspace), stdin=subprocess.DEVNULL, check=True)

    def tearDown(self):
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_01_negative_unauthorized_request_rejected_with_401(self):
        """Prove requests with missing or invalid token receive HTTP 401 and raise RouterUnavailable."""
        # Client with wrong API key
        bad_config = LocalRouterConfig(base_url=self.base_url, api_key="invalid-wrong-key")
        bad_client = NineRouterClient(config=bad_config)

        # 1. Negative discovery
        with self.assertRaises(RouterUnavailable) as ctx:
            bad_client.discover()
        self.assertIn("local 9Router request failed", str(ctx.exception))

        # Verify request evidence recorded at server
        self.assertTrue(len(Authenticated9RouterHandler.requests_log) >= 1)
        last_req = Authenticated9RouterHandler.requests_log[-1]
        self.assertEqual(last_req["method"], "GET")
        self.assertEqual(last_req["path"], "/v1/models")
        self.assertEqual(last_req["auth"], "Bearer invalid-wrong-key")

        # 2. Negative chat completion (must set dummy models first to reach transport)
        bad_client.models = ModelRoutingTable([
            ModelCapabilities("qwen2.5-coder-32b", False, False, False, False, False)
        ])
        budget = CallBudget(requests=1, tokens=500)
        with self.assertRaises(RouterUnavailable) as ctx:
            bad_client.chat(
                model_id="qwen2.5-coder-32b",
                messages=({"role": "user", "content": "hello"},),
                budget=budget,
                provider_terms_approved=True,
                max_tokens=100,
            )
        self.assertIn("local 9Router request failed", str(ctx.exception))

        last_req2 = Authenticated9RouterHandler.requests_log[-1]
        self.assertEqual(last_req2["method"], "POST")
        self.assertEqual(last_req2["path"], "/v1/chat/completions")
        self.assertEqual(last_req2["auth"], "Bearer invalid-wrong-key")

    def test_02_positive_authenticated_chat_completion_with_full_evidence(self):
        """Prove authenticated local-router completion returns 200, parsed message, and token usage."""
        client = NineRouterClient(
            config=LocalRouterConfig(base_url=self.base_url, api_key=VALID_API_KEY)
        )

        # Model discovery
        caps = client.discover()
        discovered_ids = [m.model_id for m in caps]
        self.assertIn("qwen2.5-coder-32b", discovered_ids)

        # Chat completion
        budget = CallBudget(requests=1, tokens=500)
        chat_res = client.chat(
            model_id="qwen2.5-coder-32b",
            messages=(
                {"role": "system", "content": "You are an assistant."},
                {"role": "user", "content": "Generate task plan"},
            ),
            budget=budget,
            provider_terms_approved=True,
            max_tokens=100,
        )

        # Assert client parsed output
        self.assertEqual(chat_res.model, "qwen2.5-coder-32b")
        self.assertIn("Authenticated completion verified", chat_res.text)
        self.assertEqual(chat_res.prompt_tokens, 42)
        self.assertEqual(chat_res.completion_tokens, 18)
        self.assertEqual((chat_res.prompt_tokens or 0) + (chat_res.completion_tokens or 0), 60)

        # Verify exact server-side request evidence
        last_req = Authenticated9RouterHandler.requests_log[-1]
        self.assertEqual(last_req["method"], "POST")
        self.assertEqual(last_req["path"], "/v1/chat/completions")
        self.assertEqual(last_req["auth"], f"Bearer {VALID_API_KEY}")
        self.assertEqual(last_req["body"]["model"], "qwen2.5-coder-32b")
        self.assertEqual(len(last_req["body"]["messages"]), 2)

    def test_03_lifecycle_integration_with_real_authenticated_router(self):
        """Prove SupervisedNativeLifecycle executes with real authenticated 9Router calls and audit logging."""
        db_path = self.workspace / ".subagentbridge" / "audit_9router.db"
        prod_sys = build_production_system(
            workspace_root=self.workspace,
            db_path=db_path,
            nine_router_base_url=self.base_url,
            nine_router_api_key=VALID_API_KEY,
        )

        # Discover models from authenticated router
        prod_sys.nine_router.discover()

        store = SQLiteStore(db_path)
        run_id = "run_authenticated_router_001"
        store.upsert_run({
            "run_id": run_id,
            "goal": "Authenticated 9Router model integration test",
            "workspace_path": str(self.workspace),
            "status": "SUBMITTED",
            "model": "qwen2.5-coder-32b",
        })
        tree_sha = resolve_tree_sha(self.workspace)
        tasks_contracts, dependencies, task_records = TaskDecomposer.decompose_goal(
            goal="Authenticated 9Router model integration test",
            run_id=run_id,
            tree_sha=tree_sha,
        )

        for r in task_records:
            store.upsert_task(r)

        lifecycle = SupervisedNativeLifecycle(sys=prod_sys, workspace_path=self.workspace, store=store)
        coordinator, principals = lifecycle.create_coordinator_for_run(
            run_id=run_id,
            tasks=tasks_contracts,
            dependencies=dependencies,
        )

        # Execute lifecycle with consult_model=True and provider_terms_approved=True
        Authenticated9RouterHandler.requests_log.clear()
        result = lifecycle.execute_lifecycle(
            run_id=run_id,
            coordinator=coordinator,
            principals=principals,
            task_records=task_records,
            command_map={"default": [sys.executable, "-c", "print('model step ok')"]},
            consult_model=True,
            provider_terms_approved=True,
            model_id="qwen2.5-coder-32b",
        )

        self.assertEqual(result.get("status"), "COMPLETED")

        # Prove real authenticated HTTP requests occurred during the lifecycle
        router_posts = [
            r for r in Authenticated9RouterHandler.requests_log
            if r["method"] == "POST" and r["path"] == "/v1/chat/completions"
        ]
        self.assertTrue(len(router_posts) >= 1)
        for post in router_posts:
            self.assertEqual(post["auth"], f"Bearer {VALID_API_KEY}")

        # Check durable audit ledger contains MODEL_CONSULTED events with token counts
        stream_rows = prod_sys.ledger._read_rows(f"run:{run_id}")
        consulted_payloads = [json.loads(r[3]) for r in stream_rows if r[2] == "MODEL_CONSULTED"]
        self.assertTrue(len(consulted_payloads) >= 1)
        self.assertEqual(consulted_payloads[0]["prompt_tokens"], 42)
        self.assertEqual(consulted_payloads[0]["completion_tokens"], 18)

        store.close()

    def test_04_d02_fail_closed_when_terms_unapproved(self):
        """Prove lifecycle immediately fails closed under D-02 if provider terms are not approved."""
        db_path = self.workspace / ".subagentbridge" / "audit_d02.db"
        prod_sys = build_production_system(
            workspace_root=self.workspace,
            db_path=db_path,
            nine_router_base_url=self.base_url,
            nine_router_api_key=VALID_API_KEY,
        )

        store = SQLiteStore(db_path)
        run_id = "run_d02_unapproved"
        store.upsert_run({
            "run_id": run_id,
            "goal": "D-02 unapproved test",
            "workspace_path": str(self.workspace),
            "status": "SUBMITTED",
            "model": "default",
        })
        tree_sha = resolve_tree_sha(self.workspace)
        tasks_contracts, dependencies, task_records = TaskDecomposer.decompose_goal(
            goal="D-02 unapproved test",
            run_id=run_id,
            tree_sha=tree_sha,
        )

        for r in task_records:
            store.upsert_task(r)

        lifecycle = SupervisedNativeLifecycle(sys=prod_sys, workspace_path=self.workspace, store=store)
        coordinator, principals = lifecycle.create_coordinator_for_run(
            run_id=run_id,
            tasks=tasks_contracts,
            dependencies=dependencies,
        )

        Authenticated9RouterHandler.requests_log.clear()
        result = lifecycle.execute_lifecycle(
            run_id=run_id,
            coordinator=coordinator,
            principals=principals,
            task_records=task_records,
            command_map={"default": [sys.executable, "-c", "print('fail closed')"]},
            consult_model=True,
            provider_terms_approved=False,  # Unapproved!
        )

        self.assertEqual(result.get("status"), "FAILED")
        self.assertIn("D-02 provider terms review required", result.get("reason", ""))

        # Zero network requests sent!
        self.assertEqual(len(Authenticated9RouterHandler.requests_log), 0)

        store.close()


if __name__ == "__main__":
    unittest.main()
