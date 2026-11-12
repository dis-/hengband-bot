"""The plan-above-survival layer of the dungeon ladder (dungeon_ladder.LADDER, layer
"plan-above-survival").

``HengbotPolicy._decide`` asks this layer where its rows stand: below the global map
(ladder_global_map), above the emergency ladder and every layer below.  Each plan answers
survival and the summons inside itself (dungeon_ladder.FLOOR_PLANS).  The plans are asked
top-down and the first key returned wins, as in ``_decide``; ``PASS`` hands the decision on to
the layers below.  scripts/dungeon_ladder_lint.py reads the rows here
(dungeon_ladder.LAYER_MODULES), so the table still states this order.
"""
from __future__ import annotations

from hengbot import quest25_battle, quest_find_exit, quest_room_sweep
from hengbot.dungeon_ladder import PASS


def key(policy, snapshot):
    """The plan-above-survival layer's answer, or PASS when none of its rungs acts."""
    # A FIND_EXIT plan fights at its chokes: the ladders below walk away from them.
    find_exit = policy._town_producer_entry(
        "quest_find_exit.key", lambda: quest_find_exit.key(policy, snapshot), family="quest-request")
    if find_exit is not None:
        return find_exit
    # Q25's revised plan, phase by phase (it answers survival and the summons itself).
    phase_battle = policy._town_producer_entry(
        "quest25_battle.key", lambda: quest25_battle.key(policy, snapshot), family="quest-request")
    if phase_battle is not None:
        return phase_battle
    room_sweep = policy._town_producer_entry(
        "quest_room_sweep.key", lambda: quest_room_sweep.key(policy, snapshot), family="quest-request")
    if room_sweep is not None:
        return room_sweep
    return PASS
