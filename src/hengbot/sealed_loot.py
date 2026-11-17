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
leaves the escape as it was.  Its reasons (``REASONS``) hold the stuck count as
``STUCK_NEUTRAL_REASONS`` do (policy_observation), so the walk and the next wall stay with this rung until the pocket
opens and the loot owner, above, walks in.

Owner 2026-11-13, on the traps (問い1): 「トラップ破壊かトラップ解除があればそれを優先。なければ壁を溶かす。」
When the pocket's way in crosses only detected traps (``trap_route``: the fewest traps, from the
walk's reach through trap grids into the pocket; the 13:10 room was one trap, (23,87), from the
cross's centre), the traps are cleared before any wall is melted (``_trap_key``): an absorbed
disarming or Trap/Door Destruction power (me_powers ``TRAP``, once a trap), then a carried rod or
wand of Disarming or wand of Trap/Door Destruction (both beams, cmd-zaprod.cpp / cmd-zapwand.cpp:
KILL_TRAP disarms the trap, KILL_DOOR turns it to floor, effect/effect-feature.cpp), then the
disarm command (policy_navigation ``_step_toward``, ``CHEST_DISARM_BUDGET`` presses a trap:
exe_disarm succeeds at skill - trap power percent, at least 2, and moves onto the grid; a failure
sets the trap off only when the skill is 5 or less or randint1(skill) <= 5).  A trap past its
presses with no device use left is no way in, and the melt above stays the way.  *Destruction*
is not such a means.

