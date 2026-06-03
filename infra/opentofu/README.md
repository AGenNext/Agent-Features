# Platform provisioning (OpenTofu)

Day-0 infrastructure for the Agent Features platform, declared with
[OpenTofu](https://opentofu.org). It provisions, against an existing
Kubernetes cluster:

- the `agent-features-system` and `features` namespaces,
- the `Feature` CRD (from the operator's committed manifest),
- the **operator** (ServiceAccount + ClusterRole + binding + Deployment),
- the **gateway** (Deployment + Service),
- optional CNCF deps via Helm: **KEDA** (scale-to-zero) and the
  **OpenTelemetry Collector** (telemetry pipeline).

## Usage

```bash
cd infra/opentofu
tofu init
tofu plan  -var kube_context=kind-agent-features
tofu apply -var kube_context=kind-agent-features
```

Override images and toggles via variables (see `variables.tf`):

```bash
tofu apply \
  -var operator_image=ghcr.io/agennext/agent-features-operator:v0.1.0 \
  -var gateway_image=ghcr.io/agennext/agent-features-gateway:v0.1.0 \
  -var enable_keda=true -var enable_otel=true
```

## Notes

- The cluster itself (kind/EKS/GKE) is assumed to exist; this config targets a
  reachable kube-context. Add a cluster module if you want OpenTofu to create
  the cluster too.
- The CRD is applied via `kubernetes_manifest`, which reads the cluster schema
  at plan time — run against a live context, or split CRD application into a
  bootstrap apply (`-target=kubernetes_manifest.feature_crd`) first.
