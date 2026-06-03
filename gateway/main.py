"""Agent Features gateway — FastAPI application.

The front door of the platform. It exposes two faces over the same catalog and
invoker (see docs/ARCHITECTURE.md):

* a REST API for browsing and invoking features, and
* an MCP (JSON-RPC) endpoint at ``/mcp`` for agent tool-use.

Catalog and invoker are pluggable. By default the app wires the dev pair
(in-memory catalog + in-process invoker); in a cluster these become the
Kubernetes catalog + gRPC invoker without touching the routes below.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from . import __version__, mcp
from .catalog import Catalog
from .invoker import FeatureUnavailable, Invoker
from .models import Feature, InvokeRequest, InvokeResponse
from .samples import build_dev_catalog_and_invoker
from .validation import ValidationError, validate

logger = logging.getLogger(__name__)


def create_app(catalog: Catalog | None = None, invoker: Invoker | None = None) -> FastAPI:
    """Build the gateway app, optionally with injected catalog/invoker."""

    if catalog is None or invoker is None:
        dev_catalog, dev_invoker = build_dev_catalog_and_invoker()
        catalog = catalog or dev_catalog
        invoker = invoker or dev_invoker

    app = FastAPI(
        title="Agent Features Gateway",
        version=__version__,
        summary="Features as a Service for Agents — discovery and invocation.",
    )
    app.state.catalog = catalog
    app.state.invoker = invoker

    @app.get("/")
    def info() -> dict[str, Any]:
        return {
            "service": "agent-features-gateway",
            "version": __version__,
            "endpoints": ["/health", "/features", "/features/{name}", "/features/{name}/invoke", "/mcp"],
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/features", response_model=list[Feature])
    def list_features(tag: str | None = None, q: str | None = None) -> list[Feature]:
        tags = [tag] if tag else None
        return catalog.list(query=q, tags=tags)

    @app.get("/features/{name}", response_model=Feature)
    def get_feature(name: str) -> Feature:
        feature = catalog.get(name)
        if feature is None:
            raise HTTPException(status_code=404, detail=f"unknown feature: {name}")
        return feature

    @app.post("/features/{name}/invoke", response_model=InvokeResponse)
    async def invoke_feature(name: str, body: InvokeRequest) -> InvokeResponse:
        feature = catalog.get(name)
        if feature is None:
            raise HTTPException(status_code=404, detail=f"unknown feature: {name}")
        try:
            validate(body.input, feature.manifest.input_schema)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors) from exc
        try:
            result = await invoker.invoke(name, body.input, body.context)
        except FeatureUnavailable as exc:
            # Log the cause; return a generic message so no internal detail leaks.
            logger.warning("feature %s unavailable: %s", name, exc)
            raise HTTPException(
                status_code=503, detail=f"feature '{name}' is currently unavailable"
            ) from exc
        return InvokeResponse(
            feature=name,
            version=feature.manifest.version,
            output=result.output,
            latency_ms=result.latency_ms,
        )

    @app.post("/mcp")
    async def mcp_endpoint(request: Request) -> dict[str, Any] | None:
        message = await request.json()
        return await mcp.handle(message, catalog, invoker)

    return app


app = create_app()
