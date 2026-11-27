"""The loot memory belongs to the map it was seen on: a floor change and a change of town forget it.

The loot memory (policy ``_known_loot``, the committed ``_loot_target`` and the deferral sets) is map
coordinates.  The floor change in ``_observe`` forgot it, but every town shares floor_key (0, 0, 0),
so a change of town under the same floor key kept the piles of the town left behind, and the loot
walk (``_normal_loot_key``, seek-loot) walked to their coordinates on the new town's map, where the
pile is not.  The routing terrain was already forgotten there (policy_navigation
``_scope_terrain_to_town`` / ``_forget_left_town_terrain``, 2026-09-25); the loot memory was not.

n1-b life-419 (Zombie Magic-Eater CL50, build bot-da2924aea, 2026-11-27 11:03-11:06): in Morivant
(town id 2) two gold piles (tval 127) were seen at (34,79) (turn 11260613) and (64,180) (turn
11261289) while the staff errand (me-staff:approach-tower) held the board.  The errand's Inn
teleport back to the Outpost (me-staff:return-outpost '1ma', turn 11262110) kept both cells, and on
the Outpost (town id 0) seek-loot took the board for 138 boards (turns 11262113-11262615): 40 steps
west to (33,80), where the empty (34,79) was dropped, then 85 steps east to (63,179), where the empty
(64,180) was dropped.  The 138 town decisions with no progress raised the town repetition detector
(town:cycle-break, turn 11262618), and town:blocked:repetition waited '5' until the owner-halt
loop-detected (turn 11262708).

``forget`` is the one reset of the loot memory: the floor change and the change of town both call it.
"""

from __future__ import annotations

from hengbot.town_hold import LOOT_OWNERS as CLAIM_LOOT_OWNERS


def forget(policy, cause: str) -> None:
    """Forget every remembered pile, the committed loot goal and the deferrals (see the module)."""
    policy._known_loot.clear()
    policy._release_claim_goal(cause, policy._loot_target, owners=CLAIM_LOOT_OWNERS)
    policy._loot_target = None
    policy._deferred_loot.clear()
    policy._safety_deferred_loot.clear()
    policy._nav_ledger_deferred_loot.clear()
    policy._loot_ledger_rearmed.clear()
    policy._loot_safety_rearmed.clear()
    policy._loot_defer_blocker = None
    policy._pending_loot_pickup = None
