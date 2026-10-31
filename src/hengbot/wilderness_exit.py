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

# lib/edit/TerrainDefinitions.jsonc: SHAFT_UP (13) and SHAFT_DOWN (14).
SHAFT_TERRAIN_IDS = frozenset({13, 14})

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
    if floor_key is None:
        return False
    dungeon_id, level, _quest = floor_key
    if dungeon_id <= 0 or level <= 0:
        return False
    info = dungeon_knowledge.get(dungeon_id)
    if info is None or wilderness_map is None:
        return False
    climb = 2 if grid is not None and grid.terrain_id in SHAFT_TERRAIN_IDS else 1
    if level - climb >= info.min_depth:
        return False
    y, x = getattr(info, "wild_y", None), getattr(info, "wild_x", None)
    if y is None or x is None:
        return False
    rows = wilderness_map.rows
    cell = rows[y][x] if 0 <= y < len(rows) and 0 <= x < len(rows[y]) else ""
    return not (cell.isdigit() and cell != "0")
