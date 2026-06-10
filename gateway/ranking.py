"""Vendor ranking — the marketplace's selection brain.

Closes the observability feedback loop: every invocation records an outcome
(success + latency) in a :class:`MetricsStore`, and a :class:`RankingPolicy`
turns those signals into an ordering over the vendors that provide a capability.

Two policies ship:

* ``BaselinePolicy`` — trust tier, then newest version (the static default).
* ``MetricsPolicy`` — observed success rate and latency, with a trust prior and
  an optimistic cold-start so unproven providers still get a chance.

Selection is pluggable so a richer scorer (cost, fairness, A/B exploration) can
drop in without touching the gateway.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .catalog import feature_id, rank_features
from .models import Feature, TrustTier

# A small prior so trusted vendors lead on a tie or with no data yet.
_TRUST_PRIOR = {TrustTier.OFFICIAL: 0.10, TrustTier.VERIFIED: 0.05, TrustTier.COMMUNITY: 0.0}


@dataclass
class FeatureMetrics:
    invocations: int = 0
    successes: int = 0
    total_latency_ms: float = 0.0

    @property
    def success_rate(self) -> float | None:
        return self.successes / self.invocations if self.invocations else None

    @property
    def avg_latency_ms(self) -> float | None:
        return self.total_latency_ms / self.successes if self.successes else None


class MetricsStore:
    """Thread-safe per-feature outcome counters fed by the gateway."""

    def __init__(self) -> None:
        self._m: dict[str, FeatureMetrics] = {}
        self._lock = threading.Lock()

    def record(self, feature_id: str, *, success: bool, latency_ms: float = 0.0) -> None:
        with self._lock:
            m = self._m.setdefault(feature_id, FeatureMetrics())
            m.invocations += 1
            if success:
                m.successes += 1
                m.total_latency_ms += latency_ms

    def get(self, feature_id: str) -> FeatureMetrics | None:
        return self._m.get(feature_id)


@runtime_checkable
class RankingPolicy(Protocol):
    def score(self, feature: Feature, store: MetricsStore) -> float: ...
    def rank(self, features: list[Feature], store: MetricsStore) -> list[Feature]: ...


class BaselinePolicy:
    """Static ordering: trust tier, then newest version, then vendor."""

    def score(self, feature: Feature, store: MetricsStore) -> float:
        return _TRUST_PRIOR.get(feature.manifest.trust, 0.0)

    def rank(self, features: list[Feature], store: MetricsStore) -> list[Feature]:
        return rank_features(features)


class MetricsPolicy:
    """Data-driven ordering: observed success rate and latency win.

    ``score = base + trust_prior - latency_penalty`` where ``base`` is the
    observed success rate, or an optimistic ``default_prior`` before any data
    (so a new provider isn't starved). Ties fall back to the baseline order.
    """

    def __init__(self, *, default_prior: float = 0.7, latency_weight: float = 0.1) -> None:
        self.default_prior = default_prior
        self.latency_weight = latency_weight

    def score(self, feature: Feature, store: MetricsStore) -> float:
        m = store.get(feature_id(feature))
        if m and m.invocations > 0 and m.success_rate is not None:
            base = m.success_rate
            latency_penalty = ((m.avg_latency_ms or 0.0) / 1000.0) * self.latency_weight
        else:
            base = self.default_prior
            latency_penalty = 0.0
        return base + _TRUST_PRIOR.get(feature.manifest.trust, 0.0) - latency_penalty

    def rank(self, features: list[Feature], store: MetricsStore) -> list[Feature]:
        # Stable baseline order as the deterministic tie-breaker.
        baseline = {id(f): i for i, f in enumerate(rank_features(features))}
        return sorted(features, key=lambda f: (-self.score(f, store), baseline[id(f)]))
