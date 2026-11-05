"""What a magic mapping (周辺感知) showed, as exploration knowledge (#47).

Owner 2026-11-01: 「周辺感知を取り込んだあとはマップを全マス捜索する必要はまったくない。
もう少し効率化できないだろうか」 -> 「部屋だけ見て回る」 (memory
mapped-area-rooms-only-decision-20261101): inside the mapped area corridors and
dead ends count as explored and are not walked; a room is visited only until
its inside was seen (from the entrance or inside); the rest of the exploration
goes to the unmapped area and to the stairs.

Game facts.  map_area (spell-kind/spells-floor.cpp) gives every grid within
``range`` (Grid::calc_distance from the caster; a third in a DARKNESS dungeon)
CAVE_KNOWN, and CAVE_MARK to its REMEMBER terrain and REMEMBER neighbours, on
the mimic terrain (a secret door maps as granite).  Floors are not marked, so
the map shows walls, doors, rubble and stairs and leaves the floor blank.  The
terrains without REMEMBER (lib/edit/TerrainDefinitions.jsonc: FLOOR, the
invisible trap that mimics it, DIRT, GRASS, GLASS_FLOOR) are all MOVE, so a
blank grid inside the range is walkable floor: what the player reads off the
map, nothing more (fair play).

Rooms and corridors.  The board carries no CAVE_ROOM.  A dungeon tunnel is one
grid wide and a room's edge grid has five floor neighbours
(``me_powers.OPEN_SPACE_NEIGHBOURS``, the dark-room trigger's reading), so a
blank or seen-floor grid with that many open neighbours is inside an open
space; those grids and their open neighbours are the room, and every other
blank grid is corridor.  A two-wide passage reads as a room (it is walked as
before); a closet one grid wide reads as a dead end.

Sources.  ``SOURCES`` lists who knows where a mapping was cast on this floor
visit: the Magic-Eater's absorbed staff (``me_powers``) and the floor's
exploration ledger, which keeps every disc across a bot restart on the same
floor and forgets them on a new floor (owner 2026-11-01 「階の記録に残す」,
``refresh`` writes the discs there), and a carried staff or rod (area_mapping).
A scroll of the same effect is the carried source's last means, and is read when picked up (area_mapping).

Owner 2026-11-05 「ランダムクエストの階だけ特殊な探索ルールにしているのをやめる。地図がわかって
いるなら全マス歩かない。」: a runtime RANDOM quest floor reads the map as any floor does.  A
fixed quest floor keeps its own exploration, its plan's navigator (the area is not applied there).
"""

from __future__ import annotations

from dataclasses import dataclass

from hengbot import area_mapping, me_powers
from hengbot.model import Position, game_distance
from hengbot.policy_constants import NEIGHBOR_OFFSETS


ATTR = "_mapped_area"


def _ledger(policy, snapshot):
    """The exploration ledger bound to this floor, else None."""
    ledger = getattr(policy, "_exploration_ledger", None)
    return ledger if ledger is not None and ledger.floor_key == snapshot.floor_key else None


def recorded_areas(policy, snapshot) -> tuple:
    """(centre, radius) of the discs the floor's ledger kept (an earlier bot
    session's mappings on this floor)."""
    ledger = _ledger(policy, snapshot)
    return () if ledger is None else tuple(
        (Position(y, x), radius) for y, x, radius in ledger.mapped_areas)


# (centre, radius) of each mapping cast on the current floor visit.
SOURCES = (me_powers.mapped_areas, recorded_areas, area_mapping.carried_areas)

Cell = tuple[int, int]


@dataclass(frozen=True)
class MappedArea:
    floor: tuple
    discs: tuple
    cells: frozenset      # every grid within a disc
    corridor: frozenset   # blank corridor grids: walkable floor, explored

    def covers(self, key: Cell) -> bool:
        return key in self.cells

    def explored(self, known: set) -> set:
        """Corridor grids and every grid of the area already seen."""
        return set(self.corridor) | (self.cells & known)

    def walkable(self, known: set, blocked: set) -> set:
        """Blank corridor grids the router may cross (a seen or bumped grid
        keeps what was seen)."""
        return set(self.corridor) - known - blocked


def current(policy) -> MappedArea | None:
    return getattr(policy, ATTR, None)


def covers(policy, key: Cell) -> bool:
    area = current(policy)
    return area is not None and area.covers(key)


def disc_cells(snapshot, centre: Position, radius: int) -> set:
    # get_area(OUTER_WALL_EXCLUSIVE): the permanent outer wall is not scanned.
    return {
        (y, x)
        for y in range(max(1, centre.y - radius), min(snapshot.height - 1, centre.y + radius + 1))
        for x in range(max(1, centre.x - radius), min(snapshot.width - 1, centre.x + radius + 1))
        if game_distance(centre, Position(y, x)) <= radius
    }


def _open_neighbours(cell: Cell, open_cells: set) -> list:
    y, x = cell
    return [(y + dy, x + dx) for dy, dx in NEIGHBOR_OFFSETS if (y + dy, x + dx) in open_cells]


def _corridor(blank: set, seen_floor: set) -> frozenset:
    """Blank grids outside every open space (see the module docstring)."""
    open_cells = blank | seen_floor
    room = set()
    for cell in open_cells:
        neighbours = _open_neighbours(cell, open_cells)
        if len(neighbours) >= me_powers.OPEN_SPACE_NEIGHBOURS:
            room.add(cell)
            room.update(neighbours)
    return frozenset(blank - room)


def build(snapshot, discs: tuple, known: set, seen_floor: set, nothing_left: set = frozenset()) -> MappedArea:
    """``nothing_left``: grids whose blanks are explored even in an open space."""
    cells = set()
    for centre, radius in discs:
        cells |= disc_cells(snapshot, centre, radius)
    blank = cells - known
    return MappedArea(snapshot.floor_key, discs, frozenset(cells),
                      _corridor(blank, seen_floor) | (blank & nothing_left))


def floor_discs(policy, snapshot) -> tuple:
    """Every live mapping of this floor visit, as (centre, radius)."""
    return tuple(sorted({disc for source in SOURCES for disc in source(policy, snapshot)}))


def _fixed_quest_floor(policy, snapshot) -> bool:
    return snapshot.floor_key[2] != 0 and not policy._on_random_quest_floor(snapshot)


def refresh(policy, snapshot, known: set, seen_floor: set) -> MappedArea | None:
    """The area of this floor visit's mappings, rebuilt when a cast is added.

    ``known`` is every grid the board has shown on this visit and
    ``seen_floor`` the walkable ones among them (navigation's remembered
    sets).  The classification is made once per cast, from the board that
    first carried the mapped walls.
    """
    discs = () if _fixed_quest_floor(policy, snapshot) or snapshot.dungeon_level <= 0 else floor_discs(
        policy, snapshot)
    ledger = _ledger(policy, snapshot)
    if ledger is not None:
        ledger.note_mapped_areas((centre.y, centre.x, radius) for centre, radius in discs)
    area = current(policy)
    if not discs:
        area = None
    elif area is None or area.floor != snapshot.floor_key or area.discs != discs:
        area = build(snapshot, discs, known, seen_floor, area_mapping.destroyed_cells(policy, snapshot))
    setattr(policy, ATTR, area)
    return area
