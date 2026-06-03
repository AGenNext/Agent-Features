"""Pydantic models mirroring the protocol-first contract.

These are the Python projection of ``proto/agentfeatures/v1/feature.proto``.
The gateway speaks JSON, so we keep schemas as parsed ``dict`` objects rather
than serialized strings, but the field names track the proto so codegen and
hand-written models stay aligned.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Visibility(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"


class Protocol(str, Enum):
    GRPC = "grpc"
    HTTP = "http"


class Phase(str, Enum):
    PENDING = "pending"
    PROVISIONING = "provisioning"
    READY = "ready"
    FAILED = "failed"


class Manifest(BaseModel):
    """Self-describing record of a capability — maps 1:1 onto an MCP tool."""

    name: str
    version: str = "1.0.0"
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    visibility: Visibility = Visibility.PUBLIC
    protocol: Protocol = Protocol.GRPC


class Feature(BaseModel):
    """A manifest plus its runtime status, as surfaced by the catalog."""

    manifest: Manifest
    phase: Phase = Phase.READY
    endpoint: str | None = None


class RequestContext(BaseModel):
    """Carries trace context, tenancy and deadline through an invocation."""

    trace_id: str | None = None
    tenant: str | None = None
    timeout_ms: int = 30_000
    metadata: dict[str, str] = Field(default_factory=dict)


class InvokeRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    context: RequestContext = Field(default_factory=RequestContext)


class InvokeResponse(BaseModel):
    feature: str
    version: str
    output: dict[str, Any]
    latency_ms: float
