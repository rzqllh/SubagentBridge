# SubagentBridge: 9Router Setup and Model Configuration

SubagentBridge integrates with **9Router** as a local loopback model provider. This document explains how 9Router operates, how capability checks fail closed, and how to verify the integration.

---

## 1. Overview and Security Policy (Decision D-02)

To prevent uncontained network egress and data leaks:
- SubagentBridge connects **only** to local 9Router loopback endpoints on `127.0.0.1`.
- Any external hostname, non-loopback IP, or unapproved upstream route is blocked by policy and raises a security violation.
- All requests require local bearer credentials when configured.

---

## 2. Model Routing Table and Capability Verification

The routing table maps available model identifiers to verified capabilities:

```python
from subagentbridge.models.capability import ModelCapabilities, ModelRoutingTable

capabilities = [
    ModelCapabilities(
        model_id="anthropic/claude-3-5-sonnet",
        tool_calls=True,
        structured_output=True,
        streaming=True,
        input_cost_known=True,
        output_cost_known=True,
    ),
    ModelCapabilities(
        model_id="deepseek/deepseek-coder",
        tool_calls=True,
        structured_output=True,
        streaming=True,
        input_cost_known=True,
        output_cost_known=True,
    ),
]

routing_table = ModelRoutingTable(capabilities)
```

### Fail-Closed Behavior
If a dispatch requires a capability (e.g., `tool_calls=True` or `structured_output=True`) and the candidate model does not support it, SubagentBridge raises `UnknownCapability` or `CapabilityMismatch` and halts dispatch rather than falling back to unverified prompt simulation.

---

## 3. Local 9Router Client Usage

```python
from subagentbridge.models.nine_router import LocalRouterConfig, NineRouterClient, CallBudget

config = LocalRouterConfig(
    base_url="http://127.0.0.1:8080/v1",
    api_key="local-token-xyz",
    allowed_models=("anthropic/claude-3-5-sonnet",),
)

client = NineRouterClient(config)

# Check model availability on loopback
models = client.list_available_models()

# Complete a prompt with budget bounds
budget = CallBudget(max_tokens=4096, max_cost_microunits=50000)
response = client.complete(
    model_id="anthropic/claude-3-5-sonnet",
    prompt="Explain the task acceptance criteria.",
    budget=budget,
)
```

---

## 4. Verification

Run the live loopback unit and integration suite:
```bash
python -m unittest tests/test_nine_router_live_loopback.py
```
Expected result: 4 tests ran, 4 passed (Exit 0).
