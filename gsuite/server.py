"""Stdio MCP server.

Registers only the tools whose feature flags are enabled (see settings.py).
Logs go to stderr — stdout is reserved for MCP protocol frames.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from . import __version__
from .auth import scope_report
from .settings import load_settings, scope_gaps
from .tools import ToolSpec, build_registry


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


log = logging.getLogger("gsuite.server")


def _build_server() -> tuple[Server, dict[str, ToolSpec]]:
    settings = load_settings()
    enabled = set(settings.enabled_features())

    # Scope gap check — disable features whose scopes weren't granted. This
    # keeps the server from advertising tools that would 403 on first call.
    report = scope_report()
    if report["needs_reauth"]:
        log.warning(
            "scope gap detected: missing %s — run `gsuite auth` to fix. "
            "Affected features will be disabled this session.",
            report["missing_scopes"],
        )
        from .settings import FEATURE_SCOPES, _collapse_scopes
        granted = set(report["granted_scopes"])
        usable = set()
        for f in enabled:
            required = _collapse_scopes(set(FEATURE_SCOPES.get(f, [])))
            if not scope_gaps(granted, required):
                usable.add(f)
        enabled = usable

    registry = build_registry(enabled)
    log.info(
        "gsuite %s starting; features=%s tools=%s",
        __version__,
        sorted(enabled),
        sorted(registry),
    )

    server: Server = Server("gsuite")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=spec.input_schema,
            )
            for spec in registry.values()
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        spec = registry.get(name)
        if spec is None:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "ok": False,
                            "error": f"unknown or disabled tool: {name}",
                            "retryable": False,
                            "enabled_features": sorted(enabled),
                        }
                    ),
                )
            ]
        args = arguments or {}
        try:
            # Handlers are sync (they hit Google APIs via googleapiclient, which
            # is blocking). Offload to a thread so we don't stall the MCP loop.
            result = await asyncio.to_thread(spec.handler, **args)
        except TypeError as exc:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "ok": False,
                            "error": f"bad arguments for {name}: {exc}",
                            "retryable": False,
                        }
                    ),
                )
            ]
        except Exception as exc:  # noqa: BLE001 — we surface every failure as a structured error
            log.exception("tool %s failed", name)
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "ok": False,
                            "error": f"{type(exc).__name__}: {exc}",
                            "retryable": True,
                        }
                    ),
                )
            ]
        return [TextContent(type="text", text=json.dumps(result, default=str))]

    return server, registry


async def _run() -> None:
    _setup_logging()
    server, _ = _build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
