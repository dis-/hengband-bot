"""Fixed-quest rewards placed on a town map: picked up before leaving town.

market/building-quest.cpp castle_quest turns a COMPLETED quest into REWARDED
and asks for the town to be rebuilt; floor/wild.cpp wilderness_gen then builds
the town from lib/edit/towns, whose ``[EQU $QUESTn 3]`` feature rule puts the
reward object on its floor cell, and right after that turns every REWARDED
quest into FINISHED.  So the reward exists only on this town level: once the
character leaves (the inn, recall, a stair or the wilderness), every later
visit is built with status 4 and the cell is bare floor (#47 D62, n1-c
life-098: the Telmora Q2 Feanorian lamp was seen at distance 1 and lost to
the staff sequence's inn trip to the Outpost).

This module owns the reward latch ``_fixed_quest_reward_pending`` (set when
the reward is claimed, rebuilt here from the allowlisted reward cell after a
restart) and serves it as the first non-emergency town owner, ahead of the
class-specific town sequences; the pickup itself stays
``_fixed_quest_reward_key`` (the allowlisted cells of
FIXED_QUEST_REWARD_POSITIONS).
"""

from __future__ import annotations

from hengbot.policy_constants import (
    FIXED_QUEST_REWARD_POSITIONS, QUEST_STATUS_FINISHED, QUEST_STATUS_REWARDED, WAIT_KEY,
)
from hengbot.town_pack_budget import explicit_pickup_cells

PACK_FULL_REASON = "fixedquest:reward-pack-full"
WAIT_REASON = "fixedquest:reward-wait"
_HANDED_OVER = frozenset({QUEST_STATUS_REWARDED, QUEST_STATUS_FINISHED})


def _reward_on_floor(policy, snapshot, quest_id: int) -> bool:
    """An object lies on one of this quest's allowlisted reward cells."""
    return any(
        (grid := snapshot.grid_at(position)) is not None and grid.object_count > 0
        for position in policy._fixed_quest_reward_positions(snapshot, quest_id))


def pending(policy, snapshot) -> int | None:
    """The latched reward quest; rebuilt from the visible reward after a restart."""
    if policy._fixed_quest_reward_pending is None:
        for quest_id in FIXED_QUEST_REWARD_POSITIONS:
            quest = snapshot.quests.get(quest_id)
            if (quest is not None and quest.status in _HANDED_OVER
                    and _reward_on_floor(policy, snapshot, quest_id)):
                policy._fixed_quest_reward_pending = quest_id
                break
    return policy._fixed_quest_reward_pending


def reward_key(policy, snapshot) -> str | None:
    """Approach and pick up the latched reward of this town.

    None when nothing is latched or the pickup finished on this board, and
    when the pack is full: the town owners then make room for it.  A latch
    that has no step this board waits rather than leaving the town.

    The reward is an explicit pickup (its own ``g`` on the cell): the walk
    onto its allowlisted cells is not an implicit town pickup, so the slot
    reserve of town_pack_budget.floor_step_fits does not refuse that step
    (the full pack keeps its own handoff).
    """
    quest_id = pending(policy, snapshot)
    if quest_id is None:
        return None
    with explicit_pickup_cells(policy._fixed_quest_reward_positions(snapshot, quest_id)):
        key = policy._fixed_quest_reward_key(snapshot, quest_id)
    if key is not None or policy._fixed_quest_reward_pending is None:
        return key
    if policy.last_reason == PACK_FULL_REASON:
        return None
    policy.last_reason = WAIT_REASON
    return WAIT_KEY


def town_key(policy, snapshot, hostiles) -> str | None:
    """The reward pickup ahead of the other non-emergency town owners.

    A hit this turn or a hostile in contact keeps the board for the town's
    survival owners (shelter, recovery, fight/flee; survival first): the
    reward stays on the floor while the character stays in this town.
    """
    if (not snapshot.in_town or snapshot.store is not None
            or getattr(policy, "_took_damage", False)
            or policy._physical_adjacent_hostiles(snapshot)):
        return None
    return reward_key(policy, snapshot)
