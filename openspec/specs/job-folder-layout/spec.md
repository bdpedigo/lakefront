## ADDED Requirements

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

### Requirement: Job folder naming uses snake_case
Job folder names SHALL use snake_case (e.g., `test_simple`, `test_flaky`).

#### Scenario: Valid job folder name
- **WHEN** a folder is named `test_simple`
- **THEN** it SHALL be recognized as a valid job folder

#### Scenario: Invalid job folder name
- **WHEN** a folder uses kebab-case like `test-simple`
- **THEN** it SHALL NOT be importable as a Python module and is invalid

### Requirement: Config file references modules relative to repo root
The `config.yaml` inside a job folder SHALL use dotted Python paths relative to the repository root for `job`, `insertion`, and optional `setup` fields.

#### Scenario: Config references colocated modules
- **WHEN** `jobs/test_simple/config.yaml` contains `job: jobs.test_simple.job.process`
- **THEN** the runner SHALL resolve the path to `jobs/test_simple/job.py::process`

### Requirement: Items module provides insertion function
Each job folder SHALL contain a module (e.g., `items.py`) that exports a callable returning a list of work items.

#### Scenario: Items module returns work items
- **WHEN** `jobs/test_simple/items.py` defines `def get_items() -> list`
- **THEN** the config SHALL reference it as `insertion: jobs.test_simple.items.get_items`
