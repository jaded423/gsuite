"""Tool registry — decorator-based self-registration.

Each tool module decorates its public handler functions with `@tool(...)`;
import side-effects populate `_REGISTRY`. The server filters by feature flag
at startup via `build_registry(enabled_features)`.

Handlers are called with `**arguments` from the MCP client, so their Python
signatures must match the declared `input_schema` property names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    feature: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]


_REGISTRY: list[ToolSpec] = []


def tool(
    *, name: str, feature: str, description: str, input_schema: dict[str, Any]
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a handler function as an MCP tool.

    The decorated function is returned unchanged so it's still directly
    callable by Python code (tests, internal callers).
    """

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        if any(t.name == name for t in _REGISTRY):
            raise ValueError(f"duplicate tool registration: {name}")
        _REGISTRY.append(
            ToolSpec(
                name=name,
                feature=feature,
                description=description,
                input_schema=input_schema,
                handler=fn,
            )
        )
        return fn

    return decorate


def all_tools() -> list[ToolSpec]:
    return list(_REGISTRY)


def build_registry(enabled_features: set[str]) -> dict[str, ToolSpec]:
    return {t.name: t for t in _REGISTRY if t.feature in enabled_features}
