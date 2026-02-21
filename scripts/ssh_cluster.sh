#!/bin/bash
# Script to SSH/exec into the Ray head node

set -e

CLUSTER_NAME="${CLUSTER_NAME:-lakefront-ray-cluster}"

# Get head pod name
HEAD_POD=$(kubectl get pod -l ray.io/cluster=${CLUSTER_NAME} -l ray.io/node-type=head -o jsonpath='{.items[0].metadata.name}')

if [ -z "$HEAD_POD" ]; then
    echo "ERROR: Could not find Ray head pod"
    echo "Make sure the cluster is running:"
    echo "  kubectl get pods -l ray.io/cluster=${CLUSTER_NAME}"
    exit 1
fi

echo "Connecting to Ray head node: ${HEAD_POD}"
echo ""

# Execute interactive bash shell
kubectl exec -it "${HEAD_POD}" -- bash
