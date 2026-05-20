## Context

We have a Ray-based infrastructure (local dev + KubeRay for production) and a growing set of data processing jobs. Currently `jobs/simple_job.py` is a monolithic script. We need a composable pattern where job logic, work item selection, and resource requirements are decoupled so that new jobs are just a function + a YAML config.

Nothing in the current repo implementation is fixed. Existing scripts, YAMLs, and job code can be replaced, restructured, or deleted as needed. This is a greenfield redesign of the job system.

## Goals / Non-Goals

**Goals:**
- Job authors write a Python function with `@ray.remote` resource declarations and an optional `setup()` — that's it
- Work item sources ("insertions") are standalone functions returning a list, swappable at deploy time
- A YAML config file wires `(job, insertion)` together; a runner loads the YAML and executes
- Support simple fan-out (map over items) and complex setup-then-fan-out (shared state via `ray.put`)
- KubeRay cluster uses on-demand head + spot workers; task resources drive autoscaling
- Failure recovery via idempotent writes + "diff expected vs completed" re-insertion

**Non-Goals:**
- DAG orchestration (multi-stage pipelines with dependencies between stages) — keep it single-stage fan-out for now
- External queue infrastructure (Redis, Celery, Kafka) — the output table is the tracker
- GUI/dashboard beyond Ray's built-in dashboard
- Multi-cluster federation

## Decisions

### 1. Resources declared on `@ray.remote`, not in YAML

**Decision**: Job functions declare their resource needs (CPU, memory, GPU) in the `@ray.remote` decorator. YAML can override via `.options()` for local testing, but defaults live with the code.

**Rationale**: The job author knows "this loads a 20GB mesh, it needs 32GB RAM." That knowledge belongs next to the code, not in a config file that drifts out of sync.

**Alternative**: Resources only in YAML. Rejected because it separates resource knowledge from the code that determines the requirement.

### 2. YAML config as the deployment unit

**Decision**: Each run is defined by a YAML file specifying `job` (Python dotted path) and `insertion` (Python dotted path). Optional fields: `setup`, resource overrides, Ray runtime env.

**Rationale**: YAML files are cheap to create, easy to version, and can be parameterized. A scientist can copy `configs/segclr_all.yaml`, change the insertion to `get_failed_segments`, and rerun without touching code.

**Alternative**: Pure Python composition (`execute(MyJob(), MyInsertion())`). Rejected for the common case because it requires editing code to change what runs, but remains available as the underlying mechanism.

### 3. Insertions as plain functions

**Decision**: An insertion is a callable `() -> list[Any]`. No base class, no protocol — just a function.

**Rationale**: Simplest possible interface. A function that queries a database and returns segment IDs, or reads a file and returns paths, or just returns `range(100)`. No framework lock-in.

The insertion is responsible for determining *what* work items to process, including retry logic. For retries, the insertion queries the output destination to determine what has been completed and returns only the remaining items. The runner has no knowledge of output format or completion state — that responsibility lives entirely in the insertion.

### 4. Setup phase for shared state

**Decision**: Jobs may define a `setup() -> dict[str, ray.ObjectRef]` function. The runner calls it before fan-out and passes the refs to each task invocation.

**Rationale**: Loading meshes/synapses once into Ray's object store and sharing via ObjectRef is zero-copy and efficient. Without this, each task would independently load shared data.

**Alternative**: Each task loads its own data. Rejected for large shared datasets (wasteful network/memory).

### 5. On-demand head + spot workers, dual lifecycle modes

**Decision**: KubeRay cluster uses a small non-preemptible node for the head pod and a spot/preemptible node pool for workers. Workers autoscale 0-N based on pending tasks (minReplicas: 0). Two cluster lifecycle modes are supported:

- **Mode A (primary)**: Persistent RayCluster with autoscaling workers. Head stays on, workers scale to zero when idle. Jobs are submitted to the existing cluster with no cold start. Tear down manually when done (`kubectl delete raycluster`).
- **Mode B**: Ephemeral via `RayJob` CRD. Everything (head + workers) spins up per job and tears down after. Zero cost between runs but 2-5 min cold start.

The runner and job code are identical in both modes — only the deployment mechanism differs.

