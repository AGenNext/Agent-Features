"""Echo feature — the reference feature workload.

It implements the ``FeatureService`` gRPC contract from
``proto/agentfeatures/v1/feature.proto``: ``Invoke`` returns its input's
``message`` back as ``echo``. This is what the gateway's GrpcInvoker calls.

The generated stubs (``feature_pb2``, ``feature_pb2_grpc``) are produced from
the proto with ``buf generate`` (see buf.gen.yaml at the repo root) and made
importable as the ``agentfeatures.v1`` package.
"""

from __future__ import annotations

import time
from concurrent import futures

import grpc
from google.protobuf import struct_pb2

from agentfeatures.v1 import feature_pb2, feature_pb2_grpc

PORT = 9090


class EchoService(feature_pb2_grpc.FeatureServiceServicer):
    def Invoke(self, request, context):  # noqa: N802 (gRPC naming)
        start = time.perf_counter()
        message = request.input.fields["message"].string_value

        output = struct_pb2.Struct()
        output.update({"echo": message})
        latency_ms = (time.perf_counter() - start) * 1000
        return feature_pb2.InvokeResponse(output=output, latency_ms=latency_ms)


def serve() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    feature_pb2_grpc.add_FeatureServiceServicer_to_server(EchoService(), server)
    server.add_insecure_port(f"[::]:{PORT}")
    server.start()
    print(f"echo feature listening on :{PORT}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
