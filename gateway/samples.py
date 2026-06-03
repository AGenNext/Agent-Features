"""Dev sample features.

These simulate feature workloads by running in-process. Each pairs a
:class:`Manifest` (what the catalog advertises) with a handler (what the local
invoker runs). In a cluster these would be separate OCI containers implementing
the ``FeatureService`` gRPC contract; here they let the gateway run end-to-end
with no dependencies.
"""

from __future__ import annotations

import ast
import datetime as dt
import operator as op
from typing import Any

from .catalog import InMemoryCatalog
from .invoker import Handler, LocalInvoker
from .models import Manifest

# (manifest, handler) pairs registered below.
_FEATURES: list[tuple[Manifest, Handler]] = []


def _register(manifest: Manifest, handler: Handler) -> None:
    _FEATURES.append((manifest, handler))


# --- calculator --------------------------------------------------------------

_OPERATORS = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
    ast.Pow: op.pow, ast.Mod: op.mod, ast.USub: op.neg, ast.UAdd: op.pos,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")


def _calculator(payload: dict[str, Any]) -> dict[str, Any]:
    tree = ast.parse(payload["expression"], mode="eval")
    return {"result": _safe_eval(tree)}


_register(
    Manifest(
        name="calculator",
        description="Safely evaluates an arithmetic expression.",
        tags=["math", "utility"],
        input_schema={
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
        output_schema={
            "type": "object",
            "properties": {"result": {"type": "number"}},
        },
    ),
    _calculator,
)


# --- text_stats --------------------------------------------------------------

def _text_stats(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload["text"]
    words = text.split()
    sentences = [s for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    return {
        "characters": len(text),
        "words": len(words),
        "sentences": len(sentences),
    }


_register(
    Manifest(
        name="text_stats",
        description="Counts characters, words and sentences in a block of text.",
        tags=["text", "nlp"],
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "characters": {"type": "integer"},
                "words": {"type": "integer"},
                "sentences": {"type": "integer"},
            },
        },
    ),
    _text_stats,
)


# --- clock -------------------------------------------------------------------

def _clock(payload: dict[str, Any]) -> dict[str, Any]:
    offset_hours = float(payload.get("utc_offset_hours", 0))
    tz = dt.timezone(dt.timedelta(hours=offset_hours))
    now = dt.datetime.now(tz)
    return {"iso8601": now.isoformat(), "utc_offset_hours": offset_hours}


_register(
    Manifest(
        name="clock",
        description="Returns the current time at a given UTC offset.",
        tags=["time", "utility"],
        input_schema={
            "type": "object",
            "properties": {
                "utc_offset_hours": {"type": "number", "default": 0}
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "iso8601": {"type": "string"},
                "utc_offset_hours": {"type": "number"},
            },
        },
    ),
    _clock,
)


# --- wiring ------------------------------------------------------------------

def build_dev_catalog_and_invoker() -> tuple[InMemoryCatalog, LocalInvoker]:
    """Build a catalog + invoker pair backed by the dev sample features."""

    manifests = [m for m, _ in _FEATURES]
    handlers = {m.name: h for m, h in _FEATURES}
    return InMemoryCatalog(manifests), LocalInvoker(handlers)
