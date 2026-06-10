"""The static marketplace dashboard is served and wired to the REST API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from gateway.main import create_app


def client() -> TestClient:
    return TestClient(create_app())


def test_ui_served_at_slash_ui():
    r = client().get("/ui/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # Key panels are present in the single-file SPA.
    for marker in (
        "Agent Features", "Live ranking", "Invoke console", "Capabilities",
        "Comparator", "Evaluator", "Component generator",
        "Orchestrator", "flow builder", "Chat", "Provenance", "Agent DSL",
    ):
        assert marker in r.text


def test_ui_bare_path_redirects():
    r = client().get("/ui", follow_redirects=False)
    assert r.status_code in (307, 308)
    assert r.headers["location"] == "/ui/"


def test_root_info_advertises_ui():
    assert client().get("/").json()["ui"] == "/ui"