**Rationale**: Mode A is the primary target for active development periods (frequent job submissions, low latency). Mode B handles long idle periods (months between jobs) where even a small head node cost is undesirable. `nodeSelector` and `tolerations` pin pods to correct pools in both modes.

### 6. "Output table is the job tracker" for durability

**Decision**: No external state store for tracking job progress. Jobs write results to a destination (Delta Lake table, cloud storage). Re-running = query for what's missing and reprocess.

**Rationale**: Zero additional infrastructure. The data lake is already durable. Insertion functions like `get_incomplete_segments()` naturally express retries.

**Alternative**: Redis-backed Ray GCS for head node HA. Deferred — adds ops complexity, can add later if head node failures become a problem.

### 7. Two-tier retry strategy using Ray's built-in fault tolerance

**Decision**: Use Ray's native retry mechanisms for transient failures within a run, and insertion-based diffing for permanent failures across runs.

- **Short-term (within a run)**: `max_retries` on `@ray.remote` handles worker crashes and spot preemption (default: 3 retries). `retry_exceptions` handles transient application errors (e.g., `[ConnectionError, TimeoutError]`). These are configured per-job on the decorator.
- **Long-term (across runs)**: Tasks that permanently fail after all retries are reported by the runner. To reprocess, re-run the job with an insertion that diffs expected vs completed items in the output table.

The YAML config does not configure retries — that's the job author's responsibility on the decorator, alongside resource declarations.

## Directory Layout

```
lakefront/
├── jobs/                         # Job functions (@ray.remote), flat or nested
│   ├── segclr_to_lake.py
│   └── complex_job/
│       ├── process.py
│       └── setup.py
├── insertions/                   # Item source functions (() -> list)
│   ├── all_segments.py
│   └── retry_segments.py
├── configs/                      # YAML run configs (the deployment unit)
│   ├── segclr_all.yaml
│   └── segclr_retry.yaml
├── runner.py                     # Single-file runner, invoked via uv
├── k8s/
│   └── ray-cluster.yaml
├── Dockerfile
├── justfile                      # Wraps all common operations
└── pyproject.toml
```

- `jobs/` supports both flat files and nested directories. Dotted paths in YAML resolve relative to `jobs/`.
- `runner.py` is a single Python file invoked via `uv run runner.py configs/<name>.yaml`.
- `justfile` wraps all operations: `just run segclr_all`, `just submit segclr_all`, `just cluster-up`, `just cluster-down`.

## Testing Philosophy

Every feature must be locally testable before moving on. The justfile is the single interface for all testing:

- **Local Ray** (`just run <config>`) — runs the runner on the laptop with Ray auto-init. Zero infrastructure.
- **Local kind cluster** (`just cluster-up-local`, `just submit <config>`) — tests the full container + KubeRay path without cloud costs.
- **Remote GKE** (`just cluster-up`, `just submit <config>`) — production path.

Each feature addition includes a corresponding test config and justfile command. The user should never need to remember a raw `uv run` or `kubectl` incantation — just the `just` commands.

### Justfile Commands (complete list)

| Command | Description |
|---------|-------------|
| `just run <config>` | Run a config locally (Ray auto-init) |
| `just test-simple` | Shorthand: run the simple fan-out test config |
| `just test-setup` | Shorthand: run the setup-phase test config |
| `just test-failure` | Shorthand: run the failure-handling test config |
| `just cluster-up-local` | Start kind cluster + deploy Ray |
| `just cluster-down-local` | Tear down local kind cluster |
| `just submit <config>` | Submit job to running cluster (local or remote) |
| `just dashboard` | Port-forward Ray dashboard |
| `just build-image` | Build Docker image |
| `just cluster-up` | Launch remote GKE cluster |
| `just cluster-down` | Tear down remote GKE cluster |

## Risks / Trade-offs

- **Head node failure loses in-flight state** → Mitigated by idempotent writes + re-insertion. Accept the risk for now; Redis GCS HA is a future option.
- **Spot preemption during long tasks** → Mitigated by `max_retries=3` on `@ray.remote`. Very long tasks (>1hr) may need checkpointing, which is out of scope.
- **YAML config proliferation** → Mitigated by keeping configs minimal (2-3 fields). Conventions over configuration.
- **No DAG support** → Acceptable for current workloads. If needed later, can compose multiple YAML runs sequentially or adopt a lightweight orchestrator.
