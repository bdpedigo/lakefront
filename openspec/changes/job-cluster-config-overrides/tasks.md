## 1. Job Config Schema

- [x] 1.1 Add `cluster:` section with `head_machine_type` and `worker_machine_type` to `jobs/segclr/config.yaml` as the first real use case
- [x] 1.2 Verify runner ignores the new `cluster:` key (run `just run segclr` locally)

## 2. Justfile Recipe

- [x] 2.1 Replace the existing no-arg `cluster-up` recipe with a parameterized `cluster-up job=""` recipe that reads `jobs/<job>/config.yaml` when job is provided
- [x] 2.2 Add Python one-liner to extract `cluster.head_machine_type` and `cluster.worker_machine_type` from the config and export as env vars
- [x] 2.3 Ensure the recipe falls through to defaults when no job is provided or when the config has no `cluster:` section

## 3. Validation

- [x] 3.1 Test `just cluster-up segclr` outputs correct env vars (dry-run or echo)
- [x] 3.2 Test `just cluster-up` with no args still works (uses script defaults)
- [x] 3.3 Test `just cluster-up nonexistent_job` fails with clear error
