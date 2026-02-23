#!/bin/bash
# Script to start Jupyter on Ray head node and connect to it via port-forward

set -e

CLUSTER_NAME="${CLUSTER_NAME:-lakefront-ray-cluster}"
LOCAL_PORT="${LOCAL_PORT:-8888}"
REMOTE_PORT="${REMOTE_PORT:-8888}"

# Get head pod name
HEAD_POD=$(kubectl get pod -l ray.io/cluster=${CLUSTER_NAME} -l ray.io/node-type=head -o jsonpath='{.items[0].metadata.name}')

if [ -z "$HEAD_POD" ]; then
    echo "ERROR: Could not find Ray head pod"
    echo "Make sure the cluster is running:"
    echo "  kubectl get pods -l ray.io/cluster=${CLUSTER_NAME}"
    exit 1
fi

echo "Found Ray head node: ${HEAD_POD}"
echo ""

# Start Jupyter - if it's already running, this will fail but we'll handle it
echo "Starting Jupyter notebook server on head node..."
echo ""

# Start Jupyter in the background with no browser and allow remote connections
# Use the full path to jupyter since PATH may not be set in kubectl exec
# Use || true to ignore errors if it's already running  
kubectl exec "${HEAD_POD}" -- bash -c "nohup /app/.venv/bin/jupyter lab \
    --ip=0.0.0.0 \
    --port=${REMOTE_PORT} \
    --no-browser \
    --allow-root \
    --ServerApp.token='' \
    --ServerApp.password='' \
    --ServerApp.root_dir=/app \
    > /tmp/jupyter.log 2>&1 &" || echo "Note: Jupyter may already be running"

echo "Waiting for Jupyter to start..."
sleep 3

echo ""
echo "Setting up port-forward from localhost:${LOCAL_PORT} to pod:${REMOTE_PORT}..."
echo "Access Jupyter at: http://localhost:${LOCAL_PORT}"
echo ""
echo "Press Ctrl+C to stop port-forwarding"
echo ""

kubectl port-forward "${HEAD_POD}" ${LOCAL_PORT}:${REMOTE_PORT}
