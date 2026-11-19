"""Where a quest plan waits: only where the monsters it waits for will come.

Owner 2026-11-19 (verbatim): 「待ち方をもっと効率化する必要がある」, and how: 「地形と敵の位置、敵の
アルゴリズムを確認して有効な場所で待つ」.

A room-sweep plan (quest_room_sweep) waits at its ``stands`` for ``meet_turns``, and for a coming
enemy in view up to ``enemy_wait_turns``; after a disengage (quest_summon_answer) it waits for what
acts on the player.  Fixed cells and fixed counts wasted those waits: n1-c life-217 (2026-11-19)
walked Quest 33's 段1 stands round and round because the Dagons it waited for at [15,38] never
came, and after 段1 waited at [14,47] for the Queen Ants, which never came either.  This reader
judges from the board and the game's monster AI whether each awaited monster will come to a cell.

The game (C:/hengband/src):

* It acts at all (``acts``): ``sweep_monster_process`` processes a monster only while
  ``decide_process_continue`` holds (monster/monster-processor.cpp:672, 701-722):
  the player within its ``aaf`` (the race's ``vision``), or within MAX_PLAYER_SIGHT (20) with its
  grid in the player's view, or while it holds a target.  The sleep counter falls by the same two
  conditions only (monster/monster-status.cpp:122-131), so a sleeper out of them never wakes.
  (quest_summon_answer._acts is this test; the target branch is not read: the board shows none.)
* It moves toward the player (monster-floor/monster-sweep-grid.cpp ``create_deciders``,
  :455-505): a monster neither PASS_WALL nor KILL_WALL (those go straight, ``should_go_straight``)
  that the player cannot see follows the flow (``NoiseTrackingMoveGridDecider``), which
  ``update_flow`` (grid/grid.cpp:806-913) stamps by a breadth-first walk from the player over the
  grids with MOVE (CAN_FLY too for a flyer, ``get_grid_flow_type``, monrace-definition.cpp:398)
  and over closed doors, and stops at ``monster_flow_depth`` = 32 steps.  Beyond that a monster
  out of the player's line has no flow (cost 0), and the scent (``grid.when``) is only laid around
  the player: no decider applies and it heads straight at him (``evalute_deciders``' default), into
  the first wall.  So it comes when the flow reaches it, or it has a line to the player, or it goes
  through walls (``_Reader.comes``).
* Its own steps (monster-floor/monster-move.cpp ``process_monster_movement``:377-440, monster/
  monster-info.cpp ``monster_can_cross_terrain``:42-118): pits only flying (DARK_PIT has no MOVE),
  deep water flying, swimming or AQUATIC, lava flying or IM_FIRE, a closed or locked door with
  OPEN_DOOR or BASH_DOOR (process_door) or PASS_WALL (doors have CAN_PASS), a non-permanent wall
  with PASS_WALL or KILL_WALL, an AQUATIC one only on water; NEVER_MOVE never steps.  Another
  monster in the way is passed only by KILL_BODY with a greater ``mexp * level`` or MOVE_BODY with
  a greater ``mexp`` (monster-attack/monster-attack-processor.cpp:120-150); one that does not act
  where the player waits never steps aside, so it blocks (the Dagons, 2026-11-19).
* It does not come when it runs (``mon_will_run``, monster-sweep-grid.cpp:35-72): afraid, or, from
  6 to 25 grids away, of a level that with 25 (+8 by its index) plus 4 is no more than the
  player's (the reading here takes only that sure case, +8 counted), and a pack animal (FRIENDS,
  ANIMAL, not through walls) that sees the player or is within 10 by the flow hides
  (``HidingMoveGridDecider``, :186-226) while the walkable cells around the player are fewer than
  8 x (HP + SP) / (max HP + max SP), less 2 for a race with no spells (the ROOM flag's other 2 is
  not on the quest map: not read).

What is awaited (``awaited``): every hostile awake monster on the board, seen or sensed, that the
plan does not leave alone; and, on a plan with ``alignment_split``, each tracked race's placements
the kill lines and the board do not account for (quest_alignment_split ``living``), on their placed
cells, beyond the player's telepathy for a race it shows -- their sleep is unknown, and a sleeper
within reach wakes (above).

The choice (``choose``): around a stand, the cells a walk reaches within ``SEARCH_STEPS`` (the stand
itself always), of plain floor, not taken by a monster, out of the plan's ``line_races`` lines, not
refused by a weapon warning or by an owner (left_cells), and, on a plan with ``alignment_split``, not
a cell where a GOOD and an EVIL summoner both act (the plan's own refusal by vision, and the line
within 20 as ``acts`` reads it), nor one to which a coming monster with a side passes on its way (the
flow's) through the line of a living summoner of the other side (``_passes_the_other_side``).  The
plan's order of phases: a tracked race of an ``alignment_split`` plan is waited for only around a
stand one of its members acts on.  The best is the cell most awaited monsters come to; on a tie the
stand itself, then (for monsters a wait has been spent on, below) the nearest to them, then the
fewest steps from the stand, then the one with a line to the most of them (the shot as they come),
then the narrowest (fewest open cells around: a choke).  None when no cell brings any.

A wait that ran out with nothing come (``spend``) is the board's evidence that the reading was wrong
for those monsters from that distance (n1-c life-217: the Queens did not come to [14,47], within
their vision and the flow's depth): each is from then on counted only at a cell nearer to it than
that (``_unspent``), and the nearest goes first, which also wakes a sleeper faster
(monster-status.cpp:152, the waking is MAX_MONSTER_SENSING / distance a notice).  So the waits for
the same monsters never repeat, and a sweep whose stops bring nothing ends by name
(quest_room_sweep ``NOTHING_COMES_REASON``) instead of walking its round again.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from hengbot import quest_alignment_split, quest_exposure
from hengbot.item_reservation import decision_memo
from hengbot.model import Position

FLOW_DEPTH = 32  # grid.cpp update_flow monster_flow_depth
SEARCH_STEPS = 24  # the walk from a stand within which another waiting cell is looked for
MAX_PLAYER_SIGHT = 20
WAIT_KINDS = frozenset({"floor", "passage"})
_FLOW_KINDS = frozenset({"floor", "exit", "passage", "tree", "shallow_water", "deep_water", "lava", "door"})
_WALK_KINDS = frozenset({"floor", "exit", "passage", "tree", "shallow_water", "door"})
_NEIGHBOURS = tuple((dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)


@dataclass(frozen=True)
class Awaited:
    key: tuple
    race: int
    cell: tuple[int, int]
    knowledge: object
    monster: object = None  # the board's MonsterState; None for a placement not on the board


@dataclass(frozen=True)
class Choice:
    cell: tuple[int, int]
    keys: frozenset
    closeness: float  # mean game distance to the monsters that come


def _cell(position) -> tuple[int, int]:
    return position.y, position.x


def _flags(awaited: Awaited) -> frozenset:
    return frozenset(getattr(awaited.knowledge, "flags", frozenset()))


# -- what is awaited ---------------------------------------------------------------------


def _known(snapshot) -> list:
    return [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters) if monster.hostile]


def _telepathy(policy, snapshot) -> int:
    from hengbot import search_coverage

    return 0 if snapshot.player.hallucinated else search_coverage.walk_radius(policy, snapshot)


def awaited(policy, snapshot, navigator, plan, left_alone=frozenset()) -> tuple[Awaited, ...]:
    def compute():
        rows = []
        known = _known(snapshot)
        for monster in known:
            knowledge = policy._monrace_knowledge.get(monster.race_id)
            if knowledge is None or monster.asleep or monster.race_id in left_alone:
                continue
            rows.append(Awaited(("seen", monster.index), monster.race_id, _cell(monster.position), knowledge, monster))
        split = quest_alignment_split.split_of(plan)
        if split is not None:
            here = _cell(snapshot.player.position)
            reach = _telepathy(policy, snapshot)
            for race in split["tracked_races"]:
                knowledge = policy._monrace_knowledge.get(race)
                if knowledge is None or race in left_alone:
                    continue
                shown = not ({"EMPTY_MIND", "WEIRD_MIND"} & set(knowledge.flags))
                on_board = sum(1 for monster in known if monster.race_id == race)
                left = quest_alignment_split.living(policy, snapshot, navigator, plan, race) - on_board
                cells = [cell for cell, placed in navigator.battlefield.monster_placements if placed == race
                         and not (shown and quest_exposure.game_distance(here, cell) <= reach)]
                rows.extend(Awaited(("placed", race, cell), race, cell, knowledge) for cell in cells[:max(0, left)])
        return tuple(rows)

    return decision_memo(policy, "quest_wait_placement.awaited", snapshot,
                         (navigator.quest_id, tuple(sorted(navigator.split_kills.items())), left_alone), compute)


# -- the game's movement ------------------------------------------------------------------


def _permanent(snapshot, cell) -> bool:
    grid = snapshot.grid_at(Position(*cell))
    return grid is None or not grid.known or bool(getattr(grid, "permanent", True))


def _crosses(snapshot, terrain, flags, cell) -> bool:
    """monster_can_cross_terrain over the quest map's kinds, with process_door's doors."""
    kind = terrain.get(cell)
    fly, aquatic = "CAN_FLY" in flags, "AQUATIC" in flags
    if kind is None:
        return False
    if kind in {"wall", "rubble"}:
        return bool({"PASS_WALL", "KILL_WALL"} & flags) and not _permanent(snapshot, cell)
    if kind == "door":
        return bool({"OPEN_DOOR", "BASH_DOOR", "PASS_WALL"} & flags) or not _closed(snapshot, cell)
    if fly:
        return True
    if kind == "pit":
        return False
    if kind == "deep_water":
        return "CAN_SWIM" in flags or aquatic
    if kind == "shallow_water":
        return True
    if aquatic:
        return False
    if kind == "lava":
        return bool({"IM_FIRE", "RES_ALL"} & flags)
    return kind in _WALK_KINDS


def _closed(snapshot, cell) -> bool:
    grid = snapshot.grid_at(Position(*cell))
    return grid is None or not grid.known or grid.is_closed_door


def _flow_from(terrain, start, fly: bool) -> dict:
    """update_flow's distances, walked from the monster's cell (the grid graph is undirected)."""
    kinds = _FLOW_KINDS | ({"pit"} if fly else frozenset())
    dist = {start: 0}
    pending = deque([start])
    while pending:
        cell = pending.popleft()
        if dist[cell] >= FLOW_DEPTH:
            continue
        for dy, dx in _NEIGHBOURS:
            nxt = (cell[0] + dy, cell[1] + dx)
            if nxt not in dist and terrain.get(nxt) in kinds:
                dist[nxt] = dist[cell] + 1
                pending.append(nxt)
    return dist


def _steps_from(snapshot, terrain, flags, start, blocked) -> frozenset:
    seen, pending = {start}, deque([start])
    while pending:
        cell = pending.popleft()
        for dy, dx in _NEIGHBOURS:
            nxt = (cell[0] + dy, cell[1] + dx)
            if nxt not in seen and nxt not in blocked and _crosses(snapshot, terrain, flags, nxt):
                seen.add(nxt)
                pending.append(nxt)
    return frozenset(seen)


def _passes(mover: Awaited, other) -> bool:
    """process_monster_attack_to_monster: KILL_BODY or MOVE_BODY over a lesser monster."""
    flags = _flags(mover)
    mine, theirs = mover.knowledge, other.knowledge
    if mine is None or theirs is None:
        return False
    if "KILL_BODY" in flags and "NEVER_BLOW" not in flags and mine.experience * mine.level > theirs.experience * theirs.level:
        return True
    return "MOVE_BODY" in flags and "NEVER_MOVE" not in flags and mine.experience > theirs.experience


class _Reader:
    """One board's readings, cached across the cells weighed."""

    def __init__(self, policy, snapshot, navigator, plan, rows):
        from hengbot import quest_summon_answer as answer

        self.policy, self.snapshot, self.navigator, self.plan = policy, snapshot, navigator, plan
        self.rows = rows
        self.terrain = navigator.battlefield.terrain
        self.open_cells = answer._open_cells(navigator, snapshot)
        self.flows: dict = {}
        self.steps: dict = {}
        player = snapshot.player
        self.hide_line = (8 * (player.hp + player.mp)) // max(1, player.max_hp + player.max_mp)
        self.level = int(getattr(player, "level", 0) or 0)
        self.summoners = quest_alignment_split.summoners(policy, snapshot, navigator, plan)

    def acts(self, row: Awaited, spot) -> bool:
        from hengbot import quest_summon_answer as answer

        return answer._acts(self.open_cells, row.cell, int(getattr(row.knowledge, "vision", 0) or 0), spot)

    def _flow(self, row: Awaited) -> dict:
        fly = "CAN_FLY" in _flags(row)
        if (row.cell, fly) not in self.flows:
            self.flows[(row.cell, fly)] = _flow_from(self.terrain, row.cell, fly)
        return self.flows[(row.cell, fly)]

    def flow_to(self, spot, fly: bool) -> dict:
        """update_flow's distances from a player on ``spot``."""
        if (spot, fly, "to") not in self.flows:
            self.flows[(spot, fly, "to")] = _flow_from(self.terrain, spot, fly)
        return self.flows[(spot, fly, "to")]

    def _runs(self, row: Awaited, spot) -> bool:
        monster = row.monster
        if monster is not None and monster.fearful:
            return True
        distance = quest_exposure.game_distance(row.cell, spot)
        level = int(getattr(row.knowledge, "level", 0) or 0)
        return 5 < distance <= MAX_PLAYER_SIGHT + 5 and level + 25 + 8 + 4 <= self.level

    def _hides(self, row: Awaited, spot, flow_distance) -> bool:
        flags = _flags(row)
        if not ({"FRIENDS", "ANIMAL"} <= flags) or {"PASS_WALL", "KILL_WALL"} & flags:
            return False
        if flow_distance is None or flow_distance >= MAX_PLAYER_SIGHT // 2:
            if not quest_exposure.projectable(self.open_terrain(), row.cell, spot):
                return False
        room = sum(1 for dy, dx in _NEIGHBOURS
                   if _crosses(self.snapshot, self.terrain, flags, (spot[0] + dy, spot[1] + dx)))
        if not getattr(row.knowledge, "abilities", ()):
            room -= 2
        return room < self.hide_line

    def open_terrain(self) -> dict:
        if not hasattr(self, "_open_terrain"):
            self._open_terrain = {cell: ("floor" if cell in self.open_cells else "wall") for cell in self.terrain}
        return self._open_terrain

    def _blocked(self, row: Awaited, spot) -> frozenset:
        """The cells of the board's monsters that stay where they are while the player waits on
        ``spot`` (asleep, NEVER_MOVE, or not acting there) and that ``row`` cannot pass."""
        cells = set()
        for other in self.rows_on_board:
            if other.key == row.key or _passes(row, other):
                continue
            monster = other.monster
            if (monster.asleep or "NEVER_MOVE" in _flags(other) or not self.acts(other, spot)):
                cells.add(other.cell)
        return frozenset(cells)

    @property
    def rows_on_board(self) -> list:
        if not hasattr(self, "_board_rows"):
            rows = []
            for monster in _known(self.snapshot):
                knowledge = self.policy._monrace_knowledge.get(monster.race_id)
                rows.append(Awaited(("seen", monster.index), monster.race_id, _cell(monster.position), knowledge, monster))
            self._board_rows = rows
        return self._board_rows

    def comes(self, row: Awaited, spot) -> bool:
        """``row`` acts on a player on ``spot`` and will come to him (module docstring)."""
        flags = _flags(row)
        if row.knowledge is None or "NEVER_MOVE" in flags or not self.acts(row, spot):
            return False
        if self._runs(row, spot):
            return False
        flow_distance = self._flow(row).get(spot)
        straight = bool({"PASS_WALL", "KILL_WALL"} & flags)
        if not straight and flow_distance is None and not quest_exposure.projectable(self.open_terrain(), spot, row.cell):
            return False
        if self._hides(row, spot, flow_distance):
            return False
        blocked = self._blocked(row, spot) - {spot}
        key = (row.key, blocked)
        if key not in self.steps:
            self.steps[key] = _steps_from(self.snapshot, self.terrain, flags, row.cell, blocked)
        reached = self.steps[key]
        return any((spot[0] + dy, spot[1] + dx) in reached for dy, dx in _NEIGHBOURS)

    def comers(self, spot) -> frozenset:
        return frozenset(row.key for row in self.rows if self.comes(row, spot))

    def both_sides_act(self, spot) -> bool:
        sides = {mark for mark, cell, vision in self.summoners if self.acts_at(cell, vision, spot)}
        return {quest_alignment_split.GOOD, quest_alignment_split.EVIL} <= sides

    def acts_at(self, cell, vision, spot) -> bool:
        from hengbot import quest_summon_answer as answer

        return answer._acts(self.open_cells, cell, vision, spot)


