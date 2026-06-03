# Agent Features Operator

A Kubernetes operator (Go + controller-runtime, Kubebuilder layout) that
reconciles a `Feature` custom resource into a running workload: a `Deployment`
plus a `Service`, with status reporting the lifecycle `phase` and the in-cluster
`endpoint` the gateway routes to.

```
Feature CR ──▶ FeatureReconciler ──▶ Deployment + Service
                                      status.phase / status.endpoint
```

## Layout

```
api/v1alpha1/feature_types.go        # the Feature CRD (Go types + markers)
internal/controller/feature_controller.go  # the reconciler
cmd/main.go                          # manager entrypoint
config/crd/bases/                    # CRD manifest
config/rbac/role.yaml                # ClusterRole
config/samples/                      # example Feature
```

The CRD spec mirrors the protocol-first contract in
[`../proto/agentfeatures/v1/feature.proto`](../proto/agentfeatures/v1/feature.proto):
`image`, `protocol`, `inputSchema`/`outputSchema`, `tags`, `visibility`, and a
`runtime` block (replicas, resources, `accelerator` for AI-native/GPU features).

## Develop

```bash
go build ./...      # compile
go vet ./...        # static checks
make run            # run against the current kube-context

make install        # apply the CRD
make deploy         # CRD + RBAC + a sample Feature
```

> `config/crd/bases` and `api/v1alpha1/zz_generated.deepcopy.go` are committed by
> hand (rather than via `controller-gen`) so the module builds and applies
> without the codegen toolchain. Regenerating them with Kubebuilder is safe.

## How a feature reaches the cluster

1. Source is built into an OCI image by **Buildpacks** → `spec.image`.
2. A `Feature` CR is authored/validated with **KCL** and applied.
3. This operator reconciles it into a Deployment + Service.
4. kubelet runs the pod via **containerd**.
5. The gateway discovers it (`status.phase: Ready`) and routes invocations to
   `status.endpoint`.
