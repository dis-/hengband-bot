"""The summoner-shots layer of the dungeon ladder (dungeon_ladder.LADDER, layer "summoner-shots").

``HengbotPolicy._decide`` asks this layer where its rows stand: below the emergency ladder
(owner 2026-11-06 「命に関わる時の後へ回す」), above the floor avoidance
(ladder_floor_avoidance).  The rungs are asked top-down and the first key returned wins, as in
``_decide``; ``PASS`` hands the decision on to the layers below.  Neither rung is asked while
the quiet recall or a summons answer is due.  scripts/dungeon_ladder_lint.py reads the rows
here (dungeon_ladder.LAYER_MODULES), so the table still states this order.
"""
from __future__ import annotations

from hengbot import return_yield, summon_response, worsens_kill
from hengbot.dungeon_ladder import PASS


def key(policy, snapshot, *, emergency_hostiles):
    """The summoner-shots layer's answer, or PASS when none of its rungs acts."""
    # Threat tiers plan step 11 (design 4.4, 10a): a summoner, breeder or shrieker that
    # dies 被害無く is killed first, directly above the summoner shots (D2).
    if not (return_yield.quiet_recall_due(policy, snapshot)
            or summon_response.action_due(policy, snapshot)):
        worsens = worsens_kill.key(policy, snapshot, emergency_hostiles)
        if worsens is not None:
            return worsens

    # Owner 2026-11-06 「命に関わる時の後へ回す」: the emergency ladder above
    # answers first, then the last shots at a summoner.
    summoner_ranged = None if return_yield.quiet_recall_due(policy, snapshot) or summon_response.action_due(policy, snapshot) else policy._town_producer_entry("_summoner_ranged_kill_key", lambda: policy._summoner_ranged_kill_key(
        snapshot, emergency_hostiles
    ))
    if summoner_ranged is not None:
        return summoner_ranged
    return PASS
