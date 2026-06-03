"""Feature invocation — the dispatch (write) side of the gateway.

``Invoker`` is the seam between the gateway and where features actually run.
``LocalInvoker`` runs handlers in-process for dev; ``GrpcInvoker`` will dial a
feature workload's ``FeatureService`` over gRPC once the operator schedules
pods. The gateway calls ``invoke`` after validating input, so handlers can
trust their arguments.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from .models import RequestContext

# A dev handler is a plain function from input dict to output dict.
Handler = Callable[[dict[str, Any]], dict[str, Any]]


class InvokeResult:
    __slots__ = ("output", "latency_ms")

    def __init__(self, output: dict[str, Any], latency_ms: float) -> None:
        self.output = output
        self.latency_ms = latency_ms


class FeatureUnavailable(Exception):
    """Raised when the target feature cannot be reached or does not exist."""


@runtime_checkable
class Invoker(Protocol):
    async def invoke(
        self, feature: str, payload: dict[str, Any], context: RequestContext
    ) -> InvokeResult:
        ...


class LocalInvoker:
    """Runs feature handlers in the gateway process (dev mode)."""

    def __init__(self, handlers: dict[str, Handler]) -> None:
        self._handlers = handlers

    async def invoke(
        self, feature: str, payload: dict[str, Any], context: RequestContext
    ) -> InvokeResult:
        handler = self._handlers.get(feature)
        if handler is None:
            raise FeatureUnavailable(f"no handler registered for '{feature}'")
        start = time.perf_counter()
        output = handler(payload)
        latency_ms = (time.perf_counter() - start) * 1000
        return InvokeResult(output=output, latency_ms=round(latency_ms, 3))


class GrpcInvoker:
    """Production invoker that calls a feature pod's ``FeatureService``.

    Stubbed until the operator phase (M1). It will resolve the feature's
    in-cluster endpoint from the catalog, dial gRPC, propagate the trace
    context from ``RequestContext`` and map ``InvokeResponse`` back.
    """

    def __init__(self, *, endpoint_resolver: Callable[[str], str] | None = None):
        self._resolve = endpoint_resolver

    async def invoke(self, feature, payload, context):  # pragma: no cover
        raise NotImplementedError(
            "GrpcInvoker arrives with the operator (M1); use LocalInvoker for dev."
        )
