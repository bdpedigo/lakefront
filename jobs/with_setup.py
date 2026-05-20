import ray


def setup():
    """Load a shared lookup table into the object store."""
    lookup = {i: i * 10 for i in range(100)}
    return {"lookup_ref": ray.put(lookup)}


@ray.remote
def process(item, lookup_ref=None):
    """Job that uses shared state from setup phase.

    Note: Ray auto-dereferences ObjectRefs passed as arguments,
    so lookup_ref is the actual dict, not an ObjectRef.
    """
    lookup = lookup_ref if lookup_ref else {}
    return {"item": item, "looked_up": lookup.get(item, None)}
