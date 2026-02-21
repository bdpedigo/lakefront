#!/bin/bash
# Script to delete the GKE cluster and clean up resources

set -e

#==============================================================================
# CONFIGURATION
#==============================================================================

PROJECT_ID="${GCP_PROJECT_ID:-exalted-beanbag-334502}"
ZONE="${GKE_ZONE:-us-west1-c}"
CLUSTER_NAME="${CLUSTER_NAME:-lakefront-ray-cluster}"

#==============================================================================
# MAIN
#==============================================================================

echo "========================================"
echo "Cluster Cleanup"
echo "========================================"
echo ""
echo "This will delete:"
echo "  - GKE Cluster: ${CLUSTER_NAME}"
echo "  - Zone: ${ZONE}"
echo "  - Project: ${PROJECT_ID}"
echo ""
read -p "Are you sure you want to delete this cluster? (yes/N): " -r
echo

if [[ ! $REPLY =~ ^yes$ ]]; then
    echo "Aborted"
    exit 0
fi

echo ""
echo "Setting project..."
gcloud config set project "${PROJECT_ID}"

echo ""
echo "Deleting Ray cluster from Kubernetes..."
kubectl delete -f k8s/ray-cluster.yaml --ignore-not-found=true
kubectl delete -f k8s/ray-service.yaml --ignore-not-found=true

echo ""
echo "Waiting for resources to be deleted..."
sleep 10

echo ""
echo "Deleting GKE cluster..."
gcloud container clusters delete "${CLUSTER_NAME}" \
    --zone="${ZONE}" \
    --quiet

echo ""
echo "========================================"
echo "Cleanup Complete!"
echo "========================================"
echo ""
echo "The following resources have been deleted:"
echo "  ✓ Ray cluster and service"
echo "  ✓ GKE cluster: ${CLUSTER_NAME}"
echo ""
echo "Note: Kubernetes secrets were deleted with the cluster."
echo "Your local Docker images and code remain unchanged."
