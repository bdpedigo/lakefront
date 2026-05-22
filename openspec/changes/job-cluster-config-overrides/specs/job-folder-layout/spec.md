## MODIFIED Requirements

### Requirement: Job folder contains all artifacts for a unit of work
A job folder SHALL be a directory under `jobs/` that contains an `__init__.py`, one or more Python files with Ray job definitions, an items module with an insertion function, and a `config.yaml`. The `config.yaml` MAY additionally contain an optional `cluster:` mapping with keys `head_machine_type` and/or `worker_machine_type` (both strings). Unknown keys in the config SHALL be ignored by the runner.

#### Scenario: Complete job folder
- **WHEN** a developer creates `jobs/my_job/` with `__init__.py`, `job.py`, `items.py`, and `config.yaml`
- **THEN** the runner SHALL be able to execute the job via `python runner.py jobs/my_job/config.yaml`

#### Scenario: Job folder with cluster overrides
- **WHEN** `jobs/my_job/config.yaml` contains a `cluster:` section with `worker_machine_type: e2-highmem-32`
- **THEN** the runner SHALL ignore the `cluster:` key during execution, and the cluster-up recipe SHALL use the value when provisioning

#### Scenario: Missing config file
- **WHEN** a job folder exists without a `config.yaml`
- **THEN** the runner SHALL raise an error when attempting to discover or run that job
