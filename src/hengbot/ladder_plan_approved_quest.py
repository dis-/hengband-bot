"""The plan-approved-quest layer of the dungeon ladder (dungeon_ladder.LADDER, layer
"plan-approved-quest").

``HengbotPolicy._decide`` asks this layer where its rows stand: below the opening, above the
pre-combat rungs.  On an approved quest floor (``profile``, the floor's approved strategy) it
ends the decision unconditionally: the approved-floor survival gate, the quiet light refill,
the chest of a completed quest, the one-time quest's tick rest, then the navigator, whose
answer is returned as it stands (None included).  Off such a floor ``PASS`` hands the decision
on to the layers below.  scripts/dungeon_ladder_lint.py reads the rows here
(dungeon_ladder.LAYER_MODULES), so the table still states this order.
"""
from __future__ import annotations

from hengbot import once_quest_recall
from hengbot.dungeon_ladder import PASS
from hengbot.item_reservation import reserved_item_command
from hengbot.model import Position
from hengbot.policy_constants import QUEST_STATUS_COMPLETED, WAIT_KEY
from hengbot.quest_navigator import QuestFloorNavigator
from hengbot.town_hold import LOOT_OWNERS as CLAIM_LOOT_OWNERS


def key(policy, snapshot, *, profile, strategic_hostiles, strategic_adjacent, physical_hostiles):
    """The plan-approved-quest layer's answer, or PASS when none of its rungs acts."""
    player = snapshot.player
    if profile is not None:
        # Approved-floor survival remains above the navigator. Keeping this
        # scoped to the quest branch preserves byte-for-byte dispatch order
        # on every non-quest floor.
        survival = policy._town_producer_entry("_survival_gate_key#1", lambda: policy._survival_gate_key(snapshot, physical_hostiles))
        if survival is not None:
            return survival
        # Approved quest navigation owns the whole floor and returns before
        # the ordinary light-maintenance block below. Refill during a quiet
        # turn so a long fixed-map sweep cannot consume every remaining turn
        # of lantern fuel while oil is already in the pack.
        if not physical_hostiles and not player.confused:
            refill = policy._light_refill_item(snapshot)
            if refill is not None:
                policy.last_reason = "refill-light"
                return reserved_item_command(policy, snapshot, "refill", refill)
        info = policy._quest_knowledge.get(profile.quest_id)
        if info is None or info.battlefield is None:
            policy.last_reason = "quest:blocked:enter"
            return WAIT_KEY
        navigator = policy._quest_navigators.setdefault(
            profile.quest_id,
            QuestFloorNavigator(profile.quest_id, info.battlefield),
        )
        snapshot = navigator.with_loot_memory(snapshot)
        quest = snapshot.quests.get(profile.quest_id)
        completed = quest is not None and quest.status == QUEST_STATUS_COMPLETED
        if not completed and policy._chest_position is not None:
            # A quiet observation is not a cleared quest. Chest approach
            # can reveal an enemy and yield to EXECUTE, whose survey then
            # retreats and hides that enemy, restarting the chest approach.
            policy._release_claim_goal(
                "chest-deferred-quest-incomplete", owners=CLAIM_LOOT_OWNERS
            )
            policy._chest_position = None
            policy._chest_phase_counts = {}
            policy._chest_collecting = False
            policy._chest_preopen_objects = None
        if completed and not physical_hostiles:
            # Fixed-quest sweep would otherwise treat a chest as generic
            # loot and carry it out unopened. Process it on this floor so
            # only Chest::open() contents enter the pack.
            chest = policy._town_producer_entry("_chest_processing_key#1", lambda: policy._chest_processing_key(
                snapshot,
                physical_hostiles,
                preferred_position=Position(*profile.engagement_plan["chest_position"])
                if profile.engagement_plan.get("chest_position") is not None
                else None,
            ))
            if chest is not None:
                # Chest work temporarily owns movement/search turns. The
                # previous sweep goal must not expire as stalled while we
                # deliberately process a different floor object.
                if policy._loot_target is not None:
                    policy._release_claim_goal(
                        "loot-chest-processing", policy._loot_target, owners=CLAIM_LOOT_OWNERS
                    )
                    policy._nav_ledger.release("loot", policy._loot_target)
                    policy._loot_target = None
                return chest
        tick_rest = once_quest_recall.tick_rest_before_navigator(policy, snapshot)
        if tick_rest is not None:
            return tick_rest
        return policy._town_producer_entry("navigator.decide", lambda: navigator.decide(
            policy, snapshot, strategic_hostiles, strategic_adjacent
        ))
    return PASS
