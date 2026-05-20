## ADDED Requirements

### Requirement: Insertion is a zero-argument callable returning a list
An insertion SHALL be a Python function that takes no arguments and returns a `list[Any]` of work items.

#### Scenario: Insertion returns segment IDs
- **WHEN** an insertion function queries a database and returns `[101, 102, 103, ...]`
- **THEN** the runner receives that list and creates one Ray task per item

#### Scenario: Insertion returns file paths
- **WHEN** an insertion function lists a cloud storage directory and returns `["gs://bucket/a.csv", "gs://bucket/b.csv"]`
- **THEN** the runner creates one Ray task per file path

### Requirement: Retry insertion derives work from completed state
An insertion for retrying failed work SHALL query the output destination to determine what has been completed and return only the remaining items.

#### Scenario: Retry after partial completion
- **WHEN** an insertion queries a Delta Lake table and finds 800 of 1000 expected rows
- **THEN** it returns the 200 missing item identifiers

### Requirement: Insertions are standalone and reusable
An insertion function SHALL have no dependency on any specific job. Different jobs MAY use the same insertion.

#### Scenario: Same insertion, different jobs
- **WHEN** `insertions.all_segments.get_items` is referenced by both `configs/segclr.yaml` and `configs/mesh_transform.yaml`
- **THEN** both jobs receive the same list of segment IDs and process them independently
