## MODIFIED Requirements

### Requirement: Config resolution accepts paths inside job folders
The runner SHALL accept config file paths that point into job folders (e.g., `jobs/test_simple/config.yaml`) in addition to any legacy path format.

#### Scenario: Runner invoked with job-folder config path
- **WHEN** the runner is called with `python runner.py jobs/test_simple/config.yaml`
- **THEN** it SHALL load and execute the config from that path

#### Scenario: Justfile shorthand resolves to job folder
- **WHEN** a user runs `just run test_simple`
- **THEN** the justfile SHALL expand this to `python runner.py jobs/test_simple/config.yaml`
