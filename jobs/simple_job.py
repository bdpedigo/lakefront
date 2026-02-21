#!/usr/bin/env python
"""
Simple Ray job for testing distributed computation.

This job demonstrates basic Ray functionality:
- Remote task execution
- Distributed computation
- Result aggregation

This is a standalone script that can be:
- Run locally: `python jobs/simple_job.py`
- Submitted to Ray cluster: `ray job submit -- python jobs/simple_job.py`
"""

import time

import numpy as np
import ray


@ray.remote
def compute_sum_of_squares(start: int, end: int) -> float:
    """Compute sum of squares for a range of numbers.

    This is a simple task to demonstrate Ray's distributed execution.
    In production, this would be replaced with real workloads like
    data processing, machine learning, etc.
    """
    time.sleep(0.5)  # Simulate some computation
    result = sum(i**2 for i in range(start, end))
    return result


@ray.remote
def process_array(arr: np.ndarray) -> dict:
    """Process a numpy array and return statistics.

    Demonstrates passing data to remote tasks.
    """
    time.sleep(0.3)
    return {
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "sum": float(np.sum(arr)),
        "size": len(arr),
    }


def main():
    """Main entry point for the Ray job."""
    print("=" * 60)
    print("Starting Simple Ray Job")
    print("=" * 60)

    # Initialize Ray (will connect to existing cluster if available)
    if not ray.is_initialized():
        ray.init(address="auto", ignore_reinit_error=True)

    print("\nRay Cluster Resources:")
    print(f"  Available CPUs: {ray.available_resources().get('CPU', 0)}")
    print(
        f"  Available Memory: {ray.available_resources().get('memory', 0) / (1024**3):.2f} GB"
    )
    print(f"  Nodes: {len(ray.nodes())}")

    # Test 1: Distributed sum of squares
    print("\n" + "-" * 60)
    print("Test 1: Distributed Sum of Squares")
    print("-" * 60)

    num_tasks = 10
    chunk_size = 10000

    start_time = time.time()

    # Submit tasks
    futures = []
    for i in range(num_tasks):
        start = i * chunk_size
        end = (i + 1) * chunk_size
        future = compute_sum_of_squares.remote(start, end)
        futures.append(future)

    # Gather results
    results = ray.get(futures)
    total = sum(results)

    elapsed = time.time() - start_time

    print(f"Completed {num_tasks} tasks in {elapsed:.2f}s")
    print(f"Total sum of squares (0 to {num_tasks * chunk_size}): {total}")

    # Test 2: Process multiple arrays
    print("\n" + "-" * 60)
    print("Test 2: Array Processing")
    print("-" * 60)

    num_arrays = 5
    arrays = [np.random.randn(1000) for _ in range(num_arrays)]

    start_time = time.time()

    # Submit array processing tasks
    futures = [process_array.remote(arr) for arr in arrays]
    stats = ray.get(futures)

    elapsed = time.time() - start_time

    print(f"Processed {num_arrays} arrays in {elapsed:.2f}s")
    for i, stat in enumerate(stats):
        print(f"  Array {i}: mean={stat['mean']:.3f}, std={stat['std']:.3f}")

    print("\n" + "=" * 60)
    print("Ray Job Completed Successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
