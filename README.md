# Lakefront - Ray Job Controller

Messing around with Ray and KubeRay for connectomics workflows.

## Commands 

To build and push the Docker image:

```bash
./scripts/build_and_push.sh
```

To build and push without Ray: 

```bash
IMAGE_NAME="lakefront" DOCKERFILE="Dockerfile.noray" ./scripts/build_and_push.sh
```

To start a Ray cluster on GKE:

```bash
./scripts/launch_cluster.sh
```

To start a cluster without Ray:

```bash
IMAGE_NAME="lakefront" DOCKERFILE="Dockerfile.noray" ./scripts/launch_cluster.sh
```