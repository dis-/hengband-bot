"""Which cells of a fixed quest map a never-moving caster's spells reach.

Owner 2026-11-04, Q18: 「叫びを受ける位置を特定して可能な限り避ける」.

The game's rule (C:/hengband/src), which a plain line of sight does not give:

 * make_attack_spell refuses beyond the maximum range, 18 (mspell-attack.cpp:320,
   angband-system.cpp:47; distance as Grid::calc_distance, the long axis plus half the
   short one).
 * decide_lite_projection (mspell-lite.cpp:209): the spell goes on when the caster can
   ``projectable`` the player's cell, OR, through adjacent_grid_check, one of the eight
   cells beside the player that has the PROJECTION terrain.  In that second case the
   spell is aimed at that neighbour.
 * check_thrown_mspell (mspell-attack.cpp:211): an aimed-off spell still goes when it
   needs no direct line.  SHRIEK is not in its list, TELE_TO is.

So a shriek reaches a player the caster cannot see, from a cell beside him (``shout``);
a pull needs the direct line to the player's own cell (``pull``).  A sleeping caster casts
nothing (awake_monster, monster-processor.cpp, returns before any spell), so both maps
are conservative; a caster's range is ``cdis`` (monster-update.cpp, the distance below).  Recorded n1-a (2026-11-04 18:40) took 47 shrieks
standing on [4,13], which no siren has a line to: the siren at [6,14] reaches [4,14].

``projection_path`` is the port of the game's rasterizer; terrain is the quest map's.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass

from hengbot.model import Position
from hengbot.projection_path import projection_path

MAX_SPELL_RANGE = 18  # AngbandSystem::get_max_range
PROJECTING_KINDS = frozenset({"floor", "exit", "shallow_water", "deep_water", "passage", "tree"})
_WALKABLE_KINDS = frozenset({"floor", "exit", "shallow_water", "deep_water", "passage"})
_NEIGHBOURS = tuple((dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0))


def game_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Grid::calc_distance."""
    dy, dx = abs(a[0] - b[0]), abs(a[1] - b[1])
    return max(dy, dx) + min(dy, dx) // 2


def _projects(terrain) -> set[tuple[int, int]]:
    return {cell for cell, kind in terrain.items() if kind in PROJECTING_KINDS}


def projectable(terrain, source: tuple[int, int], target: tuple[int, int]) -> bool:
    """target/projection-path-calculator.cpp ``projectable``."""
    open_cells = _projects(terrain)
    path = projection_path(
        Position(*source), Position(*target), MAX_SPELL_RANGE,
        lambda pos: (pos.y, pos.x) not in open_cells)
    return not path or path[-1] == Position(*target)


@dataclass(frozen=True)
class Exposure:
    """Per cell, the casters that reach it."""
    pull: dict[tuple[int, int], frozenset[tuple[int, int]]]
    shout: dict[tuple[int, int], frozenset[tuple[int, int]]]

    def exposed(self, cell: tuple[int, int]) -> bool:
        return bool(self.shout.get(cell))


