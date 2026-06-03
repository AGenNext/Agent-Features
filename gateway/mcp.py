"""MCP (Model Context Protocol) adapter.

This is the agent-native face of the gateway. It exposes the catalog as MCP
*tools* over JSON-RPC 2.0 so any MCP-capable agent consumes the marketplace
with no custom glue: each feature manifest becomes a tool whose ``inputSchema``
is the feature's ``input_schema``.

Only the subset needed to be useful is implemented: ``initialize``,
``tools/list`` and ``tools/call``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .catalog import Catalog
from .invoker import FeatureUnavailable, Invoker
from .models import RequestContext
from .validation import ValidationError, validate

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "agent-features-gateway", "version": "0.1.0"}

# JSON-RPC error codes (subset of the spec).
INVALID_PARAMS = -32602
METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32603


def _tool(manifest) -> dict[str, Any]:
    """Project a feature manifest onto an MCP tool definition."""

    return {
        "name": manifest.name,
        "description": manifest.description,
        "inputSchema": manifest.input_schema or {"type": "object"},
    }


async def handle(message: dict[str, Any], catalog: Catalog, invoker: Invoker) -> dict[str, Any] | None:
    """Handle one JSON-RPC request, returning the response (or None for notifications)."""

    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}

    # Notifications (no id) get no response.
    if msg_id is None and method not in ("initialize",):
        return None

    if method == "initialize":
        return _ok(msg_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        })

    if method == "tools/list":
        tools = [_tool(f.manifest) for f in catalog.list()]
        return _ok(msg_id, {"tools": tools})

    if method == "tools/call":
        return await _call(msg_id, params, catalog, invoker)

    return _err(msg_id, METHOD_NOT_FOUND, f"unknown method: {method}")


async def _call(msg_id, params, catalog: Catalog, invoker: Invoker) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}

    feature = catalog.get(name) if name else None
    if feature is None:
        return _err(msg_id, INVALID_PARAMS, f"unknown tool: {name}")

    try:
        validate(arguments, feature.manifest.input_schema)
        result = await invoker.invoke(name, arguments, RequestContext())
    except ValidationError as exc:
        # exc.errors are our own schema-violation messages about the caller's
        # input — safe and useful to return. We avoid stringifying the
        # exception itself so no internal detail leaks.
        return _tool_error(msg_id, "invalid input: " + "; ".join(exc.errors))
    except FeatureUnavailable as exc:
        # Log the cause server-side; return a generic message to the caller.
        logger.warning("feature %s unavailable: %s", name, exc)
        return _tool_error(msg_id, f"feature '{name}' is currently unavailable")

    # MCP tool results are content blocks; we return the output as JSON text.
    return _ok(msg_id, {
        "content": [{"type": "text", "text": json.dumps(result.output)}],
        "isError": False,
    })


def _ok(msg_id, result) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id, code, message) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _tool_error(msg_id, message) -> dict[str, Any]:
    # Tool-level errors surface inside the result so the agent can react.
    return _ok(msg_id, {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    })
