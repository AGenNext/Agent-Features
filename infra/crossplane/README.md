# Crossplane packaging — provision the marketplace as one claim

[Crossplane](https://github.com/crossplane/crossplane) lets a platform team
define their own Kubernetes APIs by *composing* resources. This directory
packages the Agent-Features platform as such an API: creating a single
`AgentPlatform` claim provisions the namespace, the gateway
Deployment/Service, and the seeded `echo` Feature CR.

## Why it fits this project

Crossplane's model is the infrastructure mirror of our own composer:

| Crossplane | Agent-Features gateway |
|---|---|
| `Composition` (pipeline of composed resources) | `Composite` (pipeline of capability steps) |
| `CompositeResourceDefinition` (XRD declares the API) | composite `input_schema` declares the contract |
| Claim (`AgentPlatform`) | `POST /composites/{name}/invoke` |
| Patches wire claim fields → resources | refs wire `input.x` / `step.field` → steps |

The seeded feature is the dog-food moment: to Crossplane, a
`Feature` CR (`agentfeatures.io/v1alpha1`, reconciled by `operator/`) is just
another composed resource.

## Files

- `xrd.yaml` — `CompositeResourceDefinition`: the `XAgentPlatform` composite
  with namespaced claim kind `AgentPlatform` (parameters: `namespace`,
  `gatewayImage`, `replicas`, `catalogMode`).
- `composition.yaml` — pipeline-mode `Composition` using
  `function-patch-and-transform`; each workload is wrapped in a
  provider-kubernetes `Object`. Surfaces the gateway's in-cluster endpoint on
  the composite status.
- `claim.yaml` — example claim.

## Install

```sh
# 1. Crossplane core
helm install crossplane crossplane-stable/crossplane \
  --namespace crossplane-system --create-namespace

# 2. provider-kubernetes + the patch-and-transform function
kubectl apply -f - <<'EOF'
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata: {name: provider-kubernetes}
spec: {package: xpkg.crossplane.io/crossplane-contrib/provider-kubernetes:v0.14.1}
---
apiVersion: pkg.crossplane.io/v1
kind: Function
metadata: {name: function-patch-and-transform}
spec: {package: xpkg.crossplane.io/crossplane-contrib/function-patch-and-transform:v0.7.0}
EOF

# 3. The Feature CRD + operator (so the seeded Feature is reconciled)
kubectl apply -f ../../operator/config/crd/bases/agentfeatures.io_features.yaml

# 4. This platform API, then claim it
kubectl apply -f xrd.yaml -f composition.yaml
kubectl apply -f claim.yaml
kubectl get agentplatform marketplace -o jsonpath='{.status.gatewayEndpoint}'
```

## Limitations

- Conditional seeding (e.g. a `seedEchoFeature` flag) needs
  `function-go-templating`; this reference composition always seeds `echo`.
- provider-kubernetes needs RBAC to manage `features.agentfeatures.io`
  (and core resources) — grant its service account accordingly.
- Like the OpenTofu/KCL scaffolds, this is **validated YAML, not applied
  here**: the dev sandbox has no cluster or Crossplane control plane.
