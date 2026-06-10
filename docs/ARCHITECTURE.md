# Agent Features Platform — Reference Architecture

> **Features as a Service for Agents** — a cloud-native, **agent-native**,
> **protocol-first** marketplace where AI agents discover and invoke modular
> capabilities ("features") on demand.

This document is the reference design. It is **protocol-first**: the wire
contract in [`proto/agentfeatures/v1/feature.proto`](../proto/agentfeatures/v1/feature.proto)
is the source of truth, and every component — gateway, operator, feature
runtime — conforms to it.

---

## 1. Design principles

| # | Principle | What it means here |
|---|-----------|--------------------|
| 1 | **Protocol-first** | The contract (Protobuf/gRPC + MCP) is authoritative. Code is generated from / validated against it. Schemas travel with every feature. |
| 2 | **Agent-native** | Agents are first-class clients. Discovery and invocation map directly onto an LLM tool-use loop. The external protocol is **MCP** (Model Context Protocol). |
| 3 | **AI-native** | A feature can itself be an AI workload (inference, RAG, embeddings). Discovery is semantic, not just keyword. GPU-aware scheduling is a runtime concern, not a special case. |
| 4 | **Cloud-native / CNCF** | Kubernetes control plane, **containerd** runtime, OCI packaging, declarative CRDs, OpenTelemetry everywhere. |
| 5 | **Declarative & reconciled** | A `Feature` is a Kubernetes Custom Resource. An operator reconciles desired state into running workloads. |

---

## 2. The protocol (protocol-first)

Two layers, one contract.

### 2.1 Agent-facing — MCP (Model Context Protocol)

Agents speak **MCP**, the agent-native standard for tool discovery and
invocation. The gateway exposes the catalog as MCP *tools*:

- `tools/list` → every published `Feature` becomes an MCP tool whose
  `inputSchema` is the feature's JSON Schema.
- `tools/call` → invokes a feature; the result is the feature's output.

This means any MCP-capable agent (Claude, etc.) consumes the marketplace with
**zero custom glue** — the manifest *is* the tool definition.

### 2.2 Control plane — gRPC / Protobuf

Internally, components communicate over gRPC defined in
[`feature.proto`](../proto/agentfeatures/v1/feature.proto):

- `FeatureCatalog` — `Discover`, `Describe` (browse/search the catalog).
- `FeatureService` — `Invoke`, `InvokeStream` (run a capability; the contract
  every feature workload implements).

gRPC + Protobuf are themselves CNCF-graduated, giving us strong typing,
streaming, and polyglot codegen. The MCP layer is a thin adapter over these.

```
        ┌──────────────┐   MCP (JSON-RPC)    ┌─────────────────────┐
Agent ──▶│   Gateway    │◀───────────────────▶│  Agent tool-use loop │
        │ (FastAPI/MCP) │                     └─────────────────────┘
        └──────┬───────┘
               │ gRPC (feature.proto)
        ┌──────▼───────┐     resolves      ┌──────────────────┐
        │ FeatureCatalog│◀────────────────▶│  Kubernetes API   │  (Feature CRs)
        └──────┬───────┘                   └──────────────────┘
               │ gRPC Invoke
        ┌──────▼───────┐
        │ Feature pod  │  ← OCI container, run by containerd via CRI
        └──────────────┘
```

---

## 3. Resource model

### 3.1 `Feature` (CRD, `agentfeatures.io/v1alpha1`)

The unit of the marketplace. Authoring a capability = applying a `Feature` CR.

```yaml
apiVersion: agentfeatures.io/v1alpha1
kind: Feature
metadata:
  name: web-summarizer
spec:
  description: "Fetches a URL and returns an LLM summary."
  image: ghcr.io/agennext/feature-web-summarizer:1.2.0
  protocol: grpc            # how the gateway talks to the workload
  tags: [web, nlp, ai]
  visibility: public
  inputSchema: |            # JSON Schema — also the MCP tool inputSchema
    {"type":"object","properties":{"url":{"type":"string"}},"required":["url"]}
  outputSchema: |
    {"type":"object","properties":{"summary":{"type":"string"}}}
  runtime:
    minReplicas: 0          # scale-to-zero via KEDA/Knative
    maxReplicas: 10
    resources:
      requests: {cpu: "250m", memory: "256Mi"}
    accelerator: none       # or "nvidia.com/gpu: 1" for AI-native features
status:
  phase: Ready              # Pending | Provisioning | Ready | Failed
  endpoint: web-summarizer.features.svc.cluster.local:9090
  observedGeneration: 3
  conditions: [...]
```

The set of `Feature` CRs **is** the registry — no separate database. The
Kubernetes API server is the catalog's system of record.

### 3.2 `FeatureInvocation` (optional CRD)

For audited or long-running/async invocations, an `Invoke` may be recorded as a
`FeatureInvocation` CR (request, status, result ref, trace ID) — enabling
GitOps-style auditing and replay.

---

## 4. Components

