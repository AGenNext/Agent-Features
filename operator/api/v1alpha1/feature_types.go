package v1alpha1

import (
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// Visibility controls which agents may discover a feature.
// +kubebuilder:validation:Enum=Public;Internal;Private
type Visibility string

const (
	VisibilityPublic   Visibility = "Public"
	VisibilityInternal Visibility = "Internal"
	VisibilityPrivate  Visibility = "Private"
)

// FeatureProtocol is how the gateway reaches the feature workload.
// +kubebuilder:validation:Enum=grpc;http
type FeatureProtocol string

const (
	ProtocolGRPC FeatureProtocol = "grpc"
	ProtocolHTTP FeatureProtocol = "http"
)

// RuntimeSpec describes how the feature workload is scheduled and scaled.
type RuntimeSpec struct {
	// MinReplicas; 0 enables scale-to-zero (via KEDA/Knative).
	// +kubebuilder:default=1
	// +optional
	MinReplicas *int32 `json:"minReplicas,omitempty"`

	// +kubebuilder:default=3
	// +optional
	MaxReplicas *int32 `json:"maxReplicas,omitempty"`

	// +optional
	Resources corev1.ResourceRequirements `json:"resources,omitempty"`

	// Accelerator requests a device plugin resource, e.g. "nvidia.com/gpu".
	// Empty means CPU-only. Enables AI-native (GPU) features.
	// +optional
	Accelerator string `json:"accelerator,omitempty"`
}

// FeatureSpec is the desired state of a Feature.
type FeatureSpec struct {
	// +optional
	Description string `json:"description,omitempty"`

	// Image is the OCI image implementing the feature (built by Buildpacks).
	// +kubebuilder:validation:MinLength=1
	Image string `json:"image"`

	// +kubebuilder:default=grpc
	// +optional
	Protocol FeatureProtocol `json:"protocol,omitempty"`

	// Port the workload serves on.
	// +kubebuilder:default=9090
	// +optional
	Port int32 `json:"port,omitempty"`

	// +optional
	Tags []string `json:"tags,omitempty"`

	// +kubebuilder:default=Public
	// +optional
	Visibility Visibility `json:"visibility,omitempty"`

	// InputSchema is a JSON Schema (draft 2020-12) for invocation arguments.
	// It doubles as the MCP tool inputSchema. Stored as a raw string.
	// +optional
	InputSchema string `json:"inputSchema,omitempty"`

	// +optional
	OutputSchema string `json:"outputSchema,omitempty"`

	// +optional
	Runtime RuntimeSpec `json:"runtime,omitempty"`
}

// FeaturePhase is a coarse lifecycle summary surfaced to the catalog.
// +kubebuilder:validation:Enum=Pending;Provisioning;Ready;Failed
type FeaturePhase string

const (
	PhasePending      FeaturePhase = "Pending"
	PhaseProvisioning FeaturePhase = "Provisioning"
	PhaseReady        FeaturePhase = "Ready"
	PhaseFailed       FeaturePhase = "Failed"
)

// FeatureStatus is the observed state of a Feature.
type FeatureStatus struct {
	// +optional
	Phase FeaturePhase `json:"phase,omitempty"`

	// Endpoint is the in-cluster address once Ready (host:port).
	// +optional
	Endpoint string `json:"endpoint,omitempty"`

	// +optional
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`

	// +optional
	// +patchMergeKey=type
	// +patchStrategy=merge
	Conditions []metav1.Condition `json:"conditions,omitempty" patchStrategy:"merge" patchMergeKey:"type"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:shortName=feat
// +kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
// +kubebuilder:printcolumn:name="Endpoint",type=string,JSONPath=`.status.endpoint`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// Feature is a capability published to the agent marketplace.
type Feature struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   FeatureSpec   `json:"spec,omitempty"`
	Status FeatureStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// FeatureList contains a list of Feature.
type FeatureList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []Feature `json:"items"`
}
