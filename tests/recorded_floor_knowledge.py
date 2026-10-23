"""Keep recorded dungeon replays on the frontier of their recorded boards.

Two declared walls; production exploration and the #101 pins remain untouched.

``pre_seen_floor_rule`` / ``pre_seen_floor_replay``: replays whose subject is
not which floor counts as explored and that were recorded before 2026-10-23
walked to floor the player had already seen in its own light, because the bot
then counted only CAVE_MARK cells as explored.  The owner decision 2026-10-23
「探索済みとする」 (#101) made ``_build_grid_index`` remember every cell shown
inside the board's light radius as explored, so such a replay picks another
frontier than the one its later recorded boards confirm.  This wall hides only
the light radius from ``_build_grid_index`` (the one reader of it there), so
the replay keeps the old marks.  Replays whose subject IS the explored floor
pin the new divergence instead (test_floor_dwell_seen_floor_recorded).

``pre_remains_pile_rule`` / ``pre_remains_pile_replay``: replays recorded
before 2026-10-23 walked to (and picked up) floor piles of only corpses or
skeletons of monsters (tval 10), in case one was a bounty.  The owner decision
2026-10-23 「自動拾いを活用して判別すること」 (#101) leaves that to the game's
auto-pickup, so ``_floor_pile_is_worthless`` now also counts a pile of only
tval 10 as worthless.  This wall restores the old set {1, 3} for a replay
whose subject is not that pile.  Replays whose subject IS the pile pin the new
divergence instead (test_floor_dwell_seen_floor_recorded).
"""

from contextlib import contextmanager
from dataclasses import replace
from functools import wraps
from unittest.mock import patch

from hengbot.policy import HengbotPolicy

_build_grid_index = HengbotPolicy._build_grid_index


def _pre_seen_floor_build_grid_index(policy, snapshot):
    return _build_grid_index(policy, replace(snapshot, light_radius=None))


@contextmanager
def pre_seen_floor_rule():
    """Mark only CAVE_MARK cells as explored, as before 2026-10-23."""
    with patch.object(HengbotPolicy, "_build_grid_index",
                      _pre_seen_floor_build_grid_index):
        yield


def _pre_remains_pile_is_worthless(grid) -> bool:
    return bool(grid.object_tvals) and all(
        tval in {1, 3} for tval in grid.object_tvals)


@contextmanager
def pre_remains_pile_rule():
    """Keep piles of only remains (tval 10) as loot, as before 2026-10-23."""
    with patch.object(HengbotPolicy, "_floor_pile_is_worthless",
                      staticmethod(_pre_remains_pile_is_worthless)):
        yield


def pre_remains_pile_replay(replay):
    """Run ``replay`` under ``pre_remains_pile_rule``."""
    @wraps(replay)
    def wrapped(*args, **kwargs):
        with pre_remains_pile_rule():
            return replay(*args, **kwargs)

    return wrapped


def pre_seen_floor_replay(replay):
    """Run ``replay`` under ``pre_seen_floor_rule``."""
    @wraps(replay)
    def wrapped(*args, **kwargs):
        with pre_seen_floor_rule():
            return replay(*args, **kwargs)

    return wrapped
