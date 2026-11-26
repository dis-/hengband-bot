"""An explored 50F+ floor the dive goes no deeper from is left by its stairs, not Word of Recall.

Owner 2026-11-26 (verbatim): 「…いずれも、ゲーム内選択に関して私の以前の指示を破ることを許可する。」.
The rules this changes: owner 2026-11-17 (the 50F+ efficiency study's 第1位) 「適当な閾値を決めて、
探索が済んだら帰還する。」 and owner 2026-11-22 Q1 「今のまま帰還」 -- an explored floor the dive goes
no deeper from (explored_floor ``dead_end``: the 95F cap, a depth gate such as 80F while 81F asks
a speed the character lacks, the floor above a guardian the kit cannot pass, a dungeon's last
floor) was left by Word of Recall (explored_floor ``recall_key``), so each such trip explored
exactly one level.

The record (the supervisor's measurement, 2026-11-26): the winning life (n1-c life-221) made 625
recall round trips in 42.8 h, about 4 min each, of which about 2 min in town and 0.6 min the
recall wait; the town took 9.8 h (23%).  At a no-descend floor 49% of the returns were
``explored-dead-end-floor``, and on 2026-11-22 60 of 61 visits of Angband 80F ended by the
Recall.  The first form of this rule (finale_farm, the same day: n1-c life-222's 50 one-floor 95F
trips for the Black Market's Restore Mana, 17 of them ended so with 6-12 of 23 pack slots free)
held only while the finale's Black Market supply was short; this is the one rule for every such
floor.

The rule (``key``, asked by explored_floor ``recall_key`` in the Recall's place): on an explored
dead-end floor (explored_floor ``dead_end``: 50F and deeper only), outside any quest (the floor's exits
locked: policy ``_floor_navigation_exit_locked``), not Angband 99F/100F (the finale's floors,
their own rules) nor the finale expedition (angband_finale ``lifted``), and only while the stair
down back to this depth is admitted (``_return_admitted``: the depth gates, the 50F+ admission,
the cap, a guardian the kit cannot pass -- the climb never strands the dive above its depth),
the up stair underfoot is taken, else the walk goes to the nearest stair the map knows and a walk
reaches (none known or reachable: the Recall is read as before).  The floor above is a new level;
the dive's own descent (ladder_descent) walks to its stair down, a new level of this depth.  The
trip's other returns are untouched (pack full, the supplies, the HP and potion thresholds, every
survival and escape rule, the *Destruction* means spent come before the explore this replaces),
and every arrival rule runs on each new level as on any floor change.

The game (C:/hengband/src): stairs are always connected -- a new level puts a stair under the
player that leads back (floor/floor-changer.cpp set_stairs: a down stair after going up, its
``grid.special`` the floor left), and the floor left is saved (cmd-action/cmd-move.cpp
do_cmd_go_up sets SAVE_FLOORS; floor/floor-leaver.cpp set_grid_by_leaving_floor follows the
stair's ``special`` to the saved floor).  So the arrival stair of the floor above leads back to
this explored level, not to a new one: it is recorded as such before the '<' is sent
(fled_floor_stairs ``note_flight``, read by ``_is_descent_target``) and the dive takes another
stair down.  No descent cooldown (``_defer_descent``) is set: no enemy prompted the climb, and
the floor above costs only the walk to its next stair down (the loot on the way by the usual
rules).

``EXTRA_FLOORS`` = 4 (five explored dead-end floors a trip at most): one recall round trip's
overhead (about 2.6 of its 4 min: the town and the wait) is shared by N + 1 floors, 2.6 / (N + 1)
min a floor -- 1.3 at N = 1, 0.65 at 3, 0.52 at 4, 0.29 at 8; past 4 the saving per floor is
under 0.15 min while the loot is carried unsold and the town's restocking waits longer.  The
finale_farm record left 6-12 slots free after one floor, so most trips end by ``pack-full``
before the bound; the bound is for a pack the loot does not fill.

State: ``FLOORS`` (``_deep_stairs_floors``, the explored floors this trip left by the stairs;
a town board clears it, policy_observation ``observe_town_visit_epoch``) and ``COUNTED``
(``_deep_stairs_floor``, this floor visit is counted; floor_visit_memory forgets it on the floor
change).  A restart loses both: the new process counts the trip's floors again from none.
"""
from __future__ import annotations

