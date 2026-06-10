// Package controller holds the Feature reconciler: it turns a Feature custom
// resource into a running workload (Deployment + Service) and reports status.
package controller

import (
	"context"
	"fmt"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/util/intstr"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"

	agentfeaturesv1alpha1 "github.com/AGenNext/Agent-Features/operator/api/v1alpha1"
)

// FeatureReconciler reconciles a Feature object.
type FeatureReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=agentfeatures.io,resources=features,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=agentfeatures.io,resources=features/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=agentfeatures.io,resources=features/finalizers,verbs=update
// +kubebuilder:rbac:groups=apps,resources=deployments,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=core,resources=services,verbs=get;list;watch;create;update;patch;delete

// Reconcile drives a Feature toward its desired state.
func (r *FeatureReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	var feature agentfeaturesv1alpha1.Feature
	if err := r.Get(ctx, req.NamespacedName, &feature); err != nil {
		// Gone: owned objects are garbage-collected via owner references.
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	// Reconcile the Service first so we can publish the endpoint early.
	svc, err := r.reconcileService(ctx, &feature)
	if err != nil {
		return r.fail(ctx, &feature, "ServiceError", err)
	}

	dep, err := r.reconcileDeployment(ctx, &feature)
	if err != nil {
		return r.fail(ctx, &feature, "DeploymentError", err)
	}

	// Derive phase from Deployment availability.
	endpoint := fmt.Sprintf("%s.%s.svc.cluster.local:%d", svc.Name, svc.Namespace, feature.Spec.Port)
	phase := agentfeaturesv1alpha1.PhaseProvisioning
	if dep.Status.AvailableReplicas > 0 {
		phase = agentfeaturesv1alpha1.PhaseReady
	}

	feature.Status.Phase = phase
	feature.Status.Endpoint = endpoint
	feature.Status.ObservedGeneration = feature.Generation
	meta := metav1.Condition{
		Type:    "Available",
		Status:  metav1.ConditionStatus(boolToStatus(phase == agentfeaturesv1alpha1.PhaseReady)),
		Reason:  string(phase),
		Message: fmt.Sprintf("%d/%d replicas available", dep.Status.AvailableReplicas, replicas(&feature)),
		LastTransitionTime: metav1.Now(),
	}
	setCondition(&feature.Status.Conditions, meta)
	if err := r.Status().Update(ctx, &feature); err != nil {
		return ctrl.Result{}, err
	}

	logger.Info("reconciled feature", "name", feature.Name, "phase", phase, "endpoint", endpoint)
	return ctrl.Result{}, nil
}

func (r *FeatureReconciler) reconcileDeployment(ctx context.Context, f *agentfeaturesv1alpha1.Feature) (*appsv1.Deployment, error) {
	labels := labelsFor(f)
	reps := replicas(f)

	dep := &appsv1.Deployment{ObjectMeta: metav1.ObjectMeta{Name: f.Name, Namespace: f.Namespace}}
	_, err := controllerutil.CreateOrUpdate(ctx, r.Client, dep, func() error {
		dep.Labels = labels
		dep.Spec.Replicas = &reps
		dep.Spec.Selector = &metav1.LabelSelector{MatchLabels: labels}
		dep.Spec.Template.ObjectMeta.Labels = labels
		dep.Spec.Template.Spec.Containers = []corev1.Container{{
			Name:      "feature",
			Image:     f.Spec.Image,
			Ports:     []corev1.ContainerPort{{ContainerPort: f.Spec.Port, Name: string(protocolOrDefault(f))}},
			Resources: withAccelerator(f.Spec.Runtime),
		}}
		return controllerutil.SetControllerReference(f, dep, r.Scheme)
	})
	return dep, err
}

func (r *FeatureReconciler) reconcileService(ctx context.Context, f *agentfeaturesv1alpha1.Feature) (*corev1.Service, error) {
	labels := labelsFor(f)
	svc := &corev1.Service{ObjectMeta: metav1.ObjectMeta{Name: f.Name, Namespace: f.Namespace}}
	_, err := controllerutil.CreateOrUpdate(ctx, r.Client, svc, func() error {
		svc.Labels = labels
		svc.Spec.Selector = labels
		svc.Spec.Ports = []corev1.ServicePort{{
			Name:       string(protocolOrDefault(f)),
			Port:       f.Spec.Port,
			TargetPort: intstr.FromInt32(f.Spec.Port),
		}}
		return controllerutil.SetControllerReference(f, svc, r.Scheme)
	})
	return svc, err
}

func (r *FeatureReconciler) fail(ctx context.Context, f *agentfeaturesv1alpha1.Feature, reason string, cause error) (ctrl.Result, error) {
	f.Status.Phase = agentfeaturesv1alpha1.PhaseFailed
	setCondition(&f.Status.Conditions, metav1.Condition{
		Type:               "Available",
		Status:             metav1.ConditionFalse,
		Reason:             reason,
		Message:            cause.Error(),
		LastTransitionTime: metav1.Now(),
	})
	// Best-effort status update; surface the original error for requeue.
	_ = r.Status().Update(ctx, f)
	return ctrl.Result{}, cause
}

// SetupWithManager wires the reconciler to watch Features and the workloads it owns.
func (r *FeatureReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&agentfeaturesv1alpha1.Feature{}).
		Owns(&appsv1.Deployment{}).
		Owns(&corev1.Service{}).
		Complete(r)
}

// --- helpers -----------------------------------------------------------------

func labelsFor(f *agentfeaturesv1alpha1.Feature) map[string]string {
	return map[string]string{
		"app.kubernetes.io/managed-by": "agent-features-operator",
		"agentfeatures.io/feature":     f.Name,
	}
}

func replicas(f *agentfeaturesv1alpha1.Feature) int32 {
	if f.Spec.Runtime.MinReplicas != nil {
		return *f.Spec.Runtime.MinReplicas
	}
	return 1
}

func protocolOrDefault(f *agentfeaturesv1alpha1.Feature) agentfeaturesv1alpha1.FeatureProtocol {
	if f.Spec.Protocol == "" {
		return agentfeaturesv1alpha1.ProtocolGRPC
	}
	return f.Spec.Protocol
}

// withAccelerator copies the runtime resources and, if an accelerator is
// requested, adds it as a limit (device-plugin convention).
func withAccelerator(rt agentfeaturesv1alpha1.RuntimeSpec) corev1.ResourceRequirements {
	res := *rt.Resources.DeepCopy()
	if rt.Accelerator != "" {
		if res.Limits == nil {
			res.Limits = corev1.ResourceList{}
		}
		res.Limits[corev1.ResourceName(rt.Accelerator)] = resource.MustParse("1")
	}
	return res
}

func boolToStatus(b bool) string {
	if b {
		return string(metav1.ConditionTrue)
	}
	return string(metav1.ConditionFalse)
}

// setCondition upserts a condition by type, preserving transition time when
// the status is unchanged.
func setCondition(conditions *[]metav1.Condition, c metav1.Condition) {
	for i := range *conditions {
		if (*conditions)[i].Type == c.Type {
			if (*conditions)[i].Status == c.Status {
				c.LastTransitionTime = (*conditions)[i].LastTransitionTime
			}
			(*conditions)[i] = c
			return
		}
	}
	*conditions = append(*conditions, c)
}
