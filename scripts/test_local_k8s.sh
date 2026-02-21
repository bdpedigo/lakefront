#!/bin/bash
# Script to test KubeRay deployment locally using kind
# This allows testing the cluster setup before deploying to GKE

set -e

#==============================================================================
# CONFIGURATION
#==============================================================================

CLUSTER_NAME="${KIND_CLUSTER_NAME:-lakefront-ray-local}"
K8S_PROVIDER="${K8S_PROVIDER:-kind}"  # kind or minikube

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
    
    if [ "$K8S_PROVIDER" = "kind" ]; then
        if ! command -v kind &> /dev/null; then
            echo "ERROR: kind not found. Install with:"
            echo "  brew install kind"
            exit 1
        fi
    elif [ "$K8S_PROVIDER" = "minikube" ]; then
        if ! command -v minikube &> /dev/null; then
            echo "ERROR: minikube not found. Install with:"
            echo "  brew install minikube"
            exit 1
        fi
    else
        echo "ERROR: K8S_PROVIDER must be 'kind' or 'minikube'"
        exit 1
    fi
    
    if ! command -v kubectl &> /dev/null; then
        echo "ERROR: kubectl not found"
        exit 1
    fi
    
    if ! command -v helm &> /dev/null; then
        echo "ERROR: helm not found. Install with:"
        echo "  brew install helm"
        exit 1
    fi
    
    if ! docker image inspect lakefront-ray:latest &> /dev/null; then
        echo "ERROR: Docker image not found. Build it first:"
        echo "  ./scripts/build_docker.sh"
        exit 1
    fi
    
    echo "✓ All prerequisites met"
}

create_local_cluster() {
    print_header "Creating Local Kubernetes Cluster"
    
    if [ "$K8S_PROVIDER" = "kind" ]; then
        # Check if cluster exists
        if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
            echo "Cluster ${CLUSTER_NAME} already exists"
            read -p "Delete and recreate? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                kind delete cluster --name "${CLUSTER_NAME}"
            else
                echo "Using existing cluster"
                kubectl config use-context "kind-${CLUSTER_NAME}"
                return
            fi
        fi
        
        # Create kind cluster with extra port mappings
        echo "Creating kind cluster..."
        cat <<EOF | kind create cluster --name "${CLUSTER_NAME}" --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      # Ray dashboard
      - containerPort: 30265
        hostPort: 8265
        protocol: TCP
      # Ray client
      - containerPort: 30001
        hostPort: 10001
        protocol: TCP
EOF
        
    elif [ "$K8S_PROVIDER" = "minikube" ]; then
        if minikube status -p "${CLUSTER_NAME}" &> /dev/null; then
            echo "Cluster ${CLUSTER_NAME} already exists"
            minikube start -p "${CLUSTER_NAME}"
        else
            echo "Creating minikube cluster..."
            minikube start -p "${CLUSTER_NAME}" --cpus=4 --memory=8192
        fi
    fi
    
    echo "✓ Cluster created"
}

load_docker_image() {
    print_header "Loading Docker Image into Cluster"
    
    if [ "$K8S_PROVIDER" = "kind" ]; then
        echo "Loading image into kind..."
        kind load docker-image lakefront-ray:latest --name "${CLUSTER_NAME}"
    elif [ "$K8S_PROVIDER" = "minikube" ]; then
        echo "Loading image into minikube..."
        minikube -p "${CLUSTER_NAME}" image load lakefront-ray:latest
    fi
    
    echo "✓ Image loaded"
}

