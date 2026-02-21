#!/bin/bash
# Script to clean up local Kubernetes cluster

set -e

CLUSTER_NAME="${KIND_CLUSTER_NAME:-lakefront-ray-local}"
K8S_PROVIDER="${K8S_PROVIDER:-kind}"

echo "========================================"
echo "Local Cluster Cleanup"
echo "========================================"
echo ""
echo "Provider: ${K8S_PROVIDER}"
echo "Cluster: ${CLUSTER_NAME}"
echo ""

read -p "Delete local cluster? (y/N): " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted"
    exit 0
fi

if [ "$K8S_PROVIDER" = "kind" ]; then
    echo "Deleting kind cluster..."
    kind delete cluster --name "${CLUSTER_NAME}"
elif [ "$K8S_PROVIDER" = "minikube" ]; then
    echo "Deleting minikube cluster..."
    minikube delete -p "${CLUSTER_NAME}"
fi

# Clean up temp files
rm -f /tmp/ray-cluster-local.yaml
rm -f /tmp/ray-service-local.yaml

echo ""
echo "✓ Cleanup complete"
