"""
runners/__init__.py — runner registry.

Concrete backends register themselves here. manager.py and server.py never
import a concrete runner class directly; they resolve runners by stable name.
"""

from __future__ import annotations

from .base import AgentRunner

_REGISTRY: dict[str, AgentRunner] = {}


def register_runner(name: str, runner: AgentRunner) -> None:
    if name in _REGISTRY:
        raise ValueError(f"runner {name!r} already registered")
    _REGISTRY[name] = runner


def get_runner(name: str) -> AgentRunner:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"no runner registered for {name!r} — available: {sorted(_REGISTRY)}"
        ) from None


def available_runners() -> list[str]:
    return sorted(_REGISTRY)


# Production runners. Keep registration here so startup and persistence
# rehydration see the same stable registry.
from .agy_runner import AgyRunner  # noqa: E402

register_runner("agy", AgyRunner())

# Claude/GPT/DeepSeek runners are intentionally not registered until their
# implementations and runtime contracts are verified.
