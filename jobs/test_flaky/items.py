def get_items():
    """Returns items where some are designed to trigger failures.

    Items divisible by 3 will cause the flaky job to fail.
    Out of 10 items (0-9): 0, 3, 6, 9 will fail = 4 failures, 6 successes.
    """
    return list(range(10))
