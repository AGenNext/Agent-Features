# Deploy & end-to-end

Manifests and a script to run the whole platform on a local
[kind](https://kind.sigs.k8s.io) cluster and prove the
**agent → gateway → operator-scheduled feature** loop.

## One command

```bash
make e2e        # requires docker, kind, kubectl, pack
```

`scripts/e2e.sh` will:

1. create a kind cluster (`deploy/kind/kind-config.yaml`),
2. build the **gateway** and **operator** images, and the **echo feature** with
   Buildpacks (no Dockerfile),
3. load them into kind,
4. apply namespaces, the `Feature` CRD, operator (RBAC + Deployment) and gateway
   (RBAC + Deployment + NodePort Service),
5. publish the echo `Feature`; the operator reconciles it to a Deployment +
   Service and reports `status.phase: Ready`,
6. invoke it through the gateway on `localhost:8000`.

Expected final output:

```json
{"feature": "echo", "version": "1.0.0", "output": {"echo": "hello from kind"}, "latency_ms": 1.2}
```

## Layout

```
deploy/namespaces.yaml          # system + features namespaces
deploy/operator/operator.yaml   # operator SA + binding + Deployment
deploy/gateway/gateway.yaml     # gateway SA + read RBAC + Deployment + NodePort
deploy/kind/kind-config.yaml    # single-node cluster, gateway on :8000
scripts/e2e.sh                  # orchestrates the above
```

The gateway runs in **cluster mode** (`AGENT_FEATURES_MODE=cluster`): it
discovers Features from the Kubernetes API and routes invocations over gRPC to
each feature's `status.endpoint`.

> The local test suite (`make test`) already verifies the gateway → gRPC →
> feature data path in-process. This kind setup adds the Kubernetes scheduling
> and discovery layer around it.
