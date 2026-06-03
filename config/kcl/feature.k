# KCL schemas for authoring and validating Feature custom resources.
# These mirror the CRD in operator/config/crd and the protocol-first contract
# in proto/agentfeatures/v1/feature.proto, but add typed, composable authoring
# with built-in validation (KCL `check` blocks) — so a malformed Feature fails
# at author time, not at `kubectl apply`.

schema Runtime:
    """Scheduling and scaling for a feature workload."""
    minReplicas: int = 1
    maxReplicas: int = 3
    # Device-plugin resource for AI-native features, e.g. "nvidia.com/gpu".
    accelerator?: str
    resources?: {str:}

    check:
        minReplicas >= 0, "minReplicas must be >= 0 (0 enables scale-to-zero)"
        maxReplicas >= minReplicas, "maxReplicas must be >= minReplicas"

schema FeatureSpec:
    """Desired state of a Feature."""
    description?: str
    image: str
    protocol: "grpc" | "http" = "grpc"
    port: int = 9090
    tags?: [str]
    visibility: "Public" | "Internal" | "Private" = "Public"
    # Marketplace identity: many vendors can provide the same capability.
    capability?: str   # defaults to the feature name if unset
    vendor: str = "community"
    trust: "Official" | "Verified" | "Community" = "Community"
    # JSON Schema (draft 2020-12) for invocation arguments; doubles as the
    # MCP tool inputSchema.
    inputSchema?: str
    outputSchema?: str
    runtime?: Runtime

    check:
        len(image) > 0, "image is required"
        port > 0 and port < 65536, "port must be in 1..65535"

schema Feature:
    """A capability published to the agent marketplace."""
    apiVersion: str = "agentfeatures.io/v1alpha1"
    kind: str = "Feature"
    metadata: {str:}
    spec: FeatureSpec

    check:
        "name" in metadata, "metadata.name is required"
