"""Deterministic board sampling for merge checks; daily runs leave env unset.

Only independent cases may be sampled. Ordered replays, population assertions
and coverage/partition controls must continue to use their complete inputs.
"""

import os


SAMPLE_ENV = "HENGBOT_TEST_SAMPLE"
SAMPLED_MODULES = ("tests.test_town_terminal_exit_round16",) + tuple(
    f"tests.test_town_producer_purity_part{part}" for part in range(1, 7)
)


def sample(items):
    """Keep indexes 0, N, 2N, ... and the last, in their original order.

    The default returns the original list object. Invalid configuration fails
    even for an empty input, rather than silently skipping verification.
    """
    raw = os.environ.get(SAMPLE_ENV, "1")
    try:
        stride = int(raw)
    except ValueError as error:
        raise ValueError(f"{SAMPLE_ENV} must be a positive integer: {raw!r}") from error
    if stride < 1:
        raise ValueError(f"{SAMPLE_ENV} must be a positive integer: {raw!r}")
    if stride == 1:
        return items
    selected = items[::stride]
    if items and (len(items) - 1) % stride:
        selected.append(items[-1])
    return selected
