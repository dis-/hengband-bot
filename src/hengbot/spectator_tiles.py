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
standard symbol. The frame's unique on-map '@' anchors its panel; a received
state panel must agree with that anchor. Ambiguous screens have no tiles.
``map`` is [floor row, floor column] of the origin cell plus the floor's
dungeon level and quest ID: Original32 picks floor/wall variants from the
floor coordinates and the game's floor seed (original-tiles.cpp floor_seed).
``palette_ext`` (present only when some entry has one) is parallel to
``palette``: for an entry whose top visible item has a found_item_ids record,
[sval, flavor_id, artifact_id] (each null when the game did not print it),
else null. The Original32 tiles (tiles=3/4) select item pictures from it; the
5-field palette entries stay unchanged for the 8x8/16x16 page code.
Nothing in the decision path imports this module.
"""

import unicodedata
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


# The character sheet's sex titles (src/player/player-sex.cpp sex_info, both
# languages) and their player_sex IDs (SEX_FEMALE 0, SEX_MALE 1).
_SEX_TITLES = {"女性": 0, "Female": 0, "男性": 1, "Male": 1}


def spectator_tile_player(class_id, sex_title) -> dict:
    """Class ID and, once the bot has read the C screen, sex ID for Original32."""
    result = {}
    if type(class_id) is int and 0 <= class_id < len(_CLASSES):
        result["class_id"] = class_id
    if sex_title in _SEX_TITLES:
        result["sex_id"] = _SEX_TITLES[sex_title]
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


GOLD_TVAL = 127


def _top_item_identity(found_records, tvals):
    """The found_item_ids record of the cell's top visible item, or None.

    found_items/found_item_ids list the non-gold stacks in the same order as
    the visible tvals ("t"), so the first visible non-gold item is the first
    record; a gold top item or any disagreement between the lists has none.
    """
    if not tvals or tvals[0] == GOLD_TVAL:
        return None
    tvals_found, records = found_records
    if not tvals_found or not records or tvals_found[0] != tvals[0]:
        return None
    record = records[0]
    if not isinstance(record, Mapping):
        return None
    identity = tuple(record.get(key) if type(record.get(key)) is int else None
                     for key in ("sval", "flavor_id", "artifact_id"))
    return identity if any(value is not None for value in identity) else None


def _found_item_records(grid_map):
    """(y, x) -> (non-gold tvals, identity records) from the same received map."""
    tvals = {(row[0], row[1]): row[3:] for row in grid_map.get("found_items", ())
             if isinstance(row, list) and len(row) >= 3}
    return {(row[0], row[1]): (tvals.get((row[0], row[1]), []), row[2:])
            for row in grid_map.get("found_item_ids", ())
            if isinstance(row, list) and len(row) >= 2}


def _encode_index(index, width):
    digits = []
    for _ in range(width):
        digits.append(INDEX_ALPHABET[index % 64])
        index //= 64
    return "".join(reversed(digits))


def _screen_cells(line):
    """Yield (screen column, glyph); wide glyphs take two cells (bot-screen.cpp:67-73)."""
    col = 0
    for glyph in line:
        yield col, glyph
        col += 2 if unicodedata.east_asian_width(glyph) in {"W", "F"} else 1


def _screen_panel(state, screen):
    """Resolve only this frame's anchor, never a previous frame's offset."""
    # The side panel holds wide glyphs (腕力, 知能, ...), so a string index is not a screen column.
    anchors = [(row, col)
               for row, line in enumerate(screen.get("lines", ())[:screen["height"] - 1])
               if row >= ROW_MAP
               for col, glyph in _screen_cells(line)
               if COL_MAP <= col < screen["width"] and glyph == "@"]
    if len(anchors) != 1:
        return None, "player_glyph_count"
    player = state.get("player", {})
    if any(type(player.get(axis)) is not int for axis in ("y", "x")):
        return None, "player_position"
    row, col = anchors[0]
    derived = {"row_min": player["y"] - (row - ROW_MAP),
               "col_min": player["x"] - (col - COL_MAP)}
    panel = state.get("panel")
    if panel is None:
        return derived, "derived"
    if not isinstance(panel, Mapping) or any(
            type(panel.get(key)) is not int or panel[key] != value
            for key, value in derived.items()):
        return None, "mismatch"
    return panel, "state"


def spectator_tiles(state: Mapping[str, object], screen: Mapping[str, object],
                    *, panel_counts=None) -> dict | None:
    """Copy received cells; optionally count panel outcomes per projection attempt."""
    panel, outcome = _screen_panel(state, screen)
    if panel_counts is not None:
        panel_counts[outcome] = panel_counts.get(outcome, 0) + 1
    if panel is None:
        return None
    height = max(0, screen["height"] - 2)
    width = max(0, screen["width"] - COL_MAP)
    y0, x0 = panel["row_min"], panel["col_min"]
    terrain = _terrain_on_screen(state, y0, x0, height, width)
    cells = {(cell["y"], cell["x"]): cell
             for cell in state.get("grid_map", {}).get("cells", ())}
    item_records = _found_item_records(state.get("grid_map", {}))
    monsters = {monster["index"]: monster for field in
                ("visible_monsters", "detected_monsters")
                for monster in state.get(field, ())}
    player = state.get("player", {})
    hallucinated = player.get("status", {}).get("hallucinated", False)
    player_pos = (player.get("y"), player.get("x"))
    palette, extensions, indices, rows = [], [], {}, []
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
            identity = (None if tval is None or (y, x) not in item_records
                        else _top_item_identity(item_records[y, x], tvals))
            entry = (*terrain[y, x], race, tval, (y, x) == player_pos, identity)
            if entry not in indices:
                indices[entry] = len(palette)
                palette.append(list(entry[:5]))
                extensions.append(None if identity is None else list(identity))
            row.append(indices[entry])
        rows.append(row)
    index_width = 1
    while len(palette) > 64 ** index_width:
        index_width += 1
    symbols = [_encode_index(index, index_width) for index in range(len(palette))]
    floor = state.get("floor", {})
    floor = floor if isinstance(floor, Mapping) else {}
    level, quest = (floor.get(key) for key in ("level", "quest_id"))
    result = {"origin": [ROW_MAP, COL_MAP],
              "map": [y0, x0, level if type(level) is int else 0,
                      quest if type(quest) is int else 0],
              "palette": palette,
              "rows": ["".join("." * index_width if index is None else symbols[index]
                               for index in row) for row in rows]}
    if index_width > 1:
        result["index_width"] = index_width
    if any(extension is not None for extension in extensions):
        result["palette_ext"] = extensions
    return result
