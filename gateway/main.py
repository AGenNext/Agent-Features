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

import json
import logging
import os
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, mcp, signing
from .catalog import Catalog, feature_id, match_version
from .composer import Composer, Composite, CompositeResult, CompositeSummary
from .composites import build_dev_composites
from .invoker import FeatureInputError, FeatureUnavailable, Invoker
from .models import (
    CapabilitySummary,
    Feature,
    InvokeRequest,
    InvokeResponse,
    ProviderScore,
    RequestContext,
)
from .ranking import BaselinePolicy, MetricsPolicy, MetricsStore, RankingPolicy
from .samples import build_dev_catalog_and_invoker
from .validation import collect_errors

logger = logging.getLogger(__name__)


def create_app(catalog: Catalog | None = None, invoker: Invoker | None = None) -> FastAPI:
    """Build the gateway app, optionally with injected catalog/invoker."""

    if catalog is None and invoker is None and os.getenv("AGENT_FEATURES_MODE") == "cluster":
        # Cluster mode: discover Features from the Kubernetes API and invoke the
        # workloads the operator scheduled, over gRPC.
        from .catalog import KubernetesCatalog
        from .invoker import GrpcInvoker

        namespace = os.getenv("FEATURES_NAMESPACE", "features")
        k8s_catalog = KubernetesCatalog(namespace=namespace)

        def _resolve(name: str) -> str:
            feature = k8s_catalog.get(name)
            if feature is None or not feature.endpoint:
                raise FeatureUnavailable(f"no endpoint for feature '{name}'")
            return feature.endpoint

        catalog = k8s_catalog
        invoker = GrpcInvoker(endpoint_resolver=_resolve)

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

    # Ranking: record outcomes and let a policy order vendors. MetricsPolicy
    # learns from observed success/latency; baseline is the static fallback.
    store = MetricsStore()
    policy: RankingPolicy = (
        BaselinePolicy()
        if os.getenv("AGENT_FEATURES_RANKING") == "baseline"
        else MetricsPolicy()
    )
    app.state.metrics = store
    app.state.ranking = policy

    def _providers(capability: str, vendor: str | None = None, version: str | None = None):
        out = [f for f in catalog.list() if f.manifest.capability == capability]
        if vendor:
            out = [f for f in out if f.manifest.vendor == vendor]
        if version:
            out = [f for f in out if match_version(f.manifest.version, version)]
        return out

    @app.get("/")
    def info() -> dict[str, Any]:
        return {
            "service": "agent-features-gateway",
            "version": __version__,
            "ui": "/ui",
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

    @app.get("/features/{name}/signature")
    def feature_signature(name: str) -> dict[str, Any]:
        # Supply-chain provenance: the manifest's canonical digest plus its
        # Sigstore/cosign verification status (see gateway/signing.py).
        feature = catalog.get(name)
        if feature is None:
            raise HTTPException(status_code=404, detail=f"unknown feature: {name}")
        return signing.verify(name, feature.manifest.model_dump(mode="json"))

    async def _invoke(feature: Feature, body: InvokeRequest) -> InvokeResponse:
        name = feature.manifest.name
        fid = feature_id(feature)
        # Caller error — not a reflection of feature quality; not recorded. The
        # detail is plain data from a pure check (never an exception), so it is
        # safe to return.
        input_errors = collect_errors(body.input, feature.manifest.input_schema)
        if input_errors:
            raise HTTPException(status_code=422, detail=input_errors)
        try:
            result = await invoker.invoke(name, body.input, body.context)
        except FeatureInputError as exc:
            # Caller error too — don't penalise the feature. Log the specifics
            # server-side and return a generic message: the exception string can
            # carry feature/transport internals (e.g. gRPC details), so we never
            # echo it to the caller. Detailed input feedback already comes from
            # our own schema validation above.
            logger.info("feature %s rejected input: %s", name, exc)
            raise HTTPException(
                status_code=422, detail=f"feature '{name}' rejected the input"
            ) from exc
        except FeatureUnavailable as exc:
            store.record(fid, success=False)
            logger.warning("feature %s unavailable: %s", name, exc)
            raise HTTPException(
                status_code=503, detail=f"feature '{name}' is currently unavailable"
            ) from exc
        store.record(fid, success=True, latency_ms=result.latency_ms)
        return InvokeResponse(
            feature=name,
            version=feature.manifest.version,
            output=result.output,
            latency_ms=result.latency_ms,
            vendor=feature.manifest.vendor,
        )

    @app.post("/features/{name}/invoke", response_model=InvokeResponse)
    async def invoke_feature(name: str, body: InvokeRequest) -> InvokeResponse:
        feature = catalog.get(name)
        if feature is None:
            raise HTTPException(status_code=404, detail=f"unknown feature: {name}")
        return await _invoke(feature, body)

    @app.get("/capabilities", response_model=list[CapabilitySummary])
    def list_capabilities() -> list[CapabilitySummary]:
        return catalog.list_capabilities()

    @app.get("/capabilities/{capability}", response_model=list[Feature])
    def get_capability(capability: str) -> list[Feature]:
        # All providers of the capability, best-first per the active policy.
        providers = _providers(capability)
        if not providers:
            raise HTTPException(status_code=404, detail=f"unknown capability: {capability}")
        return policy.rank(providers, store)

    @app.get("/capabilities/{capability}/ranking", response_model=list[ProviderScore])
    def capability_ranking(capability: str) -> list[ProviderScore]:
        # The live ranking with the scores and metrics behind it.
        providers = _providers(capability)
        if not providers:
            raise HTTPException(status_code=404, detail=f"unknown capability: {capability}")
        scored = []
        for f in policy.rank(providers, store):
            m = store.get(feature_id(f))
            scored.append(
                ProviderScore(
                    feature_id=feature_id(f),
                    vendor=f.manifest.vendor,
                    version=f.manifest.version,
                    score=round(policy.score(f, store), 4),
                    invocations=m.invocations if m else 0,
                    success_rate=m.success_rate if m else None,
                    avg_latency_ms=round(m.avg_latency_ms, 3) if m and m.avg_latency_ms else None,
                )
            )
        return scored

    @app.post("/capabilities/{capability}/invoke", response_model=InvokeResponse)
    async def invoke_capability(
        capability: str,
        body: InvokeRequest,
        vendor: str | None = None,
        version: str | None = None,
    ) -> InvokeResponse:
        # The marketplace ranks providers (honouring vendor/version pins) and
        # invokes the top one.
        providers = _providers(capability, vendor=vendor, version=version)
        ranked = policy.rank(providers, store)
        if not ranked:
            raise HTTPException(
                status_code=404,
                detail=f"no provider for capability '{capability}'"
                + (f" (vendor={vendor})" if vendor else "")
                + (f" (version={version})" if version else ""),
            )
        return await _invoke(ranked[0], body)

    # --- composition: orchestrate capabilities into a pipeline ---------------

    async def _run_capability(
        capability: str,
        input_dict: dict[str, Any],
        vendor: str | None = None,
        version: str | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Resolve + invoke one capability for a composite.

        Returns ``(output, None)`` on success or ``(None, message)`` on failure,
        where ``message`` is a safe, caller-facing string (never an exception
        string — internals are logged, not returned).
        """
        ranked = policy.rank(_providers(capability, vendor=vendor, version=version), store)
        if not ranked:
            return None, f"no provider for capability '{capability}'"
        feature = ranked[0]
        fid = feature_id(feature)
        errors = collect_errors(input_dict, feature.manifest.input_schema)
        if errors:
            return None, "invalid input: " + "; ".join(errors)
        try:
            result = await invoker.invoke(feature.manifest.name, input_dict, RequestContext())
        except FeatureInputError as exc:
            logger.info("composite step %s rejected input: %s", capability, exc)
            return None, "the feature rejected the input"
        except FeatureUnavailable as exc:
            store.record(fid, success=False)
            logger.warning("composite step %s unavailable: %s", capability, exc)
            return None, "the provider is currently unavailable"
        store.record(fid, success=True, latency_ms=result.latency_ms)
        return result.output, None

    composer = Composer(_run_capability)
    composites: dict[str, Composite] = {c.name: c for c in build_dev_composites()}

    def _composite_summary(c: Composite) -> CompositeSummary:
        return CompositeSummary(
            name=c.name,
            capability=c.capability,
            description=c.description,
            steps=[{"name": s.name, "capability": s.capability} for s in c.steps],
        )

    @app.get("/composites", response_model=list[CompositeSummary])
    def list_composites() -> list[CompositeSummary]:
        return [_composite_summary(c) for c in composites.values()]

    @app.get("/composites/{name}", response_model=Composite)
    def get_composite(name: str) -> Composite:
        if name not in composites:
            raise HTTPException(status_code=404, detail=f"unknown composite: {name}")
        return composites[name]

    @app.post("/compose", response_model=CompositeSummary, status_code=201)
    def compose(spec: Composite) -> CompositeSummary:
        # Publish a composition to the registry — a developer assembling an agent
        # from marketplace capabilities, the way a compose file references images.
        composites[spec.name] = spec
        return _composite_summary(spec)

    @app.post("/composites/{name}/invoke", response_model=CompositeResult)
    async def invoke_composite(name: str, body: InvokeRequest) -> CompositeResult:
        composite = composites.get(name)
        if composite is None:
            raise HTTPException(status_code=404, detail=f"unknown composite: {name}")
        errors = collect_errors(body.input, composite.input_schema)
        if errors:
            raise HTTPException(status_code=422, detail=errors)
        return await composer.run(composite, body.input)

    # --- chat: a deterministic, streaming console over the catalog -----------
    # No LLM: a tiny command grammar resolves to a feature/capability call and
    # the steps stream back as Server-Sent Events. Errors are generic, safe
    # messages (specifics are logged), matching the rest of the gateway.

    async def _chat(text: str) -> AsyncIterator[dict[str, Any]]:
        text = text.strip()
        if not text or text == "help":
            for line in (
                "Commands:",
                "  <feature> {json}         invoke a feature",
                "  cap:<capability> {json}  invoke the best-ranked provider",
                "  list                     list available features",
            ):
                yield {"type": "status", "text": line}
            return
        if text == "list":
            yield {"type": "status", "text": "features:"}
            for f in catalog.list():
                yield {"type": "status", "text": f"  {f.manifest.name} ({f.manifest.capability})"}
            return

        head, _, tail = text.partition(" ")
        try:
            payload = json.loads(tail) if tail.strip() else {}
        except ValueError:
            yield {"type": "error", "message": "the text after the command must be valid JSON"}
            return

        if head.startswith("cap:"):
            capability = head[4:]
            yield {"type": "status", "text": f"resolving capability '{capability}'…"}
            ranked = policy.rank(_providers(capability), store)
            if not ranked:
                yield {"type": "error", "message": f"no provider for capability '{capability}'"}
                return
            feature = ranked[0]
        else:
            feature = catalog.get(head)
            if feature is None:
                yield {"type": "error", "message": f"unknown feature '{head}' (try 'list')"}
                return

        yield {"type": "status", "text": f"invoking {feature.manifest.vendor}/{feature.manifest.name}…"}
        errors = collect_errors(payload, feature.manifest.input_schema)
        if errors:
            yield {"type": "error", "message": "invalid input: " + "; ".join(errors)}
            return
        fid = feature_id(feature)
        try:
            result = await invoker.invoke(feature.manifest.name, payload, RequestContext())
        except FeatureInputError as exc:
            logger.info("chat: feature %s rejected input: %s", feature.manifest.name, exc)
            yield {"type": "error", "message": "the feature rejected the input"}
            return
        except FeatureUnavailable as exc:
            store.record(fid, success=False)
            logger.warning("chat: feature %s unavailable: %s", feature.manifest.name, exc)
            yield {"type": "error", "message": "the feature is currently unavailable"}
            return
        store.record(fid, success=True, latency_ms=result.latency_ms)
        yield {
            "type": "result", "feature": feature.manifest.name, "vendor": feature.manifest.vendor,
            "output": result.output, "latency_ms": result.latency_ms,
        }

    @app.post("/chat/stream")
    async def chat_stream(request: Request) -> StreamingResponse:
        body = await request.json()
        text = str(body.get("message", ""))

        async def sse() -> AsyncIterator[str]:
            async for event in _chat(text):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream")

    @app.post("/mcp")
    async def mcp_endpoint(request: Request) -> dict[str, Any] | None:
        message = await request.json()
        return await mcp.handle(message, catalog, invoker)

    # The marketplace dashboard — a static, framework-free SPA that consumes the
    # REST API above (same-origin, so no CORS). Served at /ui.
    @app.get("/ui", include_in_schema=False)
    def ui_redirect() -> RedirectResponse:
        return RedirectResponse(url="/ui/")

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/ui", StaticFiles(directory=static_dir, html=True), name="ui")

    return app


app = create_app()
