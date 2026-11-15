"""The stair that leads back to the floor an escape by stairs left.

Owner 2026-10-31 (the escape descent cooldown, ``_defer_descent``): 「逃げた階に戻らないための
決定」.  The cooldown counts decisions, and the floor it keeps the bot off is still there when it
ends: Hengband saves the floors of a dive (floor/floor-leaver.cpp set_grid_by_leaving_floor: a
stair's ``grid.special`` keeps the id of the floor it leads to; floor-changer.cpp update_floor
loads that saved floor, its monsters where they were).  The up stair the escape took lands the
player on the down stair of the saved floor above whose ``special`` is the floor it fled, and that
stair, taken again, is the same fled floor.

n1-b life-405 (Magic-Eater Lv42, Castle, 2026-11-15 23:28-23:5x; the owner's 「現にn1-bは同じ範囲を
ループしている」): 50F's arrival stair stood two cells from a sleeping 年経たマグマのエレメンタル and
three more sleepers (T1, ``emergency:stairs``), 49F was explored for the 200 decisions of the
cooldown, ``seek-downstairs`` walked back to the stair it had arrived on and ``descend`` loaded the
same 50F: the same four sleepers at the same cells, about every 30 seconds.

``note_flight`` (from ``_defer_descent``, which every up-stair escape calls before it sends '<')
remembers the floor left; on the next floor change ``observe_floor_change`` records the down stair
the player stands on, when the change went up from that floor.  The descent owners do not take a
recorded stair on that floor (``leads_back``): ``_is_descent_target`` and ``_usable_downstairs``.
Another down stair of the floor is a new floor (``special`` 0: get_unused_floor_id), as is every
stair after the town.

The record holds while the saved floor can be the one the bot stands on: it is forgotten in town
(a dungeon entered again is generated anew) and for a floor key reached any other way than up
by stairs from below (a recall, a level teleport, a trap door, a descent from above: a floor the
game may have generated anew).
"""

from __future__ import annotations

PENDING = "_fled_floor_pending"
MEMORY = "_fled_floor_stairs"


def note_flight(policy, snapshot) -> None:
    """An escape by stairs from this floor is about to be sent."""
    if snapshot.dungeon_level > 0:
        setattr(policy, PENDING, (snapshot.floor_key, snapshot.dungeon_level))


def _memory(policy) -> dict:
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        memory = {}
        setattr(policy, MEMORY, memory)
    return memory


def observe_floor_change(policy, snapshot, previous_floor) -> None:
    """The floor changed: record the stair back to a fled floor, forget what no longer holds."""
    pending = getattr(policy, PENDING, None)
    setattr(policy, PENDING, None)
    memory = _memory(policy)
    if snapshot.in_town or snapshot.dungeon_level <= 0:
        memory.clear()
        return
    went_up_by_stairs = (
        previous_floor is not None
        and previous_floor[0] == snapshot.floor_key[0]
        and previous_floor[1] > snapshot.dungeon_level
    )
    here = snapshot.grid_at(snapshot.player.position)
    on_down_stair = here is not None and here.has_down_stairs
    if not (went_up_by_stairs and on_down_stair):
        memory.pop(snapshot.floor_key, None)
        return
    if pending is not None and pending[0] == previous_floor:
        memory[snapshot.floor_key] = memory.get(snapshot.floor_key, frozenset()) | {
            snapshot.player.position}


def leads_back(policy, snapshot, position) -> bool:
    """The down stair at ``position`` of this floor leads back to a floor an escape left."""
    memory = getattr(policy, MEMORY, None)
    return bool(memory) and position in memory.get(snapshot.floor_key, ())
