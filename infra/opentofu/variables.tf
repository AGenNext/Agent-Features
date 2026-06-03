variable "kubeconfig" {
  description = "Path to the kubeconfig file."
  type        = string
  default     = "~/.kube/config"
}

variable "kube_context" {
  description = "kubeconfig context to target."
  type        = string
  default     = null
}

variable "system_namespace" {
  description = "Namespace for platform components (operator, gateway)."
  type        = string
  default     = "agent-features-system"
}

variable "features_namespace" {
  description = "Namespace where Feature workloads are scheduled."
  type        = string
  default     = "features"
}

variable "operator_image" {
  type    = string
  default = "ghcr.io/agennext/agent-features-operator:latest"
}

variable "gateway_image" {
  type    = string
  default = "ghcr.io/agennext/agent-features-gateway:latest"
}

variable "enable_keda" {
  description = "Install KEDA for scale-to-zero of features."
  type        = bool
  default     = true
}

variable "enable_otel" {
  description = "Install the OpenTelemetry Collector."
  type        = bool
  default     = true
}
