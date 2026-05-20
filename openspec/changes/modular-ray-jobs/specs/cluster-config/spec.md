## ADDED Requirements

### Requirement: KubeRay cluster uses on-demand head node
The RayCluster spec SHALL pin the head pod to a non-preemptible node pool using `nodeSelector`.

#### Scenario: Head node survives spot reclamation
- **WHEN** the cloud provider reclaims spot instances
- **THEN** the head pod remains running on its on-demand node and GCS state is preserved

### Requirement: KubeRay cluster uses spot workers
The RayCluster spec SHALL pin worker pods to a spot/preemptible node pool using `nodeSelector` and `tolerations`.

#### Scenario: Workers scheduled on spot nodes
- **WHEN** worker pods are created
- **THEN** they are scheduled exclusively on spot/preemptible nodes

### Requirement: Worker pool autoscales based on task demand
The RayCluster spec SHALL enable autoscaling with `minReplicas: 0` so that workers scale down to zero when idle and scale up when tasks are pending.

#### Scenario: Scale up on job submission
- **WHEN** a job submits 100 tasks requiring 4 CPUs each
- **THEN** KubeRay autoscaler adds worker pods until demand is met (or maxReplicas reached)

#### Scenario: Scale down after job completion
- **WHEN** all tasks complete and no new work is pending
- **THEN** worker pods scale back down to 0

### Requirement: Cluster launch script creates both node pools
The launch script SHALL create an on-demand node pool for the head and a spot node pool for workers, then deploy the RayCluster resource.

#### Scenario: Fresh cluster creation
- **WHEN** `scripts/launch_cluster.sh` is run
- **THEN** it creates a GKE cluster with an on-demand pool and a spot pool, installs the KubeRay operator, creates secrets, and deploys the RayCluster
