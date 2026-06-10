# Optional CNCF platform dependencies, installed via Helm.

# KEDA — event-driven autoscaling, enabling scale-to-zero for features.
resource "helm_release" "keda" {
  count            = var.enable_keda ? 1 : 0
  name             = "keda"
  repository       = "https://kedacore.github.io/charts"
  chart            = "keda"
  namespace        = "keda"
  create_namespace = true
}

# OpenTelemetry Collector — receives traces/metrics from the gateway and
# features and exports to the configured backend (see observability/).
resource "helm_release" "otel_collector" {
  count            = var.enable_otel ? 1 : 0
  name             = "otel-collector"
  repository       = "https://open-telemetry.github.io/opentelemetry-helm-charts"
  chart            = "opentelemetry-collector"
  namespace        = var.system_namespace
  create_namespace = false

  set {
    name  = "mode"
    value = "deployment"
  }

  depends_on = [kubernetes_namespace.system]
}
