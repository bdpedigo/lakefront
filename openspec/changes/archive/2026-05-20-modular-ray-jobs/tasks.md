## Principles

- **Test locally immediately** — every feature gets a local test before moving on. No deferred testing.
- **Justfile is the interface** — all operations (run, test, cluster up/down, submit) are `just <command>`. If it's not in the justfile, it doesn't exist for the user.
- **Incremental verification** — each section ends with a "Test" step that uses justfile commands. Instructions state exactly what the user should see.

---

## 0. Justfile Scaffold

- [x] 0.1 Create `justfile` with initial commands: `just run <config>`, `just test-simple`, `just test-setup`, `just test-failure`
- [x] 0.2 Add cluster commands: `just cluster-up-local`, `just cluster-down-local`, `just submit <config>`
- [x] 0.3 Add utility commands: `just build-image`, `just dashboard`

## 1. Runner Core + First Local Test

- [x] 1.1 Create YAML config schema (job, insertion, optional setup, optional resource overrides)
- [x] 1.2 Create runner module that loads YAML, resolves dotted paths to callables
- [x] 1.3 Implement fan-out execution: call insertion, submit Ray tasks, collect results or monitor
- [x] 1.4 Add Ray environment detection (local auto-init vs cluster connect)
- [x] 1.5 **Test: `just run configs/simple.yaml`** — verify fan-out, results printed, exit 0
  - _Expect_: "Submitted N tasks… Completed N/N… 0 failures"

- [x] 1.6 Implement setup phase: call setup(), pass ObjectRefs to tasks as kwargs
- [x] 1.7 **Test: `just run configs/setup_example.yaml`** — verify shared state is passed
  - _Expect_: Each task prints that it received the shared ref; results collected

- [x] 1.8 Implement error handling: continue on task failure, collect and report failures at end
- [x] 1.9 **Test: `just run configs/failure_test.yaml`** — verify continue-on-failure
  - _Expect_: "Completed 7/10… 3 failures:" followed by item IDs and error messages, exit 1

## 2. Job Authoring

- [x] 2.1 Create `jobs/square.py` — simple @ray.remote job: takes an int, returns int**2
- [x] 2.2 Create `jobs/with_setup.py` — job with setup phase (shared lookup table via ray.put)
- [x] 2.3 Create `jobs/flaky.py` — job that fails on certain items (for failure testing)

## 3. Insertion Authoring

- [x] 3.1 Create `insertions/range_items.py` — returns `list(range(N))` for testing
- [x] 3.2 Create `insertions/flaky_items.py` — returns items where some are designed to trigger failures

## 4. YAML Configs

- [x] 4.1 `configs/simple.yaml` — wires `jobs.square.process` + `insertions.range_items.get_items`
- [x] 4.2 `configs/setup_example.yaml` — wires `jobs.with_setup.process` + setup + insertion
- [x] 4.3 `configs/failure_test.yaml` — wires `jobs.flaky.process` + `insertions.flaky_items.get_items`

## 5. Local Kind Cluster Testing

- [x] 5.1 `just cluster-up-local` — start kind cluster, load Docker image, deploy RayCluster
- [x] 5.2 `just submit configs/simple.yaml` — submit job via `ray job submit` to local cluster
  - _Expect_: Same output as local run, but executed on kind cluster
- [x] 5.3 `just dashboard` — port-forward Ray dashboard, open browser
- [x] 5.4 `just cluster-down-local` — clean teardown

## 6. Cluster Config (GKE / Remote)

- [x] 6.1 Update `k8s/ray-cluster.yaml` with nodeSelector for on-demand head and spot workers
- [x] 6.2 Enable autoscaling (minReplicas: 0, maxReplicas configurable) on worker group
- [x] 6.3 Update `scripts/launch_cluster.sh` to create on-demand + spot node pools
- [x] 6.4 `just cluster-up` / `just cluster-down` for remote cluster
- [x] 6.5 **Test: `just submit configs/simple.yaml`** on remote cluster — verify same behavior as local

---

## Test Instructions (for user — production verification)

Local tests (`just run`, `just test-*`) are run during implementation and verified before moving on. The commands below are the **production path** that requires your GKE cluster and credentials:

| Step | Command | Expected |
|------|---------|----------|
| 1. Build + push image | `just build-image && just push-image` | Image in your container registry |
| 2. Bring up cluster | `just cluster-up` | GKE cluster with on-demand head pool + spot worker pool, KubeRay operator installed, RayCluster deployed |
| 3. Verify cluster | `just dashboard` | Ray dashboard opens in browser, shows head node + 0 workers (autoscaled down) |
| 4. Submit simple job | `just submit configs/simple.yaml` | Workers autoscale up, 10 tasks fan out, all succeed, workers scale back to 0 |
| 5. Submit setup job | `just submit configs/setup_example.yaml` | Setup phase runs on head, shared state distributed, tasks use it |
| 6. Submit failure job | `just submit configs/failure_test.yaml` | 7/10 succeed, 3 failures reported, cluster stays healthy |
| 7. Tear down | `just cluster-down` | GKE cluster and node pools deleted, no lingering resources |
