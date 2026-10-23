"""PR-05 partial: dynamically provided model capabilities, fail-closed routing.

Discover models and capabilities from a trusted 9Router endpoint in later PR-05
integration; NEVER infer abilities from name/provider or advertise free usage.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

class UnknownCapability(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    model_id: str
    tool_calls: bool | None
    structured_output: bool | None
    streaming: bool | None
    input_cost_known: bool
    output_cost_known: bool

    def __post_init__(self):
        if (type(self.model_id) is not str or not self.model_id.strip()
                or len(self.model_id) > 256 or any(ord(c) < 32 for c in self.model_id)
                or any(type(v) not in (bool, type(None)) for v in
                       (self.tool_calls, self.structured_output, self.streaming))
                or type(self.input_cost_known) is not bool
                or type(self.output_cost_known) is not bool):
            raise ValueError('valid discovered model and capability flags required')


class ModelRoutingTable:
    def __init__(self, models: Iterable[ModelCapabilities]):
        self._models: dict[str, ModelCapabilities] = {}
        for model in models:
            if not isinstance(model, ModelCapabilities):
                raise ValueError('model capability records required')
            if model.model_id in self._models:
                raise ValueError('duplicate discovered model identity')
            self._models[model.model_id] = model

    @property
    def models(self) -> tuple[ModelCapabilities, ...]:
        return tuple(self._models.values())

    def select(self, requested_ids: Iterable[str], *, coding: bool = False, structured: bool = False, streaming: bool = False) -> ModelCapabilities:
        for ident in requested_ids:
            m = self._models.get(ident)
            if m is None:
                continue
            if coding and m.tool_calls is not True:
                continue
            if structured and m.structured_output is not True:
                continue
            if streaming and m.streaming is not True:
                continue
            return m
        raise UnknownCapability('no model with independently confirmed required capabilities')