install_kuberay_operator() {
    print_header "Installing KubeRay Operator"
    
    # Add KubeRay Helm repo
    helm repo add kuberay https://ray-project.github.io/kuberay-helm/ 2>/dev/null || true
    helm repo update
    
    # Check if operator is already installed
    if helm list -n kuberay-system 2>/dev/null | grep -q kuberay-operator; then
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

create_local_ray_config() {
    print_header "Creating Local Ray Configuration"
    
    # Create a modified ray-cluster.yaml with reduced resources for local testing
    cat > /tmp/ray-cluster-local.yaml <<'EOF'
apiVersion: ray.io/v1
kind: RayCluster
metadata:
  name: lakefront-ray-cluster
  namespace: default
spec:
  rayVersion: "2.54.0"
  enableInTreeAutoscaling: false
  
  headGroupSpec:
    rayStartParams:
      dashboard-host: "0.0.0.0"
      port: "6379"
      disable-usage-stats: "true"
    
    template:
      spec:
        containers:
          - name: ray-head
            image: lakefront-ray:latest
            imagePullPolicy: IfNotPresent
            
            # Reduced resources for local testing
            resources:
              requests:
                memory: "1Gi"
                cpu: "1"
              limits:
                memory: "2Gi"
            
            env:
              - name: RAY_DEDUP_LOGS
                value: "0"
              - name: PYTHONUNBUFFERED
                value: "1"
            
            ports:
              - containerPort: 6379
                name: gcs-server
              - containerPort: 8265
                name: dashboard
              - containerPort: 10001
                name: client
  
  workerGroupSpecs:
    - groupName: worker-group
      replicas: 1  # Just 1 worker for local testing
      minReplicas: 0
      maxReplicas: 2
      
      rayStartParams:
        port: "6379"
      
      template:
        spec:
          containers:
            - name: ray-worker
              image: lakefront-ray:latest
              imagePullPolicy: IfNotPresent
              
              # Reduced resources for local testing
              resources:
                requests:
                  memory: "1Gi"
                  cpu: "1"
                limits:
                  memory: "2Gi"
              
              env:
                - name: RAY_DEDUP_LOGS
                  value: "0"
                - name: PYTHONUNBUFFERED
                  value: "1"
EOF

    # Create service with NodePort for local access
    cat > /tmp/ray-service-local.yaml <<'EOF'
apiVersion: v1
kind: Service
metadata:
  name: lakefront-ray-head
  namespace: default
spec:
  type: NodePort
  selector:
    ray.io/cluster: lakefront-ray-cluster
    ray.io/node-type: head
  
  ports:
    - name: dashboard
      port: 8265
      targetPort: 8265
      nodePort: 30265
      protocol: TCP
    
    - name: client
      port: 10001
      targetPort: 10001
      nodePort: 30001
      protocol: TCP
    
    - name: gcs-server
      port: 6379
      targetPort: 6379
      protocol: TCP
EOF
    
    echo "✓ Local configuration created"
}

deploy_ray_cluster() {
    print_header "Deploying Ray Cluster"
    
    # Apply configurations
    kubectl apply -f /tmp/ray-cluster-local.yaml
    kubectl apply -f /tmp/ray-service-local.yaml
    
    echo ""
    echo "Waiting for Ray head node to start..."
    # Note: Readiness probes can take time - we just wait for Running status
    # Ray is functional even before the health checks pass
    kubectl wait --for=jsonpath='{.status.phase}'=Running pod \
        -l ray.io/cluster=lakefront-ray-cluster \
        -l ray.io/node-type=head \
        --timeout=180s
    
    # Give Ray a moment to fully initialize
    sleep 5
    
    echo "✓ Ray cluster deployed"
}

run_test_job() {
    print_header "Running Test Job"
    
    HEAD_POD=$(kubectl get pod -l ray.io/cluster=lakefront-ray-cluster -l ray.io/node-type=head -o jsonpath='{.items[0].metadata.name}')
    
    if [ -z "$HEAD_POD" ]; then
        echo "ERROR: Could not find Ray head pod"
        exit 1
    fi
    
    echo "Head pod: ${HEAD_POD}"
    echo "Executing simple_job.py..."
    echo ""
    
    kubectl exec "${HEAD_POD}" -- python jobs/simple_job.py
    
    echo ""
    echo "✓ Test job completed successfully"
}

print_cluster_info() {
    print_header "Cluster Information"
    
    echo "Cluster: ${CLUSTER_NAME}"
    echo "Provider: ${K8S_PROVIDER}"
    echo ""
    
    echo "Ray Cluster Status:"
    kubectl get raycluster
    echo ""
    
    echo "Ray Pods:"
    kubectl get pods -l ray.io/cluster=lakefront-ray-cluster
    echo ""
    
    echo "Ray Service:"
    kubectl get service lakefront-ray-head
    echo ""
    
    echo "Access Information:"
    echo "  Ray Dashboard: http://localhost:8265"
    echo "  Ray Client Port: 10001"
    echo ""
    
    echo "Useful commands:"
    echo "  # SSH into head node"
    echo "  kubectl exec -it ${HEAD_POD} -- bash"
    echo ""
    echo "  # View logs"
    echo "  kubectl logs ${HEAD_POD}"
    echo ""
    echo "  # Submit a job"
    echo "  kubectl exec ${HEAD_POD} -- python jobs/simple_job.py"
    echo ""
    echo "  # Open dashboard"
    echo "  open http://localhost:8265"
    echo ""
    echo "  # Clean up"
    echo "  ./scripts/cleanup_local_k8s.sh"
}

#==============================================================================
# MAIN
#==============================================================================

main() {
    print_header "Local KubeRay Testing with ${K8S_PROVIDER}"
    
    check_prerequisites
    create_local_cluster
    load_docker_image
    install_kuberay_operator
    create_local_ray_config
    deploy_ray_cluster
    run_test_job
    print_cluster_info
    
    print_header "Local Testing Complete!"
    echo "Your Ray cluster is running locally and ready to use."
    echo "Open http://localhost:8265 to view the Ray dashboard."
}

main
