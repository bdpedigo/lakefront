#!/bin/bash
# Copy all files from scratch/ to the Ray head node's /tmp/scratch/

set -e

CLUSTER_NAME="${CLUSTER_NAME:-lakefront-ray-cluster}"

HEAD_POD=$(kubectl get pod -l ray.io/cluster=${CLUSTER_NAME} -l ray.io/node-type=head -o jsonpath='{.items[0].metadata.name}')

if [ -z "$HEAD_POD" ]; then
    echo "ERROR: Could not find Ray head pod"
    echo "Make sure the cluster is running:"
    echo "  kubectl get pods -l ray.io/cluster=${CLUSTER_NAME}"
    exit 1
fi

echo "Syncing scratch/ to ${HEAD_POD}:/app/scratch/ ..."
kubectl exec "${HEAD_POD}" -- mkdir -p /app/scratch
kubectl cp scratch/. "${HEAD_POD}:/app/scratch/"
echo "Done."
