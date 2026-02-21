#!/usr/bin/env python
"""
Local runner for testing Ray jobs without Kubernetes.

This script initializes a local Ray cluster and runs the simple_job.
Use this for development and testing before deploying to KubeRay.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import ray


def main():
    parser = argparse.ArgumentParser(description="Run Ray job locally for testing")
    parser.add_argument(
        "--num-cpus",
        type=int,
        default=None,
        help="Number of CPUs to allocate to local Ray cluster (default: all available)",
    )
    parser.add_argument(
        "--memory",
        type=int,
        default=None,
        help="Memory in GB to allocate to local Ray cluster (default: all available)",
    )
    parser.add_argument(
        "--job",
        type=str,
        default="jobs/simple_job.py",
        help="Path to the Ray job script to run (default: jobs/simple_job.py)",
    )
    args = parser.parse_args()

    print("Initializing local Ray cluster...")

    # Initialize Ray locally
    init_kwargs = {"ignore_reinit_error": True}

    if args.num_cpus is not None:
        init_kwargs["num_cpus"] = args.num_cpus

    if args.memory is not None:
        init_kwargs["object_store_memory"] = args.memory * 1024 * 1024 * 1024

    context = ray.init(**init_kwargs)

    print("Ray cluster started:")
    if hasattr(context, "dashboard_url") and context.dashboard_url:
        print(f"  Dashboard URL: {context.dashboard_url}")
    print(f"  Available CPUs: {ray.available_resources().get('CPU', 0)}")
    print(
        f"  Available Memory: {ray.available_resources().get('memory', 0) / (1024**3):.2f} GB"
    )
    print()

    # Run the job script
    try:
        job_path = Path(args.job)
        if not job_path.exists():
            print(f"Error: Job script not found: {job_path}", file=sys.stderr)
            return 1

        print(f"Running job: {job_path}")
        print("-" * 60)

        # Execute the job script as a subprocess
        result = subprocess.run(["python", str(job_path)], check=True, cwd=Path.cwd())
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"\nJob failed with exit code {e.returncode}", file=sys.stderr)
        return e.returncode
    except Exception as e:
        print(f"\nError running job: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1
    finally:
        ray.shutdown()


if __name__ == "__main__":
    sys.exit(main())
