"""The floor-avoidance layer of the dungeon ladder (dungeon_ladder.LADDER, layer "floor-avoidance").

``HengbotPolicy._decide`` asks this layer where its rows stand: below the summoner shots,
above the light layer (ladder_light).  Off the town floor the owner's summons, sight,
Resistance-potion, one-shot breath and never-moving-monster rules answer first; then the
unseen retreat, the dug pocket (anaguma) and the detected-threat preparation, over which an
ordinary or already-latched town return takes the decision.  The rungs are asked top-down
and the first key returned wins, as in ``_decide``; ``None`` hands the decision on to the
layers below.  scripts/dungeon_ladder_lint.py reads the rows here
(dungeon_ladder.LAYER_MODULES), so the table still states this order.

The hostiles are ``_decide``'s, computed once per decision and passed in unchanged, by
name: the physical views go to the physical consumers only
(test_policy_combat's routing check reads them here).
"""
from __future__ import annotations

from hengbot import (
    anaguma,
    destruction_use,
    immobile_ranged_kill,
    immobile_threat_memory,
    oneshot_breath,
    resist_potion,
    summon_response,
)


def key(policy, snapshot, *, strategic_hostiles, strategic_adjacent, physical_hostiles,
        physical_adjacent) -> str | None:
    """The floor-avoidance layer's key, or None when none of its rungs acts."""
    if not snapshot.in_town:
        # Owner 2026-11-04: the answer to the summons of this floor visit.
        summons = summon_response.key(policy, snapshot)
        if summons is not None:
            return summons
        # Owner 2026-11-05: a race that disenchants the gear, at first sight.
        sight_use = destruction_use.sight_trigger_key(policy, snapshot)
        if sight_use is not None:
            return sight_use
        # Owner 2026-11-05: the Potion of Resistance, before any attack below.
        resist = resist_potion.ladder_key(
            policy, snapshot, strategic_hostiles, strategic_adjacent, physical_hostiles)
        if resist is not None:
            return resist
        # Owner 2026-11-08 「感知で見えたら備える」: a known breath or ball that kills from full HP.
        one_shot = oneshot_breath.key(policy, snapshot)
        if one_shot is not None:
            return one_shot
        # Owner 2026-11-02 「遠距離で安全に倒せるなら倒す方を優先する」:
        # before any never-moving monster is avoided.
        immobile_kill = immobile_ranged_kill.key(policy, snapshot)
        if immobile_kill is not None:
            return immobile_kill
        immobile_summoner = policy._town_producer_entry(
            "_immobile_summoner_key",
            lambda: policy._immobile_summoner_key(snapshot, physical_hostiles),
            board=snapshot,
        )
        if immobile_summoner is not None:
            return immobile_summoner
        # Beside an avoided never-moving monster (owner 2026-11-01 21h).
        step_out = immobile_threat_memory.step_out_key(policy, snapshot)
        if step_out is not None:
            return step_out

    unseen_intercept = policy._town_producer_entry("_unseen_retreat_intercept_key", lambda: policy._unseen_retreat_intercept_key(
        snapshot, physical_hostiles, physical_adjacent
    ))
    unseen_action = unseen_intercept
    if unseen_action is None:
        unseen_action = policy._town_producer_entry("_unseen_retreat_key", lambda: policy._unseen_retreat_key(
            snapshot, physical_hostiles
        ))
    detected_preparation = None
    if unseen_action is None:
        # Owner 2026-11-10 穴熊 「掘れるなら掘る」: the dug pocket comes before the
        # existing chokes; it declines (None) where it cannot be dug (anaguma).
        anaguma_key = anaguma.key(policy, snapshot, physical_hostiles)
        if anaguma_key is not None:
            return anaguma_key
        detected_preparation = policy._town_producer_entry("_detected_threat_preparation_key", lambda: policy._detected_threat_preparation_key(
            snapshot, physical_hostiles
        ))
    contested_action = unseen_action or detected_preparation
    if contested_action is not None:
        # An ordinary or already-latched town return owns this contested
        # decision. Keep unseen retreat above anticipatory detected-threat
        # preparation when no return would act, without promoting return
        # above unrelated gates.
        town_return = (
            None
            if policy._escape_state.owner not in {None, "return", "unseen"}
            else policy._town_producer_entry("_return_to_town_key#1", lambda: policy._return_to_town_key(snapshot, strategic_hostiles))
        )
        if town_return is not None:
            return town_return
        return contested_action
