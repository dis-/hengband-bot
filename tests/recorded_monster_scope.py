"""Keep older recorded replays on the monsters their recording saw.

6cce55f61a (n1-c life-085) keeps a monster in view whose cell the grid map does
not export.  A replay recorded before it now sees monsters the recorded decisions
did not, answers them (an emergency teleport from a sleeping summoner, a detour to
fight) and leaves the recorded path, after which its boards no longer follow from
its keys.  Declared wall, for the prefix of replays whose subject is not that
parser rule: the boards parse as they did when recorded.  The rule itself is pinned
by tests/test_n1c_deaths_1101_recorded.py.
"""

from contextlib import contextmanager
from functools import wraps
from unittest.mock import patch

from hengbot import model


@contextmanager
def pre_exported_position_rule():
    """Place visible monsters through the grid map only."""
    with patch.object(model, "_exported_position", lambda _monster_data: None):
        yield


def pre_exported_position_replay(replay):
    """Run ``replay`` under ``pre_exported_position_rule``."""
    @wraps(replay)
    def wrapped(*args, **kwargs):
        with pre_exported_position_rule():
            return replay(*args, **kwargs)

    return wrapped
