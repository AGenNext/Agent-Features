# Composing agents from the marketplace (Docker Hub–style)

A developer assembles an agent the way they assemble a container app: pull
building blocks from a **registry** and wire them together in a **compose file**.

| Docker | Agent Features |
|--------|----------------|
| Docker Hub (registry of images) | the **feature marketplace** (`/capabilities`) — versioned, multi-vendor, ranked |
| `image:tag` | a **capability** + version (`greet`, `^1.2`) — resolved & ranked to a vendor |
| `docker-compose.yml` | an **agent compose file** — a composite pipeline of capabilities |
| `docker pull` | capability **resolution** (best vendor, honoring version pins) |
| `docker push` | `POST /compose` — **publish** a composite to the registry |
| `docker run` | `POST /composites/{name}/invoke` — **run** it |

## Why this is the efficient way to build agents

The agent stays thin: instead of hand-chaining three tool calls, it calls one
**composed capability**. The platform handles, for every step:

- **resolution + ranking** — each step automatically gets the best-performing
  vendor (the ranking engine), so your agent improves without code changes;
- **validation** — inputs are schema-checked before each call;
- **observability** — every sub-call is recorded and traced.

Composites are themselves capabilities, so they **compose recursively** — a
pipeline can use another pipeline.

## Files

- [`greet-report.agent.yaml`](greet-report.agent.yaml) — a working two-step
  pipeline (`greet` → `text_stats`) over the dev sample capabilities.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/composites` | List published composites |
| GET  | `/composites/{name}` | Full composite spec |
| POST | `/compose` | Publish a composite (the compose file as JSON) |
| POST | `/composites/{name}/invoke` | Run it; returns the composed output + per-step trace |

## The reference DSL

Step inputs and the final output reference the run context by dotted path:

- `input.<field>` — a field of the caller's input
- `<stepName>.<field>` — a field of an earlier step's output

That's the whole language — enough to pipe data through a pipeline, declaratively.
