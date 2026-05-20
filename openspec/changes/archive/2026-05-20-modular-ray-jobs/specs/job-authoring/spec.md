## ADDED Requirements

### Requirement: Job function uses @ray.remote with resource declarations
A job function SHALL be a Python function decorated with `@ray.remote` that declares its CPU, memory, and GPU requirements directly on the decorator.

#### Scenario: Job with resource requirements
- **WHEN** a job author creates a function decorated with `@ray.remote(num_cpus=4, memory=32 * 1024**3)`
- **THEN** Ray schedules the task on a worker with at least 4 CPUs and 32GB memory

#### Scenario: Job with default resources
- **WHEN** a job author creates a function decorated with `@ray.remote` without explicit resources
- **THEN** Ray uses default resource allocation (1 CPU)

### Requirement: Job function accepts work item as first argument
A job function SHALL accept a single work item as its first positional argument, followed by any shared ObjectRef keyword arguments provided by the setup phase.

#### Scenario: Simple job invocation
- **WHEN** a job function is defined as `def process(item)`
- **THEN** runner calls `process.remote(item)` for each work item from the insertion

#### Scenario: Job with shared state
- **WHEN** a job function is defined as `def process(item, mesh_ref=None, synapse_ref=None)` and setup returns `{"mesh_ref": ref1, "synapse_ref": ref2}`
- **THEN** runner calls `process.remote(item, mesh_ref=ref1, synapse_ref=ref2)` for each item

### Requirement: Optional setup function for shared state
A job module MAY define a `setup()` function that loads shared data into Ray's object store and returns a dict of `str -> ray.ObjectRef`.

#### Scenario: Setup loads shared data
- **WHEN** a job module defines `def setup()` that calls `ray.put(meshes)` and returns `{"mesh_ref": ref}`
- **THEN** the runner calls `setup()` once before fan-out and passes the returned refs to every task

#### Scenario: No setup function
- **WHEN** a job module does not define a `setup` function and the YAML config has no `setup` field
- **THEN** runner skips the setup phase and invokes tasks with only the work item argument

### Requirement: Jobs declare max_retries for fault tolerance
Job functions SHOULD declare `max_retries` and `retry_exceptions` on the `@ray.remote` decorator for resilience to worker preemption and transient errors.

#### Scenario: Worker preemption during task
- **WHEN** a spot worker is preempted while running a task decorated with `@ray.remote(max_retries=3)`
- **THEN** Ray reschedules the task on another available worker, up to 3 times
