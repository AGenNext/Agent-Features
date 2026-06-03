"""Tests for the multi-vendor marketplace layer: capabilities, ranking, pins."""

from __future__ import annotations

from fastapi.testclient import TestClient

from gateway.main import create_app

client = TestClient(create_app())


def test_list_capabilities_groups_vendors():
    caps = {c["capability"]: c for c in client.get("/capabilities").json()}
    assert "greet" in caps
    greet = caps["greet"]
    assert greet["provider_count"] == 2
    assert set(greet["vendors"]) == {"acme", "globex"}
    # Acme is verified -> preferred over community Globex despite older version.
    assert greet["preferred"] == "acme/greet-acme@1.0.0"


def test_get_capability_ranked_best_first():
    providers = client.get("/capabilities/greet").json()
    assert [p["manifest"]["vendor"] for p in providers] == ["acme", "globex"]


def test_get_unknown_capability_404():
    assert client.get("/capabilities/nope").status_code == 404


def test_invoke_capability_picks_preferred_vendor():
    res = client.post("/capabilities/greet/invoke", json={"input": {"name": "Ada"}}).json()
    assert res["vendor"] == "acme"
    assert res["output"]["greeting"] == "Hello, Ada. — Acme"


def test_invoke_capability_vendor_pin():
    res = client.post(
        "/capabilities/greet/invoke",
        params={"vendor": "globex"},
        json={"input": {"name": "Ada"}},
    ).json()
    assert res["vendor"] == "globex"
    assert "globex" in res["output"]["greeting"]


def test_invoke_capability_version_pin():
    res = client.post(
        "/capabilities/greet/invoke",
        params={"version": "1.2.0"},
        json={"input": {"name": "Ada"}},
    ).json()
    assert res["vendor"] == "globex"


def test_invoke_capability_no_provider_404():
    res = client.post(
        "/capabilities/greet/invoke",
        params={"vendor": "ghost"},
        json={"input": {"name": "Ada"}},
    )
    assert res.status_code == 404