def reader(policy, snapshot, navigator, plan, left_alone=frozenset()) -> _Reader:
    return decision_memo(policy, "quest_wait_placement.reader", snapshot,
                         (navigator.quest_id, tuple(sorted(navigator.split_kills.items())), left_alone),
                         lambda: _Reader(policy, snapshot, navigator, plan,
                                         awaited(policy, snapshot, navigator, plan, left_alone)))


def comers_at(policy, snapshot, navigator, plan, spot, left_alone=frozenset()) -> frozenset:
    """The keys of the awaited monsters that come to a player on ``spot``."""
    return reader(policy, snapshot, navigator, plan, left_alone).comers(spot)


def comes(policy, snapshot, navigator, plan, monster, spot=None) -> bool:
    """A board monster acts on a player on ``spot`` (where he stands by default) and comes."""
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    row = Awaited(("seen", monster.index), monster.race_id, _cell(monster.position), knowledge, monster)
    here = _cell(snapshot.player.position) if spot is None else spot
    return reader(policy, snapshot, navigator, plan).comes(row, here)


# -- the choice -----------------------------------------------------------------------------


def _closeness(rows_by_key, spot, keys) -> float:
    return sum(quest_exposure.game_distance(spot, rows_by_key[key].cell) for key in keys) / max(1, len(keys))


