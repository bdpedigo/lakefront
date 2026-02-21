# Kubernetes Configuration for Lakefront Ray

This directory contains Kubernetes manifests for deploying Ray clusters using KubeRay.

## Files

### ray-cluster.yaml
The main RayCluster custom resource definition. Configures:
- **Head node**: 1 replica with dashboard and coordination services
- **Worker nodes**: 2-10 replicas (configurable) for distributed computation
- **Secrets**: Mounts `/root/.cloudvolume/secrets` for authentication
- **Resources**: CPU, memory, and storage limits for both head and workers

### ray-service.yaml
Service definition to expose the Ray cluster:
- **Dashboard**: Port 8265 for Ray web UI
- **Client**: Port 10001 for Ray client connections
- **Type**: LoadBalancer for external access (change to ClusterIP for internal only)

## Configuration Notes

### Image Registry
Before deploying, you need to:
1. Push your Docker image to Docker Hub
2. Update the `image:` field in ray-cluster.yaml

Example for Docker Hub:
```bash
# Login to Docker Hub
docker login

# Tag the image with your Docker Hub username
docker tag lakefront-ray:latest YOUR-DOCKERHUB-USERNAME/lakefront-ray:latest

# Push to Docker Hub
docker push YOUR-DOCKERHUB-USERNAME/lakefront-ray:latest

# Update ray-cluster.yaml
# Change: image: lakefront-ray:latest
# To:     image: YOUR-DOCKERHUB-USERNAME/lakefront-ray:latest
# And:    imagePullPolicy: Always
```

### Secrets
The cluster expects a Kubernetes secret named `cloudvolume-secrets` with your authentication files:
- cave-secret.json
- google-secret.json
- aws-secret.json
- etc.

This will be created by the cluster launch script in Step 4.

### Resource Sizing
Current configuration (can be adjusted in ray-cluster.yaml):

**Head Node:**
- Memory: 4-8 GiB
- CPU: 2 cores
- Storage: 4-16 GiB

**Worker Nodes:**
- Memory: 8-32 GiB
- CPU: 4 cores
- Storage: 8-32 GiB
- Replicas: 2 (can scale 0-10)

Adjust based on your workload requirements.

## Deployment

These files will be used by the cluster launch script (Step 4), but you can also deploy manually:

```bash
# Install KubeRay operator (if not already installed)
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm install kuberay-operator kuberay/kuberay-operator --version 1.0.0

# Create secrets (see Step 4 script for full command)
kubectl create secret generic cloudvolume-secrets \
  --from-file=$HOME/.cloudvolume/secrets/

# Deploy the cluster
kubectl apply -f k8s/ray-cluster.yaml
kubectl apply -f k8s/ray-service.yaml

# Check status
kubectl get rayclusters
kubectl get pods -l ray.io/cluster=lakefront-ray-cluster

# Get dashboard URL
kubectl get service lakefront-ray-head
```

## Connecting to the Cluster

Once deployed, you can:

1. **Access the dashboard**: `http://<EXTERNAL-IP>:8265`
2. **Submit jobs**: `ray job submit --address http://<EXTERNAL-IP>:8265 -- python jobs/simple_job.py`
3. **SSH into head node**: `kubectl exec -it <head-pod-name> -- bash`
4. **View logs**: `kubectl logs <pod-name>`
