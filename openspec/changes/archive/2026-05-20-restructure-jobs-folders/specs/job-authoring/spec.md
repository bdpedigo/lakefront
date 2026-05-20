## MODIFIED Requirements

### Requirement: Insertion functions live alongside job code
Insertion functions SHALL be defined in a module colocated within the job folder rather than in a separate top-level `insertions/` package.

#### Scenario: Insertion in job folder
- **WHEN** a job folder `jobs/test_simple/` contains `items.py` with `def get_items()`
- **THEN** the config SHALL reference it as `insertion: jobs.test_simple.items.get_items`

#### Scenario: No separate insertions directory
- **WHEN** all jobs have been migrated to the folder layout
- **THEN** the top-level `insertions/` directory SHALL be removed
