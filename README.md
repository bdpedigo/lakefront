# Lakefront - Ray Job Controller

Messing around with Ray and KubeRay for connectomics workflows.

## Commands 

To build and push the Docker image:

```bash
./scripts/build_and_push.sh
```

To start a Ray cluster on GKE:

```bash
./scripts/launch_cluster.sh
```

To sync local files in scratch to the Ray head node (say, if iterating on scripts):

```bash
./scripts/sync_scratch.sh
```

To SSH into the Ray head node:

```bash
./scripts/ssh_cluster.sh
```

To SSH into the Ray head node and immediately run another script:

```bash
./scripts/ssh_cluster.sh -- ./scripts/job.sh
```

To launch Jupyter Lab on the Ray head node and connect to it from your local machine:

```bash
./scripts/jupyter_connect.sh
```