from hengbot import fled_floor_stairs
from hengbot.model import DUNGEON_ANGBAND
from hengbot.policy_constants import UP_STAIRS_KEY

EXTRA_FLOORS = 4
# Angband's 99F/100F: the finale's floors (angband_finale_battle), never left so.
FINALE_FIRST_FLOOR = 99
FLOORS = "_deep_stairs_floors"
COUNTED = "_deep_stairs_floor"
REASON = "deep-stairs:seek-stairs"
ASCEND_REASON = "deep-stairs:ascend"


def floors(policy) -> int:
    return int(getattr(policy, FLOORS, 0) or 0)


def forget_trip(policy) -> None:
    """A town board: the next trip counts its floors from none."""
    setattr(policy, FLOORS, 0)


def _return_admitted(policy, snapshot) -> bool:
    """The stair down from the floor above back to this depth is one the dive takes: every
    refusal of ``_is_descent_target`` that reads the destination depth."""
    from hengbot import angband_cap  # import cycle
    dungeon, depth = snapshot.floor_key[0], snapshot.dungeon_level
    return not (policy._missing_required_abilities(snapshot, depth)
                or policy._guardian_floor_blocked(snapshot, dungeon, depth)
                or angband_cap.capped(snapshot, depth, policy)
                or policy._deep_stair_refused(snapshot, depth))


def applies(policy, snapshot) -> bool:
    """This floor is one the rule leaves by its stairs (the caller has read it explored): a dead
    end (explored_floor ``dead_end``, 50F and deeper only), no quest, not Angband 99F/100F nor
    the finale expedition."""
    from hengbot import angband_finale, explored_floor  # import cycle
    if (snapshot.in_town or policy._floor_navigation_exit_locked(snapshot)
            or not explored_floor.dead_end(policy, snapshot)):
        return False
    if snapshot.floor_key[0] == DUNGEON_ANGBAND and (
            snapshot.dungeon_level >= FINALE_FIRST_FLOOR or angband_finale.lifted(policy)):
        return False
    return _return_admitted(policy, snapshot)


def due(policy, snapshot) -> bool:
    """This explored dead-end floor is left by its stairs: the rule applies, and this floor is
    counted or the trip has left fewer than EXTRA_FLOORS so."""
    if not applies(policy, snapshot):
        return False
    return bool(getattr(policy, COUNTED, None)) or floors(policy) < EXTRA_FLOORS


def key(policy, snapshot) -> str | None:
    """explored_floor ``recall_key``'s replacement on such a floor (``due``): the up stair
    underfoot, else the walk to the nearest stair the map knows and a walk reaches; None when
    none is (the Recall is read as before)."""
    if not due(policy, snapshot):
        return None
    here = snapshot.grid_at(snapshot.player.position)
    allow_descent = not policy._descent_is_blocked(snapshot)

    def stair(grid) -> bool:
        return (policy._is_upstairs_target(grid)
                or (allow_descent and policy._is_descent_target(snapshot, grid)))

    if here is not None and policy._is_upstairs_target(here):
        _count(policy)
        # The down stair this lands on leads back to this explored level (connected stairs, a
        # saved floor): the dive takes another one.
        fled_floor_stairs.note_flight(policy, snapshot)
        policy.last_reason = ASCEND_REASON
        return UP_STAIRS_KEY
    policy._claim_target_capture = []
    try:
        step = policy._nearest_goal_step(snapshot, stair)
    finally:
        step_target = policy._take_claim_target()
    if step is None:
        return None
    _count(policy)
    policy.last_reason = REASON
    policy._declare_reach(step_target)
    return policy._town_producer_entry(
        "_step_toward:deep-stairs", lambda: policy._step_toward(snapshot, step), family="explore")


def _count(policy) -> None:
    if not getattr(policy, COUNTED, None):
        setattr(policy, COUNTED, True)
        setattr(policy, FLOORS, floors(policy) + 1)
