# Lakefront — modular Ray job runner
# Usage: just <command> [args]

# Run a config locally (Ray auto-init)
run config:
    uv run python runner.py configs/{{config}}.yaml

# Shorthand test commands
test-simple:
    just run simple

test-setup:
    just run setup_example

test-failure:
    just run failure_test

# Start local kind cluster with Ray
cluster-up-local:
    scripts/test_local_k8s.sh

# Tear down local kind cluster
cluster-down-local:
    scripts/cleanup_local_k8s.sh

# Submit a job to the running cluster (uploads working dir automatically)
submit config:
    ray job submit --address http://localhost:8265 --working-dir . -- python runner.py configs/{{config}}.yaml

# Build the Docker image
build:
    docker build -t lakefront:latest .

# Port-forward Ray dashboard and open browser
dashboard:
    kubectl port-forward svc/raycluster-head-svc 8265:8265 &
    open http://localhost:8265

# Launch remote GKE cluster (on-demand head + spot workers)
cluster-up:
    scripts/launch_cluster.sh

# Tear down remote GKE cluster
cluster-down:
    scripts/cleanup_cluster.sh