def exposure_map(terrain, casters, *, pullers=None, aimed_off_reach=None) -> Exposure:
    """``casters``: the cells of the never-moving casters.

    ``pullers``: the casters whose direct line pulls (TELE_TO); None, all of them.
    ``aimed_off_reach``: per caster cell, the farthest player a spell aimed at a neighbour
    reaches; None or absent, the whole spell range.  decide_process_continue
    (monster-processor.cpp:708) processes a monster within its ``aaf`` (the race's
    ``vision``), or within MAX_PLAYER_SIGHT 20 with its own cell in the player's view
    (``has_los_at``).  A player the caster has no line to does not see the caster either,
    so beyond ``vision`` such a caster does not act at all: a shrieker 40 (vision 4) shrieks
    from farther only along its direct line; a siren 1272 (vision 20) everywhere in range.
    """
    open_cells = _projects(terrain)
    pull: dict[tuple[int, int], set] = {}
    shout: dict[tuple[int, int], set] = {}
    for caster in casters:
        pulls = pullers is None or caster in pullers
        aimed_off = min(MAX_SPELL_RANGE, (aimed_off_reach or {}).get(caster, MAX_SPELL_RANGE))
        direct = {cell for cell in open_cells
                  if game_distance(caster, cell) <= MAX_SPELL_RANGE
                  and projectable(terrain, caster, cell)}
        for cell in open_cells:
            distance = game_distance(caster, cell)
            if distance > MAX_SPELL_RANGE:
                continue
            if cell in direct:
                if pulls:
                    pull.setdefault(cell, set()).add(caster)
                shout.setdefault(cell, set()).add(caster)
            elif distance <= aimed_off and any(
                    (cell[0] + dy, cell[1] + dx) in direct for dy, dx in _NEIGHBOURS):
                shout.setdefault(cell, set()).add(caster)
    return Exposure({cell: frozenset(found) for cell, found in pull.items()},
                    {cell: frozenset(found) for cell, found in shout.items()})


def can_reach(terrain, flags, source: tuple[int, int], player: tuple[int, int]) -> bool:
    """A monster with these race ``flags`` has a walk from ``source`` to beside ``player``.

    monster_can_cross_terrain (monster-info.cpp:42): an AQUATIC one stays on water, one
    that neither swims nor flies stays out of deep water; walls and rubble stop all but
    the ones that pass or eat them.
    """
    if {"PASS_WALL", "KILL_WALL"} & flags:
        return True
    if "AQUATIC" in flags and "CAN_FLY" not in flags:
        allowed = {"shallow_water", "deep_water"}
    elif {"CAN_SWIM", "CAN_FLY"} & flags:
        allowed = _WALKABLE_KINDS
    else:
        allowed = _WALKABLE_KINDS - {"deep_water"}
    seen, pending = {source}, [source]
    while pending:
        cell = pending.pop()
        if game_distance(cell, player) <= 1 and max(abs(cell[0] - player[0]), abs(cell[1] - player[1])) <= 1:
            return True
        for dy, dx in _NEIGHBOURS:
            nxt = (cell[0] + dy, cell[1] + dx)
            if nxt not in seen and terrain.get(nxt) in allowed:
                seen.add(nxt)
                pending.append(nxt)
    return False


def least_exposed_path(
    terrain, exposure: Exposure, start: tuple[int, int], goals, blocked=frozenset(),
    *, forbidden=frozenset(),
) -> list[tuple[int, int]]:
    """The 8-way walk with the fewest exposed cells, then the fewest steps, never onto
    ``forbidden``.  With nothing forbidden (the way back of a player already pulled), the
    fewest pull cells come first.

    Owner 2026-11-04 「テレポートバックは確実に避けるべき」: callers forbid the pull cells.
    """
    goals = set(goals)
    blocked = frozenset(blocked) | frozenset(forbidden)
    pull_first = not forbidden
    best = {start: (0, 0, 0)}
    previous: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    queue = [((0, 0, 0), start)]
    while queue:
        cost, cell = heapq.heappop(queue)
        if cost != best[cell]:
            continue
        if cell in goals:
            path = []
            while cell is not None:
                path.append(cell)
                cell = previous[cell]
            return path[::-1]
        for dy, dx in _NEIGHBOURS:
            nxt = (cell[0] + dy, cell[1] + dx)
            if terrain.get(nxt) not in _WALKABLE_KINDS or nxt in blocked:
                continue
            step = (cost[0] + int(nxt in exposure.pull) if pull_first else cost[0],
                    cost[1] + int(exposure.exposed(nxt)), cost[2] + 1)
            if nxt not in best or step < best[nxt]:
                best[nxt] = step
                previous[nxt] = cell
                heapq.heappush(queue, (step, nxt))
    return []
