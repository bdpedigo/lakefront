## ADDED Requirements

### Requirement: Job config supports optional cluster section
A job's `config.yaml` MAY include a `cluster:` mapping with optional keys `head_machine_type` and `worker_machine_type`. Both keys are strings representing GCE machine type names.

#### Scenario: Config with both overrides
- **WHEN** `jobs/segclr/config.yaml` contains `cluster: { head_machine_type: e2-standard-8, worker_machine_type: e2-highmem-32 }`
- **THEN** the cluster-up recipe SHALL pass those values as `HEAD_MACHINE_TYPE` and `WORKER_MACHINE_TYPE` environment variables to the launch script

#### Scenario: Config with only worker override
- **WHEN** a config specifies `cluster: { worker_machine_type: n2-highmem-16 }` without `head_machine_type`
- **THEN** the cluster-up recipe SHALL pass `WORKER_MACHINE_TYPE=n2-highmem-16` and leave `HEAD_MACHINE_TYPE` unset (script uses its default)

#### Scenario: Config with no cluster section
- **WHEN** a config has no `cluster:` key
- **THEN** the cluster-up recipe SHALL invoke the launch script with no machine type overrides (script defaults apply)

### Requirement: Justfile cluster-up recipe accepts optional job name
The `cluster-up` recipe SHALL accept an optional positional argument specifying a job folder name. When provided, it SHALL read cluster overrides from that job's `config.yaml`.

#### Scenario: cluster-up with job name
- **WHEN** a user runs `just cluster-up segclr`
- **THEN** the recipe reads `jobs/segclr/config.yaml`, extracts any `cluster:` overrides, and invokes `scripts/launch_cluster.sh` with the corresponding environment variables

#### Scenario: cluster-up without job name
- **WHEN** a user runs `just cluster-up`
- **THEN** the recipe invokes `scripts/launch_cluster.sh` with no overrides (using script defaults)

#### Scenario: cluster-up with nonexistent job
- **WHEN** a user runs `just cluster-up nonexistent_job`
- **THEN** the recipe SHALL fail with an error indicating the config file was not found
