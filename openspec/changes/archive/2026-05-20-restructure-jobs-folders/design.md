## Context

Currently the repo splits job-related artifacts across three directories:
- `jobs/` — Ray task functions and setup functions
- `insertions/` — Functions that produce work-item lists
- `configs/` — YAML files that wire a job + insertion + optional setup together

The runner resolves dotted Python paths from the YAML config (e.g., `jobs.test.square.process`). Adding a new job means touching all three directories and keeping the dotted paths consistent.

## Goals / Non-Goals

**Goals:**
- Colocate all artifacts for a unit of work into one folder under `jobs/`
- Make it trivial to add a new job: copy a folder, edit in-place
- Keep the runner's wiring logic (YAML → resolve → fan-out) unchanged in spirit

**Non-Goals:**
- Changing the Ray execution model (fan-out, setup phase, etc.)
- Adding new runner features (retries config, progress bars, etc.)
- Restructuring non-test jobs (segclr) in this change — only test jobs move first

## Decisions

### 1. Folder-per-job layout

Each job folder: `jobs/<name>/`
```
jobs/
  test_simple/
    __init__.py
    job.py          # @ray.remote process function
    items.py        # insertion function (get_items)
    config.yaml     # wiring config
  test_flaky/
    __init__.py
    job.py
    items.py
    config.yaml
  test_setup/
    __init__.py
    job.py
    items.py
    config.yaml
```

**Rationale**: A flat folder makes it immediately clear what belongs together. The `__init__.py` exports the key symbols for the runner.

**Alternative considered**: Keep `insertions/` separate but colocate configs into `jobs/`. Rejected because it still splits related code across two trees.

### 2. Config paths become `jobs/<name>/config.yaml`

The runner and justfile change from `configs/test/simple.yaml` to `jobs/test_simple/config.yaml`. The shorthand invocation becomes `just run test_simple`.

**Rationale**: Single source of truth per job folder. No mapping between config names and module paths.

### 3. Dotted paths in config update to new module locations

Config files use paths like `jobs.test_simple.job.process` and `jobs.test_simple.items.get_items`.

**Rationale**: Matches Python's import resolution for the new layout.

### 4. Remove top-level `configs/` and `insertions/` after migration

Once all jobs are moved, these directories are deleted.

## Risks / Trade-offs

- **[Path breakage]** → All dotted paths in configs must be updated atomically. Mitigation: do in one commit, run each config to verify.
- **[Import resolution]** → Runner must be invoked from repo root for module paths to work. This is already the case today.
- **[segclr not migrated]** → The `jobs/segclr/` folder already partially follows this pattern (has `__init__.py` + job code). It doesn't have a colocated config or insertion yet; that's a follow-up.
