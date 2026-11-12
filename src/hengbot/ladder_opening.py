"""The opening layer of the dungeon ladder (dungeon_ladder.LADDER, layer "opening").

``HengbotPolicy._decide`` asks this layer where its rows stand: below the light layer
(ladder_light), above the approved quest floor (ladder_plan_approved_quest).  The opening
route's Q34 town rung first; then, once the breakout dig is off this floor or has no route
left, the weapon the dig put away goes back.  The rungs are asked top-down and the first key
returned wins, as in ``_decide``; ``PASS`` hands the decision on to the layers below.
scripts/dungeon_ladder_lint.py reads the rows here (dungeon_ladder.LAYER_MODULES), so the table
still states this order.
"""
from __future__ import annotations

from hengbot import retreat_enclosure, walkout_dig
from hengbot.dungeon_ladder import PASS


def key(policy, snapshot, *, strategic_hostiles):
    """The opening layer's answer, or PASS when none of its rungs acts."""
    opening_q34 = policy._town_producer_entry("_opening_q34_town_key", lambda: policy._opening_q34_town_key(snapshot, strategic_hostiles), family="quest-request")
    if opening_q34 is not None:
        return opening_q34

    if (
        policy._breakout_dig_floor is not None
        and (
            snapshot.floor_key != policy._breakout_dig_floor
            or (
                policy._town_producer_entry("_dig_to_known_downstairs_key", lambda: policy._dig_to_known_downstairs_key(snapshot), family="departure") is None
                and not walkout_dig.has_route(policy, snapshot)
                and not retreat_enclosure.dig_has_route(policy, snapshot)
            )
        )
    ):
        restore = policy._town_producer_entry("_breakout_restore_weapon_key#1", lambda: policy._breakout_restore_weapon_key(snapshot))
        if restore is not None:
            return restore
    return PASS
