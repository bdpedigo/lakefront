- We are trying to create a deployment which uses Ray to run workloads on a remote cluster, but we want to start by running everything locally on our laptop for development and testing. This will allow us to iterate quickly without needing to set up a full remote cluster right away.
- We would like to target KubeRay for the remote cluster deployment.
- We have some specific authentication issues that need to be implemented to make this work in our stack.
- In the /old_examples folder there are example dockerfiles, cluster launch scripts, and kubernetes yaml files. These were for different workflows and did not use Ray. But we should use them as a starting point for configuring our Ray cluster and workloads.
- Always iterate slowly and test locally before moving to remote deployment. This will help us catch issues early and ensure our code works correctly in a simple environment before adding the complexity of remote execution.
- Propose changes to the user in small incremental steps; wait for feedback before proceeding to the next step. This will help ensure we are on the right track and allow for adjustments based on the user's needs and preferences. Explain reasoning behind each proposed change to help the user understand the benefits and trade-offs of different approaches.
- The user will ask questions about approach. This does not mean they are challenging the current design, but rather they want to understand the rationale behind it. Always provide clear explanations for why certain decisions were made and how they contribute to the overall goals of the project. Do not take questions as a direction to implement a different approach unless the user explicitly states that they want to change course.
- Be succinct. Unless prompted to expand on an idea.

## KubeRay Implementation Plan

**Goal**: Build a Ray application that can run locally for development and deploy to a KubeRay cluster for production workloads.

### Step 1: Local Ray Job ✅ COMPLETED
- Created a simple Ray job script (`jobs/simple_job.py`) that demonstrates basic Ray functionality
- Created a local test script (`scripts/run_local.py`) to run it without Kubernetes
- Verified Ray works correctly on local machine
- Established standalone script structure (no package required)

### Step 2: Docker Image with Authentication ✅ COMPLETED
- Built Dockerfile based on old_examples/Dockerfile pattern with uv for fast installs
- Included Ray and all dependencies from pyproject.toml
- Set up directory for authentication secret mounting (/root/.cloudvolume/secrets)
- Tested Docker image locally - job runs successfully in 0.81s (54x faster than venv creation)
- Created build and test scripts for easy local validation

### Step 3: KubeRay Cluster YAML ✅ COMPLETED
- Created RayCluster custom resource definition
- Configured head node and worker node specifications
- Set up secret mounting for authentication (similar to old kube-task.yml)
- Defined resource limits (CPU, memory, storage)
- Created Service for dashboard and client access

### Step 4: Cluster Launch Script ✅ COMPLETED
- Created script similar to make_cluster.sh but for KubeRay
- Handles GKE cluster creation
- Installs KubeRay operator
- Creates Kubernetes secrets
- Deploys RayCluster
- Added cleanup script for easy teardown

### Step 5: Local Testing ✅ COMPLETED
- Created test_local_k8s.sh script for testing with kind/minikube
- Handles local cluster creation and image loading
- Deploys Ray with reduced resources for local testing
- Sets up NodePort service for localhost access (dashboard on :8265)
- Runs test job to verify functionality
- Created cleanup script for easy teardown

### Step 6: Job Submission and Testing ✅ COMPLETED
- Created scripts to submit Ray jobs to the cluster (submit_job.sh)
- Created SSH/exec script for interactive access (ssh_cluster.sh)
- End-to-end workflow verified
- Complete workflow documented
