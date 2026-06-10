"""Tests for the metrics-fed ranking engine."""

from __future__ import annotations

from fastapi.testclient import TestClient

from gateway.catalog import feature_id
from gateway.main import create_app
from gateway.models import Feature, Manifest, TrustTier
from gateway.ranking import MetricsPolicy, MetricsStore


def _feat(vendor: str, trust: TrustTier, version: str = "1.0.0") -> Feature:
    return Feature(
        manifest=Manifest(
            name=f"{vendor}-impl", capability="cap", vendor=vendor, trust=trust, version=version
        )
    )


def test_cold_start_prefers_trust():
    acme = _feat("acme", TrustTier.VERIFIED)
    globex = _feat("globex", TrustTier.COMMUNITY)
    policy, store = MetricsPolicy(), MetricsStore()
    assert [f.manifest.vendor for f in policy.rank([globex, acme], store)] == ["acme", "globex"]


def test_metrics_override_trust():
    acme = _feat("acme", TrustTier.VERIFIED)
    globex = _feat("globex", TrustTier.COMMUNITY)
    policy, store = MetricsPolicy(), MetricsStore()

    # Acme keeps failing; Globex keeps succeeding fast.
    for _ in range(5):
        store.record(feature_id(acme), success=False)
        store.record(feature_id(globex), success=True, latency_ms=5.0)

    ranked = [f.manifest.vendor for f in policy.rank([acme, globex], store)]
    assert ranked == ["globex", "acme"]  # observed success beats the trust prior
    assert policy.score(globex, store) > policy.score(acme, store)


def test_latency_breaks_ties_among_successful():
    fast = _feat("fast", TrustTier.COMMUNITY)
    slow = _feat("slow", TrustTier.COMMUNITY)
    policy, store = MetricsPolicy(), MetricsStore()
    for _ in range(10):
        store.record(feature_id(fast), success=True, latency_ms=2.0)
        store.record(feature_id(slow), success=True, latency_ms=900.0)
    assert [f.manifest.vendor for f in policy.rank([slow, fast], store)] == ["fast", "slow"]


# --- end-to-end: invocations feed the ranking ---------------------------------

client = TestClient(create_app())


def test_invocations_recorded_in_ranking():
    client.post(
        "/capabilities/greet/invoke",
        params={"vendor": "globex"},
        json={"input": {"name": "Ada"}},
    )
    ranking = {r["vendor"]: r for r in client.get("/capabilities/greet/ranking").json()}
    assert ranking["globex"]["invocations"] >= 1
    assert ranking["globex"]["success_rate"] == 1.0
    # Every provider gets a score.
    assert all(isinstance(r["score"], float) for r in ranking.values())
