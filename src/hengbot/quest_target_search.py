"""The target of a random quest not found: circle the floor, and detect on the way.

Owner 2026-11-05: 「ランダムクエストで標的が見つからないときはフロアを周回して探す。既に地図が
完成している場合は全マス探索しない。標的に損傷を与えている場合、悠長な探索をすると回復されて
しまうからである。」, and 「この探索モードのとき、邪悪感知や全感知など有効な感知手段があれば定期的に
使って発見を早める」.

The mode (``searching``): a TAKEN runtime RANDOM quest occupies this floor and its exit lock
holds.  Everything that releases the lock (quest_floor_exit_locked: panic, starving, the
5-scroll reserve, the unviable floor) still releases it and ends the mode; no leave rule is
added.  Every combat, survival and hunt rung is above both askers, and the cell a detection
or sighting last showed the target on is walked to first (hunt_target.route_key), until the
player sees it empty.

The loop (``loop_key``, asked where ordinary exploration has answered nothing, so an
unfinished map keeps exploring as any floor does).  The stops are drawn from the ground the
player can walk to, what the bot remembers and what a mapping left as corridor (fair play):
 - each room: a connected group of open-space grids (mapped_area's reading,
   me_powers.OPEN_SPACE_NEIGHBOURS), by the grid nearest its middle;
 - then, for ground out of every stop's sight (a cave, a long corridor), the grid farthest
   from the stops, until all walkable ground is within MAX_SIGHT of one (define.h, how far
   the game shows anything).
A lap goes to the nearest stop not yet seen by walking distance, committed until seen: the
greedy short tour.  A stop is seen when the player stands on it, holds it in view lit, or
holds it in view inside the light radius.  With every stop seen the next lap draws them
again.  A lap with no stop left to walk to answers nothing, and the ladder below it runs
(the secret walls, the stall bound).

A loop step is progress: new ground is not what it is for, so the no-progress and stuck
counts restart on each (as sealed_pocket's use does).

The detection (``detection_key``, on the dungeon's safe decision, under me_powers' own rows,
which cast an absorbed power first): only a means that can show this race
(hunt_target.REVEALS), the carried Rod of Detection before the Staff of Detect Evil.  Again
under the owner's search spacing of 2026-11-02 (me_powers.redetect_due): every earlier cast
that could have shown the race is at least its radius away, or the latest is
HUNT_REDETECT_GAME_TURNS old.  Nothing is bought or kept for it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from hengbot import area_mapping, hunt_target, me_powers
from hengbot.item_reservation import reserved_item_command
from hengbot.model import (
    SV_ROD_DETECTION, SV_STAFF_DETECT_EVIL, TVAL_ROD, TVAL_STAFF, Position, Snapshot, game_distance,
)
from hengbot.policy_constants import NEIGHBOR_OFFSETS


LOOP_REASON = "quest-search:loop"
DETECT_REASON = "quest-search:detect"
MEMORY = "_quest_target_search"
MAX_SIGHT = 20  # define.h
# (tval, sval): (the command kind, hunt_target.REVEALS's effect), the fuller search first.
CARRIED_DETECTION = {
    (TVAL_ROD, SV_ROD_DETECTION): ("rod", "detect-all"),
    (TVAL_STAFF, SV_STAFF_DETECT_EVIL): ("staff", "detect-evil"),
}


@dataclass
class Memory:
    floor: tuple
    stops: tuple = ()
    seen: set = field(default_factory=set)
    goal: Position | None = None
    casts: list = field(default_factory=list)  # (position, radius, turn) a carried device searched
    pending: tuple | None = None               # (turn, position, radius) of the last use
    failed: dict = field(default_factory=dict)  # position -> failed uses


def _memory(policy, snapshot: Snapshot) -> Memory:
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        memory = Memory(snapshot.floor_key)
        setattr(policy, MEMORY, memory)
    return memory


def searching(policy, snapshot: Snapshot) -> bool:
    """A random quest's target is still to be killed here and the floor is held for it."""
    return (not snapshot.in_town and snapshot.dungeon_level > 0
            and not snapshot.player.recalling and not policy._returning_to_town
            and policy._on_random_quest_floor(snapshot)
            and policy._active_kill_quest_id(snapshot) == snapshot.floor_key[2]
            and policy._quest_floor_exit_locked(snapshot))


def _routes(policy, snapshot: Snapshot) -> dict:
    """Every walkable cell -> (walking distance, first step), breadth first."""
    start = snapshot.player.position
    routes = {start: (0, None)}
    queue = deque([start])
    while queue:
        here = queue.popleft()
        distance, first = routes[here]
        for neighbour in policy._walkable_neighbors(snapshot, here, allow_damaging=False):
            if neighbour not in routes and neighbour not in policy._engagement_avoid_cells:
                routes[neighbour] = (distance + 1, neighbour if first is None else first)
                queue.append(neighbour)
    return routes


