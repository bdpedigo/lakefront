## 1. Runner Core

- [ ] 1.1 Create YAML config schema (job, insertion, optional setup, optional resource overrides)
- [ ] 1.2 Create runner module that loads YAML, resolves dotted paths to callables
- [ ] 1.3 Implement fan-out execution: call insertion, submit Ray tasks, collect results or monitor
- [ ] 1.4 Implement setup phase: call setup(), pass ObjectRefs to tasks as kwargs
- [ ] 1.5 Implement error handling: continue on task failure, collect and report failures at end
- [ ] 1.6 Add Ray environment detection (local auto-init vs cluster connect)

## 2. Job Authoring

- [ ] 2.1 Convert existing `jobs/simple_job.py` to follow the new convention (@ray.remote with resources, single-item function signature)
- [ ] 2.2 Create an example job with a setup phase (shared state via ray.put)

## 3. Insertion Authoring

- [ ] 3.1 Create `insertions/` directory with an example insertion function (e.g. range-based for testing)
- [ ] 3.2 Create an example "retry" insertion that diffs expected vs completed items

## 4. YAML Configs

- [ ] 4.1 Create example config for the simple job
- [ ] 4.2 Create example config for the setup-phase job

## 5. Local Testing

- [ ] 5.1 Run simple job via runner locally, verify fan-out and result reporting
- [ ] 5.2 Run setup-phase job via runner locally, verify shared state passing
- [ ] 5.3 Test partial failure scenario (some tasks intentionally fail), verify continue-on-failure

## 6. Cluster Config

- [ ] 6.1 Update `k8s/ray-cluster.yaml` with nodeSelector for on-demand head and spot workers
- [ ] 6.2 Enable autoscaling (minReplicas: 0, maxReplicas configurable) on worker group
- [ ] 6.3 Update `scripts/launch_cluster.sh` to create on-demand + spot node pools
- [ ] 6.4 Test runner via `ray job submit` on local kind cluster
