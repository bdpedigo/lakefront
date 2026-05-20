# Lakefront — modular Ray job runner
# Usage: just <command> [args]

# Run a config locally (Ray auto-init)
run config:
    uv run python runner.py configs/{{config}}.yaml

# Shorthand test commands
test-simple:
    just run test/simple

test-setup:
    just run test/setup_example

test-failure:
    just run test/failure_test

# Start local kind cluster with Ray
cluster-up-local:
    scripts/test_local_k8s.sh

# Tear down local kind cluster
cluster-down-local:
    scripts/cleanup_local_k8s.sh

# Submit a job to the running cluster (uploads working dir automatically)
submit config:
    uv run ray job submit --address http://localhost:8265 --working-dir . -- uv run python runner.py configs/{{config}}.yaml

# Build the Docker image and push to Docker Hub
build:
    scripts/build_and_push.sh

# Build the Docker image locally only (no push)
build-local:
    LOCAL_ONLY=1 scripts/build_and_push.sh

# Port-forward Ray dashboard and open browser
dashboard:
    kubectl port-forward svc/lakefront-ray-cluster-head-svc 8265:8265 &
    open http://localhost:8265

# Launch remote GKE cluster (on-demand head + spot workers)
cluster-up:
    scripts/launch_cluster.sh

# Tear down remote GKE cluster
cluster-down:
    scripts/cleanup_cluster.sh
