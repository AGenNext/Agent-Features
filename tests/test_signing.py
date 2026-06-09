"""Manifest digest + Sigstore/cosign signature status."""

from __future__ import annotations

from fastapi.testclient import TestClient

from gateway import signing
from gateway.main import create_app

client = TestClient(create_app())


def test_digest_is_canonical_and_stable():
    # Key order / whitespace must not change the digest.
    a = signing.manifest_digest({"name": "x", "version": "1.0.0"})
    b = signing.manifest_digest({"version": "1.0.0", "name": "x"})
    assert a == b
    assert a.startswith("sha256:") and len(a) == len("sha256:") + 64


def test_digest_changes_with_content():
    assert signing.manifest_digest({"v": 1}) != signing.manifest_digest({"v": 2})


def test_signature_endpoint_reports_unsigned_without_a_bundle(tmp_path, monkeypatch):
    # No bundle on disk -> 'unsigned', but the digest + verify command are given.
    monkeypatch.setattr(signing, "SIGNATURES_DIR", str(tmp_path))
    body = client.get("/features/calculator/signature").json()
    assert body["feature"] == "calculator"
    assert body["digest"].startswith("sha256:")
    assert body["signed"] is False
    assert body["status"] == "unsigned"
    assert "cosign verify-blob" in body["command"]


def test_signature_endpoint_unknown_feature_404():
    assert client.get("/features/nope/signature").status_code == 404


def test_resolve_bundle_only_matches_known_names():
    # The request string is used solely as a key into an allowlist built from
    # trusted names, so traversal / injection inputs resolve to nothing and
    # never reach a path or argv.
    known = ["calculator", "greet-acme"]
    assert signing.resolve_bundle("calculator", known).endswith("calculator.bundle")
    for bad in ["../../etc/passwd", "a/b", "name;rm -rf", "..", "unknown"]:
        assert signing.resolve_bundle(bad, known) is None


def test_verify_without_bundle_is_unsigned():
    res = signing.verify("calculator", {"name": "calculator"}, None)
    assert res["status"] == "unsigned"
    assert res["signed"] is False
    assert res["command"] == ""
