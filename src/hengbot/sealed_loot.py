"""Sensed loot in a walled pocket the floor gives no way into: melt the way in.

Owner 2026-11-13, answering n1-c life-205 (Orc cave 23F, 13:10-13:18): 「価値に関係なく溶かす」.
The floor's items were detected inside small rooms walled on every side (a hardened leather
armour, two scrolls of trap detection and a potion of restore constitution, (24,86)-(25,91)); the
explore spent every frontier, the secret-door search found no door and the stuck escape read
Recall.  Now, asked where that escape would leave (policy ``_stuck_escape_key``, after the
player's own sealed pocket), when nothing hostile is seen or sensed: Stone to Mud melts the
nearest wall toward the pocket, the absorbed power before a carried wand, whatever the items
are worth, and the ordinary loot owner takes them once the pocket opens.

The pocket (``pocket_walls``): the loot candidates no walk reaches, and the grids joined to them
that are neither a known wall nor a hazard the walk refuses (policy ``_is_avoidable_hazard_grid``:
a trap or damaging ground).  It is walled when none of its grids touches the walk's reach (a
touching one is a frontier, the explore's) and it stays inside the board; its walls are the
known meltable walls beside it.  The 13:10 pocket was such: its only side open to the corridor
was a row of detected traps ((23,87)-(23,89)), which the walk does not cross, so no walk
reached the dirt floor behind them; one wall beside the corridor, (24,89), was the way in.

The way in is the Stone to Mud route (retreat_enclosure ``melt_route`` / ``melt_toward_key``,
the walled-off hunt's): melt the route's next wall once beside it, else walk toward it.  Its
walls are counted against every use carried (sealed_pocket ``melt_charges``, one wall a charge
as Q2's breach counts them); fewer uses than walls, no means, or a hostile seen or sensed
leaves the escape as it was.  Its reason holds the stuck count (policy_constants
``STUCK_NEUTRAL_REASONS``), so the walk and the next wall stay with this rung until the pocket
opens and the loot owner, above, walks in.
"""

from __future__ import annotations

from collections import deque

from hengbot import retreat_enclosure, sealed_pocket
from hengbot.me_absorbed_substitutes import CAST_SUFFIX
from hengbot.model import Position
from hengbot.policy_constants import NEIGHBOR_OFFSETS

REASON = "stuck:sealed-loot-stone-to-mud"
REASONS = frozenset({REASON, REASON + CAST_SUFFIX})


def _safe(snapshot) -> bool:
    """No hostile in sight or sensed (the owner's 「安全な時」)."""
    return not any(monster.hostile
                   for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters))


def _reach(policy, snapshot) -> set[Position]:
    start = snapshot.player.position
    reached, queue = {start}, deque([start])
    while queue:
        for neighbour in policy._walkable_neighbors(snapshot, queue.popleft()):
            if neighbour not in reached:
                reached.add(neighbour)
                queue.append(neighbour)
    return reached


def _neighbours(position: Position):
    return (Position(position.y + dy, position.x + dx) for dy, dx in NEIGHBOR_OFFSETS)


def _known_wall(snapshot, position: Position) -> bool:
    grid = snapshot.grids.get(position)
    return grid is not None and grid.known and not grid.passable


def _bound(policy, snapshot, position: Position) -> bool:
    """A known wall, or a hazard the walk refuses."""
    return (_known_wall(snapshot, position)
            or policy._is_avoidable_hazard_grid(snapshot.grids.get(position)))


def _pocket(policy, snapshot, loot: Position, reach: set) -> set[Position] | None:
    """The grids joined to ``loot`` within the bounds (``_bound``), or None when they touch the
    reach or the board's edge (not walled)."""
    pocket, queue = {loot}, deque([loot])
    while queue:
        for neighbour in _neighbours(queue.popleft()):
            if neighbour in pocket or _bound(policy, snapshot, neighbour):
                continue
            if neighbour in reach:
                return None
            if not (0 < neighbour.y < snapshot.height - 1 and 0 < neighbour.x < snapshot.width - 1):
                return None
            pocket.add(neighbour)
            queue.append(neighbour)
    return pocket


def pocket_walls(policy, snapshot, reach: set) -> set[Position]:
    """The known meltable walls beside every walled pocket holding a loot candidate."""
    walls, seen = set(), set()
    for loot in sorted(policy._loot_candidates(snapshot) - reach, key=lambda cell: (cell.y, cell.x)):
        if loot in seen:
            continue
        pocket = _pocket(policy, snapshot, loot, reach)
        if pocket is None:
            continue
        seen |= pocket
        walls |= {wall for cell in pocket for wall in _neighbours(cell)
                  if wall not in pocket and _known_wall(snapshot, wall)
                  and retreat_enclosure.meltable(policy, snapshot, snapshot.grids[wall])}
    return walls


def key(policy, snapshot) -> str | None:
    """The next use or step on the way into a walled pocket of loot, else None."""
    player = snapshot.player
    if (snapshot.in_town or player.blind or player.confused or player.recalling
            or not _safe(snapshot) or not sealed_pocket.can_melt(policy, snapshot)):
        return None
    reach = _reach(policy, snapshot)
    walls = pocket_walls(policy, snapshot, reach)
    if not walls:
        return None
    route = retreat_enclosure.melt_route(policy, snapshot, walls)
    if route is None or route[1] > sealed_pocket.melt_charges(policy, snapshot):
        return None
    return retreat_enclosure.melt_toward_key(policy, snapshot, reach, walls, REASON, power_first=True)
