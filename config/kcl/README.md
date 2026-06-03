# Feature authoring with KCL

Typed, validated authoring of `Feature` custom resources using
[KCL](https://kcl-lang.io). The schemas in `feature.k` mirror the CRD but add
`check` blocks, so mistakes (missing image, `maxReplicas < minReplicas`, bad
port) fail at author time rather than at `kubectl apply`.

## Usage

```bash
# Render the Features in main.k to Kubernetes YAML.
kcl run main.k > features.yaml
kubectl apply -f features.yaml

# Or pipe straight to the cluster.
kcl run main.k | kubectl apply -f -
```

## Why KCL over raw YAML

- **Validated** — `check` blocks reject invalid specs before they reach the API.
- **Typed & defaulted** — `protocol`, `visibility`, replica counts get safe
  defaults; enums are enforced.
- **Composable** — share a base spec across many features, override per feature.

Edit `main.k` to add your own features.
