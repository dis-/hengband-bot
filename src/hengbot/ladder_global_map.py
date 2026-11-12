"""The global-map layer of the dungeon ladder (dungeon_ladder.LADDER, layer "global-map").

``HengbotPolicy._decide`` asks this layer first, before every other layer: on the global
wilderness map it ends the decision (the Zul trip's walk, else the global map's own survival
rung, whose answer may be None); off it, ``PASS`` hands the decision on to the layers below.
scripts/dungeon_ladder_lint.py reads the rows here (dungeon_ladder.LAYER_MODULES), so the table
still states this order.
"""
from __future__ import annotations

from hengbot import zul_trip
from hengbot.dungeon_ladder import PASS


def key(policy, snapshot, *, physical_hostiles):
    """The global-map layer's answer, or PASS when none of its rungs acts."""
    # The global map is a distinct command space.  Town/store owners can
    # retain durable work while crossing it, but their travel, shopping,
    # repetition, and fundraising commands are not valid here.  Route or
    # enter the town before allowing any of those owners to select again.
    if policy._on_global_wilderness_map(snapshot):
        # Owner 2026-11-07: the Zul trip is the one exception to the
        # never-the-wilderness rule, and only while it is under way.
        zul = zul_trip.global_key(policy, snapshot)
        if zul is not None:
            return zul
        return policy._town_producer_entry("_wilderness_survival_key", lambda: policy._wilderness_survival_key(snapshot, physical_hostiles), family="survival")
    return PASS
