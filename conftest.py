"""Test bootstrap: ensure generated gRPC stubs exist and are importable.

The stubs (``gen/python``) are generated from ``proto/`` — normally by ``buf
generate`` / ``make proto``, but we self-bootstrap here via grpc_tools so a
fresh checkout runs the end-to-end test with no extra step. The reference
feature under ``examples/features/echo`` is added to the path too.
"""

import os
import sys

_ROOT = os.path.dirname(__file__)
_GEN = os.path.join(_ROOT, "gen", "python")
_PROTO = os.path.join(_ROOT, "proto", "agentfeatures", "v1", "feature.proto")


def _ensure_stubs() -> None:
    pb2 = os.path.join(_GEN, "agentfeatures", "v1", "feature_pb2.py")
    if os.path.exists(pb2):
        return
    try:
        import grpc_tools
        from grpc_tools import protoc
    except ImportError:  # grpcio-tools absent; the e2e test will importorskip.
        return
    os.makedirs(_GEN, exist_ok=True)
    # grpc_tools bundles the well-known protos (Struct, Timestamp); the `python
    # -m` CLI adds this include automatically, a direct main() call must not.
    well_known = os.path.join(os.path.dirname(grpc_tools.__file__), "_proto")
    rc = protoc.main([
        "grpc_tools.protoc",
        f"-I{os.path.join(_ROOT, 'proto')}",
        f"-I{well_known}",
        f"--python_out={_GEN}",
        f"--grpc_python_out={_GEN}",
        _PROTO,
    ])
    if rc != 0:
        return
    for pkg in (("agentfeatures",), ("agentfeatures", "v1")):
        open(os.path.join(_GEN, *pkg, "__init__.py"), "a").close()


_ensure_stubs()

for _path in (_GEN, os.path.join(_ROOT, "examples", "features", "echo")):
    if _path not in sys.path:
        sys.path.insert(0, _path)
