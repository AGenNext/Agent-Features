# Agent Features — Features as a Service for Agents

A cloud-native, **agent-native** marketplace where AI agents discover modular
*features* (tools/capabilities) and invoke them on demand. Think of it as an
app store for agent tools: each feature publishes a self-describing manifest, so
an agent — or an LLM doing tool-use — can browse what's available and call it
with validated arguments.

The platform is **protocol-first**: the contract in
[`proto/agentfeatures/v1/feature.proto`](proto/agentfeatures/v1/feature.proto)
is the source of truth. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for
the full reference design (Kubernetes operator, `Feature` CRD, containerd
runtime, CNCF mapping, MCP).

## What's here today

This repo currently implements the **gateway** — the front door agents talk to.
It speaks **MCP** (Model Context Protocol) outward and dispatches to feature
workloads inward. In dev mode it runs a few sample features in-process so the
whole discover → invoke loop works with no cluster:

```
Agent ──MCP──▶ Gateway ──(dev: in-process / prod: gRPC)──▶ Feature
                └ browse catalog, validate input, route, observe
```

The Kubernetes operator and gRPC feature runtime are the next milestones (see
the roadmap in the architecture doc).

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

uvicorn gateway.main:app --reload
open http://127.0.0.1:8000/ui          # marketplace dashboard
open http://127.0.0.1:8000/docs        # interactive REST docs
```

### Marketplace dashboard

A zero-build dashboard ships with the gateway at **`/ui`** — a framework-free
SPA that consumes the REST API below (same-origin, no toolchain). It's a *panel
of panels*: browse **capabilities**, watch the **live vendor ranking** update as
calls succeed, scan the **feature** catalog, and exercise any feature from the
**invoke console**.

Or run it in a container with Docker Compose (gateway in dev mode — the whole
marketplace, no cluster):

```bash
docker compose up --build                            # gateway at :8000
docker compose --profile observability up --build    # + HertzBeat monitoring
```

> The operator needs a Kubernetes API, so it's not in Compose — use the kind
> path (`make e2e`) for the operator + gRPC feature pods.

## API

| Method | Path                          | Purpose                                  |
|--------|-------------------------------|------------------------------------------|
| GET    | `/`                           | Service info                             |
| GET    | `/ui`                         | Marketplace dashboard (static SPA)       |
| GET    | `/health`                     | Liveness probe                           |
| GET    | `/features`                   | Browse the catalog (filter by `tag`/`q`) |
| GET    | `/features/{name}`            | Full manifest + status for one feature   |
| GET    | `/features/{name}/signature`  | Manifest digest + Sigstore/cosign status |
| POST   | `/agents/compile`             | Compile agent.next DSL → composite + 6-language client stubs |
| POST   | `/features/{name}/invoke`     | Run a feature with validated inputs      |
| GET    | `/capabilities`               | Canonical capabilities + their ranked vendors |
| GET    | `/capabilities/{cap}`         | All providers of a capability, best-first |
| POST   | `/capabilities/{cap}/invoke`  | Resolve the best provider and invoke (pin with `?vendor=`/`?version=`) |
| GET    | `/capabilities/{cap}/ranking` | Live vendor ranking with scores & metrics |
| POST   | `/mcp`                        | MCP (JSON-RPC): `initialize`, `tools/list`, `tools/call` |

### Browse and invoke (REST)

```bash
curl http://127.0.0.1:8000/features
curl "http://127.0.0.1:8000/features?tag=math"

curl -X POST http://127.0.0.1:8000/features/calculator/invoke \
  -H 'content-type: application/json' \
  -d '{"input": {"expression": "2 * (3 + 4)"}}'
# -> {"feature":"calculator","version":"1.0.0","output":{"result":14.0},"latency_ms":0.2}
```

### Use it as an agent (MCP)

```bash
curl -X POST http://127.0.0.1:8000/mcp -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

curl -X POST http://127.0.0.1:8000/mcp -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call",
       "params":{"name":"calculator","arguments":{"expression":"6 / 2"}}}'
```

Each feature manifest *is* an MCP tool definition — its `input_schema` becomes
the tool's `inputSchema` — so MCP-capable agents need no custom glue. A runnable
client is in [`examples/agent_client.py`](examples/agent_client.py).

## Marketplace: capabilities & vendors

A **feature** is one vendor's implementation (unique `name`, `version`,
`vendor`, `trust` tier). A **capability** is the canonical thing it provides —
many vendors can compete on the same capability. The marketplace key is
`(capability, vendor, version)`.

```bash
curl http://127.0.0.1:8000/capabilities          # canonical capabilities + ranked vendors
curl http://127.0.0.1:8000/capabilities/greet     # every provider, best-first

# Let the marketplace pick the best provider...
curl -X POST http://127.0.0.1:8000/capabilities/greet/invoke \
  -H 'content-type: application/json' -d '{"input":{"name":"Ada"}}'
# ...or pin a vendor / version (ranges supported):
curl -X POST "http://127.0.0.1:8000/capabilities/greet/invoke?vendor=globex" ...
curl -X POST "http://127.0.0.1:8000/capabilities/greet/invoke?version=^1.2.0" ...
```

**Versioning** — `?version=` accepts exact (`1.2.0`), caret (`^1.2`), tilde
(`~1.2`), comparators (`>=1.2.0`, `<2.0.0`), or `latest`/`*`. Among satisfying
providers the marketplace still applies ranking (below).

**Ranking** is pluggable (`gateway/ranking.py`). The default `MetricsPolicy`
*learns*: every invocation records success/latency, and providers are scored by
observed `success_rate − latency_penalty + trust_prior`, with an optimistic
cold start so new vendors aren't starved. Set `AGENT_FEATURES_RANKING=baseline`
for the static trust→version order instead.

```bash
curl http://127.0.0.1:8000/capabilities/greet/ranking   # live scores + metrics
```

A vendor that actually performs overtakes a more-trusted one that doesn't — a
10%+ success-rate gap overrides the trust prior. The `greet` capability ships
two demo vendors (`acme`, verified; `globex`, community) to show resolution,
pinning, and ranking.

## Sample (dev) features

| Name          | Tags             | What it does                                  |
|---------------|------------------|-----------------------------------------------|
| `calculator`  | math, utility    | Safely evaluates an arithmetic expression     |
| `text_stats`  | text, nlp        | Character/word/sentence counts for a text     |
| `clock`       | time, utility    | Current time at a given UTC offset            |

In production these become independent OCI containers implementing the
`FeatureService` gRPC contract; here they run in-process via `LocalInvoker`.

## Project layout

```
proto/agentfeatures/v1/feature.proto   # protocol-first contract (source of truth)
docs/ARCHITECTURE.md                    # full reference design + CNCF mapping
gateway/                                # FastAPI + MCP gateway
  ├── main.py        # app & routes (REST + /mcp)
  ├── models.py      # Python projection of the proto
  ├── catalog.py     # discovery: InMemoryCatalog (dev) / KubernetesCatalog (stub)
  ├── invoker.py     # dispatch: LocalInvoker (dev) / GrpcInvoker (stub)
  ├── validation.py  # JSON-Schema input validation
  ├── mcp.py         # MCP (JSON-RPC) adapter
  └── samples.py     # dev sample features
examples/agent_client.py                # discover-then-invoke demo
tests/test_gateway.py                   # REST + MCP end-to-end tests
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
