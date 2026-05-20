## ADDED Requirements

### Requirement: Runner loads and executes a YAML config
The runner SHALL accept a YAML config file path as input, resolve the `job` and `insertion` dotted paths to Python callables, and execute the job over the insertion's items using Ray.

#### Scenario: Simple fan-out job
- **WHEN** runner is invoked with a YAML config specifying `job: jobs.segclr_to_lake.process_segment` and `insertion: insertions.all_segments.get_items`
- **THEN** runner imports both callables, calls the insertion to get a list of items, and invokes the job function as a Ray task for each item

#### Scenario: Job with setup phase
- **WHEN** the YAML config specifies a `setup` dotted path (e.g. `setup: jobs.segclr_to_lake.setup`)
- **THEN** runner calls `setup()` first, receives a `dict[str, ray.ObjectRef]`, and passes the ObjectRefs as keyword arguments to each task invocation

### Requirement: Runner works in any Ray environment
The runner SHALL work locally (Ray auto-initializes) and on a Ray cluster (connects to existing runtime) using the same command and YAML config.

#### Scenario: Local execution
- **WHEN** runner is invoked locally with no Ray cluster running
- **THEN** Ray initializes a local instance and the job executes successfully

#### Scenario: Cluster execution
- **WHEN** runner is invoked within a Ray cluster (e.g. via `ray job submit`)
- **THEN** runner connects to the existing cluster and fans tasks out to available workers

### Requirement: Runner continues on task failure
The runner SHALL continue executing remaining tasks when individual tasks fail permanently (after `max_retries` exhausted). Failed task details SHALL be collected and reported at the end.

#### Scenario: Partial task failure
- **WHEN** 3 out of 100 tasks fail after all retries
- **THEN** runner completes the remaining 97 tasks, then reports the 3 failures with their item identifiers and error messages

#### Scenario: All tasks fail
- **WHEN** every task fails
- **THEN** runner reports all failures and exits with a non-zero exit code

### Requirement: Runner supports both output patterns
The runner SHALL support jobs where each task writes its own output (fire-and-forget) and jobs where the runner collects results via `ray.get()` for bulk output.

#### Scenario: Task-writes-own-output job
- **WHEN** a job function writes its results directly (e.g. to Delta Lake) and returns None or a status
- **THEN** runner invokes tasks and monitors for failures without collecting return values for output

#### Scenario: Runner-collects-results job
- **WHEN** a job function returns data to the caller
- **THEN** runner collects results via `ray.get()` and makes them available for bulk output (e.g. writing a single file)