Owner 2026-11-18, on sensed loot whose surroundings the map does not know (n1-c life-216, Castle
64F, 2026-11-17 01:22: an amulet of the Magi at (38,18) inside a vault whose outside was not on the
map, so the melt route, which runs over known grids only, found no way and the loot was left):
「周辺感知があれば使用して入口を探す。なければ諦める。」  When no walled pocket above answers, a loot
candidate the walk does not reach whose enclosure (``enclosures``: the grids joined to it within
the bounds, short of the reach and the board's edge) holds a grid the map does not know (neither
known nor a magic mapping's blank floor) is mapped (``_map_key``): the player walks to the reached
grid nearest the loot and casts 周辺感知 there (area_mapping ``loot_enclosure_key``: the absorbed
power, then a carried staff or rod).  The ways above then take over: the loot walk through the
entrance the map shows, or the melt over the walls it shows.  Once an enclosure a floor visit
(``_MAPPED_MEMORY``, by its loot grids), and not where a live map of this floor visit already
covers the loot: mapped and still no way in, the loot is given up, as it is without a means.  No
grid the map does not know is melted through.  An enclosure whose known walls are all permanent
(a vault the melt cannot open) stays as it was.
"""

from __future__ import annotations

from hengbot import safety_watch
import heapq
from collections import deque

from hengbot import area_mapping, mapped_area, me_powers, retreat_enclosure, sealed_pocket
from hengbot.item_reservation import reserved_item_command
from hengbot.me_absorbed_substitutes import CAST_SUFFIX
from hengbot.model import (SV_ROD_DISARMING, SV_WAND_DISARMING, SV_WAND_TRAP_DOOR_DEST, TVAL_ROD,
                           TVAL_WAND, Position, game_distance)
from hengbot.policy_constants import CHEST_DISARM_BUDGET, NEIGHBOR_OFFSETS

REASON = "stuck:sealed-loot-stone-to-mud"
TRAP_REASON = "stuck:sealed-loot-trap"
DEVICE_SUFFIX = ":device"
MAP_REASON = "stuck:sealed-loot-map"  # the walk to where the enclosure is mapped
# The casts ``_map_key`` asks for (me_powers' and area_mapping's reasons).
MAP_CAST_REASONS = frozenset({
    f"{me_powers.REASON}:{me_powers.LOOT_ENCLOSURE}:{me_powers.MAP_AREA}",
    f"{area_mapping.REASON}:{area_mapping.LOOT_ENCLOSURE}",
})
REASONS = frozenset({REASON, REASON + CAST_SUFFIX, TRAP_REASON, TRAP_REASON + DEVICE_SUFFIX,
                     MAP_REASON}) | MAP_CAST_REASONS
# (floor_key, loot grids an enclosure was mapped for) of this floor visit (owner 2026-11-18).
_MAPPED_MEMORY = "_sealed_loot_mapped"
# The carried devices that clear a trap on their beam, Disarming first (it keeps the doors).
TRAP_DEVICES = ((TVAL_ROD, SV_ROD_DISARMING), (TVAL_WAND, SV_WAND_DISARMING),
                (TVAL_WAND, SV_WAND_TRAP_DOOR_DEST))
# Device uses a trap, a floor visit: a use that leaves the trap (a failed activation) is tried
# once more, as the disarm command's presses are.
DEVICE_USES_PER_TRAP = CHEST_DISARM_BUDGET
_DEVICE_MEMORY = "_sealed_loot_trap_device_uses"


@safety_watch.watched("sealed_loot._safe")  # record only (owner 2026-11-15 Q9)
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


def pockets(policy, snapshot, reach: set) -> list[set[Position]]:
    """Every walled pocket holding a loot candidate (``_pocket``)."""
    found, seen = [], set()
    for loot in sorted(policy._loot_candidates(snapshot) - reach, key=lambda cell: (cell.y, cell.x)):
        if loot in seen:
            continue
        pocket = _pocket(policy, snapshot, loot, reach)
        if pocket is None:
            continue
        seen |= pocket
        found.append(pocket)
    return found


def pocket_walls(policy, snapshot, reach: set) -> set[Position]:
    """The known meltable walls beside every walled pocket holding a loot candidate."""
    return {wall for pocket in pockets(policy, snapshot, reach) for cell in pocket
            for wall in _neighbours(cell)
            if wall not in pocket and _known_wall(snapshot, wall)
            and retreat_enclosure.meltable(policy, snapshot, snapshot.grids[wall])}


def _trap_grid(snapshot, position: Position) -> bool:
    """A known trap the player can step on (no monster on it)."""
    grid = snapshot.grids.get(position)
    return (grid is not None and grid.known and grid.trap and grid.passable
            and not grid.has_monster)


def trap_route(policy, snapshot, reach: set, inside: set) -> list[Position] | None:
    """The steps from the player into ``inside`` crossing the fewest known traps (then the
    fewest steps), through the walk's reach and trap grids only; None when no such route."""
    start = snapshot.player.position
    best, came = {start: (0, 0)}, {}
    queue = [(0, 0, start.y, start.x)]
    while queue:
        traps, steps, y, x = heapq.heappop(queue)
        here = Position(y, x)
        if best.get(here) != (traps, steps):
            continue
        if here in inside:
            path = [here]
            while path[-1] in came:
                path.append(came[path[-1]])
            return path[-2::-1]
        on_trap = _trap_grid(snapshot, here)
        onward = set()
        if here in reach and not on_trap:
            onward |= set(policy._walkable_neighbors(snapshot, here))
        onward |= {cell for cell in _neighbours(here)
                   if _trap_grid(snapshot, cell) or (on_trap and (cell in reach or cell in inside))}
        for cell in onward:
            if _trap_grid(snapshot, cell):
                cost = (traps + 1, steps + 1)
            elif cell in reach or cell in inside:
                cost = (traps, steps + 1)
            else:
                continue
            if cost < best.get(cell, (1 << 30, 0)):
                best[cell], came[cell] = cost, here
                heapq.heappush(queue, (*cost, cell.y, cell.x))
    return None


def _device_uses(policy, snapshot) -> dict:
    """Device uses aimed at each trap on this floor visit."""
    memory = getattr(policy, _DEVICE_MEMORY, None)
    if memory is None or memory[0] != snapshot.floor_key:
        memory = (snapshot.floor_key, {})
        setattr(policy, _DEVICE_MEMORY, memory)
    return memory[1]


def _trap_device(policy, snapshot, trap: Position):
    """A carried rod or wand that clears ``trap`` with a use left for it, else None."""
    if _device_uses(policy, snapshot).get((trap.y, trap.x), 0) >= DEVICE_USES_PER_TRAP:
        return None
    for ident in TRAP_DEVICES:
        for item in snapshot.inventory:
            if (item.tval, item.sval) != ident:
                continue
            if (item.charges > 0) if item.tval == TVAL_WAND else not item.charging:
                return item
    return None


def _clearable(policy, snapshot, trap: Position) -> bool:
    """A device use or a disarm press is left for ``trap``."""
    return (policy._floor_trap_disarm_attempts[(trap.y, trap.x)] < CHEST_DISARM_BUDGET
            or _trap_device(policy, snapshot, trap) is not None)


def _trap_key(policy, snapshot, step: Position) -> str | None:
    """The next use or step through the trap route's next ``step``, else None."""
    if not _trap_grid(snapshot, step):
        policy.last_reason = TRAP_REASON
        return policy._step_toward(snapshot, step)
    power = me_powers.power_key(policy, snapshot, me_powers.TRAP, step)
    if power is not None:
        return power
    device = _trap_device(policy, snapshot, step)
    direction = me_powers.beam_direction(policy, snapshot, snapshot.player.position, step)
    if device is not None and direction is not None:
        kind = "rod" if device.tval == TVAL_ROD else "wand"
        used = reserved_item_command(policy, snapshot, kind, device, suffix=direction)
        if used is not None:
            uses = _device_uses(policy, snapshot)
            uses[(step.y, step.x)] = uses.get((step.y, step.x), 0) + 1
            policy.last_reason = TRAP_REASON + DEVICE_SUFFIX
            return used
    if policy._floor_trap_disarm_attempts[(step.y, step.x)] >= CHEST_DISARM_BUDGET:
        return None
    # The disarm command (``_step_toward`` presses it on a trap, counting the press).
    policy.last_reason = TRAP_REASON
    return policy._step_toward(snapshot, step)


def key(policy, snapshot) -> str | None:
    """The next use or step on the way into a walled pocket of loot, else None."""
    player = snapshot.player
    if (snapshot.in_town or player.blind or player.confused or player.recalling
            or not _safe(snapshot)):
        return None
    reach = _reach(policy, snapshot)
    found = pockets(policy, snapshot, reach)
    walled = _walled_key(policy, snapshot, reach, found) if found else None
    # Owner 2026-11-18: the loot whose surroundings the map does not know is mapped once.
    return walled if walled is not None else _map_key(policy, snapshot, reach)


def _walled_key(policy, snapshot, reach: set, found: list) -> str | None:
    """The next use or step into one of the walled pockets ``found``, else None."""
    # 問い1: the traps on the way in are cleared before any wall is melted.
    route = trap_route(policy, snapshot, reach, set().union(*found))
    if route is not None and all(_clearable(policy, snapshot, cell)
                                 for cell in route if _trap_grid(snapshot, cell)):
        cleared = _trap_key(policy, snapshot, route[0])
        if cleared is not None:
            return cleared
    if not sealed_pocket.can_melt(policy, snapshot):
        return None
    walls = pocket_walls(policy, snapshot, reach)
    if not walls:
        return None
    route = retreat_enclosure.melt_route(policy, snapshot, walls)
    if route is None or route[1] > sealed_pocket.melt_charges(policy, snapshot):
        return None
    return retreat_enclosure.melt_toward_key(policy, snapshot, reach, walls, REASON, power_first=True)


def _on_board_inside(snapshot, position: Position) -> bool:
    """Not the board's edge (the permanent outer wall, never mapped: mapped_area.disc_cells)."""
    return 0 < position.y < snapshot.height - 1 and 0 < position.x < snapshot.width - 1


def _enclosure(policy, snapshot, loot: Position, reach: set) -> set[Position]:
    """The grids joined to ``loot`` within the bounds (``_bound``), short of the reach and the
    board's edge."""
    enclosure, queue = {loot}, deque([loot])
    while queue:
        for neighbour in _neighbours(queue.popleft()):
            if (neighbour in enclosure or neighbour in reach or not _on_board_inside(snapshot, neighbour)
                    or _bound(policy, snapshot, neighbour)):
                continue
            enclosure.add(neighbour)
            queue.append(neighbour)
    return enclosure


def _permanent_only(snapshot, enclosure: set) -> bool:
    """Every known wall beside ``enclosure`` is permanent (and there is one)."""
    walls = {wall for cell in enclosure for wall in _neighbours(cell)
             if wall not in enclosure and _known_wall(snapshot, wall)}
    return bool(walls) and all(snapshot.grids[wall].permanent for wall in walls)


def enclosures(policy, snapshot, reach: set) -> list[frozenset[Position]]:
    """The loot grids of each enclosure (``_enclosure``) of loot no walk reaches that holds a grid
    the map does not know, nearest the player first; an enclosure of permanent walls only is not
    one (the melt cannot open it)."""
    blank = area_mapping.blank_floor(policy, snapshot)
    candidates = policy._loot_candidates(snapshot) - reach
    here = snapshot.player.position
    found, seen = [], set()
    for loot in sorted(candidates, key=lambda cell: (game_distance(here, cell), cell.y, cell.x)):
        if loot in seen:
            continue
        enclosure = _enclosure(policy, snapshot, loot, reach)
        seen |= enclosure
        unknown = any(((grid := snapshot.grids.get(cell)) is None or not grid.known)
                      and (cell.y, cell.x) not in blank for cell in enclosure)
        if unknown and not _permanent_only(snapshot, enclosure):
            found.append(frozenset(candidates & enclosure))
    return found


def _mapped(policy, snapshot) -> set:
    """The loot grids an enclosure was mapped for on this floor visit."""
    memory = getattr(policy, _MAPPED_MEMORY, None)
    if memory is None or memory[0] != snapshot.floor_key:
        memory = (snapshot.floor_key, set())
        setattr(policy, _MAPPED_MEMORY, memory)
    return memory[1]


def _first_step(policy, snapshot, goal: Position) -> Position | None:
    """The first step of the walk to ``goal`` (``_reach``'s walk), else None."""
    start = snapshot.player.position
    came, queue = {start: None}, deque([start])
    while queue:
        here = queue.popleft()
        if here == goal:
            while came[here] != start:
                here = came[here]
            return here
        for neighbour in policy._walkable_neighbors(snapshot, here):
            if neighbour not in came:
                came[neighbour] = here
                queue.append(neighbour)
    return None


def _map_key(policy, snapshot, reach: set) -> str | None:
    """The walk to, or the cast of, 周辺感知 for the nearest enclosure not yet mapped, else None
    (owner 2026-11-18 「周辺感知があれば使用して入口を探す。なければ諦める。」)."""
    if not area_mapping.means_held(policy, snapshot):
        return None
    spent = _mapped(policy, snapshot)
    discs = mapped_area.floor_discs(policy, snapshot)
    here = snapshot.player.position
    for loot in enclosures(policy, snapshot, reach):
        if loot & spent or any(game_distance(centre, cell) <= radius
                               for centre, radius in discs for cell in loot):
            continue  # mapped on this floor visit: given up when still no way in

        def nearness(cell, loot=loot):
            return min(game_distance(cell, item) for item in loot)

        goal = min(reach, key=lambda cell: (nearness(cell), cell.y, cell.x))
        if nearness(goal) < nearness(here):
            step = _first_step(policy, snapshot, goal)
            if step is not None:
                policy.last_reason = MAP_REASON
                return policy._step_toward(snapshot, step)
        used = area_mapping.loot_enclosure_key(policy, snapshot)
        if used is not None:
            spent |= loot
        return used
    return None
