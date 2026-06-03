# Top-level developer tasks for the Agent Features platform.
PROTO        := proto/agentfeatures/v1/feature.proto
GEN_PY       := gen/python
GATEWAY_IMG  ?= ghcr.io/agennext/agent-features-gateway:dev
OPERATOR_IMG ?= ghcr.io/agennext/agent-features-operator:dev
ECHO_IMG     ?= ghcr.io/agennext/feature-echo:dev

.PHONY: proto test run gateway-image operator-image echo-image e2e clean

# Generate Python gRPC stubs from the protocol-first contract.
proto:
	@mkdir -p $(GEN_PY)
	python -m grpc_tools.protoc -Iproto --python_out=$(GEN_PY) --grpc_python_out=$(GEN_PY) $(PROTO)
	@touch $(GEN_PY)/agentfeatures/__init__.py $(GEN_PY)/agentfeatures/v1/__init__.py

# Run the full test suite (conftest self-bootstraps the stubs).
test:
	python -m pytest -q

# Run the gateway locally (in-process dev features).
run:
	uvicorn gateway.main:app --reload

gateway-image:
	docker build -f gateway/Dockerfile -t $(GATEWAY_IMG) .

operator-image:
	docker build -f operator/Dockerfile -t $(OPERATOR_IMG) operator

# Build the reference feature with Cloud Native Buildpacks (no Dockerfile).
echo-image:
	pack build $(ECHO_IMG) --path examples/features/echo \
	  --builder paketobuildpacks/builder-jammy-base

# Full end-to-end on a local kind cluster (requires docker, kind, kubectl, pack).
e2e:
	GATEWAY_IMG=$(GATEWAY_IMG) OPERATOR_IMG=$(OPERATOR_IMG) ECHO_IMG=$(ECHO_IMG) \
	  scripts/e2e.sh

clean:
	rm -rf $(GEN_PY) .pytest_cache