def _spent(navigator) -> dict:
    """Monster key -> the distance at which a wait for it ran out with nothing come (the least)."""
    spent: dict = {}
    for key, distance in navigator.wait_spent:
        spent[key] = min(distance, spent.get(key, distance))
    return spent


def _unspent(rows_by_key, spent, spot, keys) -> frozenset:
    """``keys`` less those a spent wait waited for from as far or farther (``spend``)."""
    return frozenset(key for key in keys
                     if quest_exposure.game_distance(spot, rows_by_key[key].cell) < spent.get(key, 10 ** 6))


def _candidates(policy, snapshot, navigator, plan, stand, taken) -> dict:
    """Cell -> steps from ``stand`` over the plan's walking map, within SEARCH_STEPS."""
    from hengbot import quest_plan_base

    terrain = quest_plan_base._terrain_of(navigator, snapshot, water=False)
    walkable = {"floor", "exit", "passage", "shallow_water"}  # quest_exposure's walk (no trees)
    steps = {stand: 0}
    pending = deque([stand])
    while pending:
        cell = pending.popleft()
        if steps[cell] >= SEARCH_STEPS:
            continue
        for dy, dx in _NEIGHBOURS:
            nxt = (cell[0] + dy, cell[1] + dx)
            if nxt not in steps and nxt not in taken and terrain.get(nxt) in walkable:
                steps[nxt] = steps[cell] + 1
                pending.append(nxt)
    kinds = navigator.battlefield.terrain
    return {cell: count for cell, count in steps.items() if cell == stand or kinds.get(cell) in WAIT_KINDS}


