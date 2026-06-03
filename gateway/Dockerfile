# Gateway image. Build from the repo root:
#   docker build -f gateway/Dockerfile -t ghcr.io/agennext/agent-features-gateway:dev .
FROM python:3.11-slim AS build
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt grpcio-tools

# Generate gRPC stubs from the contract at build time (protocol-first).
COPY proto/ proto/
RUN mkdir -p gen/python \
 && python -m grpc_tools.protoc -Iproto \
      --python_out=gen/python --grpc_python_out=gen/python \
      proto/agentfeatures/v1/feature.proto \
 && touch gen/python/agentfeatures/__init__.py gen/python/agentfeatures/v1/__init__.py

COPY gateway/ gateway/

ENV PYTHONPATH=/app/gen/python \
    AGENT_FEATURES_MODE=cluster \
    FEATURES_NAMESPACE=features
EXPOSE 8000
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
