import ray


@ray.remote
def process(item):
    """Job that fails on items divisible by 3 (for failure testing)."""
    if item % 3 == 0:
        raise ValueError(f"Item {item} is divisible by 3")
    return item**2
