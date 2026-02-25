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

# Handle different invocation patterns
if [ $# -eq 0 ]; then
    # No arguments: interactive shell
    kubectl exec -it "${HEAD_POD}" -- bash
elif [ "$1" = "--" ] && [ -n "$2" ]; then
    # Arguments after --: execute script file from local filesystem
    SCRIPT_PATH="$2"
    if [ ! -f "$SCRIPT_PATH" ]; then
        echo "ERROR: Script file not found: $SCRIPT_PATH"
        exit 1
    fi
    echo "Executing script: $SCRIPT_PATH"
    kubectl exec "${HEAD_POD}" -- bash -c "$(cat "$SCRIPT_PATH")"
else
    # Regular arguments: execute as command string
    kubectl exec "${HEAD_POD}" -- bash -c "$@"
fi
