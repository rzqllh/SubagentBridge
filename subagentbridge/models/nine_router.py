"""Local-only 9Router OpenAI-compatible API client (PR-05 candidate).

Non-streaming, no tool execution, no retry, no remote endpoint. The caller must
record a D-02 provider-terms decision *outside* this adapter before invoking
models. A flag is not identity proof; the runtime is NOT autonomy-capable.

The transport seam makes every test entirely offline. By default the client
only makes HTTP requests to literal loopback addresses without redirects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import ip_address
from json import dumps, loads, JSONDecodeError
from threading import Lock
from typing import Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .capability import ModelCapabilities, ModelRoutingTable, UnknownCapability
from subagentbridge.execution.tool_executor.supervised import SupervisedReadOnlyExecutor

MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class RouterProtocolError(RuntimeError):
    """An unusable or over-limit response. Never includes credential material."""


class RouterUnavailable(RuntimeError):
    """A transport failure without disclosing request/response secrets."""


class RequestBudgetExceeded(PermissionError):
    """Request or token budget exhausted before dispatch."""


@dataclass(frozen=True, slots=True)
class LocalRouterConfig:
    base_url: str
    api_key: str = field(repr=False)
    timeout_seconds: int = 15

    def __post_init__(self) -> None:
        p = urlsplit(self.base_url)
        # Explicit IPv4/IPv6 loopback *literal*; reject DNS names, credentials,
        # fragments, nonlocal hosts, paths, and implicit arbitrary protocols.
        try:
            ip = ip_address(p.hostname or '')
            port = p.port
        except (ValueError, TypeError) as exc:
            raise ValueError('router address must be a literal loopback IP') from exc
        if (p.scheme != 'http' or not ip.is_loopback or not port or p.username or p.password
                or p.path not in ('', '/') or p.query or p.fragment):
            raise ValueError('router must be an HTTP loopback origin with explicit port')
        if not self.api_key or '\n' in self.api_key or '\r' in self.api_key:
            raise ValueError('a well-formed in-memory router credential is required')
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 60:
            raise ValueError('timeout must be in 1..60 seconds')

    @property
    def origin(self) -> str:
        return self.base_url.rstrip('/')


class JsonTransport(Protocol):
    def request(self, *, config: LocalRouterConfig, method: str, path: str,
                payload: Mapping[str, object] | None) -> object:
        ...


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RouterUnavailable('router redirects are prohibited')


class LocalHttpTransport:
    """HTTP-only, loopback-only urllib implementation; no implicit redirects."""

    def request(self, *, config: LocalRouterConfig, method: str, path: str,
                payload: Mapping[str, object] | None) -> object:
        if (method, path) not in {('GET', '/v1/models'), ('POST', '/v1/chat/completions')}:
            raise PermissionError('endpoint not allowlisted')
        body = None if payload is None else dumps(payload, separators=(',', ':')).encode('utf-8')
        req = Request(config.origin + path, data=body, method=method,
                      headers={'Authorization': 'Bearer ' + config.api_key,
                               'Accept': 'application/json', 'Content-Type': 'application/json'})
        try:
            with build_opener(ProxyHandler({}), _NoRedirect).open(req, timeout=config.timeout_seconds) as response:
                if response.status != 200:
                    raise RouterUnavailable('router returned non-200 HTTP response')
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError):
            # NEVER propagate exception strings: urllib errors may contain headers,
            # proxy credentials, user URLs, or backend-supplied response bodies.
            raise RouterUnavailable('local 9Router request failed') from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise RouterProtocolError('router response exceeds limit')
        try:
            return loads(raw)
        except (UnicodeDecodeError, JSONDecodeError):
            raise RouterProtocolError('invalid router JSON response') from None


class CallBudget:
    """Pre-charge worst-case token allowance, never refund based on claims.

    An absent usage report does not grant free requests. Counters persist only
    within the owning process; cross-restart enforcement needs PR-02 ledger.
    """
    def __init__(self, *, requests: int, tokens: int):
        if type(requests) is not int or type(tokens) is not int or requests < 0 or tokens < 0:
            raise ValueError('nonnegative integer limits required')
        self.requests_left = requests
        self.tokens_left = tokens
        self._lock = Lock()

    def charge(self, max_tokens: int) -> None:
        if type(max_tokens) is not int or max_tokens <= 0:
            raise ValueError('positive max_tokens required')
        with self._lock:
            if self.requests_left < 1 or self.tokens_left < max_tokens:
                raise RequestBudgetExceeded('9Router request/token ceiling reached')
            self.requests_left -= 1
            self.tokens_left -= max_tokens


@dataclass(frozen=True, slots=True)
class ChatReply:
    model: str
    text: str
    finish_reason: str
    prompt_tokens: int | None
    completion_tokens: int | None
    tool_calls_pending: bool
    usage_class: str


class NineRouterClient:
    """Discovers models; issues text requests only when D-02 gate supplied.

    This adapter deliberately will not execute tools, stream, retry, or issue
    executor receipts. No worker or model text grants approval credentials.
    """
    def __init__(self, config: LocalRouterConfig, *, transport: JsonTransport | None = None):
        self.config = config
        self.transport = transport or LocalHttpTransport()
        self.models: ModelRoutingTable | None = None

    def discover(self) -> tuple[ModelCapabilities, ...]:
        obj = self.transport.request(config=self.config, method='GET', path='/v1/models', payload=None)
        if not isinstance(obj, dict) or not isinstance(obj.get('data'), list):
            raise RouterProtocolError('missing models data')
        result = []
        seen = set()
        for model in obj['data']:
            if not isinstance(model, dict) or not isinstance(model.get('id'), str) or not model['id'].strip():
                raise RouterProtocolError('invalid model identity')
            ident = model['id']
            if ident in seen:
                raise RouterProtocolError('duplicate model identity')
            seen.add(ident)
            # Treat undocumented / ambiguous metadata as UNKNOWN, not guessed.
            params = model.get('supported_parameters')
            params = set(params) if isinstance(params, list) and all(isinstance(v, str) for v in params) else None
            result.append(ModelCapabilities(ident,
                tool_calls=(None if params is None else 'tools' in params),
                structured_output=(None if params is None else 'response_format' in params),
                streaming=(None if params is None else 'stream' in params),
                input_cost_known=False, output_cost_known=False))
        self.models = ModelRoutingTable(result)
        return tuple(result)

    def chat(self, *, model_id: str, messages: tuple[Mapping[str, str], ...],
             max_tokens: int, budget: CallBudget, provider_terms_approved: bool = False,
             max_retries: int = 0) -> ChatReply:
        if provider_terms_approved is not True:
            raise PermissionError('D-02 review is required before model invocation')
        if type(max_retries) is not int or not 0 <= max_retries <= 5:
            raise ValueError('max_retries must be an integer between 0 and 5')
        if self.models is None:
            raise UnknownCapability('run model discovery before sending requests')
        if not model_id or self.models.select([model_id]).model_id != model_id:
            raise UnknownCapability('model not discovered')
        if (not isinstance(messages, tuple) or not messages or len(messages) > 64 or
            any(not isinstance(m, Mapping) or set(m) != {'role', 'content'} or
                m['role'] not in {'system', 'user', 'assistant'} or
                not isinstance(m['content'], str) or len(m['content']) > 100000
                for m in messages)):
            raise ValueError('bounded text-only role/content messages required')
        budget.charge(max_tokens)
        last_exc: RouterUnavailable | None = None
        obj: object = None
        for attempt in range(max_retries + 1):
            try:
                obj = self.transport.request(config=self.config, method='POST', path='/v1/chat/completions',
                      payload={'model': model_id, 'messages': list(messages), 'max_tokens': max_tokens,
                               'stream': False})
                break
            except RouterUnavailable as exc:
                last_exc = exc
                if attempt >= max_retries:
                    raise
        if obj is None and last_exc is not None:
            raise last_exc
        if not isinstance(obj, dict) or not isinstance(obj.get('choices'), list) or len(obj['choices']) != 1:
            raise RouterProtocolError('invalid chat choices')
        choice = obj['choices'][0]
        if not isinstance(choice, dict) or not isinstance(choice.get('message'), dict):
            raise RouterProtocolError('missing assistant message')
        message = choice['message']
        if message.get('tool_calls'):
            # Refuse execution and refrain from treating such responses as completed.
            return ChatReply(model_id, '', 'TOOL_CALLS_BLOCKED', None, None, True, 'unknown')
        content = message.get('content')
        finish = choice.get('finish_reason')
        if (not isinstance(content, str) or not isinstance(finish, str)
                or message.get('role') not in (None, 'assistant')):
            raise RouterProtocolError('invalid text assistant reply')
        usage = obj.get('usage')
        p = usage.get('prompt_tokens') if isinstance(usage, dict) else None
        c = usage.get('completion_tokens') if isinstance(usage, dict) else None
        p = p if type(p) is int and p >= 0 else None
        c = c if type(c) is int and c >= 0 else None
        return ChatReply(model_id, content, finish, p, c, False,
                         'actual' if p is not None and c is not None else 'unknown')

    def execute_safe_tool_call(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, object],
        executor: SupervisedReadOnlyExecutor,
        task_id: str = "inspection",
        dispatch_id: str = "inspection",
        human_supervised: bool = True,
    ) -> dict[str, object]:
        """Execute only strictly allowlisted, read-only inspection tools through SupervisedReadOnlyExecutor.

        Arbitrary execution, modifying commands, and unconfined paths are rejected.
        """
        if not human_supervised:
            raise PermissionError("Unsupervised tool execution is forbidden")
        if tool_name in ("read_file", "read_text"):
            path_val = arguments.get("path") or arguments.get("relative_path")
            if not isinstance(path_val, str) or not path_val.strip():
                raise ValueError("Valid relative path string required")
            content = executor.read_text(path_val)
            return {"status": "SUCCESS", "tool": tool_name, "content": content}
        elif tool_name == "git_status":
            receipt = executor.run_inspection(
                task_id=task_id,
                dispatch_id=dispatch_id,
                argv=("git", "status", "--porcelain"),
                human_supervised=human_supervised,
            )
            return {
                "status": "SUCCESS",
                "tool": tool_name,
                "receipt_id": receipt.receipt_id,
                "exit_code": receipt.exit_code,
            }
        elif tool_name == "git_rev_parse":
            target = arguments.get("target", "HEAD")
            if target == "HEAD":
                argv: tuple[str, ...] = ("git", "rev-parse", "HEAD")
            elif target in ("HEAD^{tree}", "tree"):
                argv = ("git", "rev-parse", "HEAD^{tree}")
            else:
                raise PermissionError(f"Target {target!r} not allowlisted for git_rev_parse")
            receipt = executor.run_inspection(
                task_id=task_id,
                dispatch_id=dispatch_id,
                argv=argv,
                human_supervised=human_supervised,
            )
            return {
                "status": "SUCCESS",
                "tool": tool_name,
                "receipt_id": receipt.receipt_id,
                "exit_code": receipt.exit_code,
            }
        else:
            raise PermissionError(f"Tool {tool_name!r} is not in the supervised read-only allowlist")

