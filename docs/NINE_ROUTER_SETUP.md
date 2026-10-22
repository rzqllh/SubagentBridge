# Simpul — Local 9Router client (candidate)

This guide describes `subagentbridge.models.nine_router` as implemented in the open PR #3 branch. It is **not** proof that 9Router account authentication or external provider routing works end-to-end.

## Transport boundary

`LocalRouterConfig` requires a literal IPv4/IPv6 **loopback IP**, explicit port and HTTP scheme, e.g. `http://127.0.0.1:9099`. Do **not** append `/v1` to the base URL; the client itself appends `/v1/models` or `/v1/chat/completions`. Hostnames, redirects, user info and non-loopback destinations are rejected.

The client performs text-only, nonstreaming completion. It does **not** execute model tool calls, retry requests automatically, issue executor receipts or authorize external provider terms. A local proxy may contact upstream providers using its own policy; the client's loopback restriction is not a zero-external-egress promise for the entire stack.

## Python example

Set a local router credential in your process environment before running this example; never commit it.

```python
import os
from subagentbridge.models.nine_router import (
    CallBudget, LocalRouterConfig, NineRouterClient
)

client = NineRouterClient(LocalRouterConfig(
    base_url="http://127.0.0.1:9099",
    api_key=os.environ["LOCAL_ROUTER_API_KEY"],
))

# Requires a running and authenticated local 9Router endpoint.
available = client.discover()
if not available:
    raise RuntimeError("No models returned by local router")

# Only after explicitly reviewing and authorizing provider terms/egress.
budget = CallBudget(requests=1, tokens=256)
reply = client.chat(
    model_id=available[0].model_id,
    messages=({"role": "user", "content": "Summarize the task."},),
    max_tokens=256,
    budget=budget,
    provider_terms_approved=True,
)
print(reply.text)
```

This example is illustrative: the selected model must exist, pass capability checks, and be authorized for use. `provider_terms_approved=True` is a caller-supplied gate assertion, **not identity or provider authorization proof**.

## Verification and known blocker

`python -m unittest tests/test_nine_router_offline.py` exercises offline behavior. The most recent separately reported live completion attempt returned **HTTP 401**, so do **not** claim live authenticated completion has passed. The MCP server's `get_production_system()` does not forward older `SUBAGENTBRIDGE_ROUTER_URL`/`SUBAGENTBRIDGE_ROUTER_KEY` variables into the composition root; see [Configuration](CONFIGURATION.md). The composition root's default origin is port `9099`; this does not assert that a router is actually listening there.

See [Status](SIMPUL_STATUS.md) and [Security](SECURITY_APPROVAL_MODEL.md).
