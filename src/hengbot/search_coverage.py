"""Where a search for an unseen monster has looked: one model of detection coverage.

Owner 2026-11-08 (n1-b life-348, Angband 62F, RANDOM quest 46: the quest search lapped 575
cells of x 42-176 and never came near x 1-22): 「クエストターゲットを探すには少なくとも感知範囲が
フロア全域を網羅するように歩かなければならない。」

The model.  A *floor grid* is a grid inside the outer wall that the bot does not remember as
wall (unknown ground counts: the target can stand there).  With telepathy, a point the player
stood on covers the floor grids within ``walk_radius`` of it (Grid::calc_distance,
``game_distance``): MAX_PLAYER_SIGHT (20), halved in a DARKNESS dungeon
(monster/monster-update.cpp:437 ``in_darkness ? MAX_PLAYER_SIGHT / 2 : MAX_PLAYER_SIGHT``), through
walls.  Without it the player shows only what is in view, which no disc describes: the radius is 0
and the lap keeps its sight stops (quest_target_search.draw_stops) and their view rule.
A detection cast covers its own radius around where it was cast (me_powers.revealing_casts and
the quest search's carried casts give (centre, radius) only for a cast that can show the race:
DETECT_RAD_DEFAULT 30, the powerful rod's 45, a third in a DARKNESS dungeon).

``plan`` draws the walk: the given stops (the lap's room middles and sight stops), then, while
a floor grid no stop covers lies within ``walk_radius`` of a walkable cell, the walkable cell
near it that covers the most such grids.  What no walkable cell covers is ``unreachable``: the
search's door work goes toward it first (quest_target_search); only ground the door work found
nothing toward falls back to the plain lap.

``Coverage`` is the per-lap memory of what was covered (the centres, radius each), which
quest_target_search keeps in the floor's exploration ledger so a bot restart on the same floor
resumes the lap (ExplorationLedger.search_cover).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from hengbot.model import Position, Snapshot, game_distance

MAX_PLAYER_SIGHT = 20  # system/gamevalue.h
_FLOOR_CACHE = "_search_coverage_floor"  # (key, mask) of the last floor_grids


def darkness(policy, snapshot: Snapshot) -> bool:
    """The dungeon has the DARKNESS flag (lib/edit/DungeonDefinitions.jsonc)."""
    info = getattr(policy, "_dungeon_knowledge", {}).get(snapshot.floor_key[0])
    return info is not None and "DARKNESS" in info.flags


def walk_radius(policy, snapshot: Snapshot) -> int:
    """How far telepathy shows a monster around the player, 0 without it (the module docstring)."""
    if "telepathy" not in snapshot.player.abilities:
        return 0
    return MAX_PLAYER_SIGHT // 2 if darkness(policy, snapshot) else MAX_PLAYER_SIGHT


@lru_cache(maxsize=None)
def _disc(radius: int) -> np.ndarray:
    """The (2r+1)-square mask of the offsets within ``radius`` (game_distance)."""
    side = 2 * radius + 1
    mask = np.zeros((side, side), dtype=bool)
    origin = Position(0, 0)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            mask[dy + radius, dx + radius] = game_distance(origin, Position(dy, dx)) <= radius
    return mask


def _window(shape, centre, radius):
    """(board slice, disc slice) of the disc around ``centre`` clipped to the board."""
    height, width = shape
    y0, y1 = max(0, centre[0] - radius), min(height, centre[0] + radius + 1)
    x0, x1 = max(0, centre[1] - radius), min(width, centre[1] + radius + 1)
    if y0 >= y1 or x0 >= x1:
        return None
    disc = (slice(y0 - centre[0] + radius, y1 - centre[0] + radius),
            slice(x0 - centre[1] + radius, x1 - centre[1] + radius))
    return (slice(y0, y1), slice(x0, x1)), disc


def paint(mask: np.ndarray, centre, radius: int) -> None:
    """Mark every grid of ``mask`` within ``radius`` of ``centre`` (y, x)."""
    window = _window(mask.shape, centre, radius)
    if window is not None:
        board, disc = window
        mask[board] |= _disc(radius)[disc]


def disc_left(mask: np.ndarray, centre, radius: int) -> int:
    """How many marked grids of ``mask`` lie within ``radius`` of ``centre``."""
    window = _window(mask.shape, centre, radius)
    if window is None:
        return 0
    board, disc = window
    return int(np.count_nonzero(mask[board] & _disc(radius)[disc]))


def floor_grids(policy, snapshot: Snapshot) -> np.ndarray:
    """The grids inside the outer wall the bot does not remember as wall (a copy)."""
    walls = policy._remembered_wall_t
    key = (snapshot.floor_key, snapshot.height, snapshot.width, len(walls))
    cached = getattr(policy, _FLOOR_CACHE, None)
    if cached is None or cached[0] != key:
        mask = np.zeros((snapshot.height, snapshot.width), dtype=bool)
        mask[1:-1, 1:-1] = True
        if walls:
            ys, xs = np.array(sorted(walls)).T
            inside = (ys >= 0) & (ys < snapshot.height) & (xs >= 0) & (xs < snapshot.width)
            mask[ys[inside], xs[inside]] = False
        cached = (key, mask)
        setattr(policy, _FLOOR_CACHE, cached)
    return cached[1].copy()


def covered(shape, centres) -> np.ndarray:
    """The grids within the radius of some (centre (y, x), radius)."""
    mask = np.zeros(shape, dtype=bool)
    for centre, radius in centres:
        paint(mask, centre, radius)
    return mask


@dataclass(frozen=True)
class Plan:
    stops: tuple       # Position, in drawing order
    unreachable: int   # floor grids no walkable cell covers


def plan(snapshot: Snapshot, floor: np.ndarray, cells, stops, radius: int) -> Plan:
    """``stops`` and the coverage stops after them (the module docstring)."""
    shape = floor.shape
    walkable = [cell for cell in cells if 0 <= cell.y < shape[0] and 0 <= cell.x < shape[1]]
    reach = covered(shape, (((cell.y, cell.x), radius) for cell in walkable))
    left = floor & reach & ~covered(shape, (((stop.y, stop.x), radius) for stop in stops))
    stops = list(stops)
    by_column = sorted(walkable, key=lambda cell: (cell.x, cell.y))
    while left.any():
        ys, xs = np.nonzero(left)
        first = int(np.argmin(xs * shape[0] + ys))  # the westmost, then northmost grid left
        grid = Position(int(ys[first]), int(xs[first]))
        near = [cell for cell in by_column if game_distance(cell, grid) <= radius]
        best = max(near, key=lambda cell: (disc_left(left, (cell.y, cell.x), radius), -cell.x, -cell.y))
        stops.append(best)
        window = _window(shape, (best.y, best.x), radius)
        board, disc = window
        left[board] &= ~_disc(radius)[disc]
    return Plan(tuple(stops), int(np.count_nonzero(floor & ~reach)))


@dataclass
class Coverage:
    """What this lap's walk covered: (y, x, radius) centres, and their painted mask."""
    centres: set = field(default_factory=set)
    _painted: tuple | None = field(default=None, repr=False)  # (shape, centre count, mask)

    def note(self, centre: Position, radius: int) -> None:
        key = (centre.y, centre.x, radius)
        if key not in self.centres:
            self.centres.add(key)
            if self._painted is not None:
                shape, count, mask = self._painted
                paint(mask, key[:2], radius)
                self._painted = (shape, count + 1, mask)

    def clear(self) -> None:
        self.centres.clear()
        self._painted = None

    def mask(self, shape) -> np.ndarray:
        """The covered grids (painted again only when the centres changed elsewhere)."""
        if self._painted is None or self._painted[0] != shape or self._painted[1] != len(self.centres):
            self._painted = (shape, len(self.centres), covered(
                shape, (((y, x), radius) for y, x, radius in self.centres)))
        return self._painted[2]
