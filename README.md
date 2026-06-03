# Agent Features — Features as a Service for Agents

A lightweight **agent capability marketplace**. AI agents discover modular
*features* (tools/capabilities) and invoke them on demand over a clean HTTP API.

Think of it as an app store for agent tools: each feature publishes a manifest
(name, version, description, tags, JSON input/output schemas) so an agent — or
an LLM doing tool-use — can browse what's available and call it with validated
arguments.

## Why

LLM agents are only as capable as the tools they can reach. Instead of baking
every tool into every agent, this service hosts features behind a uniform
contract:

- **Discoverable** — `GET /features` returns machine-readable manifests an agent
  can feed straight into a tool-use loop.
- **Self-describing** — every feature ships JSON Schema for its inputs and
  outputs, so calls are validated before they run.
- **Uniform invocation** — one endpoint shape, `POST /features/{name}/invoke`,
  for every capability.
- **Pluggable** — drop a new file in `app/features/`, decorate it, and it's
  live. No wiring required.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# run the service
uvicorn app.main:app --reload

# interactive API docs
open http://127.0.0.1:8000/docs
```

## API

| Method | Path                          | Purpose                                  |
|--------|-------------------------------|------------------------------------------|
| GET    | `/`                           | Service info                             |
| GET    | `/health`                     | Liveness probe                           |
| GET    | `/features`                   | Browse the catalog (filter by `tag`/`q`) |
| GET    | `/features/{name}`            | Full manifest for one feature            |
| POST   | `/features/{name}/invoke`     | Run a feature with validated inputs      |
| GET    | `/features/{name}/stats`      | Invocation count & latency for a feature |

### Browse the catalog

```bash
curl http://127.0.0.1:8000/features
curl "http://127.0.0.1:8000/features?tag=math"
curl "http://127.0.0.1:8000/features?q=time"
```

### Invoke a feature

```bash
curl -X POST http://127.0.0.1:8000/features/calculator/invoke \
  -H 'content-type: application/json' \
  -d '{"input": {"expression": "2 * (3 + 4)"}}'
```

```json
{
  "feature": "calculator",
  "version": "1.0.0",
  "output": {"result": 14.0},
  "latency_ms": 0.21
}
```

## Built-in features

| Name          | Tags             | What it does                                  |
|---------------|------------------|-----------------------------------------------|
| `calculator`  | math             | Safely evaluates an arithmetic expression     |
| `text_stats`  | text, nlp        | Word/char/sentence counts for a block of text |
| `clock`       | time, utility    | Current time in a given timezone offset       |
| `uuid`        | utility, id      | Generates one or more UUID4 identifiers        |
| `hash`        | utility, crypto  | Hashes text with md5/sha1/sha256              |

## Adding a feature

Create `app/features/my_feature.py`:

```python
from pydantic import BaseModel
from app.core import Feature
from app.registry import feature


@feature
class Reverse(Feature):
    name = "reverse"
    description = "Reverses a string."
    tags = ["text"]

    class Input(BaseModel):
        text: str

    class Output(BaseModel):
        reversed: str

    def run(self, payload: "Reverse.Input") -> "Reverse.Output":
        return self.Output(reversed=payload.text[::-1])
```

It's auto-discovered on startup — no registration call needed.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Using it from an agent

See [`examples/agent_client.py`](examples/agent_client.py) for a tiny client
that lists features and turns each manifest into an OpenAI/Anthropic-style
tool definition, then invokes one.
