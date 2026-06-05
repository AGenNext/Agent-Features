"""The deterministic chat streamer resolves commands to feature calls (SSE)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from gateway.main import create_app

client = TestClient(create_app())


def _events(message: str) -> list[dict]:
    r = client.post("/chat/stream", json={"message": message})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    return [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]


def test_chat_invokes_feature_and_streams_result():
    events = _events('calculator {"expression": "2 + 2"}')
    assert events[-1]["type"] == "result"
    assert events[-1]["output"] == {"result": 4.0}
    assert any(e["type"] == "status" for e in events)


def test_chat_capability_resolves_best_provider():
    events = _events('cap:greet {"name": "Ada"}')
    result = events[-1]
    assert result["type"] == "result"
    assert result["vendor"] == "acme"  # verified > community


def test_chat_unknown_feature_streams_error():
    events = _events('nope {}')
    assert events[-1]["type"] == "error"
    assert "unknown feature" in events[-1]["message"]


def test_chat_bad_json_is_a_clean_error():
    events = _events("calculator {not json}")
    assert events[-1]["type"] == "error"


def test_chat_help_lists_commands():
    events = _events("help")
    assert any("invoke a feature" in e.get("text", "") for e in events)
