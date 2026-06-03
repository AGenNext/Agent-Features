# Echo feature (reference workload)

The smallest complete feature: it implements the `FeatureService` gRPC contract
and echoes its input. It demonstrates the full feature supply chain —
**source → OCI image (Buildpacks) → containerd → discoverable via the gateway**.

## 1. Generate the gRPC stubs (protocol-first)

From the repo root:

```bash
buf generate            # writes gen/python/agentfeatures/v1/*
```

Make `gen/python` importable when running locally:

```bash
export PYTHONPATH="$PWD/gen/python:$PYTHONPATH"
```

## 2. Run locally

```bash
pip install -r requirements.txt
python server.py        # listens on :9090
```

## 3. Build the image with Buildpacks (no Dockerfile)

```bash
pack build ghcr.io/agennext/feature-echo:0.1.0 \
  --path examples/features/echo \
  --builder paketobuildpacks/builder-jammy-base
```

The resulting image is what `Feature.spec.image` points at — see
`operator/config/samples/agentfeatures_v1alpha1_feature.yaml` and
`config/kcl/main.k`.

## 4. Publish to the marketplace

```bash
kubectl apply -f ../../../operator/config/samples/agentfeatures_v1alpha1_feature.yaml
# operator reconciles -> Deployment + Service -> status.phase: Ready
# gateway then lists it as an MCP tool and routes invocations to it.
```