def _taken(policy, snapshot, navigator, plan) -> frozenset:
    """The cells no wait is chosen on: the plan's own refusals (quest_room_sweep._path's)."""
    from hengbot import left_cells, quest_room_sweep

    refused = {_cell(cell) for cell in quest_room_sweep._refused_cells(policy, snapshot, navigator)}
    lines = set(quest_room_sweep._lines(navigator, plan, snapshot).pull)
    occupied = {_cell(monster.position) for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)}
    return frozenset(refused | lines | occupied | set(left_cells.refused_yx(policy, snapshot))
                     | set(quest_alignment_split.refused_cells(policy, snapshot, navigator, plan)))


def choose(policy, snapshot, navigator, plan, stand, left_alone=frozenset()) -> Choice | None:
    """The best waiting cell around ``stand`` (module docstring), or None."""
    stand = tuple(stand)

    def compute():
        read = reader(policy, snapshot, navigator, plan, left_alone)
        if not read.rows:
            return None
        rows_by_key = {row.key: row for row in read.rows}
        taken = _taken(policy, snapshot, navigator, plan)
        split = quest_alignment_split.split_of(plan) is not None
        spent = _spent(navigator)
        # The plan's order of phases: a tracked race (the summoners the plan orders) is waited for
        # only at a stop one of its members acts on; another cell does not bring a later phase's summoners.
        tracked = frozenset((quest_alignment_split.split_of(plan) or {}).get("tracked_races", ()))
        present = frozenset(row.race for row in read.rows if row.race in tracked and read.acts(row, stand))
        foreign = frozenset(row.key for row in read.rows if row.race in tracked and row.race not in present)
        scored = []
        for spot, steps in _candidates(policy, snapshot, navigator, plan, stand, taken - {stand}).items():
            if spot != stand and spot in taken:
                continue
            if split and read.both_sides_act(spot):
                continue
            keys = _unspent(rows_by_key, spent, spot, read.comers(spot) - foreign)
            if not keys:
                continue
            closeness = _closeness(rows_by_key, spot, keys)
            lines = sum(1 for key in keys if quest_exposure.projectable(read.open_terrain(), spot, rows_by_key[key].cell))
            room = sum(1 for dy, dx in _NEIGHBOURS
                       if navigator.battlefield.terrain.get((spot[0] + dy, spot[1] + dx)) in _WALK_KINDS)
            near = closeness if keys & spent.keys() else 0
            scored.append(((-len(keys), spot != stand, near, steps, -lines, room, spot), Choice(spot, keys, closeness)))
        scored.sort(key=lambda item: item[0])
        return tuple(choice for _, choice in scored)

    ranked = decision_memo(policy, "quest_wait_placement.choose", snapshot,
                           (navigator.quest_id, stand, tuple(sorted(navigator.split_kills.items())),
                            left_alone, navigator.wait_spent), compute)
    return _reachable(policy, snapshot, navigator, plan, ranked or (), left_alone)


