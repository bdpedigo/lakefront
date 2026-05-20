## Why

The current project scatters related artifacts across three top-level directories (`jobs/`, `configs/`, `insertions/`). Adding a new unit of work requires touching multiple locations and keeping dotted-path references in sync. Colocating everything into a single folder per job makes the repo easier to navigate and reduces coupling errors.

## What Changes

- Each job becomes a self-contained folder under `jobs/` containing:
  - `__init__.py` (exports)
  - One or more Python files with Ray job definitions and insertion functions
  - A `config.yaml` describing how the runner wires the job together
- Merge what was in `insertions/test/` into the corresponding `jobs/test_*` folders
- Remove the top-level `configs/` and `insertions/` directories
- Update `runner.py` to resolve the new layout (config path points into `jobs/<name>/config.yaml`)

## Capabilities

### New Capabilities
- `job-folder-layout`: Convention for self-contained job folders (structure, naming, discovery)

### Modified Capabilities
- `job-runner`: Config resolution changes to look inside job folders instead of a separate `configs/` tree
- `job-authoring`: Insertions now live alongside the job code rather than in a separate package

## Impact

- `jobs/`, `configs/`, `insertions/` directories restructured
- `runner.py` config-loading logic updated
- Any scripts or docs referencing old paths (e.g., `just submit test/simple`) need path updates
- No dependency or API changes
