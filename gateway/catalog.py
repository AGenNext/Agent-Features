"""Feature catalog — the discovery (read) side of the gateway.

``Catalog`` is the interface the gateway depends on. In dev we back it with an
in-memory list; in a cluster it is backed by the Kubernetes API (listing
``Feature`` custom resources). The HTTP/MCP surface is identical either way.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import Feature, Manifest


@runtime_checkable
class Catalog(Protocol):
    """Read-only view over the set of published features."""

    def list(
        self, *, query: str | None = None, tags: list[str] | None = None
    ) -> list[Feature]:
        ...

    def get(self, name: str) -> Feature | None:
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


class KubernetesCatalog:
    """Production catalog backed by ``Feature`` custom resources.

    Stubbed until the operator phase (M1). It will ``list``/``get`` against the
    Kubernetes API using a watch-backed informer cache.
    """

    def __init__(self, *, namespace: str = "features") -> None:  # pragma: no cover
        self.namespace = namespace

    def list(self, *, query=None, tags=None):  # pragma: no cover
        raise NotImplementedError(
            "KubernetesCatalog arrives with the operator (M1); use InMemoryCatalog."
        )

    def get(self, name):  # pragma: no cover
        raise NotImplementedError(
            "KubernetesCatalog arrives with the operator (M1); use InMemoryCatalog."
        )
