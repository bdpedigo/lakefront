#!/bin/bash
# Script to submit a Ray job to the remote cluster

set -e

#==============================================================================
# CONFIGURATION
#==============================================================================

JOB_SCRIPT="${1:-jobs/simple_job.py}"
CLUSTER_NAME="${CLUSTER_NAME:-lakefront-ray-cluster}"

#==============================================================================
# MAIN
#==============================================================================

if [ ! -f "$JOB_SCRIPT" ]; then
    echo "ERROR: Job script not found: $JOB_SCRIPT"
    echo ""
    echo "Usage: $0 [job_script.py]"
    echo "Example: $0 jobs/simple_job.py"
    exit 1
fi

echo "========================================"
echo "Submitting Ray Job"
echo "========================================"
echo "Script: ${JOB_SCRIPT}"
echo "Cluster: ${CLUSTER_NAME}"
echo ""

# Get head pod name
HEAD_POD=$(kubectl get pod -l ray.io/cluster=${CLUSTER_NAME} -l ray.io/node-type=head -o jsonpath='{.items[0].metadata.name}')

if [ -z "$HEAD_POD" ]; then
    echo "ERROR: Could not find Ray head pod"
    echo "Make sure the cluster is running:"
    echo "  kubectl get pods -l ray.io/cluster=${CLUSTER_NAME}"
    exit 1
fi

echo "Head pod: ${HEAD_POD}"
echo ""

# Copy job script to pod
echo "Copying job script to cluster..."
kubectl cp "${JOB_SCRIPT}" "${HEAD_POD}:/tmp/$(basename ${JOB_SCRIPT})"

# Execute job
echo ""
echo "========================================"
echo "Job Output"
echo "========================================"
kubectl exec "${HEAD_POD}" -- python "/tmp/$(basename ${JOB_SCRIPT})"

echo ""
echo "========================================"
echo "Job Complete"
echo "========================================"
