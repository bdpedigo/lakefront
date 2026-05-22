## Why

Different jobs have vastly different resource requirements (e.g., SegCLR transfer needs high-memory workers, while test jobs run fine on small instances). Currently, machine types are hardcoded in `launch_cluster.sh` environment variables or must be passed manually. We want `just cluster-up segclr` to read machine type preferences from the job's own `config.yaml` and provision the right cluster automatically.

## What Changes

- Add optional `cluster` section to job-level `config.yaml` supporting `head_machine_type` and `worker_machine_type` overrides
- Add a `just cluster-up <job>` recipe that reads a job's config and passes machine type overrides to the launch script
- Launch script already supports `HEAD_MACHINE_TYPE` and `WORKER_MACHINE_TYPE` env vars — the new recipe simply bridges config to env

## Capabilities

### New Capabilities
- `job-cluster-overrides`: Optional cluster resource fields in job config files and a justfile recipe that reads them to parameterize cluster creation

### Modified Capabilities
- `cluster-config`: Adds requirement that launch script receives machine type overrides from the calling recipe (already supported via env vars, but now formally specified)
- `job-folder-layout`: Adds optional `cluster` section to the config.yaml schema

## Impact

- `jobs/*/config.yaml` — new optional `cluster:` key (non-breaking; existing configs unchanged)
- `justfile` — new `cluster-up <job>` recipe (existing `cluster-up` no-arg recipe unchanged)
- `scripts/launch_cluster.sh` — no code changes required (already reads env vars)
