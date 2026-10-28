"""Historical selector boundaries for measured unrelated recordings.

Measured first difference: fixture row 6, turn 4168107, 14 used / 9 free;
Home is full. The new optional surplus is slot d, Curing potion, whose Magic
sale precedes the recorded General-store trip. This recording tests the
carried/worn anti-teleport distinction, not town surplus priority.

Home address replay: first difference from main is decision 15, turn 5550915,
18 used / 5 free. Slot b, four Heroism potions, is now shelved before the
recorded supplier trip. The later shovel-address confirmation owns that pin.

Only the newly widened preservable predicate gets its previous four-slot
boundary. Keep the current item reservation, budget, route, sale, recall and
hazard authorities. Do not apply to headroom or overflow pins.
"""
from contextlib import contextmanager
from functools import wraps
from unittest.mock import patch

from hengbot.policy_constants import PACK_CAPACITY, MIN_TERMINAL_FREE_PACK_SLOTS
from hengbot import town_pack_headroom


@contextmanager
def pre_pack_headroom_rule():
    original = town_pack_headroom.preservable

    def historical(policy, board, item):
        return (PACK_CAPACITY - len(board.inventory) < MIN_TERMINAL_FREE_PACK_SLOTS
                and original(policy, board, item))

    with patch.object(town_pack_headroom, "preservable", historical):
        yield


def pre_pack_headroom_class(cls):
    """Keep a shared historical prefix and its hazard controls together."""
    original = cls.__dict__["setUpClass"].__func__

    def set_up_class(klass):
        wall = pre_pack_headroom_rule()
        wall.__enter__()
        klass.addClassCleanup(wall.__exit__, None, None, None)
        original(klass)

    cls.setUpClass = classmethod(set_up_class)
    return cls


def pre_pack_headroom_replay(function):
    """Limit the historical boundary to one measured replay helper."""
    @wraps(function)
    def replay(*args, **kwargs):
        with pre_pack_headroom_rule():
            return function(*args, **kwargs)
    return replay
