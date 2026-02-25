#!/bin/bash
# Script to create a GKE cluster and deploy KubeRay
# Based on old_examples/make_cluster.sh but adapted for Ray

set -e  # Exit on error

#==============================================================================
# CONFIGURATION - Update these values for your project
#==============================================================================

# GCP Project Configuration
PROJECT_ID="${GCP_PROJECT_ID:-exalted-beanbag-334502}"
ZONE="${GKE_ZONE:-us-west1-c}"
REGION="${GKE_REGION:-us-west1}"

# Cluster Configuration
MACHINE_TYPE="${MACHINE_TYPE:-e2-highmem-16}"  # 4 vCPUs, 16GB RAM
NUM_NODES="${NUM_NODES:-1}"
CLUSTER_NAME="${CLUSTER_NAME:-lakefront-ray-cluster}"

# Disk Configuration
DISK_SIZE="${DISK_SIZE:-200}"  # GB
DISK_TYPE="${DISK_TYPE:-pd-standard}"

# Docker Image Configuration
DOCKER_USERNAME="${DOCKER_USERNAME:-bdpedigo}"  # Set via environment or command line
IMAGE_TAG=$(git rev-parse --short HEAD)
IMAGE_NAME="${IMAGE_NAME:-lakefront-ray}" # Default image name

# Deployment YAML Configuration
DEPLOYMENT_YAML="${DEPLOYMENT_YAML:-k8s/ray-cluster.yaml}"  # Path to deployment yaml
SERVICE_YAML="${SERVICE_YAML:-k8s/ray-service.yaml}"  # Path to service yaml (optional)

# Network Configuration (optional - remove these flags if using default network)
NETWORK="projects/${PROJECT_ID}/global/networks/patchseq"
SUBNETWORK="projects/${PROJECT_ID}/regions/${REGION}/subnetworks/patchseq"

# Secrets Configuration
SECRETS_DIR="${SECRETS_DIR:-$HOME/.cloudvolume/secrets}"

#==============================================================================
# FUNCTIONS
#==============================================================================

print_header() {
    echo ""
    echo "========================================"
    echo "$1"
    echo "========================================"
}

check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check gcloud
    if [ ! command -v gcloud &> /dev/null ]; then
        echo "ERROR: gcloud CLI not found. Please install it first."
        exit 1
    fi
    
    # Check kubectl
    if [ ! command -v kubectl &> /dev/null ]; then
        echo "ERROR: kubectl not found. Please install it first."
        exit 1
    fi
    
    # Check helm
    if [ ! command -v helm &> /dev/null ]; then
        echo "ERROR: helm not found. Please install it first."
        echo "Install with: brew install helm"
        exit 1
    fi
    
    # Check docker
    if [ ! command -v docker &> /dev/null ]; then
        echo "ERROR: docker not found. Please install it first."
        exit 1
    fi
    
    # Check secrets directory
    if [ ! -d "$SECRETS_DIR" ]; then
        echo "WARNING: Secrets directory not found: $SECRETS_DIR"
        echo "Cluster will be created without secrets. You can add them later."
    fi
    
    # Check Docker username
    if [ -z "$DOCKER_USERNAME" ]; then
        echo "WARNING: DOCKER_USERNAME not set."
        echo "You'll need to manually push the Docker image and update k8s/ray-cluster.yaml"
    fi
    
    echo "✓ All prerequisites met"
}

build_and_push_image() {
    if [ -z "$DOCKER_USERNAME" ]; then
        print_header "Skipping Docker Image Push (DOCKER_USERNAME not set)"
        echo "To push manually:"
        echo "  export DOCKER_USERNAME=your-username"
        echo "  docker login"
        echo "  ./scripts/build_and_push.sh"
        return
    fi
    
    print_header "Building and Pushing Docker Image"
    
    # Build and push using the build script
    # Capture the output to extract the image tag
    # Don't pass IMAGE_TAG - let build_and_push.sh determine it from git
    BUILD_OUTPUT=$(DOCKER_USERNAME="${DOCKER_USERNAME}" ./scripts/build_and_push.sh 2>&1)
    BUILD_EXIT_CODE=$?
    
    # Display the build output
    echo "$BUILD_OUTPUT"
    
    # Check if build succeeded
    if [ $BUILD_EXIT_CODE -ne 0 ]; then
        echo ""
        echo "ERROR: Docker build failed with exit code $BUILD_EXIT_CODE"
        exit 1
    fi
    
    # Extract the image tag from build output (build_and_push.sh outputs LAKEFRONT_IMAGE_TAG=xxx)
    DEPLOYED_IMAGE_TAG=$(echo "$BUILD_OUTPUT" | grep "^LAKEFRONT_IMAGE_TAG=" | cut -d'=' -f2)
    
    if [ -z "$DEPLOYED_IMAGE_TAG" ]; then
        echo "ERROR: Failed to determine image tag from build output"
        echo "Build may have succeeded but didn't output LAKEFRONT_IMAGE_TAG"
        exit 1
    fi
    
    # Export for use in deploy_ray_cluster
    export IMAGE_TAG="$DEPLOYED_IMAGE_TAG"

    echo ""
    echo "✓ Image built and pushed: ${DOCKER_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}"
}