def _route(read, flags, start, spot) -> list:
    """The way the flow leads ``start`` to a player on ``spot``: each step to a neighbour of the
    least flow distance (NoiseTrackingMoveGridDecider), until beside him; [] past the flow."""
    dist = read.flow_to(spot, "CAN_FLY" in flags)
    if start not in dist:
        return []
    route, cell = [start], start
    while dist[cell] > 1:
        cell = min(((cell[0] + dy, cell[1] + dx) for dy, dx in _NEIGHBOURS
                    if (cell[0] + dy, cell[1] + dx) in dist), key=lambda nxt: dist[nxt])
        route.append(cell)
    return route


def _passes_the_other_side(policy, navigator, plan, read, choice) -> bool:
    """On a plan with ``alignment_split``: a comer with a side whose way to the player crosses the
    line of a living summoner of the other side within its spell range (melee-spell.cpp
    ``monst_spell_monst``: a monster casts at a hostile-aligned one it can ``projectable`` to,
    and the coming one, acting, casts at it as well).  The plan's own care (QUEST_33's [14,47]:
    the Queens' flight goes north by the pits, not past the Gachapins' mouth)."""
    from hengbot import quest_summon_answer as answer

    split = quest_alignment_split.split_of(plan)
    if split is None:
        return False
    rows = {row.key: row for row in read.rows}
    sight = read.open_terrain()
    for key in choice.keys:
        row = rows[key]
        mark = answer._side_of(policy, row.race, split)
        if mark is None:
            continue
        others = [cell for side, cell, _vision in read.summoners if side != mark]
        if not others:
            continue
        for cell in _route(read, _flags(row), row.cell, choice.cell):
            if any(quest_exposure.game_distance(cell, other) <= quest_exposure.MAX_SPELL_RANGE
                   and quest_exposure.projectable(sight, other, cell) for other in others):
                return True
    return False


