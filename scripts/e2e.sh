#!/usr/bin/env bash
# End-to-end demo on a local kind cluster:
#   source -> images -> kind -> operator reconciles echo Feature -> gateway
#   discovers it -> invoke through the gateway.
#
# Requires: docker, kind, kubectl, pack. Run from the repo root: `make e2e`.
set -euo pipefail

CLUSTER=agent-features
GATEWAY_IMG=${GATEWAY_IMG:-ghcr.io/agennext/agent-features-gateway:dev}
OPERATOR_IMG=${OPERATOR_IMG:-ghcr.io/agennext/agent-features-operator:dev}
ECHO_IMG=${ECHO_IMG:-ghcr.io/agennext/feature-echo:dev}

echo "==> create kind cluster"
kind create cluster --name "$CLUSTER" --config deploy/kind/kind-config.yaml

echo "==> build images"
docker build -f gateway/Dockerfile -t "$GATEWAY_IMG" .
docker build -f operator/Dockerfile -t "$OPERATOR_IMG" operator
pack build "$ECHO_IMG" --path examples/features/echo \
  --builder paketobuildpacks/builder-jammy-base

echo "==> load images into kind"
kind load docker-image "$GATEWAY_IMG" "$OPERATOR_IMG" "$ECHO_IMG" --name "$CLUSTER"

echo "==> apply platform"
kubectl apply -f deploy/namespaces.yaml
kubectl apply -f operator/config/crd/bases/agentfeatures.io_features.yaml
kubectl apply -f operator/config/rbac/role.yaml
kubectl apply -f deploy/operator/operator.yaml
kubectl apply -f deploy/gateway/gateway.yaml

echo "==> wait for operator + gateway"
kubectl -n agent-features-system rollout status deploy/agent-features-operator
kubectl -n agent-features-system rollout status deploy/agent-features-gateway

echo "==> publish the echo feature"
kubectl apply -f operator/config/samples/agentfeatures_v1alpha1_feature.yaml
kubectl -n features wait --for=jsonpath='{.status.phase}'=Ready feature/echo --timeout=120s

echo "==> invoke through the gateway (NodePort -> localhost:8000)"
curl -sf http://localhost:8000/features | python -m json.tool
curl -sf -X POST http://localhost:8000/features/echo/invoke \
  -H 'content-type: application/json' \
  -d '{"input": {"message": "hello from kind"}}' | python -m json.tool

echo "==> done. tear down with: kind delete cluster --name $CLUSTER"
