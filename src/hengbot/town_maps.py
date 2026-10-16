"""Static town maps loaded from Hengband's JSONC town definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Mapping

from hengbot.model import Position
from hengbot.monrace_knowledge import _strip_jsonc


_WALKABLE_CHARS = frozenset(".,<>")
_STORE_TERRAINS = {
    "GENERAL_STORE": 0, "ARMOURY": 1, "WEAPON_SMITHS": 2,
    "TEMPLE": 3, "ALCHEMY_SHOP": 4, "MAGIC_SHOP": 5,
    "BLACK_MARKET": 6, "HOME": 7,
}
_EQU_CONDITION = re.compile(r"^\[EQU\s+\$([A-Z_0-9]+)\s+([0-9 ]+)\]$")


@dataclass(frozen=True)
class TownMap:
    name: str
    width: int
    height: int
    walkable: frozenset[Position]
    stores: dict[int, Position] = field(default_factory=dict)  # store_type -> entrance
    buildings: dict[int, Position] = field(default_factory=dict)
    quest_buildings: dict[int, frozenset[Position]] = field(default_factory=dict)
    quest_entrances: dict[int, frozenset[Position]] = field(default_factory=dict)
    reward_positions: frozenset[Position] = frozenset()
    entrance: Position | None = None  # the '>' dungeon entrance the town wraps

    def is_walkable(self, position: Position) -> bool:
        return position in self.walkable

    def store_position(self, store_type: int) -> Position | None:
        return self.stores.get(store_type)

    def building_position(self, building_type: int) -> Position | None:
        return self.buildings.get(building_type)

    def quest_building_positions(self, quest_id: int) -> frozenset[Position]:
        return self.quest_buildings.get(quest_id, frozenset())

    def quest_entrance_positions(self, quest_id: int) -> frozenset[Position]:
        return self.quest_entrances.get(quest_id, frozenset())


def _jsonc(path: Path) -> dict:
    data = json.loads(_strip_jsonc(path.read_text(encoding="utf-8-sig")))
    if not isinstance(data, dict):
        raise ValueError(f"invalid JSONC town definition: {path}")
    return data


def _condition_matches(condition: str | None, quest_statuses: Mapping[int, int]) -> bool:
    if condition is None:
        return True
    match = _EQU_CONDITION.fullmatch(condition.strip())
    if match is None:
        # Hengband treats malformed non-variable expressions as false. The
        # current town definitions use EQU over quest status values.
        return False
    variable, raw_values = match.groups()
    if not variable.startswith("QUEST"):
        return False
    try:
        quest_id = int(variable.removeprefix("QUEST"))
        status = int(quest_statuses.get(quest_id, 0))
        expected = {int(value) for value in raw_values.split()}
    except ValueError:
        return False
    return status in expected


def _town_map_path(path: Path) -> Path:
    if path.suffix.lower() != ".jsonc":
        raise ValueError(f"town map must use JSONC: {path}")
    return path


def parse_town_map(
    path: Path, quest_statuses: Mapping[int, int] | None = None
) -> TownMap:
    """Load the active map and glyph rules from the game's JSONC definitions.

    Missing quest statuses default to zero, matching the game's initial quest
    status and selecting the false-condition town map variant.
    """
    path = _town_map_path(path)
    statuses = quest_statuses or {}
    data = _jsonc(path)
    preferences = _jsonc(path.parent.parent / "TownPreferences.jsonc")
    legend = preferences.get("legend", {})
    if not isinstance(legend, dict):
        raise ValueError(f"invalid town preference legend: {path.parent.parent / 'TownPreferences.jsonc'}")

    definitions: dict[str, dict] = {}
    floor_symbols: set[str] = set()
    building_symbols: dict[str, int] = {}
    quest_building_symbols: dict[str, set[int]] = {}
    quest_entrance_symbols: dict[str, int] = {}
    reward_symbols: set[str] = set()
    for symbol, definition in legend.items():
        if isinstance(symbol, str) and len(symbol) == 1 and isinstance(definition, dict):
            definitions[symbol] = definition
            building_match = re.fullmatch(
                r"BUILDING_(\d+)", str(definition.get("terrain", ""))
            )
            if building_match:
                building_symbols[symbol] = int(building_match.group(1))
    for rule in data.get("featureRules", []):
        if not isinstance(rule, dict):
            continue
        symbol, definition = rule.get("symbol"), rule.get("definition")
        if isinstance(symbol, str) and len(symbol) == 1 and isinstance(definition, dict):
            definitions[symbol] = definition
            terrain = str(definition.get("terrain", ""))
            try:
                special_id = int(definition.get("special", 0))
            except (TypeError, ValueError):
                special_id = 0
            if terrain == "FLOOR":
                floor_symbols.add(symbol)
                try:
                    if int(definition.get("object", 0)) > 0:
                        reward_symbols.add(symbol)
                except (TypeError, ValueError):
                    pass
            building_match = re.fullmatch(r"BUILDING_(\d+)", terrain)
            if building_match:
                building_symbols[symbol] = int(building_match.group(1))
                if special_id > 0:
                    quest_building_symbols.setdefault(symbol, set()).add(special_id)
            if terrain == "QUEST_ENTER" and special_id > 0:
                quest_entrance_symbols[symbol] = special_id

    # TownPreferences definitions are shared defaults. Treat their terrain
    # properties the same way as the legacy parser's combined F directives.
    for symbol, definition in definitions.items():
        terrain = str(definition.get("terrain", ""))
        if terrain == "FLOOR":
            floor_symbols.add(symbol)
            try:
                if int(definition.get("object", 0)) > 0:
                    reward_symbols.add(symbol)
            except (TypeError, ValueError):
                pass
        building_match = re.fullmatch(r"BUILDING_(\d+)", terrain)
        if building_match:
            building_symbols.setdefault(symbol, int(building_match.group(1)))
            try:
                special_id = int(definition.get("special", 0))
            except (TypeError, ValueError):
                special_id = 0
            if special_id > 0:
                quest_building_symbols.setdefault(symbol, set()).add(special_id)
        if terrain == "QUEST_ENTER":
            try:
                special_id = int(definition.get("special", 0))
            except (TypeError, ValueError):
                special_id = 0
            if special_id > 0:
                quest_entrance_symbols.setdefault(symbol, special_id)

    variants = data.get("mapVariants", [])
    if not isinstance(variants, list):
        raise ValueError(f"invalid town map variants: {path}")
    selected = [
        variant for variant in variants
        if isinstance(variant, dict) and _condition_matches(variant.get("when"), statuses)
    ]
    if len(selected) != 1:
        raise ValueError(f"expected one active town map variant in {path}, found {len(selected)}")
    rows = selected[0].get("rows")
    if not isinstance(rows, list) or not rows or not all(isinstance(row, str) for row in rows):
        raise ValueError(f"invalid town map rows: {path}")

    walkable: set[Position] = set()
    stores: dict[int, Position] = {}
    buildings: dict[int, Position] = {}
    quest_buildings: dict[int, set[Position]] = {}
    quest_entrances: dict[int, set[Position]] = {}
    reward_positions: set[Position] = set()
    entrance: Position | None = None

    for y, row in enumerate(rows):
        for x, symbol in enumerate(row):
            pos = Position(y, x)
            definition = definitions.get(symbol, {})
            terrain = str(definition.get("terrain", ""))
            if symbol in _WALKABLE_CHARS or symbol in floor_symbols:
                walkable.add(pos)
            if terrain in _STORE_TERRAINS:
                stores[_STORE_TERRAINS[terrain]] = pos
                walkable.add(pos)
            if symbol in building_symbols:
                building_id = building_symbols[symbol]
                buildings[building_id] = pos
                walkable.add(pos)
            for quest_id in quest_building_symbols.get(symbol, set()):
                quest_buildings.setdefault(quest_id, set()).add(pos)
            quest_id = quest_entrance_symbols.get(symbol)
            if quest_id is not None:
                quest_entrances.setdefault(quest_id, set()).add(pos)
                walkable.add(pos)
            if symbol in reward_symbols:
                reward_positions.add(pos)
            if symbol == ">":
                entrance = pos

    return TownMap(
        name=path.stem,
        width=max(map(len, rows)),
        height=len(rows),
        walkable=frozenset(walkable),
        stores=stores,
        buildings=buildings,
        quest_buildings={key: frozenset(value) for key, value in quest_buildings.items()},
        quest_entrances={key: frozenset(value) for key, value in quest_entrances.items()},
        reward_positions=frozenset(reward_positions),
        entrance=entrance,
    )


def find_town_map(town_index: int, start: Path | None = None) -> Path | None:
    """Locate a numbered ``lib/edit/towns`` map by walking up from ``start``.

    Mirrors monrace_knowledge.find_monrace_definitions: the town files live beside
    the game data the bot already reads.
    """
    bases: list[Path] = []
    if start is not None:
        bases.append(start)
    bases.append(Path.cwd())
    seen: set[Path] = set()
    for base in bases:
        for directory in [base, *base.parents]:
            if directory in seen:
                continue
            seen.add(directory)
            edit = directory / "lib" / "edit"
            index = edit / "TownDefinitionList.jsonc"
            if not index.is_file():
                continue
            try:
                towns = _jsonc(index).get("towns", {})
                entry = towns.get(str(town_index))
                if isinstance(entry, dict):
                    relative = entry.get("normal")
                else:
                    relative = entry
                if not isinstance(relative, str) or not relative.startswith("towns/") or ".." in relative:
                    continue
                candidate = edit / relative
                if candidate.is_file() and candidate.suffix.lower() == ".jsonc":
                    return candidate
            except (OSError, ValueError, TypeError):
                continue
    return None


def find_outpost_map(start: Path | None = None) -> Path | None:
    """Locate the normal Outpost map through TownDefinitionList.jsonc."""
    return find_town_map(1, start)
