"""Tests for feature composition (the agent composer)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from gateway.main import create_app

client = TestClient(create_app())


def test_list_composites():
    names = {c["name"] for c in client.get("/composites").json()}
    assert "greet-report" in names


def test_invoke_composite_pipes_steps():
    res = client.post(
        "/composites/greet-report/invoke", json={"input": {"name": "Ada"}}
    )
    assert res.status_code == 200
    body = res.json()
    # Step 1 (greet) feeds step 2 (text_stats); output is composed from both.
    assert body["output"]["greeting"] == "Hello, Ada. — Acme"
    assert body["output"]["characters"] == len("Hello, Ada. — Acme")
    assert [t["capability"] for t in body["trace"]] == ["greet", "text_stats"]


def test_invoke_composite_validation_error():
    res = client.post("/composites/greet-report/invoke", json={"input": {}})
    assert res.status_code == 422


def test_invoke_unknown_composite_404():
    assert client.post("/composites/nope/invoke", json={"input": {}}).status_code == 404


def test_composite_failure_returns_error_data_not_500():
    # A step referencing a capability no vendor provides fails as plain data on
    # the result (200 + error), never an exception/500 (CodeQL-safe path).
    spec = {
        "name": "broken",
        "input_schema": {
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"],
        },
        "steps": [{"name": "s", "capability": "does-not-exist", "inputs": {"x": "input.x"}}],
        "output": {"y": "s.x"},
    }
    client.post("/compose", json=spec)
    res = client.post("/composites/broken/invoke", json={"input": {"x": "hi"}})
    assert res.status_code == 200
    body = res.json()
    assert body["output"] == {}
    assert body["error"] and "no provider" in body["error"]


def test_compose_then_invoke_new_composite():
    # A developer publishes a composition, then runs it.
    spec = {
        "name": "loud-greet",
        "description": "Greet, pinned to the globex vendor.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        "steps": [
            {
                "name": "g",
                "capability": "greet",
                "vendor": "globex",
                "inputs": {"name": "input.name"},
            }
        ],
        "output": {"greeting": "g.greeting"},
    }
    assert client.post("/compose", json=spec).status_code == 201
    res = client.post("/composites/loud-greet/invoke", json={"input": {"name": "Bo"}}).json()
    assert "globex" in res["output"]["greeting"]
