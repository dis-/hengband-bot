"""Whether an up staircase leaves the dungeon for the open wilderness.

Going up from a floor whose ``dun_level - climb`` is below the dungeon's
``mindepth`` lands on the surface (src/floor/floor-leaver.cpp:335-338) at the
dungeon's entrance tile (``exit_to_wilderness``).  That tile is a town only
for a dungeon entered from a town (Yeek cave, Outpost); for every other
dungeon such a '<' puts the player in the wilderness, which the bot must
never enter -- it returns to town by recall (live 2026-10-02 11:50: Castle
20F, ``status-threat:stairs``).

An up shaft climbs two floors (STAIRS + SHAFT terrain, FloorChangeMode::SHAFT,
``move_num *= 2``), so on the floor below the top it lands on the surface too
(輪6, #47, n1-c life-059: the '<' on 鉄獄2階 [5,62] was SHAFT_UP).
"""

from hengbot.stair_destination import SHAFT_TERRAIN_IDS, stair_floors  # noqa: F401

# src/floor/wild.cpp change_wild_mode: an awake hostile monster within
# MAX_PLAYER_SIGHT (seen or not) refuses the global map without a turn.
GLOBAL_MAP_REFUSED_MESSAGES = (
    "敵がすぐ近くにいるときは広域マップに入れない！",
    "You cannot enter global map, since there are some monsters nearby!",
)


def global_map_refused(snapshot) -> bool:
    """Whether this board reports the refused '<' to the global map."""
    return any(message.startswith(GLOBAL_MAP_REFUSED_MESSAGES)
               for message in snapshot.messages)


def up_stairs_exit_to_wilderness(floor_key, dungeon_knowledge, wilderness_map, grid=None) -> bool:
    """Whether '<' on ``grid`` (an ordinary staircase when None) reaches the wilderness.

    Unknown floor, dungeon or map answers False (the previous behaviour).
    """
    if not entrance_is_wilderness(floor_key, dungeon_knowledge, wilderness_map):
        return False
    return floor_key[1] - stair_floors(grid) < dungeon_knowledge[floor_key[0]].min_depth


def entrance_is_wilderness(floor_key, dungeon_knowledge, wilderness_map) -> bool:
    """Whether this dungeon's top leads to the wilderness instead of a town.

    Then no staircase walk from any of its floors ends in town: it would only
    reach the top floor and read Recall there (loop 3, #47).
    Unknown floor, dungeon or map answers False (the previous behaviour).
    """
    if floor_key is None:
        return False
    dungeon_id, level, _quest = floor_key
    if dungeon_id <= 0 or level <= 0:
        return False
    info = dungeon_knowledge.get(dungeon_id)
    if info is None or wilderness_map is None:
        return False
    y, x = getattr(info, "wild_y", None), getattr(info, "wild_x", None)
    if y is None or x is None:
        return False
    rows = wilderness_map.rows
    cell = rows[y][x] if 0 <= y < len(rows) and 0 <= x < len(rows[y]) else ""
    return not (cell.isdigit() and cell != "0")
