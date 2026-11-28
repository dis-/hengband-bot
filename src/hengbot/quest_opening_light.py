"""An approved quest's opening light (``engagement_plan.opening_light``): met by the light the
character already sheds, or recovered from the quest floor, or the floor is given up.

Q34 (strategy/quests/QUEST_34.jsonc ``opening_light``) throws at its NEVER_MOVE targets from
distance-2 points; its contract is a light of radius 2, which the brass lantern lying at [10,20]
gives (lib/edit/quests/034_DumpWitness.jsonc:85-89 legend '6' = object 347 on map row 10, column
20; lib/edit/BaseitemDefinitions.jsonc:12384 the Brass Lantern's ``LITE_2``).  The contract is
the radius, not the lantern: ``met`` reads the board's own light radius (the game's
``cur_lite``, the ``player.light_radius`` the bot JSON exports).

n1-b life-421 (2026-11-28 16:49, Klackon Magic-Eater CL31 wearing a Feanorian lamp of radius 5):
the opening walked to the lantern anyway.  The default auto-pick file (lib/pref/picktype.prf,
block ``?:[GEQ $LEVEL 30]``: ``(!未鑑定の光源`` and ``(!油つぼ``) destroyed the flask at [9,20]
and the unidentified lantern at [10,20] as the player stepped on them (autopick.cpp:59
「真鍮のランタン {未鑑定}を自動破壊します。」), and the opening held on the empty cell
(``quest:blocked:opening-lantern-missing``) until ``loop-detected``.

A character whose own light falls short and that cannot get the floor's lantern lit (the lantern
gone from its cell, or carried dry with no oil) gives the floor up (``give_up_key``) instead of
holding: the leave the ONCE quest's hold does not reverse (policy ``_unviable_quest_floor``, as
quest25_pocket gives up its sealed pocket), the return to town is latched and Word of Recall is
read, or with no readable scroll the floor's up stair (or quest exit) is walked to and taken.  Leaving an
incomplete ONCE quest fails it for good (src/dungeon/quest.cpp:234 leave_quest_check).  For Q34
that costs its reward only, the Ring of Warning (lib/edit/towns/01_Outpost_Full.jsonc:759): the
town goes on to Q31 after a failed Q34 as after a won one (01_Outpost_Full.jsonc:782-795,
「Quest 34 failed but done, continue with quest 31」), so the road to Q31-Q33 stays open.
"""

from __future__ import annotations

from hengbot import once_quest_recall, return_start
from hengbot.policy_constants import UP_STAIRS_KEY

# The contract's radius when the plan names none: the brass lantern's LITE_2
# (lib/edit/BaseitemDefinitions.jsonc:12384).
OPENING_LIGHT_RADIUS = 2

RECALL_REASON = "quest-strategy:opening-light-recall"
STAIRS_REASON = "quest-strategy:opening-light:stairs-quest-fail"
WALK_REASON = "quest-strategy:opening-light-seek-exit"
# The return trigger the latch records (the unviable-quest return's own name).
TRIGGER = "quest-unviable"


def required_radius(plan: dict) -> int:
    """The light radius the opening's fixed-target phase needs."""
    return int(plan.get("min_radius", OPENING_LIGHT_RADIUS))


def met(snapshot, plan: dict) -> bool:
    """Whether the character's light already meets the opening's contract (no lantern errand)."""
    radius = snapshot.light_radius
    return radius is not None and radius >= required_radius(plan)


def give_up_key(policy, snapshot) -> str | None:
    """Give the quest floor up for an opening light the character cannot meet (module docstring)."""
    policy._unviable_quest_floor = snapshot.floor_key
    return_start.start(policy, TRIGGER)
    recall = once_quest_recall.read_key(policy, snapshot, RECALL_REASON, deliberate=True)
    if recall is not None:
        return recall
    if snapshot.player.recalling:
        return None
    here = snapshot.grid_at(snapshot.player.position)
    if here is not None and _way_out(here):
        policy.last_reason = STAIRS_REASON
        return UP_STAIRS_KEY
    step = policy._nearest_goal_step(snapshot, _way_out)
    if step is None:
        return None
    policy.last_reason = WALK_REASON
    return policy._step_toward(snapshot, step)


def _way_out(grid) -> bool:
    """A cell the quest floor is left by: its up stair (Q34's start stair [1,20]) or its exit."""
    return bool(grid.has_up_stairs or grid.has_quest_exit)
