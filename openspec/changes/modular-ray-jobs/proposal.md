## Why

We have a growing number of data processing jobs (mesh transforms, synapse extraction, table migrations) that all follow the same pattern: get a list of work items, process each in parallel, write results. Currently each job is a bespoke script with resources, parallelism, and item selection all tangled together. We need a composable system where jobs, item sources ("insertions"), and resource requirements are independent and can be mixed/matched at deployment time via simple YAML configs.

## What Changes

- Introduce a YAML-driven job runner that takes a `(job, insertion)` tuple and fans out work over Ray tasks
- Jobs declare their own resource requirements via `@ray.remote` decorators (Option A — resources live close to the code)
- Insertions are pluggable functions that produce lists of work items; a "retry" insertion is just `all_items - completed_items`
- Support a `setup()` phase for jobs that need shared state (e.g., loading meshes into Ray object store before fan-out)
- KubeRay cluster configured with on-demand head node + spot/preemptible worker pool
- Durability via "output table is the job tracker" pattern — no external queue infrastructure

## Capabilities

### New Capabilities
- `job-runner`: YAML-driven runner that loads a job + insertion, wires them together, and executes via Ray
- `job-authoring`: Convention and protocol for writing job functions with `@ray.remote` resources and optional `setup()`
- `insertion-authoring`: Convention for writing insertion functions that produce work item lists
- `cluster-config`: KubeRay cluster configuration with on-demand head + spot workers and autoscaling

### Modified Capabilities

(none — no existing specs)

## Impact

- New directories: `jobs/`, `insertions/`, `configs/` (YAML run configs)
- New runner script/module that reads YAML and orchestrates execution
- Updates to `k8s/ray-cluster.yaml` for head/worker node pool separation
- Updates to `scripts/launch_cluster.sh` for spot node pool creation
- Dependencies: no new external deps beyond what's in pyproject.toml (Ray already included)
