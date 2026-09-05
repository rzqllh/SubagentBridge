"""Antigravity CLI runner.

Targets agy CLI 1.1.10+ print mode with ``stream-json`` output. The parser is
based on the stream shape verified against agy 1.1.10 on 2026-09-06 and stays
defensive about additional fields or future event types.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .base import AgentRunner, ParsedEvent


class AgyRunner(AgentRunner):
    """Runner for the Google Antigravity CLI (``agy``)."""

    name = "agy"
    requires_local_cli = True

    def build_command(
        self,
        message: str,
        *,
        workspace_path: str,
        model: Optional[str] = None,
        agent_type: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        skip_permissions: bool = True,
        json_schema: Optional[dict] = None,
        is_retry: bool = False,
        retry_context: Optional[str] = None,
    ) -> list[str]:
        cmd = ["agy", "--print", message, "--output-format", "stream-json"]

        if workspace_path:
            cmd.extend(["--add-dir", workspace_path])
        if model:
            cmd.extend(["--model", model])
        if agent_type:
            cmd.extend(["--agent", agent_type])
        if reasoning_effort:
            cmd.extend(["--effort", reasoning_effort])
        if skip_permissions:
            cmd.append("--dangerously-skip-permissions")
        if json_schema:
            cmd.extend(["--json-schema", json.dumps(json_schema, separators=(",", ":"))])

        return cmd

    def parse_event(self, raw_line: str) -> Optional[ParsedEvent]:
        raw_line = raw_line.strip()
        if not raw_line:
            return None

        try:
            data = json.loads(raw_line)
        except (json.JSONDecodeError, TypeError):
            return ParsedEvent("unknown", {"raw": raw_line})

        if not isinstance(data, dict):
            return ParsedEvent("unknown", {"raw": data})

        # Accept canonical events too. This keeps wrapper/fake-runner tests
        # simple and makes the parser tolerant of a future canonical stream.
        canonical_kind = data.get("kind")
        if canonical_kind:
            payload = data.get("payload", {})
            if not isinstance(payload, dict):
                payload = {"value": payload}
            return ParsedEvent(str(canonical_kind), payload)

        event_type = data.get("event") or data.get("type")

        if event_type == "init":
            conversation_id = data.get("conversation_id") or data.get("conversationId")
            payload: dict[str, Any] = {"conversation_id": conversation_id}
            if isinstance(data.get("init"), dict):
                payload["init"] = data["init"]
            return ParsedEvent("init", payload)

        if event_type == "step_update":
            step = data.get("step_update") or data.get("stepUpdate") or {}
            if not isinstance(step, dict):
                return ParsedEvent("unknown", {"raw": data})

            step_type = step.get("step_type") or step.get("stepType") or step.get("type")

            if step_type == "agent_response":
                text = step.get("text_delta")
                if text is None:
                    text = step.get("text") or step.get("content") or ""
                payload = {"text": text}
                # agy 1.1.10 also reports provisional usage on this step.
                # Keep it for diagnostics, but manager accounting uses only
                # the final result event so tokens are not double-counted.
                if isinstance(step.get("usage"), dict):
                    payload["step_usage"] = dict(step["usage"])
                return ParsedEvent("text", payload)

            if step_type == "tool_call":
                nested = step.get("tool_call") or step.get("toolCall")
                payload: dict[str, Any]
                if isinstance(nested, dict):
                    payload = dict(nested)
                    payload.setdefault("_step", step)
                else:
                    payload = dict(step)
                return ParsedEvent("tool_call", payload)

            if step_type == "thought":
                return ParsedEvent("thought", dict(step))

            # user_input/checkpoint/unknown steps are intentionally retained
            # for diagnostics without being treated as actionable events.
            return ParsedEvent("unknown", {"raw": data})

        if event_type == "result":
            # Verified agy 1.1.10 shape:
            # {"event":"result","result":{"status":"SUCCESS", ...,
            #   "usage":{"input_tokens":N,"output_tokens":N,...}}}
            result_obj = data.get("result")
            if not isinstance(result_obj, dict):
                result_obj = {}

            raw_usage = result_obj.get("usage") or data.get("usage") or {}
            if not isinstance(raw_usage, dict):
                raw_usage = {}

            usage = {
                "input_tokens": int(raw_usage.get("input_tokens") or raw_usage.get("inputTokens") or 0),
                "output_tokens": int(raw_usage.get("output_tokens") or raw_usage.get("outputTokens") or 0),
            }
            payload: dict[str, Any] = {
                "usage": usage,
                "result": result_obj,
            }
            return ParsedEvent("result", payload)

        return ParsedEvent("unknown", {"raw": data})
