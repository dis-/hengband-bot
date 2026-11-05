"""Where a staircase really leads: the one reading of a stair's destination.

src/cmd-action/cmd-move.cpp do_cmd_go_down and src/floor/floor-leaver.cpp
jump_floors: a stair moves one floor and a shaft (SHAFT terrain,
FloorChangeMode::SHAFT, ``move_num *= 2``) exactly two.  A descent is not
clamped.  alloc_stairs generates a down shaft only above the dungeon's last
two floors and only when the next floor holds no quest, so a shaft on 4F leads
straight onto a random quest on 6F (n1-b life-313, 2026-11-05).  A connected
stair keeps the shaft terrain of the way it was reached.

On the surface '>' enters the dungeon of the ENTRANCE tile, and any other down
stair of the surface enters Angband (do_cmd_go_down).
"""

from hengbot.model import DUNGEON_ANGBAND

# lib/edit/TerrainDefinitions.jsonc: SHAFT_UP (13) and SHAFT_DOWN (14).
SHAFT_TERRAIN_IDS = frozenset({13, 14})


def stair_floors(grid) -> int:
    """The floors the stair on ``grid`` moves (an ordinary staircase when None)."""
    return 2 if grid is not None and grid.terrain_id in SHAFT_TERRAIN_IDS else 1


def down_destination(current_level: int, grid) -> int:
    """The floor '>' on ``grid`` lands on from dungeon floor ``current_level``."""
    return current_level + stair_floors(grid)


def surface_dungeon(grid) -> int | None:
    """The dungeon '>' on this surface tile enters; a quest entrance enters none."""
    if grid.has_quest_enter:
        return None
    return grid.entrance_dungeon_id if grid.has_entrance else DUNGEON_ANGBAND
