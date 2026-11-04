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

So a shriek reaches a player the caster cannot see, from a cell beside him (``SHOUT``);
a pull needs the direct line (``PULL``).  Recorded n1-a (2026-11-04 18:40) took 47 shrieks
standing on [4,13], which no siren has a line to: the siren at [6,14] reaches [4,14].

``projection_path`` is the port of the game's rasterizer; terrain is the quest map's.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass

from hengbot.model import Position
from hengbot.projection_path import projection_path

MAX_SPELL_RANGE = 18  # AngbandSystem::get_max_range
_PROJECTING_KINDS = frozenset({"floor", "exit", "shallow_water", "deep_water", "passage", "tree"})
_WALKABLE_KINDS = frozenset({"floor", "exit", "shallow_water", "deep_water", "passage"})
_NEIGHBOURS = tuple((dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0))


def game_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Grid::calc_distance."""
    dy, dx = abs(a[0] - b[0]), abs(a[1] - b[1])
    return max(dy, dx) + min(dy, dx) // 2


def _projects(terrain) -> set[tuple[int, int]]:
    return {cell for cell, kind in terrain.items() if kind in _PROJECTING_KINDS}


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


def exposure_map(terrain, casters) -> Exposure:
    """``casters``: the cells of the never-moving casters."""
    open_cells = _projects(terrain)
    pull: dict[tuple[int, int], set] = {}
    shout: dict[tuple[int, int], set] = {}
    for caster in casters:
        direct = {cell for cell in open_cells
                  if game_distance(caster, cell) <= MAX_SPELL_RANGE
                  and projectable(terrain, caster, cell)}
        for cell in open_cells:
            if game_distance(caster, cell) > MAX_SPELL_RANGE:
                continue
            if cell in direct:
                pull.setdefault(cell, set()).add(caster)
                shout.setdefault(cell, set()).add(caster)
            elif any((cell[0] + dy, cell[1] + dx) in direct for dy, dx in _NEIGHBOURS):
                shout.setdefault(cell, set()).add(caster)
    return Exposure({cell: frozenset(found) for cell, found in pull.items()},
                    {cell: frozenset(found) for cell, found in shout.items()})


def least_exposed_path(
    terrain, exposure: Exposure, start: tuple[int, int], goals, blocked=frozenset(),
) -> list[tuple[int, int]]:
    """The 8-way walk with the fewest exposed cells, then the fewest steps.

    Pulled cells count before cells a shriek only reaches: among equal counts of exposed
    cells a walk that cannot be pulled is the better one.
    """
    goals = set(goals)
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
            step = (cost[0] + int(exposure.exposed(nxt)), cost[1] + int(nxt in exposure.pull),
                    cost[2] + 1)
            if nxt not in best or step < best[nxt]:
                best[nxt] = step
                previous[nxt] = cell
                heapq.heappush(queue, (step, nxt))
    return []
