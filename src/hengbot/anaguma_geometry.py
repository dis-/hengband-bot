"""Anaguma (穴熊) geometry: the zigzag pocket dug with Stone to Mud (docs/anaguma-design.md).

Pure functions over the board's known grids; no policy state.

The shape is the owner's diagram (2026-11-10, C:/hengband-backups/pdca/anaguma/
owner-zigzag-1110.png): one cell per step away from the start cell ``S`` along an
orthogonal ``axis``, alternating between two columns, so every step after the first is
diagonal and each turn is 90 degrees::

    c_k = S + k * axis + ((k + 1) % 2) * side * perp      (k = 1 .. L)

The first cell is straight ahead of ``S``; the player ends on ``P = c_L`` and the
mouth is ``M = c_(L-1)`` (``S`` when L = 1).

Game facts (C:/hengband/src, design section 1):

- one use of Stone to Mud melts the first STONE grid on its line and nothing else
  (spell-kind/spells-beam.cpp:14-18, target/projection-path-calculator.cpp:78-110,
  effect/effect-feature.cpp:232-245); each c_(k+1) is adjacent to c_k, so it is melted
  from c_k, one use per cell;
- a cell melts when its terrain has STONE: granite, magma, quartz, rubble and the doors
  (lib/edit/TerrainDefinitions.jsonc); PERMANENT never does (system/dungeon/
  dungeon-definition.cpp:40-52).  The board's ``tunnel and not permanent`` is that test;
- for k >= 2 every neighbour of c_k but c_(k-1) and c_(k+1) must stay solid: then only
  ``M`` touches ``P``, the queue is single file, and from L = 4 the next cell in line
  ``D`` has exactly two open neighbours, which is what pins a pack animal's retreat
  (design 1.7, monster-floor/monster-sweep-grid.cpp:198-273, monster/monster-info.cpp:
  132-143, monster-attack/monster-attack-processor.cpp:120-150).

Unknown grids: from a corridor the player sees only the first layer of rock; the cells two
deep are not known until a melted cell lets the light reach them.  A plan therefore presumes
an unknown grid to be rock (``presume``); the dig checks every cell again as it opens
(anaguma ``_dig_key``) and holds or ends when the presumption fails.
"""

from __future__ import annotations

from dataclasses import dataclass

from hengbot.model import Position, Snapshot
from hengbot.policy_constants import NEIGHBOR_OFFSETS

AXES = ((-1, 0), (1, 0), (0, -1), (0, 1))
SIDES = (1, -1)


@dataclass(frozen=True)
class Zigzag:
    """A planned tunnel: its start (an open cell) and its cells in digging order."""
    start: Position
    axis: tuple[int, int]
    side: int
    cells: tuple[Position, ...]

    def before(self, index: int) -> Position:
        """The cell before ``cells[index]`` on the way in (``start`` for the first)."""
        return self.start if index == 0 else self.cells[index - 1]

    def prefix(self, length: int) -> "Zigzag":
        return Zigzag(self.start, self.axis, self.side, self.cells[:length])

    @property
    def pocket(self) -> Position:
        return self.cells[-1]

    @property
    def mouth(self) -> Position:
        return self.before(len(self.cells) - 1)


def cell(start: Position, axis: tuple[int, int], side: int, index: int) -> Position:
    """c_index of the module docstring (index >= 1)."""
    perp = (axis[1], axis[0])
    offset = ((index + 1) & 1) * side  # every other cell steps sideways
    return Position(start.y + index * axis[0] + offset * perp[0],
                    start.x + index * axis[1] + offset * perp[1])


def neighbours(position: Position):
    return (Position(position.y + dy, position.x + dx) for dy, dx in NEIGHBOR_OFFSETS)


def solid(grid, presume: bool = False) -> bool:
    """A grid no monster walks through without passing or killing walls (``presume``: an
    unknown grid counts as rock)."""
    if grid is None or not grid.known:
        return presume
    return not grid.passable and not grid.is_door and not grid.is_closed_door


def diggable(grid, presume: bool = False) -> bool:
    """A grid one Stone to Mud use turns to floor (the module docstring)."""
    if grid is None or not grid.known:
        return presume
    return solid(grid) and grid.tunnel and not grid.permanent


def open_cell(grid) -> bool:
    return grid is not None and grid.known and grid.passable


def zigzag(snapshot: Snapshot, start: Position, axis, side, length: int,
           *, dug: int = 0, presume: bool = True) -> Zigzag | None:
    """The tunnel of ``length`` cells from ``start``, else None when the terrain refuses it.

    ``dug``: the first cells already melted (open floor); the rest must be diggable.  Every
    neighbour of a cell from the second on, other than its two tunnel neighbours, must be
    solid, and so must every neighbour of the last cell but the one before it."""
    if not open_cell(snapshot.grid_at(start)):
        return None
    cells = tuple(cell(start, axis, side, index) for index in range(1, length + 1))
    for index, here in enumerate(cells):
        grid = snapshot.grid_at(here)
        if not (open_cell(grid) if index < dug else diggable(grid, presume)):
            return None
    tunnel = set(cells)
    for index, here in enumerate(cells):
        if index == 0:
            continue
        allowed = {cells[index - 1]}
        if index + 1 < len(cells):
            allowed.add(cells[index + 1])
        for around in neighbours(here):
            if around in allowed:
                continue
            if around in tunnel or not solid(snapshot.grid_at(around), presume):
                return None
    return Zigzag(start, tuple(axis), side, cells)


def longest(snapshot: Snapshot, start: Position, axis, side, maximum: int,
            *, dug: int = 0, presume: bool = True) -> Zigzag | None:
    """The longest valid tunnel of at most ``maximum`` cells (None when not even one)."""
    best = None
    for length in range(max(1, dug), maximum + 1):
        found = zigzag(snapshot, start, axis, side, length, dug=dug, presume=presume)
        if found is None:
            break
        best = found
    return best


def pocket_holds(snapshot: Snapshot, pocket: Position, mouth: Position,
                 presume: bool = False) -> bool:
    """``pocket`` is open and ``mouth`` is its only open (non-solid) neighbour."""
    if not open_cell(snapshot.grid_at(pocket)):
        return False
    return all(around == mouth or solid(snapshot.grid_at(around), presume)
               for around in neighbours(pocket))
