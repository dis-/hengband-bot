"""Native town travel to a cell (#47 D52, owner 2026-11-01).

Owner 2026-11-01: 「街での移動は可能な限りトラベルコマンドを活用して」.  The
store routes already ride the game's travel command to a store landmark
(``_shopping_approach_key``: ``\\x1b`n<symbol>.``).  A building (the inn,
Morivant's Tower of Sorcery) has no landmark of its own: the selector's
``+`` lists every building in floor order (target/grid-selector.cpp
select_building_pos), so this module names the travel point by moving the
selector's cursor from the player to the cell instead (point_target: each
direction key moves the cursor one grid, ``.`` selects it; cmd-travel.cpp
do_cmd_travel then refuses only a marked wall or door, Travel::can_travel_to).

The one rule for "may this town move use travel" is ``travel_key``: light
equipped (as the store route), a macro the smallest key queue takes, then
``_town_travel_key``'s board checks (the pack budget for floor pickups, a
disclosed goal, a seen own grid, the ``TOWN_TRAVEL_MIN_DISTANCE`` walk near the
goal, and the progress bound that re-issues an interrupted route --
travel-execution.cpp stops beside a visible monster -- and hands a stalled goal
back to walking).  A visible town monster is the global town hunt's
(``_town_kill_mob_key``, ahead of every errand), as for the store route; beside
any other visible monster (a friendly) the board walks, the game refusing the
travel without a turn passing.  Every caller keeps its
own single step as the fallback and for the last step into the building,
which carries the building's command tail.

Kept walking (not this module): combat and survival movement (town:kill-mob-*,
flee, cornered fights), stepping off an entrance, and the final step into a
store or building.
"""

from __future__ import annotations

from hengbot.model import Position

TRAVEL_MACRO_PREFIX = "\x1b`n"
TRAVEL_MACRO_SELECT = "."
# The smallest frontend key queue: main-gcu.cpp term_init(..., 256) keeps one
# slot free (z-term.cpp term_key_queue_room); term_keys_push refuses a longer
# sequence whole.  The headless term holds 1023 and Windows 65534.
TRAVEL_MACRO_MAX_KEYS = 255
# Original keyset directions (cursor moves of point_target).
_DIRECTION_KEYS = {(-1, -1): "7", (-1, 0): "8", (-1, 1): "9", (0, -1): "4",
                   (0, 1): "6", (1, -1): "1", (1, 0): "2", (1, 1): "3"}


def is_travel_macro(key: str) -> bool:
    """A native travel command: a store/entrance landmark or a cell."""
    return (isinstance(key, str) and key.startswith(TRAVEL_MACRO_PREFIX)
            and key.endswith(TRAVEL_MACRO_SELECT) and len(key) > len(TRAVEL_MACRO_PREFIX) + 1)


def point_macro(origin: Position, goal: Position) -> str:
    """``\\x1b`n`` + the cursor moves from ``origin`` to ``goal`` + ``.``."""
    dy, dx = goal.y - origin.y, goal.x - origin.x
    keys = []
    while dy or dx:
        step = ((dy > 0) - (dy < 0), (dx > 0) - (dx < 0))
        keys.append(_DIRECTION_KEYS[step])
        dy, dx = dy - step[0], dx - step[1]
    return TRAVEL_MACRO_PREFIX + "".join(keys) + TRAVEL_MACRO_SELECT


def plain_cell(snapshot, cell: Position) -> bool:
    """A grid whose entry opens nothing (no store, building or entrance)."""
    grid = snapshot.grid_at(cell)
    return (grid is not None and grid.building_type < 0 and grid.store_number < 0
            and grid.building_special < 0 and not grid.has_entrance
            and not grid.has_quest_enter)


def approach_cell(policy, snapshot, target: Position) -> Position | None:
    """A plain walkable neighbour of ``target``, the same one on every board.

    A stable goal keeps ``_town_travel_key``'s progress record (and its walking
    fallback latch) on one cell while the player moves; the neighbours of an
    entrance are the few cells in front of it.
    """
    return min((cell for cell in policy._walkable_neighbors(snapshot, target)
                if plain_cell(snapshot, cell)), key=lambda cell: (cell.y, cell.x), default=None)


def travel_key(policy, snapshot, goal: Position | None, reason: str) -> str | None:
    """The travel macro to ``goal``, or None where the caller walks instead."""
    if goal is None or not policy._has_light_equipped(snapshot):
        return None
    macro = point_macro(snapshot.player.position, goal)
    if len(macro) > TRAVEL_MACRO_MAX_KEYS:
        return None
    return policy._town_travel_key(snapshot, goal, macro, reason)


def building_key(policy, snapshot, building: Position | None, reason: str) -> str | None:
    """Travel to the cell beside ``building``; the caller's own step enters it."""
    if building is None:
        return None
    return travel_key(policy, snapshot, approach_cell(policy, snapshot, building), reason)
