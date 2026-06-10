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


class FeatureInputError(Exception):
    """Raised by a feature when input is schema-valid but semantically invalid.

    Distinct from validation (which checks the JSON Schema) and from
    FeatureUnavailable (a transport/availability problem): this is the feature
    saying "I understood the shape, but the values don't make sense" — e.g. an
    un-parseable expression. The gateway surfaces it as a controlled 422 rather
    than an opaque 500, while genuinely unexpected errors stay opaque.
    """


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
    """Calls a feature workload's ``FeatureService`` over gRPC.

    ``endpoint_resolver`` maps a feature name to its ``host:port`` (in a
    cluster, from the catalog's ``Feature.endpoint``). gRPC and its generated
    stubs are imported lazily so the dev path (LocalInvoker) needs neither.
    """

    def __init__(self, *, endpoint_resolver: Callable[[str], str]) -> None:
        self._resolve = endpoint_resolver
        self._channels: dict[str, Any] = {}

    async def invoke(
        self, feature: str, payload: dict[str, Any], context: RequestContext
    ) -> InvokeResult:
        import grpc
        from google.protobuf import json_format, struct_pb2

        from agentfeatures.v1 import feature_pb2, feature_pb2_grpc

        endpoint = self._resolve(feature)
        channel = self._channels.get(endpoint)
        if channel is None:
            channel = grpc.aio.insecure_channel(endpoint)
            self._channels[endpoint] = channel
        stub = feature_pb2_grpc.FeatureServiceStub(channel)

        request = feature_pb2.InvokeRequest(
            feature=feature,
            input=struct_pb2.Struct(),
            context=feature_pb2.RequestContext(
                trace_id=context.trace_id or "",
                tenant=context.tenant or "",
                timeout_ms=context.timeout_ms,
                metadata=context.metadata,
            ),
        )
        request.input.update(payload)

        start = time.perf_counter()
        try:
            response = await stub.Invoke(request, timeout=context.timeout_ms / 1000)
        except grpc.aio.AioRpcError as exc:
            # A feature reports bad input via INVALID_ARGUMENT; everything else
            # is an availability/transport problem.
            if exc.code() == grpc.StatusCode.INVALID_ARGUMENT:
                raise FeatureInputError(exc.details() or "invalid input") from exc
            raise FeatureUnavailable(f"gRPC call to '{feature}' failed: {exc.code()}") from exc
        latency_ms = (time.perf_counter() - start) * 1000

        output = json_format.MessageToDict(response.output)
        return InvokeResult(output=output, latency_ms=round(latency_ms, 3))

    async def close(self) -> None:
        for channel in self._channels.values():
            await channel.close()
        self._channels.clear()
