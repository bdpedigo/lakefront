# Lakefront — modular Ray job runner
# Usage: just <command> [args]

# Run a config locally (Ray auto-init)
run config:
    uv run --frozen runner.py jobs/{{config}}/config.yaml

# Shorthand test commands
test-simple:
    just run test_simple

test-setup:
    just run test_setup

test-failure:
    just run test_flaky

# Start local kind cluster with Ray
cluster-up-local:
    scripts/test_local_k8s.sh

# Tear down local kind cluster
cluster-down-local:
    scripts/cleanup_local_k8s.sh

# Ensure port-forward to Ray dashboard is active
[private]
ensure-port-forward:
    #!/bin/bash
    if ! curl -s http://localhost:8265 > /dev/null 2>&1; then
        echo "Starting port-forward to Ray dashboard..."
        kubectl port-forward svc/lakefront-ray-cluster-head-svc 8265:8265 &
        sleep 2
    fi

# Check Ray cluster readiness (head + workers responding)
check-ready: ensure-port-forward
    #!/bin/bash
    echo "Checking Ray cluster readiness..."
    for i in $(seq 1 30); do
        if curl -s http://localhost:8265/api/cluster_status | grep -q '"alive"'; then
            echo "Ray cluster is ready."
            ray status --address http://localhost:8265
            exit 0
        fi
        echo "Waiting for Ray cluster... ($i/30)"
        sleep 2
    done
    echo "ERROR: Ray cluster not ready after 60s"
    exit 1

# Submit a job to the running cluster (uploads working dir automatically)
submit config: ensure-port-forward
    uv run --frozen ray job submit --address http://localhost:8265 --working-dir . -- uv run --frozen python runner.py jobs/{{config}}/config.yaml

# Build the Docker image and push to Docker Hub
build:
    scripts/build_and_push.sh

# Build the Docker image locally only (no push)
build-local:
    LOCAL_ONLY=1 scripts/build_and_push.sh

# Port-forward Ray dashboard and open browser
dashboard: ensure-port-forward
    open http://localhost:8265

# Launch remote GKE cluster (on-demand head + spot workers)
# Optionally pass a job name to read machine type overrides from its config.yaml
cluster-up job="":
    #!/bin/bash
    if [ -n "{{job}}" ]; then
        config="jobs/{{job}}/config.yaml"
        if [ ! -f "$config" ]; then
            echo "ERROR: Config not found: $config"
            exit 1
        fi
        eval "$(uv run python -c 'import yaml,sys;c=yaml.safe_load(open(sys.argv[1])).get("cluster",{});h=c.get("head_machine_type");w=c.get("worker_machine_type");m=c.get("max_workers");print(f"export HEAD_MACHINE_TYPE={h}" if h else "",end="");print(f"\nexport WORKER_MACHINE_TYPE={w}" if w else "",end="");print(f"\nexport WORKER_MAX_NODES={m}" if m else "",end="")' "$config")"
    fi
    scripts/launch_cluster.sh

# Tear down remote GKE cluster
cluster-down:
    scripts/cleanup_cluster.sh
