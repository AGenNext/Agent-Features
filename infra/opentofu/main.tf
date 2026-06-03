# Namespaces ------------------------------------------------------------------

resource "kubernetes_namespace" "system" {
  metadata {
    name   = var.system_namespace
    labels = { "app.kubernetes.io/part-of" = "agent-features" }
  }
}

resource "kubernetes_namespace" "features" {
  metadata {
    name   = var.features_namespace
    labels = { "app.kubernetes.io/part-of" = "agent-features" }
  }
}

# Feature CRD ------------------------------------------------------------------
# Applied from the operator's committed manifest so the API exists before any
# Feature is created.
resource "kubernetes_manifest" "feature_crd" {
  manifest = yamldecode(file("${path.module}/../../operator/config/crd/bases/agentfeatures.io_features.yaml"))
}

# Operator RBAC + workload -----------------------------------------------------

resource "kubernetes_service_account" "operator" {
  metadata {
    name      = "agent-features-operator"
    namespace = kubernetes_namespace.system.metadata[0].name
  }
}

resource "kubernetes_cluster_role" "operator" {
  metadata { name = "agent-features-operator-role" }

  # Mirrors operator/config/rbac/role.yaml.
  rule {
    api_groups = ["agentfeatures.io"]
    resources  = ["features", "features/status", "features/finalizers"]
    verbs      = ["get", "list", "watch", "create", "update", "patch", "delete"]
  }
  rule {
    api_groups = ["apps"]
    resources  = ["deployments"]
    verbs      = ["get", "list", "watch", "create", "update", "patch", "delete"]
  }
  rule {
    api_groups = [""]
    resources  = ["services"]
    verbs      = ["get", "list", "watch", "create", "update", "patch", "delete"]
  }
}

resource "kubernetes_cluster_role_binding" "operator" {
  metadata { name = "agent-features-operator-rolebinding" }
  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role.operator.metadata[0].name
  }
  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.operator.metadata[0].name
    namespace = kubernetes_namespace.system.metadata[0].name
  }
}

resource "kubernetes_deployment" "operator" {
  metadata {
    name      = "agent-features-operator"
    namespace = kubernetes_namespace.system.metadata[0].name
    labels    = { "app.kubernetes.io/name" = "operator" }
  }
  spec {
    replicas = 1
    selector { match_labels = { "app.kubernetes.io/name" = "operator" } }
    template {
      metadata { labels = { "app.kubernetes.io/name" = "operator" } }
      spec {
        service_account_name = kubernetes_service_account.operator.metadata[0].name
        container {
          name  = "manager"
          image = var.operator_image
          args  = ["--leader-elect"]
        }
      }
    }
  }
  depends_on = [kubernetes_manifest.feature_crd, kubernetes_cluster_role_binding.operator]
}

# Gateway workload + service ---------------------------------------------------

resource "kubernetes_deployment" "gateway" {
  metadata {
    name      = "agent-features-gateway"
    namespace = kubernetes_namespace.system.metadata[0].name
    labels    = { "app.kubernetes.io/name" = "gateway" }
  }
  spec {
    replicas = 2
    selector { match_labels = { "app.kubernetes.io/name" = "gateway" } }
    template {
      metadata { labels = { "app.kubernetes.io/name" = "gateway" } }
      spec {
        container {
          name  = "gateway"
          image = var.gateway_image
          port { container_port = 8000 }
          readiness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "gateway" {
  metadata {
    name      = "agent-features-gateway"
    namespace = kubernetes_namespace.system.metadata[0].name
  }
  spec {
    selector = { "app.kubernetes.io/name" = "gateway" }
    port {
      port        = 80
      target_port = 8000
    }
  }
}
