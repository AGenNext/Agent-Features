// Package v1alpha1 contains the API types for the agentfeatures.io group.
// +kubebuilder:object:generate=true
// +groupName=agentfeatures.io
package v1alpha1

import (
	"k8s.io/apimachinery/pkg/runtime/schema"
	"sigs.k8s.io/controller-runtime/pkg/scheme"
)

var (
	// GroupVersion is the group/version used to register these objects.
	GroupVersion = schema.GroupVersion{Group: "agentfeatures.io", Version: "v1alpha1"}

	// SchemeBuilder registers the API types with a scheme.
	SchemeBuilder = &scheme.Builder{GroupVersion: GroupVersion}

	// AddToScheme adds the types in this group-version to the given scheme.
	AddToScheme = SchemeBuilder.AddToScheme
)

func init() {
	SchemeBuilder.Register(&Feature{}, &FeatureList{})
}
