"""YAML-driven Ray job runner.

Loads a config specifying (job, insertion, optional setup), resolves dotted paths
to callables, and fans work out over Ray tasks.

Usage: uv run python runner.py configs/simple.yaml
"""

import importlib
import sys
from pathlib import Path

import ray
import yaml


def resolve_callable(dotted_path: str):
    """Resolve a dotted path like 'jobs.square.process' to a Python callable."""
    parts = dotted_path.rsplit(".", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid dotted path: {dotted_path!r} (expected 'module.attr')"
        )
    module_path, attr_name = parts
    module = importlib.import_module(module_path)
    obj = getattr(module, attr_name)
    return obj


def load_config(config_path: str) -> dict:
    """Load and validate a YAML config file."""
    with open(config_path) as f:
        config = yaml.safe_load(f)
    if "job" not in config:
        raise ValueError(f"Config missing required 'job' field: {config_path}")
    if "insertion" not in config:
        raise ValueError(f"Config missing required 'insertion' field: {config_path}")
    return config


def run(config_path: str) -> int:
    """Execute a job config. Returns exit code (0=success, 1=failures occurred)."""
    config = load_config(config_path)

    # Resolve callables
    job_fn = resolve_callable(config["job"])
    insertion_fn = resolve_callable(config["insertion"])
    setup_fn = resolve_callable(config["setup"]) if "setup" in config else None

    # Initialize Ray (auto-init locally, connects to existing cluster if available)
    if not ray.is_initialized():
        ray.init()

    # Get work items
    items = insertion_fn()
    n_tasks = len(items)
    print(f"Submitted {n_tasks} tasks")

    # Run optional setup phase
    setup_kwargs = {}
    if setup_fn is not None:
        print("Running setup phase...")
        setup_kwargs = setup_fn()

    # Apply resource overrides if specified
    task_fn = job_fn
    if "resources" in config:
        task_fn = job_fn.options(**config["resources"])

    # Fan out: submit all tasks
    refs = []
    item_map = {}  # ObjectRef -> item (for error reporting)
    for item in items:
        ref = task_fn.remote(item, **setup_kwargs)
        refs.append(ref)
        item_map[ref] = item

    # Collect results, continuing on failure
    successes = []
    failures = []
    for ref in refs:
        try:
            result = ray.get(ref)
            successes.append(result)
        except Exception as e:
            failures.append({"item": item_map[ref], "error": str(e)})

    # Report results
    n_success = len(successes)
    n_fail = len(failures)
    print(f"Completed {n_success}/{n_tasks}... {n_fail} failures")

    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  item={f['item']}: {f['error']}")
        return 1

    return 0


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <config.yaml>", file=sys.stderr)
        sys.exit(1)

    config_path = sys.argv[1]
    if not Path(config_path).exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    exit_code = run(config_path)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