create_gke_cluster() {
    print_header "Creating GKE Cluster: ${CLUSTER_NAME}"
    
    # Set project
    gcloud config set project "${PROJECT_ID}"
    
    # Check if cluster already exists
    if gcloud container clusters describe "${CLUSTER_NAME}" --zone="${ZONE}" &> /dev/null; then
        echo "Cluster ${CLUSTER_NAME} already exists in zone ${ZONE}"
        read -p "Do you want to delete and recreate it? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Deleting existing cluster..."
            gcloud container clusters delete "${CLUSTER_NAME}" --zone="${ZONE}" --quiet
        else
            echo "Using existing cluster"
            gcloud container clusters get-credentials --zone="${ZONE}" "${CLUSTER_NAME}"
            return
        fi
    fi
    
    # Build network flags
    NETWORK_FLAGS=""
    if [ -n "${NETWORK:-}" ]; then
        NETWORK_FLAGS="--network ${NETWORK} --subnetwork ${SUBNETWORK}"
    fi
    
    # Create cluster
    echo "Creating cluster with:"
    echo "  Machine type: ${MACHINE_TYPE}"
    echo "  Nodes: ${NUM_NODES}"
    echo "  Disk: ${DISK_SIZE}GB ${DISK_TYPE}"
    echo ""
    
    gcloud container clusters create "${CLUSTER_NAME}" \
        --zone="${ZONE}" \
        --no-enable-basic-auth \
        --release-channel="stable" \
        --machine-type="${MACHINE_TYPE}" \
        --image-type="COS_CONTAINERD" \
        --disk-type="${DISK_TYPE}" \
        --disk-size="${DISK_SIZE}" \
        --metadata disable-legacy-endpoints=true \
        --scopes="https://www.googleapis.com/auth/devstorage.read_only","https://www.googleapis.com/auth/logging.write","https://www.googleapis.com/auth/monitoring","https://www.googleapis.com/auth/servicecontrol","https://www.googleapis.com/auth/service.management.readonly","https://www.googleapis.com/auth/trace.append" \
        --spot \
        --num-nodes="${NUM_NODES}" \
        --logging=SYSTEM,WORKLOAD \
        --monitoring=SYSTEM \
        --enable-ip-alias \
        ${NETWORK_FLAGS} \
        --no-enable-intra-node-visibility \
        --no-enable-master-authorized-networks \
        --addons=HorizontalPodAutoscaling,HttpLoadBalancing,GcePersistentDiskCsiDriver \
        --enable-autoupgrade \
        --enable-autorepair \
        --max-unavailable-upgrade=1 \
        --max-pods-per-node="110" \
        --node-locations="${ZONE}" \
        --enable-shielded-nodes \
        --shielded-secure-boot \
        --shielded-integrity-monitoring
    
    # Get credentials
    gcloud container clusters get-credentials --zone="${ZONE}" "${CLUSTER_NAME}"
    
    echo "✓ Cluster created successfully"
}

install_kuberay_operator() {
    print_header "Installing KubeRay Operator"
    
    # Add KubeRay Helm repo
    echo "Adding KubeRay Helm repository..."
    helm repo add kuberay https://ray-project.github.io/kuberay-helm/
    helm repo update
    
    # Check if operator is already installed
    if helm list -n kuberay-system | grep -q kuberay-operator; then
        echo "KubeRay operator already installed"
    else
        # Create namespace
        kubectl create namespace kuberay-system --dry-run=client -o yaml | kubectl apply -f -
        
        # Install operator
        echo "Installing KubeRay operator..."
        helm install kuberay-operator kuberay/kuberay-operator \
            --namespace kuberay-system \
            --version 1.1.1
        
        echo "Waiting for operator to be ready..."
        kubectl wait --for=condition=available --timeout=300s \
            deployment/kuberay-operator -n kuberay-system
    fi
    
    echo "✓ KubeRay operator ready"
}

