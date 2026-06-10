"""End-to-end: agent (MCP/REST) -> gateway -> gRPC -> real feature workload.

Boots the reference echo feature as a real gRPC server, points the gateway's
GrpcInvoker at it, and drives an invocation through both the REST and MCP
faces. This exercises the actual wire path (Struct marshalling, the
FeatureService contract, response mapping) — everything the operator would wire
up in a cluster, minus Kubernetes scheduling.

Skipped automatically if the generated stubs are absent (run `make proto`).
"""

from __future__ import annotations

import json
from concurrent import futures

import pytest

grpc = pytest.importorskip("grpc")
pytest.importorskip("agentfeatures.v1.feature_pb2")

from agentfeatures.v1 import feature_pb2_grpc  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from server import EchoService  # noqa: E402  (examples/features/echo/server.py)

from gateway.catalog import InMemoryCatalog  # noqa: E402
from gateway.invoker import GrpcInvoker  # noqa: E402
from gateway.main import create_app  # noqa: E402
from gateway.models import Manifest  # noqa: E402

ECHO = Manifest(
    name="echo",
    description="Echoes its input back.",
    tags=["example"],
    input_schema={
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    },
)


@pytest.fixture
def echo_server():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    feature_pb2_grpc.add_FeatureServiceServicer_to_server(EchoService(), server)
    port = server.add_insecure_port("localhost:0")
    server.start()
    yield port
    server.stop(grace=None)


@pytest.fixture
def client(echo_server):
    catalog = InMemoryCatalog([ECHO])
    invoker = GrpcInvoker(endpoint_resolver=lambda _name: f"localhost:{echo_server}")
    return TestClient(create_app(catalog=catalog, invoker=invoker))


def test_rest_invoke_over_grpc(client):
    res = client.post("/features/echo/invoke", json={"input": {"message": "hello"}})
    assert res.status_code == 200
    assert res.json()["output"] == {"echo": "hello"}


def test_mcp_call_over_grpc(client):
    res = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"message": "yo"}},
        },
    ).json()
    assert res["result"]["isError"] is False
    assert json.loads(res["result"]["content"][0]["text"]) == {"echo": "yo"}
