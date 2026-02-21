# Lakefront - Ray Job Controller

A project for managing Ray workloads with UV package management.

## Quick Start

### 1. Install dependencies

```bash
uv sync
```

### 2. Run locally

```bash
# Activate the virtual environment
source .venv/bin/activate

# Run the controller script
python scripts/ray_controller.py
```

This will:
- Start a local Ray cluster on your machine
- Submit an example batch processing job
- Display results and shut down

### 3. Monitor (optional)

Ray starts a dashboard at `http://127.0.0.1:8265` where you can monitor:
- Active tasks
- Resource utilization
- Job history

## Project Structure

- `scripts/ray_controller.py` - Main controller that runs on your laptop
- `scripts/example_ray_task.py` - Example Ray workload to execute

## Next Steps

### Phase 2: Configuration
- Add CLI arguments to choose local vs remote mode
- Configuration file for cluster settings

### Phase 3: KubeRay Integration
- Connect to remote KubeRay cluster
- Submit jobs using Ray Jobs API
- Cloud deployment

## Development

Replace the example task in `example_ray_task.py` with your actual workload:
- Data processing with Polars/Pandas
- Scientific computing with SciPy/Scikit-learn
- Any parallel computation
