#!/bin/bash
# Helper script to test the Docker image locally

set -e

IMAGE_NAME="${1:-lakefront-ray:latest}"
CONTAINER_NAME="ray-test"

echo "========================================"
echo "Testing Docker Image: ${IMAGE_NAME}"
echo "========================================"
echo ""

# Clean up any existing container
if docker ps -a | grep -q "${CONTAINER_NAME}"; then
    echo "Removing existing container..."
    docker stop "${CONTAINER_NAME}" 2>/dev/null || true
    docker rm "${CONTAINER_NAME}" 2>/dev/null || true
fi

# Start Ray head node
echo "Starting Ray head node..."
docker run -d \
    --name "${CONTAINER_NAME}" \
    -p 8265:8265 \
    -p 6379:6379 \
    "${IMAGE_NAME}"

echo "Waiting for Ray to start..."
sleep 5

# Check if Ray is running
echo ""
echo "Checking Ray status..."
docker exec "${CONTAINER_NAME}" ray status || echo "Warning: Ray status check failed"

# Run the test job
echo ""
echo "========================================"
echo "Running Test Job"
echo "========================================"
docker exec "${CONTAINER_NAME}" python jobs/simple_job.py

echo ""
echo "========================================"
echo "Test Complete!"
echo "========================================"
echo ""
echo "Ray Dashboard: http://localhost:8265"
echo ""
echo "To stop and clean up:"
echo "  docker stop ${CONTAINER_NAME} && docker rm ${CONTAINER_NAME}"
echo ""
