"""End-to-end tests for the gateway over both its REST and MCP faces."""

from __future__ import annotations

from fastapi.testclient import TestClient

from gateway.main import create_app

client = TestClient(create_app())


# --- REST --------------------------------------------------------------------

def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_list_features():
    names = {f["manifest"]["name"] for f in client.get("/features").json()}
    assert {"calculator", "text_stats", "clock"} <= names


def test_filter_by_tag():
    res = client.get("/features", params={"tag": "math"}).json()
    assert [f["manifest"]["name"] for f in res] == ["calculator"]


def test_search_query():
    res = client.get("/features", params={"q": "time"}).json()
    assert [f["manifest"]["name"] for f in res] == ["clock"]


def test_get_unknown_feature_404():
    assert client.get("/features/nope").status_code == 404


def test_invoke_calculator():
    res = client.post(
        "/features/calculator/invoke",
        json={"input": {"expression": "2 * (3 + 4)"}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["output"] == {"result": 14.0}
    assert body["feature"] == "calculator"


def test_invoke_text_stats():
    res = client.post(
        "/features/text_stats/invoke",
        json={"input": {"text": "Hello world. How are you?"}},
    ).json()
    assert res["output"] == {"characters": 25, "words": 5, "sentences": 2}


def test_invoke_validation_error():
    res = client.post("/features/calculator/invoke", json={"input": {}})
    assert res.status_code == 422


def test_invoke_feature_input_error():
    # Schema-valid string, but not a usable expression -> controlled 422,
    # not an opaque 500.
    res = client.post(
        "/features/calculator/invoke",
        json={"input": {"expression": "2 +"}},
    )
    assert res.status_code == 422
    assert "invalid expression" in res.json()["detail"]


def test_mcp_call_feature_input_error():
    res = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "calculator", "arguments": {"expression": "2 +"}},
        },
    ).json()
    assert res["result"]["isError"] is True
    assert "invalid expression" in res["result"]["content"][0]["text"]


def test_invoke_unknown_feature_404():
    res = client.post("/features/nope/invoke", json={"input": {}})
    assert res.status_code == 404


# --- MCP ---------------------------------------------------------------------

def _rpc(method, params=None, msg_id=1):
    payload = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        payload["params"] = params
    return client.post("/mcp", json=payload).json()


def test_mcp_initialize():
    res = _rpc("initialize")
    assert res["result"]["serverInfo"]["name"] == "agent-features-gateway"


def test_mcp_tools_list():
    tools = _rpc("tools/list")["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"calculator", "text_stats", "clock"} <= names
    # Each tool carries the feature's JSON Schema as its inputSchema.
    calc = next(t for t in tools if t["name"] == "calculator")
    assert calc["inputSchema"]["required"] == ["expression"]


def test_mcp_tools_call():
    res = _rpc("tools/call", {"name": "calculator", "arguments": {"expression": "6 / 2"}})
    result = res["result"]
    assert result["isError"] is False
    assert '"result": 3.0' in result["content"][0]["text"]


def test_mcp_tools_call_validation_error():
    res = _rpc("tools/call", {"name": "calculator", "arguments": {}})
    assert res["result"]["isError"] is True


def test_mcp_unknown_method():
    res = _rpc("does/not/exist")
    assert res["error"]["code"] == -32601
