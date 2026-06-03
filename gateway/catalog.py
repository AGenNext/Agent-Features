"""Feature catalog — the discovery (read) side of the gateway.

``Catalog`` is the interface the gateway depends on. In dev we back it with an
in-memory list; in a cluster it is backed by the Kubernetes API (listing
``Feature`` custom resources). The HTTP/MCP surface is identical either way.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from .models import (
    CapabilitySummary,
    Feature,
    Manifest,
    Phase,
    Protocol as FeatureProtocol,
    TrustTier,
    Visibility,
)

GROUP = "agentfeatures.io"
VERSION = "v1alpha1"
PLURAL = "features"

# CRD enum values (capitalized) -> our lowercase model enums.
_VISIBILITY = {"Public": Visibility.PUBLIC, "Internal": Visibility.INTERNAL, "Private": Visibility.PRIVATE}
_PHASE = {
    "Pending": Phase.PENDING,
    "Provisioning": Phase.PROVISIONING,
    "Ready": Phase.READY,
    "Failed": Phase.FAILED,
}
_TRUST = {"Official": TrustTier.OFFICIAL, "Verified": TrustTier.VERIFIED, "Community": TrustTier.COMMUNITY}

# Best-first ordering of trust tiers (lower sorts first).
_TRUST_RANK = {TrustTier.OFFICIAL: 0, TrustTier.VERIFIED: 1, TrustTier.COMMUNITY: 2}


def feature_id(feature: Feature) -> str:
    m = feature.manifest
    return f"{m.vendor}/{m.name}@{m.version}"


def _semver_key(version: str) -> tuple[int, ...]:
    """Parse ``x.y.z`` into a comparable tuple; non-numeric parts sort as 0."""

    parts = version.split("-")[0].split(".")
    out = []
    for p in parts:
        out.append(int(p) if p.isdigit() else 0)
    return tuple(out)


def rank_features(features: list[Feature]) -> list[Feature]:
    """Order providers best-first: trust tier, then newest version, then vendor.

    This is the baseline ranking; a richer engine (success rate, latency, cost
    from the observability layer) plugs in here later.
    """

    return sorted(
        features,
        key=lambda f: (
            _TRUST_RANK.get(f.manifest.trust, 9),
            tuple(-n for n in _semver_key(f.manifest.version)),
            f.manifest.vendor,
        ),
    )


def resolve_feature(
    features: list[Feature],
    capability: str,
    *,
    version: str | None = None,
    vendor: str | None = None,
) -> Feature | None:
    """Pick the best feature for a capability, honouring vendor/version pins."""

    candidates = [f for f in features if f.manifest.capability == capability]
    if vendor:
        candidates = [f for f in candidates if f.manifest.vendor == vendor]
    if version:
        candidates = [f for f in candidates if f.manifest.version == version]
    ranked = rank_features(candidates)
    return ranked[0] if ranked else None


def summarize_capabilities(features: list[Feature]) -> list[CapabilitySummary]:
    """Group features into canonical capabilities with their ranked vendors."""

    by_cap: dict[str, list[Feature]] = {}
    for f in features:
        by_cap.setdefault(f.manifest.capability, []).append(f)

    summaries = []
    for capability, group in sorted(by_cap.items()):
        ranked = rank_features(group)
        summaries.append(
            CapabilitySummary(
                capability=capability,
                description=ranked[0].manifest.description,
                provider_count=len(ranked),
                vendors=[f.manifest.vendor for f in ranked],
                preferred=feature_id(ranked[0]),
            )
        )
    return summaries


def feature_from_cr(cr: dict[str, Any]) -> Feature:
    """Map a Feature custom-resource dict to a :class:`Feature` model."""

    spec = cr.get("spec", {})
    status = cr.get("status", {})
    manifest = Manifest(
        name=cr["metadata"]["name"],
        description=spec.get("description", ""),
        tags=spec.get("tags", []),
        input_schema=json.loads(spec["inputSchema"]) if spec.get("inputSchema") else {},
        output_schema=json.loads(spec["outputSchema"]) if spec.get("outputSchema") else {},
        visibility=_VISIBILITY.get(spec.get("visibility", "Public"), Visibility.PUBLIC),
        protocol=FeatureProtocol(spec.get("protocol", "grpc")),
        vendor=spec.get("vendor", "community"),
        capability=spec.get("capability", ""),
        trust=_TRUST.get(spec.get("trust", "Community"), TrustTier.COMMUNITY),
    )
    return Feature(
        manifest=manifest,
        phase=_PHASE.get(status.get("phase", "Pending"), Phase.PENDING),
        endpoint=status.get("endpoint"),
    )


@runtime_checkable
class Catalog(Protocol):
    """Read-only view over the set of published features."""

    def list(
        self, *, query: str | None = None, tags: list[str] | None = None
    ) -> list[Feature]:
        ...

    def get(self, name: str) -> Feature | None:
        ...

    def list_capabilities(self) -> list[CapabilitySummary]:
        ...

    def resolve(
        self, capability: str, *, version: str | None = None, vendor: str | None = None
    ) -> Feature | None:
        ...


class InMemoryCatalog:
    """Dev catalog seeded from a static set of manifests."""

    def __init__(self, manifests: list[Manifest]) -> None:
        self._features = {
            m.name: Feature(manifest=m, endpoint=f"local://{m.name}")
            for m in manifests
        }

    def list(
        self, *, query: str | None = None, tags: list[str] | None = None
    ) -> list[Feature]:
        results = list(self._features.values())
        if tags:
            wanted = set(tags)
            results = [
                f for f in results if wanted.issubset(set(f.manifest.tags))
            ]
        if query:
            q = query.lower()
            results = [
                f
                for f in results
                if q in f.manifest.name.lower()
                or q in f.manifest.description.lower()
                or any(q in t.lower() for t in f.manifest.tags)
            ]
        return sorted(results, key=lambda f: f.manifest.name)

    def get(self, name: str) -> Feature | None:
        return self._features.get(name)

    def list_capabilities(self) -> list[CapabilitySummary]:
        return summarize_capabilities(list(self._features.values()))

    def resolve(
        self, capability: str, *, version: str | None = None, vendor: str | None = None
    ) -> Feature | None:
        return resolve_feature(
            list(self._features.values()), capability, version=version, vendor=vendor
        )


class KubernetesCatalog:
    """Catalog backed by ``Feature`` custom resources in the cluster.

    Lists/gets Features via the Kubernetes custom-objects API. The client is
    lazy-loaded (and injectable) so importing this module needs no kubernetes
    dependency and so the mapping can be unit-tested without a cluster.
    """

    def __init__(self, *, namespace: str = "features", api: Any | None = None) -> None:
        self.namespace = namespace
        self._api = api

    def _client(self) -> Any:
        if self._api is None:
            from kubernetes import client, config

            try:
                config.load_incluster_config()
            except Exception:  # noqa: BLE001 - fall back to local kubeconfig
                config.load_kube_config()
            self._api = client.CustomObjectsApi()
        return self._api

    def list(self, *, query: str | None = None, tags: list[str] | None = None) -> list[Feature]:
        resp = self._client().list_namespaced_custom_object(GROUP, VERSION, self.namespace, PLURAL)
        features = [feature_from_cr(item) for item in resp.get("items", [])]
        if tags:
            wanted = set(tags)
            features = [f for f in features if wanted.issubset(set(f.manifest.tags))]
        if query:
            q = query.lower()
            features = [
                f
                for f in features
                if q in f.manifest.name.lower()
                or q in f.manifest.description.lower()
                or any(q in t.lower() for t in f.manifest.tags)
            ]
        return sorted(features, key=lambda f: f.manifest.name)

    def get(self, name: str) -> Feature | None:
        from kubernetes.client.exceptions import ApiException

        try:
            cr = self._client().get_namespaced_custom_object(GROUP, VERSION, self.namespace, PLURAL, name)
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise
        return feature_from_cr(cr)

    def list_capabilities(self) -> list[CapabilitySummary]:
        return summarize_capabilities(self.list())

    def resolve(
        self, capability: str, *, version: str | None = None, vendor: str | None = None
    ) -> Feature | None:
        return resolve_feature(self.list(), capability, version=version, vendor=vendor)
