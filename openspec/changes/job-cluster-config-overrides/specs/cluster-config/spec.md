## MODIFIED Requirements

### Requirement: Cluster launch script creates both node pools
The launch script SHALL create an on-demand node pool for the head and a spot node pool for workers, then deploy the RayCluster resource. Machine types for head and worker pools SHALL be configurable via `HEAD_MACHINE_TYPE` and `WORKER_MACHINE_TYPE` environment variables, with defaults of `e2-standard-4` and `e2-highmem-16` respectively.

#### Scenario: Fresh cluster creation
- **WHEN** `scripts/launch_cluster.sh` is run
- **THEN** it creates a GKE cluster with an on-demand pool and a spot pool, installs the KubeRay operator, creates secrets, and deploys the RayCluster

#### Scenario: Custom machine types via environment
- **WHEN** `HEAD_MACHINE_TYPE=e2-standard-8 WORKER_MACHINE_TYPE=e2-highmem-32 scripts/launch_cluster.sh` is run
- **THEN** the head node pool uses `e2-standard-8` and the worker node pool uses `e2-highmem-32`