def _room_groups(cells: set) -> list:
    """The connected groups of open-space grids among ``cells``."""
    def around(cell):
        return [Position(cell.y + dy, cell.x + dx) for dy, dx in NEIGHBOR_OFFSETS]

    rooms = {cell for cell in cells
             if sum(each in cells for each in around(cell)) >= me_powers.OPEN_SPACE_NEIGHBOURS}
    groups, done = [], set()
    for start in sorted(rooms, key=lambda cell: (cell.y, cell.x)):
        if start in done:
            continue
        done.add(start)
        group, stack = [start], [start]
        while stack:
            for each in around(stack.pop()):
                if each in rooms and each not in done:
                    done.add(each)
                    group.append(each)
                    stack.append(each)
        groups.append(group)
    return groups


def _middle(group: list) -> Position:
    y = sum(cell.y for cell in group) / len(group)
    x = sum(cell.x for cell in group) / len(group)
    return min(group, key=lambda cell: ((cell.y - y) ** 2 + (cell.x - x) ** 2, cell.y, cell.x))


def draw_stops(snapshot: Snapshot, cells: set) -> tuple:
    """The stops of a lap over walkable ``cells`` (the module docstring)."""
    stops = [_middle(group) for group in _room_groups(cells)] or [snapshot.player.position]
    nearest = {cell: min(game_distance(cell, stop) for stop in stops) for cell in cells}
    while nearest:
        farthest = max(nearest, key=lambda cell: (nearest[cell], -cell.y, -cell.x))
        if nearest[farthest] <= MAX_SIGHT:
            break
        stops.append(farthest)
        nearest = {cell: min(gap, game_distance(cell, farthest)) for cell, gap in nearest.items()}
    return tuple(stops)


def _seen_now(snapshot: Snapshot, stop: Position) -> bool:
    here = snapshot.player.position
    if stop == here:
        return True
    grid = snapshot.grid_at(stop)
    return grid is not None and grid.in_view and (
        grid.lit or game_distance(here, stop) <= (snapshot.light_radius or 0))


def _next_goal(snapshot: Snapshot, memory: Memory, routes: dict) -> Position | None:
    memory.seen.update(stop for stop in memory.stops if _seen_now(snapshot, stop))
    if memory.goal in routes and memory.goal not in memory.seen:
        return memory.goal
    left = [stop for stop in memory.stops if stop not in memory.seen and stop in routes]
    return None if not left else min(left, key=lambda stop: (routes[stop][0], stop.y, stop.x))


def loop_key(policy, snapshot: Snapshot) -> str | None:
    """The next step of the lap, else None."""
    if not searching(policy, snapshot):
        return None
    memory, routes = _memory(policy, snapshot), _routes(policy, snapshot)
    goal = _next_goal(snapshot, memory, routes)
    if goal is None:
        stops = draw_stops(snapshot, set(routes))
        # One stop: all the ground is in sight of one place, so there is nothing to circle.
        memory.stops, memory.seen = (stops if len(stops) > 1 else ()), set()
        goal = _next_goal(snapshot, memory, routes)
    memory.goal = goal
    if goal is None:
        return None
    policy._nav_exhausted = False
    policy._nav_stall_count = 0
    policy.last_reason = LOOP_REASON
    policy._declare_reach(goal)
    return policy._step_toward(snapshot, routes[goal][1])


def observe(policy, snapshot: Snapshot) -> None:
    """Every decision: settle the last use of a carried device."""
    memory = getattr(policy, MEMORY, None)
    if (memory is None or memory.floor != snapshot.floor_key or memory.pending is None
            or snapshot.turn == memory.pending[0]):
        return
    turn, position, radius = memory.pending
    memory.pending = None
    if any(message in area_mapping.FAILED for message in snapshot.messages):
        memory.failed[position] = memory.failed.get(position, 0) + 1
    else:
        memory.casts.append((position, radius, turn))


def _carried_detection(snapshot: Snapshot, flags: frozenset):
    held = {(item.tval, item.sval): item for item in reversed(snapshot.inventory)}
    for kind_key, (kind, effect) in CARRIED_DETECTION.items():
        item = held.get(kind_key)
        if (item is not None and hunt_target.REVEALS[effect](flags)
                and area_mapping.device_ready(item, kind)):
            return item, kind
    return None


def detection_key(policy, snapshot: Snapshot) -> str | None:
    """A carried device that can show the unseen target, when the spacing allows it."""
    if not searching(policy, snapshot):
        return None
    race = hunt_target.unseen_race(policy, snapshot)
    if race is None or not area_mapping.device_usable_now(policy, snapshot):
        return None
    flags = hunt_target.race_flags(policy, race)
    carried = _carried_detection(snapshot, flags)
    memory, here = _memory(policy, snapshot), snapshot.player.position
    if carried is None or memory.failed.get(here, 0) >= me_powers.FAILURES_PER_PLACE:
        return None
    earlier = [*memory.casts, *me_powers.revealing_casts(policy, snapshot, flags)]
    if not me_powers.redetect_due(snapshot, here, earlier):
        return None
    used = reserved_item_command(policy, snapshot, carried[1], carried[0])
    if used is None:
        return None
    policy.last_reason = DETECT_REASON
    memory.pending = (snapshot.turn, here, me_powers.map_radius(policy, snapshot))
    return used
