#!/bin/bash
# Script to build and test the Ray Docker image locally

set -e  # Exit on error

IMAGE_NAME="lakefront-ray"
PLATFORM="${PLATFORM:-linux/amd64}"  # Default to AMD64 for GKE compatibility
DOCKER_USERNAME="${DOCKER_USERNAME:-bdpedigo}"
AUTO_COMMIT="${AUTO_COMMIT:-}"  # Set to 1 to auto-commit changes

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
    if [ -n "${IMAGE_TAG:-}" ]; then
        echo "$IMAGE_TAG"
    else
        # Use short commit SHA
        git rev-parse --short HEAD 2>/dev/null || echo "latest"
    fi
}

# Run git status check
check_git_status

# Determine image tag
IMAGE_TAG=$(get_image_tag)
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

echo "========================================"
echo "Building Docker Image: ${FULL_IMAGE}"
echo "========================================"
echo "Platform: ${PLATFORM}"
echo "Git commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
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
# Use --load to load into local docker, or --push to push directly
if [ -n "${PUSH_TO_HUB}" ]; then
    echo "Building and pushing to Docker Hub as ${DOCKER_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}"
    docker buildx build --platform "${PLATFORM}" \
        -t "${FULL_IMAGE}" \
        -t "${DOCKER_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}" \
        --push \
        .
else
    echo "Building for local use..."
    docker buildx build --platform "${PLATFORM}" \
        -t "${FULL_IMAGE}" \
        --load \
        .
fi

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
