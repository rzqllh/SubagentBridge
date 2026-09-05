# Runner Spec — Adding a New Backend

Every runner implements the `AgentRunner` interface (own implementation, same contract shape
as the reviewed upstream design):

```python
class AgentRunner(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def build_command(self, message: str, session: "Session",
                       json_schema: str | None = None) -> list[str]: ...

    @abstractmethod
    def parse_event(self, data: dict) -> tuple[str, Any]: ...
```

Canonical `(kind, payload)` values `parse_event` must return:

| kind | payload | meaning |
|---|---|---|
| `init` | `str` | backend's conversation/session id |
| `text` | `str` | incremental text delta |
| `tool_call` | `dict` | tool invocation the subagent made |
| `thought` | `dict` | reasoning/thinking block |
| `result` | `dict {"input_tokens": int, "output_tokens": int}` | final usage stats |
| `unknown` | `None` | safely ignorable event |

## CLI-backed runners (`agy`, `claude`)

Straightforward: `build_command` returns the real binary's argv, `parse_event` translates
that binary's native stream-json shape.

## API-backed runners (`gpt-sol`, `gpt-luna`, `deepseek-v4-flash`)

These do **not** call the vendor API directly from the runner class. Instead:

1. `build_command` returns argv for a **local wrapper script**
   (`wrappers/gpt_wrapper.py` or `wrappers/deepseek_wrapper.py`), e.g.:
   ```python
   ["python", "wrappers/gpt_wrapper.py", "-p", message,
    "--output-format", "stream-json", "--model", session.model or "gpt-5.6-sol"]
   ```
2. The wrapper script (not the runner class) holds the actual API-calling logic: it streams
   the vendor's chat completion response and re-emits it on stdout, one JSON object per line,
   in a shape the runner's `parse_event` understands.
3. `parse_event` in `GptRunner`/`DeepSeekRunner` is trivial because we control the wrapper's
   output format — make it emit the canonical kinds directly, no translation needed.

This isolates all HTTP/API/auth concerns in the wrapper layer, keeps `manager.py` and the
subprocess execution model completely unaware of the difference between a real CLI and a
wrapped API call, and matches the extension point already implied by
`register_runner()`-style registries.

## Checklist for a New Runner

- [ ] `runners/<name>_runner.py` implementing `AgentRunner`
- [ ] If API-backed: `wrappers/<name>_wrapper.py` implementing the stream-json contract
- [ ] Register in `runners/__init__.py`
- [ ] Document required env vars in `SECURITY.md` and `API_REFERENCE.md`
- [ ] Add a test case to `TEST_PLAN.md`
