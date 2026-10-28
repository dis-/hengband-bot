"""Declared wall for recordings whose subject predates the town slot budget.

Only use on measured pre-budget transfers/uses that really need a new slot
below the four-slot reserve and whose subject is another owner's protocol.
Do not use for stacking mistakes or for tests of capacity/overflow itself.
Production budget and the recorded expected keys remain unchanged.
"""
from contextlib import contextmanager
from functools import wraps
from unittest.mock import patch


@contextmanager
def pre_pack_budget_rule():
    """Remove only the 2026-10-28 reserve, including its relief selectors."""
    with patch('hengbot.town_pack_budget.MIN_TERMINAL_FREE_PACK_SLOTS', 0):
        yield


def pre_pack_budget_replay(function):
    """A method-scoped wall; cleanup also runs when an assertion fails."""
    @wraps(function)
    def replay(*args, **kwargs):
        with pre_pack_budget_rule():
            return function(*args, **kwargs)
    return replay
