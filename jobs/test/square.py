import ray


@ray.remote
def process(item):
    """Simple job: returns item squared."""
    return item**2