create_secrets() {
    print_header "Creating Kubernetes Secrets"
    
    if [ ! -d "$SECRETS_DIR" ]; then
        echo "Secrets directory not found: $SECRETS_DIR"
        echo "Skipping secrets creation. Cluster will run without authentication."
        return
    fi
    
    # Check if secret already exists
    if kubectl get secret cloudvolume-secrets &> /dev/null; then
        echo "Secret 'cloudvolume-secrets' already exists"
        read -p "Do you want to delete and recreate it? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kubectl delete secret cloudvolume-secrets
        else
            echo "Using existing secret"
            return
        fi
    fi
    
    # Find all JSON files in secrets directory
    SECRET_FILES=()
    while IFS= read -r -d '' file; do
        SECRET_FILES+=("--from-file=$file")
    done < <(find "$SECRETS_DIR" -name "*.json" -print0)
    
    if [ ${#SECRET_FILES[@]} -eq 0 ]; then
        echo "No secret files found in $SECRETS_DIR"
        echo "Skipping secrets creation"
        return
    fi
    
    echo "Creating secret with ${#SECRET_FILES[@]} files..."
    kubectl create secret generic cloudvolume-secrets "${SECRET_FILES[@]}"
    
    echo "✓ Secrets created"
}

deploy_workload() {
    print_header "Deploying Workload"
    
    # Verify IMAGE_TAG is set (should be set by build_and_push_image)
    if [ -z "${IMAGE_TAG:-}" ]; then
        echo "ERROR: IMAGE_TAG not set. Build may have failed."
        echo "IMAGE_TAG must be set before deploying."
        exit 1
    fi
    
    # Never deploy with 'latest' tag - it causes caching issues
    if [ "${IMAGE_TAG}" = "latest" ]; then
        echo "ERROR: Cannot deploy with 'latest' tag"
        echo "This causes image caching issues on GKE nodes."
        echo "Use a specific tag (git commit SHA or version number)."
        exit 1
    fi
    
    # Use the IMAGE_TAG set by build_and_push_image
    DEPLOY_IMAGE="${DOCKER_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}"
    
    echo "Using deployment YAML: ${DEPLOYMENT_YAML}"
    echo "Using image: ${DEPLOY_IMAGE}"
    echo ""
    
    # Check if deployment yaml exists
    if [ ! -f "${DEPLOYMENT_YAML}" ]; then
        echo "ERROR: Deployment YAML not found: ${DEPLOYMENT_YAML}"
        exit 1
    fi
    
    # Check if this is a RayCluster deployment
    if grep -q "kind: RayCluster" "${DEPLOYMENT_YAML}"; then
        # Get the RayCluster name from the YAML
        RAYCLUSTER_NAME=$(grep "name:" "${DEPLOYMENT_YAML}" | head -1 | awk '{print $2}')
        
        # Check if RayCluster already exists
        if kubectl get raycluster "${RAYCLUSTER_NAME}" &> /dev/null; then
            echo "RayCluster '${RAYCLUSTER_NAME}' already exists"
            echo "To update the Docker image, the RayCluster must be deleted and recreated"
            read -p "Delete and recreate RayCluster? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "Deleting existing RayCluster..."
                kubectl delete raycluster "${RAYCLUSTER_NAME}"
                echo "Waiting for pods to terminate..."
                sleep 5
            else
                echo "Keeping existing RayCluster (image will NOT be updated)"
            fi
        fi
    fi
    
    # Apply deployment configuration with image substitution
    echo "Applying deployment configuration..."
    # Support both bdpedigo/lakefront and bdpedigo/${IMAGE_NAME} patterns
    sed "s|image: bdpedigo/lakefront:.*|image: ${DEPLOY_IMAGE}|g; s|image: bdpedigo/${IMAGE_NAME}:.*|image: ${DEPLOY_IMAGE}|g" "${DEPLOYMENT_YAML}" | kubectl apply -f -
    
    # Apply service if specified and exists
    if [ -n "${SERVICE_YAML}" ] && [ -f "${SERVICE_YAML}" ]; then
        echo "Applying service..."
        kubectl apply -f "${SERVICE_YAML}"
    fi
    
    echo ""
    echo "Waiting for pods to be ready..."
    echo "(This may take a few minutes while the image is pulled)"
    
    # Detect deployment type and wait accordingly
    if [[ "$IMAGE_NAME" == *"ray"* ]] || grep -q "ray.io/cluster" "${DEPLOYMENT_YAML}"; then
        # Wait for Ray head node
        kubectl wait --for=condition=ready pod \
            -l ray.io/cluster \
            -l ray.io/node-type=head \
            --timeout=200s 2>/dev/null || echo "Note: Not a Ray cluster or Ray pods not labeled"
    else
        # Wait for generic deployment
        DEPLOYMENT_NAME=$(grep "name:" "${DEPLOYMENT_YAML}" | head -1 | awk '{print $2}')
        if [ -n "$DEPLOYMENT_NAME" ]; then
            kubectl rollout status deployment/"${DEPLOYMENT_NAME}" --timeout=600s || echo "Deployment rollout status check skipped"
        fi
    fi

    echo "✓ Workload deployed"
}

print_cluster_info() {
    print_header "Cluster Information"
    
    echo "Cluster: ${CLUSTER_NAME}"
    echo "Zone: ${ZONE}"
    echo ""
    
    echo "Ray Cluster Status:"
    kubectl get raycluster
    echo ""
    
    echo "Ray Pods:"
    kubectl get pods -l ray.io/cluster=${IMAGE_NAME}-cluster
    echo ""
    
    echo "Ray Service:"
    kubectl get service ${IMAGE_NAME}-head
    echo ""
    
    # Get external IP
    EXTERNAL_IP=$(kubectl get service ${IMAGE_NAME}-head -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "pending")
    
    if [ "$EXTERNAL_IP" != "pending" ] && [ -n "$EXTERNAL_IP" ]; then
        echo "Ray Dashboard: http://${EXTERNAL_IP}:8265"
        echo "Ray Client: ray://\${EXTERNAL_IP}:10001"
    else
        echo "External IP is pending. Run this to check status:"
        echo "  kubectl get service ${IMAGE_NAME}-head --watch"
    fi
    
    echo ""
    echo "Useful commands:"
    echo "  # Get cluster status"
    echo "  kubectl get raycluster"
    echo ""
    echo "  # Get pods"
    echo "  kubectl get pods -l ray.io/cluster=${IMAGE_NAME}-cluster"
    echo ""
    echo "  # SSH into head node"
    echo "  kubectl exec -it \$(kubectl get pod -l ray.io/node-type=head -o name) -- bash"
    echo ""
    echo "  # View logs"
    echo "  kubectl logs \$(kubectl get pod -l ray.io/node-type=head -o name)"
    echo ""
    echo "  # Submit a job"
    echo "  kubectl exec \$(kubectl get pod -l ray.io/node-type=head -o name) -- python jobs/simple_job.py"
}

#==============================================================================
# MAIN
#==============================================================================

main() {
    print_header "GKE Cluster Setup for Lakefront"
    echo "Project: ${PROJECT_ID}"
    echo "Cluster: ${CLUSTER_NAME}"
    echo "Zone: ${ZONE}"
    echo "Machine Type: ${MACHINE_TYPE}"
    echo "Nodes: ${NUM_NODES}"
    echo "Docker Image: ${DOCKER_USERNAME}/${IMAGE_NAME}:${IMAGE_TAG}"
    echo "Deployment YAML: ${DEPLOYMENT_YAML}"
    echo ""
    
    check_prerequisites
    
    read -p "Continue with cluster creation? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted"
        exit 0
    fi
    
    # build_and_push_image
    create_gke_cluster
    # check if ray is in $ image name, install kuberay operator if so
    if [[ "$IMAGE_NAME" == *"ray"* ]] || grep -q "ray.io/cluster" "${DEPLOYMENT_YAML}"; then
        install_kuberay_operator
    fi
    create_secrets
    deploy_workload
    print_cluster_info
    
    print_header "Setup Complete!"
    echo "Your cluster is ready to use."
}

# Run main function
main
