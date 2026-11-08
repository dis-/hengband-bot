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
With telepathy, the coverage stops after them (owner 2026-11-08, n1-b life-348 Angband 62F:
「クエストターゲットを探すには少なくとも感知範囲がフロア全域を網羅するように歩かなければならない。」):
every floor grid, known or not, that some walkable grid has within telepathy's reach is within
reach of a stop (search_coverage.plan).
Before the lap (and the secret doors below), a closed door the three-pick cap wrote off, that the
game answered as a lock and that opens onto ground the walk does not reach, is walked to and
picked (locked_doors.pick_key): a failed pick is progress, and the rest of the floor can be behind
it (n1-b life-348, Angband 50F, 2026-11-08).
A lap goes to the nearest stop not yet seen by walking distance, committed until seen: the
greedy short tour.  A stop is seen when the player stands on it; with telepathy, when every
floor grid within its reach was within reach of the walk (``observe`` notes each place, the
floor's ledger keeps them across a restart) or of a cast this lap that can show the target;
without it, when it is in view lit or inside the light radius.  With every stop seen the next
lap draws them again.  Floor grids no walkable grid reaches start a door search round at once
(``_door_search_key``), once for each reach, toward them; the places a door can be include a
wall between the walk and remembered floor it does not reach (``door_walls``: 62F's corridor
cell an earthquake turned to a magma vein).  A lap with no stop left to walk to answers
nothing, and the ladder below it runs (the secret walls, the stall bound).

A loop step is progress: new ground is not what it is for, so the no-progress and stuck
counts restart on each (as sealed_pocket's use does).  So a loop whose ground a retreat's veto
walls off would circle one side for ever: retreat_enclosure.walled_off_key answers first (the
floor's Teleportation, then the owner's dig, disarm and strike, then Teleportation again or
Recall).  There is no cap on laps.

The secret doors (``_door_search_key``).  Owner the same day: 「周辺感知をもたない場合に限り何周か
ごとに隠し扉を探す」, and 2026-11-06 (n1-b lapped one floor for two hours with Magic Mapping
absorbed): 「魔法の地図を持っていても隠し扉は見えないので、クエストの標的探しで隠し扉の探索を行う」.
map_area memorizes the MIMIC terrain (spell-kind/spells-floor.cpp), so a secret door still maps
as wall; only detect_doors (spells-detection.cpp, disclose_grid) or a search shows it.  So,
whatever 周辺感知 is held, every DOOR_SEARCH_LAPS laps
the bot goes to the nearest dead end it can walk to and spends the search rounds there
(SEARCH_LIMIT, the corridor dead-end rung answers on arrival), until every dead end had them; an
absorbed Detect Doors is asked first (me_powers.SECRET_SEARCH, its own spacing).  Each round of
this starts the dead ends' counts again: a search can miss (cmd-action/cmd-others.cpp search,
skill_srh per grid).  There is no cap on laps.  A door found is a frontier, and ordinary
exploration, which is asked before the loop, walks it.  The walk is not ``seek-secret-wall``:
that reason counts to STUCK_ESCAPE_LIMIT, which releases the exit lock, and no leave rule changes
here.  A walk between dead ends restarts that count, as any loop step does.

The sealed pocket (owner 2026-11-08, n1-a life-496: Angband 6F, RANDOM quest 49, two hours of
laps over x 78-131 of a 132-wide floor, no dead end hiding the way on): 「感知手段があるならそれを
用いる。感知手段のないキャラクタの場合、扉になりうる場所の探索を追加する。」.  The places a door can
be (``door_walls``): a tunnel through a room's outer wall is a secret door one time in five
(floor/cave-generator.cpp make_walls, place_random_door(..., true); grid/door.cpp: randint0(1000)
400-599 places a closed door that mimics dungeon.outer_wall), and a corridor junction's door
(grid/feature-generator.cpp try_door) mimics a wall terrain; so, from inside, a door reads as a
remembered wall.  A wall is such a place when a walkable grid lies beside it orthogonally and the
grid straight beyond is not known and inside the outer wall (a tunnel never runs on the boundary).
 - With a means (``door_means_key``): a door detection (spell-kind/spells-detection.cpp
   detect_doors, disclose_grid, DETECT_RAD_DEFAULT, a third in a DARKNESS dungeon) is cast where a
   place no cast has covered lies within its radius: the absorbed Detect Doors first
   (me_powers.SECRET_SEARCH, its row's own spacing), then the carried Rod of Door/Stair Location,
   Rod of Detection (detect_all, cmd-zaprod.cpp), Staff of Detect Doors (cmd-usestaff.cpp) and
   Scroll of Door/Stair Location (scroll-read-executor.cpp).  So a pocket is covered once, and
   again only where a new area brings places no cast reached.  A Rod of Detection the target
   search zapped (``detection_key``) and the absorbed Detect Doors or Detection the rows cast
   cover too.  Magic Mapping and Enlightenment do not: map_area and wiz_lite memorize the MIMIC
   terrain.  *Enlightenment* would, but its self-knowledge screen is not answered
   (consumable_policy.USE_UNSUPPORTED).
 - Without one (``door_means_held`` false): each door search round also walks to the walkable
   grids beside the places no cast covered, nearest first, after the dead ends, and searches each
   SEARCH_LIMIT times as a dead end (player/player-move.cpp search: the 8 neighbours).
Nothing is given up: the laps go on with no cap.

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

from hengbot import (
    area_mapping, hunt_target, locked_doors, me_capability, me_powers, retreat_enclosure,
    search_coverage,
)
from hengbot.item_reservation import reserved_item_command
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import (
    SV_ROD_DETECT_DOOR, SV_ROD_DETECTION, SV_SCROLL_DETECT_DOOR, SV_STAFF_DETECT_DOOR,
    SV_STAFF_DETECT_EVIL, TVAL_ROD, TVAL_SCROLL, TVAL_STAFF, Position, Snapshot, game_distance,
)
from hengbot.policy_constants import NEIGHBOR_OFFSETS, SEARCH_KEY, SEARCH_LIMIT


LOOP_REASON = "quest-search:loop"
DETECT_REASON = "quest-search:detect"
DOOR_REASON = "quest-search:seek-door"
DOOR_MEANS_REASON = "quest-search:detect-doors"
SEARCH_REASON = "search"  # the corridor dead-end rung's own reason
DOOR_SEARCH_LAPS = 3  # the owner's 「何周か」: the target's healing is why the loop hurries
MEMORY = "_quest_target_search"
MONSTERS, DOORS, BOTH = "monsters", "doors", "both"  # what a carried use detects
MAX_SIGHT = 20  # define.h
# (tval, sval): (the command kind, hunt_target.REVEALS's effect), the fuller search first.
CARRIED_DETECTION = {
    (TVAL_ROD, SV_ROD_DETECTION): ("rod", "detect-all"),
    (TVAL_STAFF, SV_STAFF_DETECT_EVIL): ("staff", "detect-evil"),
}
# (tval, sval): the command kind of a carried door detection, the recharging rods first.
CARRIED_DOOR_MEANS = {
    (TVAL_ROD, SV_ROD_DETECT_DOOR): "rod",
    (TVAL_ROD, SV_ROD_DETECTION): "rod",
    (TVAL_STAFF, SV_STAFF_DETECT_DOOR): "staff",
    (TVAL_SCROLL, SV_SCROLL_DETECT_DOOR): "read",
}
# The absorbed powers (me_powers rows) whose cast discloses doors.
ABSORBED_DOOR_MEANS = (("staff", SV_STAFF_DETECT_DOOR), ("rod", SV_ROD_DETECTION))


@dataclass
class Memory:
    floor: tuple
    stops: tuple = ()
    seen: set = field(default_factory=set)
    goal: Position | None = None
    casts: list = field(default_factory=list)  # (position, radius, turn) a carried device searched
    pending: tuple | None = None               # (turn, position, radius) of the last use
    failed: dict = field(default_factory=dict)  # position -> failed uses
    laps: int = 0                              # laps finished on this floor visit
    door_lap: int = 0                          # the lap the last door search began at
    door_search: bool = False                  # the dead ends are being searched now
    door_casts: list = field(default_factory=list)  # (position, radius) a carried door detection covered
    pending_shows: str = "monsters"            # what the pending use detects: MONSTERS, DOORS or BOTH
    cover: search_coverage.Coverage = field(default_factory=search_coverage.Coverage)
    lap_turn: int = 0                          # the game turn this lap was drawn on
    unreached: int = 0                         # floor grids no walkable cell of this lap covers
    toward_done: tuple | None = None           # the reach whose door round toward them was done


def _memory(policy, snapshot: Snapshot) -> Memory:
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        memory = Memory(snapshot.floor_key)
        ledger = getattr(policy, "_exploration_ledger", None)
        if ledger is not None and ledger.floor_key == snapshot.floor_key:
            # The floor's ledger holds the lap's coverage across a bot restart.
            memory.cover.centres = ledger.search_cover
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
    """Every walkable cell -> (walking distance, first step), breadth first.

    The lap, the door search and the lock picks walk these routes, so they keep the routes'
    engagement veto as every walker does (policy ``_engagement_route_veto``)."""
    start = snapshot.player.position
    routes = {start: (0, None)}
    queue = deque([start])
    avoided = policy._engagement_avoid_cells | policy._engagement_route_veto(snapshot)
    while queue:
        here = queue.popleft()
        distance, first = routes[here]
        for neighbour in policy._walkable_neighbors(snapshot, here, allow_damaging=False):
            if neighbour not in routes and neighbour not in avoided:
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


def _cast_centres(policy, snapshot: Snapshot, memory: Memory) -> list:
    """((y, x), radius) of this lap's casts that could show the unseen target."""
    race = hunt_target.unseen_race(policy, snapshot)
    if race is None:
        return []
    flags = hunt_target.race_flags(policy, race)
    casts = [*memory.casts, *me_powers.revealing_casts(policy, snapshot, flags)]
    return [((centre.y, centre.x), radius) for centre, radius, turn in casts if turn >= memory.lap_turn]


def _lap_left(policy, snapshot: Snapshot, memory: Memory):
    """The floor grids this lap's walk and casts have not covered (search_coverage)."""
    shape = (snapshot.height, snapshot.width)
    done = memory.cover.mask(shape) | search_coverage.covered(
        shape, _cast_centres(policy, snapshot, memory))
    return search_coverage.floor_grids(policy, snapshot) & ~done


def _draw(policy, snapshot: Snapshot, memory: Memory, routes: dict) -> tuple:
    """A new lap: the room and sight stops, then the coverage stops (search_coverage.plan);
    the lap's coverage starts again here."""
    stops, radius = draw_stops(snapshot, set(routes)), search_coverage.walk_radius(policy, snapshot)
    memory.unreached, memory.lap_turn = 0, snapshot.turn
    memory.cover.clear()
    if not radius:
        return stops
    plan = search_coverage.plan(
        snapshot, search_coverage.floor_grids(policy, snapshot), routes, stops, radius)
    memory.unreached = plan.unreachable
    memory.cover.note(snapshot.player.position, radius)
    return plan.stops


def _seen_now(snapshot: Snapshot, stop: Position, left, radius: int) -> bool:
    """The player stands on the stop; with telepathy, every floor grid the stop covers was
    covered (``left`` the grids not yet), else the stop is in view lit or in the light."""
    here = snapshot.player.position
    if stop == here:
        return True
    if radius:
        return search_coverage.disc_left(left, (stop.y, stop.x), radius) == 0
    grid = snapshot.grid_at(stop)
    return grid is not None and grid.in_view and (
        grid.lit or game_distance(here, stop) <= (snapshot.light_radius or 0))


def _next_goal(policy, snapshot: Snapshot, memory: Memory, routes: dict) -> Position | None:
    radius = search_coverage.walk_radius(policy, snapshot)
    if memory.stops:
        left = _lap_left(policy, snapshot, memory) if radius else None
        memory.seen.update(stop for stop in memory.stops
                           if stop not in memory.seen and _seen_now(snapshot, stop, left, radius))
    # The player's own cell is reached, not a goal: routes holds it with no first step.
    if (memory.goal in routes and memory.goal not in memory.seen
            and memory.goal != snapshot.player.position):
        return memory.goal
    left = [stop for stop in memory.stops if stop not in memory.seen and stop in routes]
    return None if not left else min(left, key=lambda stop: (routes[stop][0], stop.y, stop.x))


def _dead_ends(policy, snapshot: Snapshot, routes: dict) -> list:
    """The walkable grids the corridor dead-end rung searches."""
    return [cell for cell in routes if policy._open_neighbor_count(snapshot, cell) <= 1]


def _walk_key(policy, snapshot: Snapshot, routes: dict, goal: Position, reason: str) -> str | None:
    """One step to ``goal``, as progress (the module docstring); None on ``goal`` itself."""
    step = routes[goal][1]
    if step is None:
        return None
    policy._nav_exhausted = False
    policy._nav_stall_count = 0
    policy._recent.clear()  # a search's standing still must not read as an oscillation
    policy.last_reason = reason
    policy._declare_reach(goal)
    return policy._step_toward(snapshot, step)


def _known(policy, snapshot: Snapshot, cell: Position) -> bool:
    key = (cell.y, cell.x)
    if key in policy._remembered_floor_t or key in policy._remembered_wall_t:
        return True
    grid = snapshot.grid_at(cell)
    return grid is not None and grid.known


def door_walls(policy, snapshot: Snapshot, routes: dict) -> set:
    """The remembered walls a door can be in (the module docstring): beside a walkable grid
    orthogonally, with the grid straight beyond inside the outer wall and unknown, or
    remembered floor the walk does not reach (a mapped room past a secret door)."""
    walls = set()
    for cell in routes:
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            wall = Position(cell.y + dy, cell.x + dx)
            if (wall.y, wall.x) not in policy._remembered_wall_t or wall in walls:
                continue
            beyond = Position(wall.y + dy, wall.x + dx)
            if (0 < beyond.y < snapshot.height - 1 and 0 < beyond.x < snapshot.width - 1
                    and (not _known(policy, snapshot, beyond)
                         or ((beyond.y, beyond.x) in policy._floor_t and beyond not in routes))):
                walls.add(wall)
    return walls


def _beside(cell: Position, walls: set) -> list:
    """The ``walls`` among the 8 grids a search at ``cell`` covers."""
    return [wall for dy, dx in NEIGHBOR_OFFSETS if (wall := Position(cell.y + dy, cell.x + dx)) in walls]


def _absorbed_door_casts(policy, snapshot: Snapshot, radius: int) -> list:
    floor = getattr(policy, me_powers.MEMORY, None)
    if floor is None or floor.floor != snapshot.floor_key:
        return []
    return [(use.position, radius) for use in floor.uses if use.used in ABSORBED_DOOR_MEANS]


def _uncovered(policy, snapshot: Snapshot, memory: Memory, walls: set) -> set:
    """The places no door detection of this floor visit reached."""
    casts = [*memory.door_casts,
             *_absorbed_door_casts(policy, snapshot, me_powers.map_radius(policy, snapshot))]
    return {wall for wall in walls
            if not any(game_distance(centre, wall) <= radius for centre, radius in casts)}


def _carried_door_means(snapshot: Snapshot):
    """(item, kind) of each carried door detection, in CARRIED_DOOR_MEANS's order."""
    held = []
    for kind_key, kind in CARRIED_DOOR_MEANS.items():
        item = next((each for each in snapshot.inventory
                     if (each.tval, each.sval) == kind_key and each.known and each.aware), None)
        if item is not None:
            held.append((item, kind))
    return held


def door_means_held(policy, snapshot: Snapshot) -> bool:
    """A door detection to use: an absorbed one with a charge, a rod, a staff with a charge
    or a scroll (a charging rod is still held)."""
    if snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER and any(
            me_capability.charges(policy, snapshot, kind, sval) > 0
            for kind, sval in ABSORBED_DOOR_MEANS):
        return True
    return any(kind != "staff" or item.charges > 0 for item, kind in _carried_door_means(snapshot))


def door_means_key(policy, snapshot: Snapshot, memory: Memory, routes: dict) -> str | None:
    """A door detection where a place no cast covered lies within its radius, else None."""
    radius = me_powers.map_radius(policy, snapshot)
    here = snapshot.player.position
    uncovered = _uncovered(policy, snapshot, memory, door_walls(policy, snapshot, routes))
    if not any(game_distance(here, wall) <= radius for wall in uncovered):
        return None
    power = me_powers.power_key(policy, snapshot, me_powers.SECRET_SEARCH)
    if power is not None:
        return power
    if (memory.failed.get(here, 0) >= me_powers.FAILURES_PER_PLACE
            or not area_mapping.device_usable_now(policy, snapshot)):
        return None
    for item, kind in _carried_door_means(snapshot):
        if kind == "read":
            if not policy._can_read_scrolls(snapshot):
                continue
            used = policy._read_key(snapshot, item)
        elif area_mapping.device_ready(item, kind):
            used = reserved_item_command(policy, snapshot, kind, item)
        else:
            continue
        if used is None:
            continue
        policy.last_reason = DOOR_MEANS_REASON
        memory.pending = (snapshot.turn, here, radius)
        memory.pending_shows = BOTH if (item.tval, item.sval) == (TVAL_ROD, SV_ROD_DETECTION) else DOORS
        return used
    return None


def _door_search_key(policy, snapshot: Snapshot, memory: Memory, routes: dict) -> str | None:
    """This decision's part of the secret door search (the module docstring), else None."""
    ends = _dead_ends(policy, snapshot, routes)
    spots, uncovered = [], set()
    if not door_means_held(policy, snapshot):
        uncovered = _uncovered(policy, snapshot, memory, door_walls(policy, snapshot, routes))
        spots = [cell for cell in routes if cell not in ends and _beside(cell, uncovered)]
    # Ground no walkable cell covers is searched toward at once, once for each reach.
    toward = (memory.unreached, len(routes)) if memory.unreached else None
    if not memory.door_search and (memory.laps - memory.door_lap >= DOOR_SEARCH_LAPS
                                   or toward not in (None, memory.toward_done)):
        memory.door_lap, memory.door_search = memory.laps, True
        for cell in (*ends, *spots):
            policy._forget_wall_search(cell)
    if not memory.door_search:
        return None
    power = me_powers.power_key(policy, snapshot, me_powers.SECRET_SEARCH)
    if power is not None:
        return power
    left = [cell for cell in ends if policy._undersearched_walls(cell)]
    if not left:
        # The dead ends first (the likelier place), then the walls a door can be in: a grid
        # beside one whose search rounds are not spent, from there or a neighbour.
        left = [cell for cell in spots
                if policy._search_counts[(cell.y, cell.x)] < SEARCH_LIMIT
                and any(policy._wall_search_counts[(wall.y, wall.x)] < SEARCH_LIMIT
                        for wall in _beside(cell, uncovered))]
    if not left:
        memory.door_search, memory.toward_done = False, toward
        return None
    goal = min(left, key=lambda cell: (routes[cell][0], cell.y, cell.x))
    if goal != snapshot.player.position:
        return _walk_key(policy, snapshot, routes, goal, DOOR_REASON)
    policy._record_wall_search(goal)
    policy.last_reason = SEARCH_REASON
    return SEARCH_KEY


def loop_key(policy, snapshot: Snapshot) -> str | None:
    """The next step of the lap or of its door search, else None."""
    if not searching(policy, snapshot):
        return None
    walled_off = retreat_enclosure.walled_off_key(policy, snapshot)
    if walled_off is not None:
        return walled_off
    memory, routes = _memory(policy, snapshot), _routes(policy, snapshot)
    lock = locked_doors.pick_key(
        policy, snapshot, routes,
        lambda goal, reason: _walk_key(policy, snapshot, routes, goal, reason))
    if lock is not None:
        return lock
    means = door_means_key(policy, snapshot, memory, routes)
    if means is not None:
        return means
    door = _door_search_key(policy, snapshot, memory, routes)
    if door is not None:
        return door
    goal = _next_goal(policy, snapshot, memory, routes)
    if goal is None:
        memory.laps += bool(memory.stops)
        stops = _draw(policy, snapshot, memory, routes)
        # One stop: all the ground is in sight of one place, so there is nothing to circle.
        # The last lap's goal is spent with it: a goal kept would outlive the redraw and be
        # walked to again, though the player stands on it (n1-b life-332, 11-07 00:25).
        memory.stops, memory.seen, memory.goal = (stops if len(stops) > 1 else ()), set(), None
        goal = _next_goal(policy, snapshot, memory, routes)
    memory.goal = goal
    return None if goal is None else _walk_key(policy, snapshot, routes, goal, LOOP_REASON)


def observe(policy, snapshot: Snapshot) -> None:
    """Every decision: note what the player's place covers, and settle the last use of a
    carried device."""
    if searching(policy, snapshot) and (radius := search_coverage.walk_radius(policy, snapshot)):
        _memory(policy, snapshot).cover.note(snapshot.player.position, radius)
    memory = getattr(policy, MEMORY, None)
    if (memory is None or memory.floor != snapshot.floor_key or memory.pending is None
            or snapshot.turn == memory.pending[0]):
        return
    turn, position, radius = memory.pending
    shown, memory.pending, memory.pending_shows = memory.pending_shows, None, MONSTERS
    if any(message in area_mapping.FAILED for message in snapshot.messages):
        memory.failed[position] = memory.failed.get(position, 0) + 1
        return
    if shown in (DOORS, BOTH):
        memory.door_casts.append((position, radius))
    if shown in (MONSTERS, BOTH):
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
    # detect_all discloses the doors too (spells-detection.cpp).
    memory.pending_shows = BOTH if carried[1] == "rod" else MONSTERS
    return used