def _reachable(policy, snapshot, navigator, plan, ranked, left_alone=frozenset()) -> Choice | None:
    """The first of ``ranked`` a walk of the plan reaches (quest_room_sweep._path) and none of
    whose comers passes the other side (``_passes_the_other_side``)."""
    from hengbot import quest_room_sweep

    here = _cell(snapshot.player.position)
    read = reader(policy, snapshot, navigator, plan, left_alone)
    for choice in ranked[:200]:
        if _passes_the_other_side(policy, navigator, plan, read, choice):
            continue
        if choice.cell == here or quest_room_sweep._path(policy, navigator, plan, snapshot, {Position(*choice.cell)}):
            return choice
    return None


def still_comes(policy, snapshot, navigator, plan, choice: Choice, left_alone=frozenset()) -> bool:
    """A chosen cell kept: monsters it was chosen for, not spent, still come there, and it is not
    now refused (the plan's refusals, both sides acting)."""
    read = reader(policy, snapshot, navigator, plan, left_alone)
    rows_by_key = {row.key: row for row in read.rows}
    if choice.cell in _taken(policy, snapshot, navigator, plan) - {_cell(snapshot.player.position)}:
        return False
    if quest_alignment_split.split_of(plan) is not None and read.both_sides_act(choice.cell):
        return False
    return bool(_unspent(rows_by_key, _spent(navigator), choice.cell, read.comers(choice.cell)))


def spend(policy, snapshot, navigator, plan, choice: Choice, left_alone=frozenset()) -> None:
    """A wait on ``choice`` ran out with nothing come: each monster it waited for is from now on
    waited for only nearer than it was (``_unspent``).  ``navigator.wait_spent`` is replaced whole."""
    rows_by_key = {row.key: row for row in reader(policy, snapshot, navigator, plan, left_alone).rows}
    navigator.wait_spent = (*navigator.wait_spent, *(
        (key, quest_exposure.game_distance(choice.cell, rows_by_key[key].cell))
        for key in sorted(choice.keys) if key in rows_by_key))
