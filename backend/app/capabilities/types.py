from __future__ import annotations

from dataclasses import dataclass, field

RISKS = ("read", "internal_write", "external_message", "destructive")


class CapabilityError(Exception):
    """Base for registry errors. Messages never contain secrets or raw upstream payloads."""


class ConfigError(CapabilityError):
    pass


class DiscoveryError(CapabilityError):
    pass


class InvocationError(CapabilityError):
    pass


@dataclass
class DiscoveredTool:
    name: str
    description: str
    input_schema: dict
    output_schema: dict | None
    implementation: dict  # how to call it: {"type": "mcp"|"http"|"function", ...}
    risk: str  # as classified from what the source declares; may be overridden by an admin
    extra: dict = field(default_factory=dict)
