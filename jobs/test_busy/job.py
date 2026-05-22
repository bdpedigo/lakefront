import math
import time

import ray


DURATION_SECONDS = 60


@ray.remote
def process(item):
    """Keep a worker CPU busy long enough for dashboard profiling."""
    deadline = time.monotonic() + DURATION_SECONDS
    accumulator = float(item + 1)
    iterations = 0

    while time.monotonic() < deadline:
        accumulator = math.sin(accumulator) * math.cos(accumulator) + math.sqrt(
            accumulator + 1.0
        )
        iterations += 1

    return {
        "item": item,
        "duration_seconds": DURATION_SECONDS,
        "iterations": iterations,
        "accumulator": accumulator,
    }