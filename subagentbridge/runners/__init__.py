"""
runners/__init__.py — runner registry.

Concrete backends (agy, claude, gpt_sol, deepseek) register themselves here.
manager.py and server.py never import a concrete runner class directly — they
look it up by name string, which is also what makes rehydration after a
server restart possible (docs/TEST_PLAN.md T11): the DB only stores the
runner's name, not a live Python object.
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


# NOTE: concrete runners (agy, claude, gpt_sol, deepseek) are implemented and
# registered in M3 (see docs/PRD.md milestones). Until then the registry is
# populated only by whatever a test or the caller registers explicitly.
