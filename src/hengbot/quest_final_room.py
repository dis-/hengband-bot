"""Door gates and the search area of an approved quest's final room.

Q34 lists every outer glass door in ``avoid_door_positions``.  One of them,
``final_door``, is the approved exception: the engagement phase picks its lock
from ``final_door_approach`` and then crosses it to reach the mobile target.
Doors listed in ``final_door_sequence`` (each with its ``approach`` cell) are
opened in order after the final door; until observed open they are gates like
the final door.  ``post_clear_pickup`` names the floor cell whose gold is
collected after the quest is cleared, before the exit.
These helpers keep the exceptions in one place so routing, the placement sweep
and the final-target approach agree on which doors are gates.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Mapping

from hengbot.model import Position, Snapshot


def final_door(plan: Mapping[str, Any]) -> Position | None:
    raw = plan.get("final_door")
    return Position(*raw) if raw is not None else None


def door_open(snapshot: Snapshot, door: Position) -> bool:
    grid = snapshot.grid_at(door)
    return grid is not None and grid.known and not grid.is_closed_door


def final_door_open(snapshot: Snapshot, plan: Mapping[str, Any]) -> bool:
    door = final_door(plan)
    return door is not None and door_open(snapshot, door)


def final_door_sequence(
    plan: Mapping[str, Any],
) -> tuple[tuple[Position, Position], ...]:
    """The (door, approach) pairs opened in order after the final door."""
    return tuple(
        (Position(*entry["door"]), Position(*entry["approach"]))
        for entry in plan.get("final_door_sequence", ())
    )


def _planned_doors(plan: Mapping[str, Any]) -> list[Position]:
    door = final_door(plan)
    planned = [door] if door is not None else []
    planned.extend(door for door, _ in final_door_sequence(plan))
    return planned


def next_sequence_door(
    snapshot: Snapshot, plan: Mapping[str, Any]
) -> tuple[Position, Position] | None:
    """The first sequence door still to open, once the final door is open."""
    if not final_door_open(snapshot, plan):
        return None
    return next(
        (
            (door, approach)
            for door, approach in final_door_sequence(plan)
            if not door_open(snapshot, door)
        ),
        None,
    )


def avoided_doors(plan: Mapping[str, Any]) -> set[Position]:
    """Doors no route may cross; the approved planned doors are never ones."""
    avoided = {Position(*raw) for raw in plan.get("avoid_door_positions", ())}
    avoided.difference_update(_planned_doors(plan))
    return avoided


def door_gates(snapshot: Snapshot, plan: Mapping[str, Any]) -> set[Position]:
    """Cells routes must not cross on this board.

    A closed planned door (the final door or a sequence door) is a gate too,
    but only until it is observed open: the approved door phase, not a route
    step, picks its lock.
    """
    gates = avoided_doors(plan)
    gates.update(
        door for door in _planned_doors(plan) if not door_open(snapshot, door)
    )
    return gates


def in_main_room(position: Position, plan: Mapping[str, Any]) -> bool:
    """Whether ``position`` is inside ``supply_recovery_bounds`` (True if unset)."""
    bounds = plan.get("supply_recovery_bounds")
    if bounds is None:
        return True
    min_y, min_x, max_y, max_x = bounds
    return min_y <= position.y <= max_y and min_x <= position.x <= max_x


def post_clear_pickup(plan: Mapping[str, Any]) -> Position | None:
    raw = plan.get("post_clear_pickup")
    return Position(*raw) if raw is not None else None


def final_search_area(
    terrain: Mapping[tuple[int, int], str], plan: Mapping[str, Any]
) -> frozenset[Position] | None:
    """Cells where the final mobile target can be searched for.

    The area is the opened main room (``supply_recovery_bounds``) plus the
    room behind the final door.  The latter is derived from the static map:
    every non-door floor cell reachable from the final door without entering
    the main room.  The mobile target cannot open doors, so the outer
    corridor outside the room's doors is not part of the search.  Plans
    without both facts return None (no restriction).
    """
    door = final_door(plan)
    bounds = plan.get("supply_recovery_bounds")
    if door is None or bounds is None:
        return None
    min_y, min_x, max_y, max_x = bounds

    def in_room(y: int, x: int) -> bool:
        return min_y <= y <= max_y and min_x <= x <= max_x

    area = {
        Position(y, x) for (y, x), kind in terrain.items()
        if in_room(y, x) and kind not in ("wall", "permanent", None)
    }
    area.add(door)
    queue = deque([door])
    seen = {door}
    while queue:
        current = queue.popleft()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            y, x = current.y + dy, current.x + dx
            nxt = Position(y, x)
            if nxt in seen or in_room(y, x):
                continue
            seen.add(nxt)
            if terrain.get((y, x)) in ("floor", "passage"):
                area.add(nxt)
                queue.append(nxt)
    return frozenset(area)
