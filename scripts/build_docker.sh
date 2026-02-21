#!/bin/bash
# Script to build and test the Ray Docker image locally

set -e  # Exit on error

IMAGE_NAME="lakefront-ray"
IMAGE_TAG="${1:-latest}"
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

echo "========================================"
echo "Building Docker Image: ${FULL_IMAGE}"
echo "========================================"

# Build the image
docker build -t "${FULL_IMAGE}" .

echo ""
echo "========================================"
echo "Build Complete!"
echo "========================================"
echo ""
echo "Image: ${FULL_IMAGE}"
echo ""
echo "To test locally:"
echo "  1. Start Ray head node:"
echo "     docker run -d --name ray-head -p 8265:8265 -p 6379:6379 ${FULL_IMAGE}"
echo ""
echo "  2. Check Ray dashboard:"
echo "     open http://localhost:8265"
echo ""
echo "  3. Submit a test job:"
echo "     docker exec ray-head python jobs/simple_job.py"
echo ""
echo "  4. Stop and remove container:"
echo "     docker stop ray-head && docker rm ray-head"
echo ""
echo "To mount secrets (for production testing):"
echo "  docker run -d --name ray-head \\"
echo "    -p 8265:8265 -p 6379:6379 \\"
echo "    -v \$HOME/.cloudvolume/secrets:/root/.cloudvolume/secrets:ro \\"
echo "    ${FULL_IMAGE}"
echo ""
echo "To push to Docker Hub:"
echo "  docker login"
echo "  docker tag ${FULL_IMAGE} bdpedigo/lakefront-ray:${IMAGE_TAG}"
echo "  docker push bdpedigo/lakefront-ray:${IMAGE_TAG}"
echo ""
