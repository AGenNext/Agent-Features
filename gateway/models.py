"""Pydantic models mirroring the protocol-first contract.

These are the Python projection of ``proto/agentfeatures/v1/feature.proto``.
The gateway speaks JSON, so we keep schemas as parsed ``dict`` objects rather
than serialized strings, but the field names track the proto so codegen and
hand-written models stay aligned.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class TrustTier(str, Enum):
    """How much the marketplace trusts a vendor — a ranking input."""

    OFFICIAL = "official"   # first-party / platform-owned
    VERIFIED = "verified"   # reviewed third party
    COMMUNITY = "community" # unreviewed


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
    """Self-describing record of a feature.

    ``name`` is the unique handle for *this* implementation. ``capability`` is
    the canonical thing it provides (many vendors' features can share one
    capability); it defaults to ``name``. ``vendor`` is who publishes it. The
    marketplace key is therefore ``(capability, vendor, version)``.
    """

    name: str
    version: str = "1.0.0"
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    visibility: Visibility = Visibility.PUBLIC
    protocol: Protocol = Protocol.GRPC

    # Marketplace identity.
    vendor: str = "community"
    capability: str = ""
    trust: TrustTier = TrustTier.COMMUNITY

    @model_validator(mode="after")
    def _default_capability(self) -> "Manifest":
        if not self.capability:
            self.capability = self.name
        return self


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
    vendor: str = "community"


class CapabilitySummary(BaseModel):
    """A canonical capability and the vendors that provide it (ranked)."""

    capability: str
    description: str = ""
    provider_count: int
    vendors: list[str] = Field(default_factory=list)
    # The provider the marketplace would pick by default, as "vendor/name@version".
    preferred: str | None = None