| Component | Tech | Responsibility |
|-----------|------|----------------|
| **Gateway** | Python / FastAPI (existing scaffold) + MCP adapter | Agent entrypoint. Speaks MCP outward, gRPC inward. Validates inputs against `inputSchema`. Emits OTel spans. |
| **Feature Operator** | **Go + Kubebuilder** (controller-runtime) | Watches `Feature` CRs; reconciles each into a `Deployment` + `Service` (+ HPA/KEDA `ScaledObject`); writes `status`. |
| **Feature runtime** | OCI container, any language | Implements `FeatureService` gRPC. An SDK/sidecar adapts a plain function to the contract. Scheduled by kubelet → **containerd** via CRI. |
| **Catalog service** | Go (reads k8s API) | Serves `Discover`/`Describe`; optional semantic search over embeddings of feature descriptions (AI-native discovery). |
| **Observability** | OpenTelemetry + Prometheus | Distributed traces span agent → gateway → feature; RED metrics per feature. |

The **gateway** keeps the FastAPI scaffold already committed; it gains an MCP
endpoint and a gRPC client instead of in-process feature execution.

---

## 5. Flows

### 5.1 Publish a feature (control plane)

```
author ──kubectl apply feature.yaml──▶ k8s API
                                          │ watch
                                  Feature Operator (Go)
                                          │ reconcile
                       Deployment + Service + ScaledObject
                                          │
                          status.endpoint populated, phase=Ready
                                          │
                              now discoverable in the catalog
```

### 5.2 Agent uses a feature (data plane)

```
agent ──MCP tools/list──▶ gateway ──Discover──▶ catalog (k8s CRs)
agent ◀── tool defs (manifests as MCP tools) ──┘
agent ──MCP tools/call(web-summarizer,{url})──▶ gateway
       gateway validates vs inputSchema
       gateway ──gRPC Invoke──▶ feature pod (containerd)
       gateway ◀── output ──┘   (OTel trace throughout)
agent ◀── result ──┘
```

---

## 6. CNCF landscape mapping

| Concern | Project |
|---------|---------|
| Orchestration | **Kubernetes** |
| Container runtime | **containerd** (CRI) |
| Packaging / distribution | **OCI** images, **Helm** chart |
| Wire protocol | **gRPC** + **Protobuf** (control plane), **MCP** (agent-facing) |
| Serverless / scale-to-zero | **Knative** or **KEDA** |
| Observability | **OpenTelemetry**, **Prometheus** |
| Networking / ingress | **Gateway API**, optional mesh (**Linkerd**/**Istio**) |
| Policy & admission | **OPA/Gatekeeper** (validate `Feature` specs) |
| Workload identity | **SPIFFE/SPIRE** (feature-to-feature authz) |
| GitOps delivery | **Argo CD** / **Flux** |

---

## 6.1 Feature supply chain

How a capability goes from source to a discoverable feature — the
platform-engineering layer *beneath* the gateway and operator:

| Stage | Tool | In this repo |
|-------|------|--------------|
| **Build** | **Cloud Native Buildpacks** (`pack`) — source → OCI image, no Dockerfile | `examples/features/echo/project.toml` |
| **Configure** | **KCL** — typed, validated authoring of `Feature` CRs | `config/kcl/` |
| **Provision** | **OpenTofu** — day-0 cluster deps, operator, gateway | `infra/opentofu/` |
| **Run** | **Kubernetes + containerd** — schedule & execute feature pods | operator-managed Deployments |
| **Serve** | **Gateway (MCP)** + **operator** | `gateway/`, `operator/` |
| **Observe** | **OpenTelemetry/Prometheus** (in-band) + **HertzBeat** (agentless monitor & alert) | `observability/` |

```
source ──Buildpacks──▶ OCI image ─┐
Feature CR authored in KCL ───────┤──▶ operator reconciles ──▶ Deployment+Service
cluster + deps via OpenTofu ──────┘        (containerd runs the pod)
                                                     │
                            gateway discovers (status: Ready) and routes;
                            OTel traces + HertzBeat alerts watch it all.
```

The contract stays central: `buf generate` (see `buf.yaml`, `buf.gen.yaml`)
produces the Go and Python stubs every stage shares.

---

## 7. Repository layout

```
.
├── proto/agentfeatures/v1/feature.proto   # protocol-first contract (source of truth)
├── buf.yaml, buf.gen.yaml                  # codegen (Go + Python) from the proto
├── docs/ARCHITECTURE.md                    # this document
├── gateway/                                # FastAPI + MCP gateway (REST + /mcp)
├── operator/                               # Go + Kubebuilder operator
│   ├── api/v1alpha1/feature_types.go       # Feature CRD types
│   ├── internal/controller/                # reconciler
│   └── config/                             # CRD, RBAC, samples
├── config/kcl/                             # KCL schemas to author/validate Features
├── infra/opentofu/                         # OpenTofu: provision the platform
├── observability/                          # OTel collector + HertzBeat monitors/alerts
├── examples/
│   ├── agent_client.py                     # discover-then-invoke demo (MCP)
│   └── features/echo/                      # reference feature (Buildpacks-built)
└── tests/                                  # gateway REST + MCP tests
```

---

## 8. Roadmap

| Milestone | Deliverable |
|-----------|-------------|
| **M0 — Protocol & design** *(this PR)* | `feature.proto`, reference architecture. |
| M1 — Operator skeleton | Kubebuilder project, `Feature` CRD, reconcile to Deployment+Service. |
| M2 — Gateway | MCP endpoint + gRPC client over the existing FastAPI app. |
| M3 — Reference feature | One OCI feature implementing `FeatureService` end-to-end on a kind cluster. |
| M4 — Scale & observe | KEDA scale-to-zero, OTel traces, Prometheus dashboards. |
| M5 — Hardening | OPA admission policies, SPIFFE identity, Helm chart, semantic discovery. |
