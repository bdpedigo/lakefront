## Context

The `launch_cluster.sh` script already reads `HEAD_MACHINE_TYPE` and `WORKER_MACHINE_TYPE` from environment variables (with defaults `e2-standard-4` and `e2-highmem-16`). The justfile has a `cluster-up` recipe that calls the script with no arguments. Job configs (`config.yaml`) currently only define `job` and `insertion` fields.

We want per-job cluster sizing without duplicating launch logic — just bridge the config to the existing env var mechanism.

## Goals / Non-Goals

**Goals:**
- Allow job authors to declare preferred machine types in their `config.yaml`
- `just cluster-up <job>` reads the job config and passes overrides to the launch script
- Zero changes to `launch_cluster.sh` (it already supports env vars)
- Existing `just cluster-up` (no args) continues to work with defaults

**Non-Goals:**
- Full cluster topology in config (num nodes, disk size, etc.) — keep it minimal for now
- Validating machine type strings against GCP API
- Supporting multiple worker pools with different machine types
- Changing the local kind cluster workflow (`cluster-up-local`)

## Decisions

**1. Config structure: flat `cluster:` section in config.yaml**

```yaml
job: jobs.segclr.transfer_segclr_batched.process_and_write_batch
insertion: jobs.segclr.transfer_segclr_batched.queue_shard_batches_test
cluster:
  head_machine_type: e2-standard-4
  worker_machine_type: e2-highmem-16
```

Alternatives considered:
- Separate `cluster.yaml` per job — rejected: adds file clutter for two optional fields
- Nested under `resources:` — rejected: `cluster:` is more descriptive and leaves room for future fields (e.g., `worker_max_nodes`)

**2. Justfile recipe reads YAML with a small Python one-liner**

The justfile already depends on `uv run`, so we can use Python + PyYAML (already a dependency) to extract values. No new tooling needed.

**3. Parameterized `cluster-up` recipe, keep existing no-arg recipe as alias**

```
cluster-up job="":
```

When `job` is empty, uses defaults. When provided, reads `jobs/<job>/config.yaml`.

## Risks / Trade-offs

- [Risk: typo in machine type string] → No immediate validation; GCP will fail at cluster creation time with a clear error. Acceptable for now.
- [Risk: config schema drift] → The runner ignores unknown keys, so adding `cluster:` is non-breaking.
- [Trade-off: Python for YAML parsing in justfile] → Adds a subprocess call, but it's fast and avoids adding `yq` as a dependency.
