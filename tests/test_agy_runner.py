import json
import unittest

from subagentbridge.runners.agy_runner import AgyRunner


class AgyRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = AgyRunner()

    def test_build_command_matches_verified_cli_flags(self) -> None:
        cmd = self.runner.build_command(
            "hello",
            workspace_path=r"C:\workspace",
            reasoning_effort="high",
            skip_permissions=True,
        )
        self.assertEqual(cmd[:5], ["agy", "--print", "hello", "--output-format", "stream-json"])
        self.assertIn("--add-dir", cmd)
        self.assertIn("--effort", cmd)
        self.assertIn("--dangerously-skip-permissions", cmd)

    def test_parse_verified_1_1_10_init(self) -> None:
        raw = json.dumps({
            "event": "init",
            "conversation_id": "conv-123",
            "init": {
                "cwd": r"C:\workspace",
                "tools": ["run_command", "view_file"],
                "permission_mode": "request-review",
            },
        })
        event = self.runner.parse_event(raw)
        self.assertIsNotNone(event)
        self.assertEqual(event.kind, "init")
        self.assertEqual(event.payload["conversation_id"], "conv-123")
        self.assertEqual(event.payload["init"]["permission_mode"], "request-review")

    def test_parse_verified_1_1_10_agent_response(self) -> None:
        raw = json.dumps({
            "event": "step_update",
            "step_update": {
                "conversation_id": "conv-123",
                "step_index": 2,
                "state": "DONE",
                "step_type": "agent_response",
                "text_delta": "SUBAGENTBRIDGE_STREAM_TEST.\n",
                "usage": {
                    "input_tokens": 27462,
                    "output_tokens": 150,
                    "thinking_tokens": 142,
                    "cache_read_tokens": 0,
                    "total_tokens": 27612,
                },
            },
        })
        event = self.runner.parse_event(raw)
        self.assertIsNotNone(event)
        self.assertEqual(event.kind, "text")
        self.assertEqual(event.payload["text"], "SUBAGENTBRIDGE_STREAM_TEST.\n")
        self.assertEqual(event.payload["step_usage"]["thinking_tokens"], 142)

    def test_parse_verified_1_1_10_result_usage(self) -> None:
        raw = json.dumps({
            "event": "result",
            "result": {
                "conversation_id": "conv-123",
                "status": "SUCCESS",
                "response": "SUBAGENTBRIDGE_STREAM_TEST.\n",
                "duration_seconds": 1.6698407,
                "num_turns": 1,
                "usage": {
                    "input_tokens": 27462,
                    "output_tokens": 150,
                    "thinking_tokens": 142,
                    "cache_read_tokens": 0,
                    "total_tokens": 27612,
                },
            },
        })
        event = self.runner.parse_event(raw)
        self.assertIsNotNone(event)
        self.assertEqual(event.kind, "result")
        self.assertEqual(event.payload["usage"]["input_tokens"], 27462)
        self.assertEqual(event.payload["usage"]["output_tokens"], 150)
        self.assertEqual(event.payload["result"]["status"], "SUCCESS")

    def test_unknown_step_is_preserved_not_raised(self) -> None:
        raw = json.dumps({
            "event": "step_update",
            "step_update": {"step_type": "checkpoint", "state": "DONE"},
        })
        event = self.runner.parse_event(raw)
        self.assertIsNotNone(event)
        self.assertEqual(event.kind, "unknown")


if __name__ == "__main__":
    unittest.main()
