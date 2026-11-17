"""The floor items a non-urgent *Destruction* would delete: a clean place first, else the valuables.

Owner 2026-11-17 (the 50F+ efficiency study's 第2位, answer 「価値の高い品は先に拾ってから撃つ」):
the uses that wait for no blow -- the approach to a T1 known only by detection and the use on a
sleeping or out-of-radius T1 (threat_tiers), the sealers of a route veto (retreat_enclosure) --
are made from a cell none of the remembered floor items lies within the circle of; where there
is none, the potions, scrolls, magic devices, rings and amulets inside it are picked up first
while no hostile is in view, then the use is made.  The instant-death and emergency uses are
unchanged (they never ask this).

The study (C:/hengband-backups/pdca/deep-efficiency-1117/REPORT.md 4.3): n1-c life-216's 1,645
uses at 50F+ deleted 2,771 remembered floor items, 652 of them worth taking (Healing, Speed,
Resistance potions, Stone to Mud wands).

Game (C:/hengband/src): spell-kind/spells-floor.cpp destroy_area deletes every item in its
circle, of radius 13 + randint0(5) for the staff and the absorbed power (cmd-usestaff.cpp:282;
the Powerful Activation's 18 + randint0(5) is never cast here), so an item 17 or nearer may go
(destruction_use ``in_worst_radius``).  The remembered items are the loot memory and the
game's found items (``remembered_piles``: the detected piles too, n1-b life-411's 64F use at
turn 5161935 had sixteen of them within 17 and no known grid under any); a pile's classes are
the found items' (grid_map ``found_items``: y, x, count, tval...).

The order, asked where the use is due (``key``, before destruction_use ``key``):

1. A committed place (``MEMORY``) is walked to while it still has a monster the use leaves within
   the sure radius and no remembered item within the worst one; on it, None: the use is made.
2. Else the nearest such place within ``PLACE_MAX_DISTANCE`` of the player, with no awake hostile
   in view: committed and walked to.
3. Else, with no hostile in view, the nearest valuable pile (``VALUABLE_TVALS``) inside the worst
   radius: walked to and picked up.
4. Else None: the use is made as before.

Every scene is bounded: ``DECISIONS_MAX`` decisions of this module per floor between two flashes
(a flash resets it), and a pile the pickup did not take is not gone to again on the floor; past
the bound the use is made as before, so no walk here can hold a use back for good.
"""

from __future__ import annotations

from hengbot import destruction_use
from hengbot.unwanted_kinds import UNWANTED_TVALS
from hengbot.model import (
    Position, TVAL_AMULET, TVAL_POTION, TVAL_RING, TVAL_ROD, TVAL_SCROLL, TVAL_STAFF, TVAL_WAND,
    game_distance,
)

PLACE_REASON = "destruction-loot:place"
FETCH_REASON = "destruction-loot:fetch"
PICKUP_REASON = "destruction-loot:pickup"
TRIGGER_REASON = "destruction-loot:trigger-autodestroy"
# Owner 2026-11-17 「薬・巻物・魔法道具・指輪・首飾り」.
VALUABLE_TVALS = frozenset({TVAL_POTION, TVAL_SCROLL, TVAL_STAFF, TVAL_WAND, TVAL_ROD,
                            TVAL_RING, TVAL_AMULET})
# The classes no pile is kept for (policy_helpers ``_floor_pile_is_junk``: skeletons, bottles,
# junk, statues, figurines, capture balls).
JUNK_TVALS = UNWANTED_TVALS | {1, 3, 10}
# The farthest (in game distance) a clean place is looked for: a short move beside the T1, not a
# second approach.
PLACE_MAX_DISTANCE = 8
# This module's decisions on a floor between two flashes before the use goes ahead regardless.
DECISIONS_MAX = 40
# {"floor": floor_key, "place": Position | None, "decisions": int, "tried": set of Position}
MEMORY = "_destruction_loot_memory"


def _memory(policy, snapshot) -> dict:
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.get("floor") != snapshot.floor_key:
        memory = {"floor": snapshot.floor_key, "place": None, "decisions": 0, "tried": set()}
        setattr(policy, MEMORY, memory)
    return memory


def observe(policy, snapshot) -> None:
    """A flash ends the scene: the next use starts with a fresh bound."""
    memory = getattr(policy, MEMORY, None)
    if memory is not None and any(message in destruction_use.FLASH for message in snapshot.messages):
        memory["place"] = None
        memory["decisions"] = 0


