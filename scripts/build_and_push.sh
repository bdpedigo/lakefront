#!/bin/bash
# Script to build and push the Ray Docker image

set -e  # Exit on error

IMAGE_NAME="${IMAGE_NAME:-lakefront-ray}"  # Default image name
PLATFORM="${PLATFORM:-linux/amd64}"  # Default to AMD64 for GKE compatibility
DOCKER_USERNAME="${DOCKER_USERNAME:-bdpedigo}"
DOCKERFILE="${DOCKERFILE:-Dockerfile}"  # Default Dockerfile
AUTO_COMMIT="${AUTO_COMMIT:-}"  # Set to 1 to auto-commit changes
LOCAL_ONLY="${LOCAL_ONLY:-}"  # Set to 1 to skip pushing to Docker Hub

# Check for uncommitted changes
check_git_status() {
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        echo "⚠️  Warning: You have uncommitted changes"
        
        if [ -n "$AUTO_COMMIT" ]; then
            echo "Auto-committing changes..."
            git add -A
            git commit -m "Build: Update for Docker image build"
            echo "✓ Changes committed"
        else
            echo ""
            read -p "Commit changes now? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                git add -A
                read -p "Commit message (default: 'Update Docker image'): " COMMIT_MSG
                COMMIT_MSG="${COMMIT_MSG:-Update Docker image}"
                git commit -m "$COMMIT_MSG"
                echo "✓ Changes committed"
            else
                echo "Building with uncommitted changes - image will be tagged with current HEAD"
            fi
        fi
    fi
}

# Get git commit SHA for tagging
get_image_tag() {
    git rev-parse --short HEAD
}

check_git_status

# Determine image tag
IMAGE_TAG=$(get_image_tag)
FULL_IMAGE="${DOCKER_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}"

echo "========================================"
echo "Building Docker Image: ${FULL_IMAGE}"
echo "========================================"
echo "Platform: ${PLATFORM}"
echo "Git commit: ${IMAGE_TAG}"
if [ -n "$LOCAL_ONLY" ]; then
    echo "Mode: LOCAL ONLY (not pushing to Docker Hub)"
else
    echo "Mode: Build and push to Docker Hub"
fi
echo ""

# Check if buildx is available
if ! docker buildx version &> /dev/null; then
    echo "ERROR: docker buildx not available"
    echo "Please enable Docker Desktop experimental features"
    exit 1
fi

# Create or use existing buildx builder
if ! docker buildx inspect multiplatform &> /dev/null; then
    echo "Creating buildx builder..."
    docker buildx create --name multiplatform --use
else
    echo "Using existing buildx builder..."
    docker buildx use multiplatform
fi

# Build the image for the target platform
if [ -n "$LOCAL_ONLY" ]; then
    echo "Building for local use only..."
    docker buildx build --platform "${PLATFORM}" \
        -f "${DOCKERFILE}" \
        -t "${IMAGE_NAME}:${IMAGE_TAG}" \
        -t "${IMAGE_NAME}:latest" \
        --load \
        .
else
    echo "Building and pushing to Docker Hub..."
    docker buildx build --platform "${PLATFORM}" \
        -f "${DOCKERFILE}" \
        -t "${FULL_IMAGE}" \
        -t "${DOCKER_USERNAME}/${IMAGE_NAME}:latest" \
        --push \
        .
fi

echo ""
echo "========================================"
echo "Build Complete!"
echo "========================================"
echo ""
echo "Image: ${FULL_IMAGE}"
echo "Tag: ${IMAGE_TAG}"
echo ""

# Export the image tag for use by calling scripts
echo "LAKEFRONT_IMAGE_TAG=${IMAGE_TAG}"

if [ -n "$LOCAL_ONLY" ]; then
    echo ""
    echo "To test locally:"
    echo "  1. Start Ray head node:"
    echo "     docker run -d --name ray-head -p 8265:8265 -p 6379:6379 ${IMAGE_NAME}:${IMAGE_TAG}"
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
    echo "    ${IMAGE_NAME}:${IMAGE_TAG}"
    echo ""
    echo "To push to Docker Hub later:"
    echo "  docker tag ${IMAGE_NAME}:${IMAGE_TAG} ${FULL_IMAGE}"
    echo "  docker push ${FULL_IMAGE}"
else
    echo ""
    echo "✓ Image pushed to Docker Hub: ${FULL_IMAGE}"
    echo ""
    echo "To deploy to cluster:"
    echo "  ./scripts/submit_job.sh"
fi
echo ""
