output "system_namespace" {
  value = kubernetes_namespace.system.metadata[0].name
}

output "features_namespace" {
  value = kubernetes_namespace.features.metadata[0].name
}

output "gateway_service" {
  description = "In-cluster address of the gateway."
  value       = "${kubernetes_service.gateway.metadata[0].name}.${var.system_namespace}.svc.cluster.local"
}
