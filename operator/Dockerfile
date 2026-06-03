# Build the operator manager binary.
FROM golang:1.24 AS build
WORKDIR /workspace
COPY go.mod go.mod
RUN go mod download || true
COPY cmd/ cmd/
COPY api/ api/
COPY internal/ internal/
RUN CGO_ENABLED=0 GOOS=linux go build -a -o manager ./cmd

# Minimal runtime image.
FROM gcr.io/distroless/static:nonroot
WORKDIR /
COPY --from=build /workspace/manager .
USER 65532:65532
ENTRYPOINT ["/manager"]
