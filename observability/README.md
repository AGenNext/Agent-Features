# Observability

Two complementary layers watch the platform:

| Tool | Role |
|------|------|
| **OpenTelemetry + Prometheus** | In-band telemetry. The gateway and features emit OTLP traces/metrics; the collector (`otel-collector.yaml`) batches and exports to Prometheus (RED metrics) and a tracing backend. A trace spans agent → gateway → feature. |
| **Apache HertzBeat** | Agentless, out-of-band monitoring + alerting. Probes the gateway and feature endpoints (`hertzbeat/monitors.yaml`) and fires threshold alarms (`hertzbeat/alerts.yaml`). |

## Why both

- **OTel/Prometheus** answers *"how is a request behaving inside the system?"*
  (latency distribution, error rate, span timing across features).
- **HertzBeat** answers *"is it up, from the outside, right now?"* and owns
  **alerting** — paging when the gateway is down or a feature endpoint is
  unreachable. Agentless probing suits features that scale to zero and churn.

## Wiring

- The OTel Collector is installed by `infra/opentofu/platform.tf`
  (`enable_otel=true`). Supply this config to the Helm release.
- Import `hertzbeat/monitors.yaml` and `hertzbeat/alerts.yaml` into HertzBeat
  (API or UI) and attach notice receivers (Slack/webhook/email).
- Per-feature monitors can be generated from the catalog so monitoring tracks
  features as the operator creates and removes them.
