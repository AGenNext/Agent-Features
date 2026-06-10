"""Input validation against a feature's JSON Schema.

The gateway validates every invocation's ``input`` against the feature
manifest's ``input_schema`` *before* dispatching to a workload — a core
protocol-first guarantee (a feature never sees malformed arguments).
"""

from __future__ import annotations

from typing import Any

try:  # jsonschema is the canonical validator; degrade gracefully if absent.
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - exercised only without the optional dep
    Draft202012Validator = None  # type: ignore[assignment]


class ValidationError(Exception):
    """Raised when an invocation payload does not satisfy a schema."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def collect_errors(payload: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Return every schema violation as a message list (empty when valid).

    A pure, side-effect-free check. Its result is safe to return to callers
    because it is plain data about *their* input versus the public schema — it
    never reads from a caught exception, so no stack-trace/internal state can
    leak through it (cf. CodeQL py/stack-trace-exposure).
    """

    if not schema:
        return []

    if Draft202012Validator is None:  # pragma: no cover - no-dep fallback
        # Minimal best-effort check: required top-level keys only.
        return [f"missing required field: {k}" for k in schema.get("required", []) if k not in payload]

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    return [_format(e) for e in errors]


def validate(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    """Validate ``payload`` against JSON Schema ``schema``.

    Raises :class:`ValidationError` listing every violation. An empty schema
    accepts anything.
    """

    errors = collect_errors(payload, schema)
    if errors:
        raise ValidationError(errors)


def _format(error: Any) -> str:
    location = "/".join(str(p) for p in error.path) or "<root>"
    return f"{location}: {error.message}"
