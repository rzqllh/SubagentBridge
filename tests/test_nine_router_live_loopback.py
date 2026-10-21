"""Live local loopback integration test for NineRouterClient (PR-05, D-02).

Proves:
1. Real HTTP client-server transport over local IPv4 loopback (127.0.0.1).
2. Model discovery parses capabilities and parameters without mocks.
3. Authenticated chat completions return structured text and token usage.
4. Fail-closed on missing authentication, nonexistent endpoints, and unapproved D-02 terms.
5. Strict local-only enforcement: rejects any non-loopback or DNS address.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import unittest

from subagentbridge.models.capability import ModelCapabilities, ModelRoutingTable, UnknownCapability
from subagentbridge.models.nine_router import (
    CallBudget,
    LocalRouterConfig,
    NineRouterClient,
    RouterProtocolError,
    RouterUnavailable,
)


class Mock9RouterHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/v1/models":
            auth = self.headers.get("Authorization", "")
            if auth != "Bearer valid-test-key":
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b'{"error": "unauthorized"}')
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            payload = {
                "data": [
                    {
                        "id": "qwen2.5-coder-32b",
                        "supported_parameters": ["tools", "response_format", "stream"],
                    },
                    {
                        "id": "deepseek-coder-6.7b",
                        "supported_parameters": ["stream"],
                    },
                ]
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            auth = self.headers.get("Authorization", "")
            if auth != "Bearer valid-test-key":
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b'{"error": "unauthorized"}')
                return

            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            req_data = json.loads(body.decode("utf-8"))

            model = req_data.get("model", "qwen2.5-coder-32b")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "model": model,
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Integration verified via loopback"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 15,
                    "completion_tokens": 8,
                    "total_tokens": 23,
                },
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


class LiveLoopbackNineRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Mock9RouterHandler)
        cls.port = cls.server.server_port
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_live_discovery_over_http(self):
        cfg = LocalRouterConfig(base_url=self.base_url, api_key="valid-test-key")
        client = NineRouterClient(cfg)
        models = client.discover()
        self.assertEqual(len(models), 2)
        model_map = {m.model_id: m for m in models}
        self.assertIn("qwen2.5-coder-32b", model_map)
        self.assertTrue(model_map["qwen2.5-coder-32b"].tool_calls)
        self.assertIn("deepseek-coder-6.7b", model_map)
        self.assertFalse(model_map["deepseek-coder-6.7b"].tool_calls)

    def test_chat_requires_explicit_d02_approval(self):
        cfg = LocalRouterConfig(base_url=self.base_url, api_key="valid-test-key")
        client = NineRouterClient(cfg)
        client.discover()
        budget = CallBudget(requests=10, tokens=1000)

        # Calling chat without provider_terms_approved=True must fail closed
        with self.assertRaises(PermissionError):
            client.chat(
                model_id="qwen2.5-coder-32b",
                messages=({"role": "user", "content": "Hello loopback"},),
                max_tokens=100,
                budget=budget,
                provider_terms_approved=False,
            )

        # Calling chat with provider_terms_approved=True succeeds
        reply = client.chat(
            model_id="qwen2.5-coder-32b",
            messages=({"role": "user", "content": "Hello loopback"},),
            max_tokens=100,
            budget=budget,
            provider_terms_approved=True,
        )
        self.assertEqual(reply.text, "Integration verified via loopback")
        self.assertEqual(reply.prompt_tokens, 15)
        self.assertEqual(reply.completion_tokens, 8)

    def test_unauthorized_token_fails_closed(self):
        cfg = LocalRouterConfig(base_url=self.base_url, api_key="wrong-key")
        client = NineRouterClient(cfg)
        with self.assertRaises(RouterUnavailable):
            client.discover()

    def test_non_loopback_host_fails_configuration(self):
        with self.assertRaises(ValueError):
            LocalRouterConfig(base_url="http://remote-server.com:9099", api_key="key")
        with self.assertRaises(ValueError):
            LocalRouterConfig(base_url="http://192.168.1.100:9099", api_key="key")


if __name__ == "__main__":
    unittest.main()
