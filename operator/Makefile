# Minimal operator Makefile. A full Kubebuilder Makefile adds controller-gen,
# envtest, kustomize, etc.; this covers the common loop.
IMG ?= ghcr.io/agennext/agent-features-operator:latest

.PHONY: build test vet run docker-build install deploy

build: vet
	go build -o bin/manager ./cmd

vet:
	go vet ./...

test:
	go test ./...

run:
	go run ./cmd

docker-build:
	docker build -t $(IMG) .

# Apply the CRD and a sample to the current kube-context.
install:
	kubectl apply -f config/crd/bases/agentfeatures.io_features.yaml

deploy: install
	kubectl apply -f config/rbac/role.yaml
	kubectl apply -f config/samples/agentfeatures_v1alpha1_feature.yaml