def remembered_piles(policy, snapshot) -> set:
    """The remembered floor piles: the loot memory (``_known_loot``, the non-junk piles of known
    grids) and the game's found items (grid_map ``found_items``: the detected ones too, whose
    grids the map may not show) that are not junk only (``JUNK_TVALS``)."""
    piles = set(getattr(policy, "_known_loot", ()))
    piles.update(Position(row[0], row[1]) for row in snapshot.found_items or ()
                 if any(tval not in JUNK_TVALS for tval in row[3:]))
    return piles


def exposed(policy, snapshot, centre=None) -> list:
    """The remembered floor piles a use made at ``centre`` (the player's cell) may delete."""
    return [position for position in remembered_piles(policy, snapshot)
            if destruction_use.in_worst_radius(snapshot, position, centre=centre)]


def _valuable(snapshot, position) -> bool:
    row = next((row for row in snapshot.found_items or ()
                if row[0] == position.y and row[1] == position.x), None)
    return row is not None and any(tval in VALUABLE_TVALS for tval in row[3:])


def _shown_leaving(snapshot, leaving) -> list:
    shown = {monster.index for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
             if monster.hostile}
    return [monster for monster in leaving if monster.index in shown]


def _place(policy, snapshot, centre, shown) -> bool:
    return (any(destruction_use.in_sure_radius(snapshot, monster, centre=centre) for monster in shown)
            and not exposed(policy, snapshot, centre))


def _in_view(snapshot, *, awake_only: bool) -> bool:
    return any(monster.hostile and not (awake_only and monster.asleep)
               for monster in snapshot.visible_monsters)


def key(policy, snapshot, leaving) -> str | None:
    """A step or a pickup before the use that leaves ``leaving``, else None (the use is made)."""
    leaving = list(leaving or ())
    if not leaving or not destruction_use.usable(policy, snapshot, leaving=leaving):
        return _committed(policy, snapshot, leaving)
    if not exposed(policy, snapshot):
        _memory(policy, snapshot)["place"] = None
        return None
    memory = _memory(policy, snapshot)
    if memory["decisions"] >= DECISIONS_MAX:
        return None
    answer = _committed(policy, snapshot, leaving)
    if answer is None:
        answer = _new_place(policy, snapshot, leaving)
    if answer is None:
        answer = _fetch(policy, snapshot)
    if answer is not None:
        memory["decisions"] += 1
    return answer


def _committed(policy, snapshot, leaving) -> str | None:
    """The walk to the committed place, while it still serves (``MEMORY``)."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.get("floor") != snapshot.floor_key or memory.get("place") is None:
        return None
    place = memory["place"]
    shown = _shown_leaving(snapshot, leaving)
    if (memory["decisions"] >= DECISIONS_MAX or not shown or not _place(policy, snapshot, place, shown)
            or not destruction_use.approach_gates(policy, snapshot)
            or snapshot.player.position == place):
        memory["place"] = None
        return None
    found = policy._nearest_goal_and_step(snapshot, lambda grid: grid.position == place)
    if found is None:
        memory["place"] = None
        return None
    step = found[1]
    memory["decisions"] += 1
    policy.last_reason = PLACE_REASON
    return policy._step_toward(snapshot, step)


def _new_place(policy, snapshot, leaving) -> str | None:
    if _in_view(snapshot, awake_only=True):
        return None
    shown = _shown_leaving(snapshot, leaving)
    here = snapshot.player.position
    found = policy._nearest_goal_and_step(snapshot, lambda grid: (
        game_distance(here, grid.position) <= PLACE_MAX_DISTANCE
        and _place(policy, snapshot, grid.position, shown)))
    if found is None:
        return None
    place, step = found
    _memory(policy, snapshot)["place"] = place
    policy.last_reason = PLACE_REASON
    return policy._step_toward(snapshot, step)


def _fetch(policy, snapshot) -> str | None:
    if _in_view(snapshot, awake_only=False):
        return None
    memory = _memory(policy, snapshot)
    here = snapshot.player.position
    piles = {position for position in exposed(policy, snapshot)
             if position not in memory["tried"] and _valuable(snapshot, position)}
    if not piles:
        return None
    if here in piles:
        pickup = policy._current_floor_item_key(
            snapshot, pickup_reason=PICKUP_REASON, trigger_reason=TRIGGER_REASON)
        if pickup is None or policy.last_reason == PICKUP_REASON:
            # Taken now, or refused (a full pack, a pile the budget refuses): not gone to again.
            memory["tried"].add(here)
        if pickup is not None:
            return pickup
        piles.discard(here)
        if not piles:
            return None
    found = policy._nearest_goal_and_step(snapshot, lambda grid: grid.position in piles)
    if found is None:
        return None
    policy.last_reason = FETCH_REASON
    return policy._step_toward(snapshot, found[1])
