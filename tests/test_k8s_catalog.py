"""Unit tests for the Kubernetes catalog mapping (no cluster required).

A fake custom-objects API stands in for the kubernetes client, so we can verify
Feature custom resources map correctly to the gateway's Feature model.
"""

from __future__ import annotations

from gateway.catalog import KubernetesCatalog, feature_from_cr
from gateway.models import Phase, Visibility

CR = {
    "metadata": {"name": "echo"},
    "spec": {
        "description": "Echoes input.",
        "tags": ["example", "utility"],
        "visibility": "Internal",
        "protocol": "grpc",
        "inputSchema": '{"type":"object","properties":{"message":{"type":"string"}},"required":["message"]}',
        "outputSchema": '{"type":"object","properties":{"echo":{"type":"string"}}}',
    },
    "status": {"phase": "Ready", "endpoint": "echo.features.svc.cluster.local:9090"},
}


class FakeApi:
    def __init__(self, items):
        self._items = items

    def list_namespaced_custom_object(self, group, version, namespace, plural):
        return {"items": self._items}


def test_feature_from_cr_maps_fields():
    f = feature_from_cr(CR)
    assert f.manifest.name == "echo"
    assert f.manifest.visibility == Visibility.INTERNAL
    assert f.manifest.input_schema["required"] == ["message"]
    assert f.phase == Phase.READY
    assert f.endpoint == "echo.features.svc.cluster.local:9090"


def test_list_filters_by_tag_and_query():
    other = {
        "metadata": {"name": "clock"},
        "spec": {"description": "time", "tags": ["time"]},
        "status": {"phase": "Ready"},
    }
    catalog = KubernetesCatalog(api=FakeApi([CR, other]))

    assert [f.manifest.name for f in catalog.list()] == ["clock", "echo"]
    assert [f.manifest.name for f in catalog.list(tags=["utility"])] == ["echo"]
    assert [f.manifest.name for f in catalog.list(query="time")] == ["clock"]
