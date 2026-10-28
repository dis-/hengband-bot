"""Viewer-only tile projection of one received state, clipped to its screen.

``origin`` is the screen [row, column], always [1, 13] (no bigtile).
Palette entries are [mimic terrain ID, lighting symbol (0 standard, 1 lite,
2 dark), apparent monster race ID or null, top item tval or null, is_player].
Rows use ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/
as zero-based palette indices; '.' is an unknown terrain cell. Normally each
cell takes one character. Above 64 entries, ``index_width`` gives the fixed
number of base-64 digits per cell (most significant first); an empty cell is
that many dots. Absent index_width means 1. No palette size is truncated.

Only grid_map runs from this state supply terrain, never remembered policy
maps, found_items, look results, or another frame. Lighting is the emitter's
canonical *symbol* index, not physical illumination. Legacy protocols use the
standard symbol. Without this state's panel there is no tile projection.
Nothing in the decision path imports this module.
"""

from collections.abc import Mapping

from hengbot.protocol import PROTOCOL_SCREEN_PARITY, grid_lighting

INDEX_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
ROW_MAP, COL_MAP = 1, 13

# Stable player IDs and English pref condition names: Hengband
# src/player/race-info-table.cpp and src/player-info/class-info.cpp;
# lib/pref/xtra-xxx.prf uses these same $RACE/$CLASS spellings.
_RACES = (
    "Human", "Half-Elf", "Elf", "Hobbit", "Gnome", "Dwarf", "Half-Orc",
    "Half-Troll", "Amberite", "High-Elf", "Barbarian", "Half-Ogre",
    "Half-Giant", "Half-Titan", "Cyclops", "Yeek", "Klackon", "Kobold",
    "Nibelung", "Dark-Elf", "Draconian", "Mindflayer", "Imp", "Golem",
    "Skeleton", "Zombie", "Vampire", "Spectre", "Sprite", "Beastman", "Ent",
    "Archon", "Balrog", "Dunadan", "Shadow-Fairy", "Kutar", "Android", "Merfolk",
)
_CLASSES = (
    "Warrior", "Mage", "Priest", "Rogue", "Ranger", "Paladin", "Warrior-Mage",
    "Chaos-Warrior", "Monk", "Mindcrafter", "High-Mage", "Tourist", "Imitator",
    "BeastMaster", "Sorcerer", "Archer", "Magic-Eater", "Bard", "Red-Mage",
    "Samurai", "ForceTrainer", "Blue-Mage", "Cavalry", "Berserker",
    "Weaponsmith", "Mirror-Master", "Ninja", "Sniper", "Elementalist",
)


def spectator_player(player: Mapping[str, object]) -> dict:
    """Pref names from received IDs; leave an unknown identity unspecified."""
    result = {}
    for field, names in (("race", _RACES), ("class", _CLASSES)):
        index = player.get(field + "_id")
        if type(index) is int and 0 <= index < len(names):
            result[field] = names[index]
    return result


def _terrain_on_screen(state, y0, x0, height, width):
    grid_map = state.get("grid_map", {})
    terrain = {}
    for y, x, length, index in grid_map.get("runs", ()):
        if not y0 <= y < y0 + height:
            continue
        terrain_id, lighting, _, known = grid_map["palette"][index]
        if not known:
            continue
        lighting = (grid_lighting(lighting) if state.get("protocol_version", 2)
                    >= PROTOCOL_SCREEN_PARITY else 0)
        for col in range(max(x, x0), min(x + length, x0 + width)):
            terrain[y, col] = (terrain_id, lighting)
    return terrain


def _encode_index(index, width):
    digits = []
    for _ in range(width):
        digits.append(INDEX_ALPHABET[index % 64])
        index //= 64
    return "".join(reversed(digits))


def spectator_tiles(state: Mapping[str, object], screen: Mapping[str, object]) -> dict | None:
    """Copy only received, on-screen cells using this state's panel offset."""
    panel = state.get("panel")
    if not isinstance(panel, Mapping):
        return None
    height = max(0, screen["height"] - 2)
    width = max(0, screen["width"] - COL_MAP)
    y0, x0 = panel["row_min"], panel["col_min"]
    terrain = _terrain_on_screen(state, y0, x0, height, width)
    cells = {(cell["y"], cell["x"]): cell
             for cell in state.get("grid_map", {}).get("cells", ())}
    monsters = {monster["index"]: monster for field in
                ("visible_monsters", "detected_monsters")
                for monster in state.get(field, ())}
    player = state.get("player", {})
    hallucinated = player.get("status", {}).get("hallucinated", False)
    player_pos = (player.get("y"), player.get("x"))
    palette, indices, rows = [], {}, []
    for y in range(y0, y0 + height):
        row = []
        for x in range(x0, x0 + width):
            if (y, x) not in terrain:
                row.append(None)
                continue
            cell = cells.get((y, x), {})
            monster = monsters.get(cell.get("m"), {})
            race = None if hallucinated or monster.get("hallucinated") else monster.get("race_id")
            if type(race) is not int or race <= 0:
                race = None
            tvals = cell.get("t", ())
            tval = tvals[0] if tvals and not hallucinated else None
            entry = (*terrain[y, x], race, tval, (y, x) == player_pos)
            if entry not in indices:
                indices[entry] = len(palette)
                palette.append(list(entry))
            row.append(indices[entry])
        rows.append(row)
    index_width = 1
    while len(palette) > 64 ** index_width:
        index_width += 1
    symbols = [_encode_index(index, index_width) for index in range(len(palette))]
    result = {"origin": [ROW_MAP, COL_MAP], "palette": palette,
              "rows": ["".join("." * index_width if index is None else symbols[index]
                               for index in row) for row in rows]}
    if index_width > 1:
        result["index_width"] = index_width
    return result
