"""PR-05 partial capability negotiation. No HTTP calls, credential handling or workers."""
from .capability import ModelCapabilities, ModelRoutingTable, UnknownCapability
__all__ = ['ModelCapabilities','ModelRoutingTable','UnknownCapability']
