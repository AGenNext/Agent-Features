"""Agent Features gateway.

The gateway is the front door of the platform. It speaks MCP to agents on the
outside and gRPC to feature workloads on the inside (see docs/ARCHITECTURE.md).
This package keeps those two concerns behind swappable interfaces so the same
HTTP/MCP surface works whether features run in-process (dev) or as Kubernetes
workloads (prod).
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
