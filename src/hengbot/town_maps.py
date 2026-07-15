"""Static town maps loaded from Hengband's ``lib/edit/towns/*.txt``.

A Hengband town is a FIXED map (the Outpost is always the same layout), so — like
a human who has walked it many times — the bot may know the whole town in advance
without the game revealing anything. This is prior knowledge the bot brings to the
table, NOT extra information injected into the game's per-snapshot output: the
emitter still only reports what the player can currently see. We use the static
map to route to stores across the town even at night, when unlit tiles the player
has not walked past are (correctly) dark in the snapshot.

Only the coarse "can I walk here" layout and the store locations are extracted —
exactly what a returning player remembers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from hengbot.model import Position

# D-grid characters that a player can walk onto. Conservative on purpose: plain
# floor, grass and the numbered store entrances / stairs. Trees, water, walls,
# rubble, building facades and quest entrances are treated as blocked so a route
# never cuts through the forest ring toward the town border. (Over-blocking at
# worst makes a tile unreachable; it never routes the bot somewhere unsafe.)
_WALKABLE_CHARS = frozenset(".,<>")
# Digits 1-8 in a town grid are the store entrances; digit d is store index d, and
# the bot's store_type is d - 1 (General Store '1' -> STORE_GENERAL 0, Home '8' ->
# STORE_HOME 7), matching the store-sale-type enum order.
_STORE_DIGITS = frozenset("12345678")


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


def _floor_flag_chars(lines: list[str]) -> frozenset[str]:
    """Characters an ``F:<char>:FLOOR:...`` directive maps to walkable floor."""
    chars = set()
    for line in lines:
        if not line.startswith("F:"):
            continue
        parts = line.split(":")
        if len(parts) >= 3 and parts[2] == "FLOOR":
            chars.add(parts[1])
    return frozenset(chars)


def _building_flag_chars(lines: list[str]) -> dict[str, int]:
    """Map fixed-map glyphs declared as ``BUILDING_n`` to building ids."""
    result: dict[str, int] = {}
    for line in lines:
        if not line.startswith("F:"):
            continue
        parts = line.split(":")
        if len(parts) < 3 or not parts[2].startswith("BUILDING_"):
            continue
        try:
            result[parts[1]] = int(parts[2].removeprefix("BUILDING_"))
        except ValueError:
            continue
    return result


def _flag_special(parts: list[str]) -> int | None:
    """Return the terrain special field when an F: line carries one."""
    if len(parts) < 10:
        return None
    try:
        return int(parts[9])
    except ValueError:
        return None


def _quest_entrance_flag_chars(lines: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in lines:
        if not line.startswith("F:"):
            continue
        parts = line.split(":")
        if len(parts) < 3 or parts[2] != "QUEST_ENTER":
            continue
        quest_id = _flag_special(parts)
        if quest_id is not None and quest_id > 0:
            result[parts[1]] = quest_id
    return result


def _quest_building_flag_chars(lines: list[str]) -> dict[str, set[int]]:
    result: dict[str, set[int]] = {}
    for line in lines:
        if not line.startswith("F:"):
            continue
        parts = line.split(":")
        if len(parts) < 3 or not parts[2].startswith("BUILDING_"):
            continue
        quest_id = _flag_special(parts)
        if quest_id is not None and quest_id > 0:
            result.setdefault(parts[1], set()).add(quest_id)
    return result


def _reward_flag_chars(lines: list[str]) -> frozenset[str]:
    """Map floor glyphs that can materialize a quest reward object."""
    chars = set()
    for line in lines:
        if not line.startswith("F:"):
            continue
        parts = line.split(":")
        if len(parts) < 6 or parts[2] != "FLOOR":
            continue
        try:
            reward_object_id = int(parts[5])
        except ValueError:
            continue
        if reward_object_id > 0:
            chars.add(parts[1])
    return frozenset(chars)


def parse_town_map(path: Path) -> TownMap:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    # TownPreferences supplies the common glyph definitions used by the full
    # Outpost map (including the Hunter's Office). Town-local F directives come
    # afterwards and therefore override the shared defaults, as in Hengband.
    preferences = path.parent.parent / "TownPreferences.txt"
    definition_lines = []
    if preferences.is_file():
        definition_lines.extend(
            preferences.read_text(encoding="utf-8", errors="replace").splitlines()
        )
    definition_lines.extend(lines)
    rows = [line[2:] for line in lines if line.startswith("D:")]
    if not rows:
        raise ValueError(f"no D: map rows in {path}")
    height = len(rows)
    width = max(len(r) for r in rows)
    floor_chars = _floor_flag_chars(definition_lines)
    building_chars = _building_flag_chars(definition_lines)
    quest_entrance_chars = _quest_entrance_flag_chars(definition_lines)
    quest_building_chars = _quest_building_flag_chars(definition_lines)
    reward_chars = _reward_flag_chars(definition_lines)
    walkable_here = _WALKABLE_CHARS | floor_chars

    walkable: set[Position] = set()
    stores: dict[int, Position] = {}
    buildings: dict[int, Position] = {}
    quest_buildings: dict[int, set[Position]] = {}
    quest_entrances: dict[int, set[Position]] = {}
    reward_positions: set[Position] = set()
    entrance: Position | None = None
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            pos = Position(y, x)
            if ch in _STORE_DIGITS:
                stores[int(ch) - 1] = pos
                walkable.add(pos)  # you walk onto the entrance
            elif ch in building_chars:
                buildings[building_chars[ch]] = pos
                walkable.add(pos)
            elif ch in walkable_here:
                walkable.add(pos)
            if ch in quest_entrance_chars:
                quest_entrances.setdefault(quest_entrance_chars[ch], set()).add(pos)
                walkable.add(pos)
            for quest_id in quest_building_chars.get(ch, set()):
                quest_buildings.setdefault(quest_id, set()).add(pos)
            if ch in reward_chars:
                reward_positions.add(pos)
            if ch == ">":
                # The dungeon entrance the player descends from. Recorded as a
                # first-class goal so the bot can route to it at night, when the
                # unlit '>' tile is absent from the emitted snapshot.
                entrance = pos

    name = path.stem
    return TownMap(
        name=name,
        width=width,
        height=height,
        walkable=frozenset(walkable),
        stores=stores,
        buildings=buildings,
        quest_buildings={key: frozenset(value) for key, value in quest_buildings.items()},
        quest_entrances={key: frozenset(value) for key, value in quest_entrances.items()},
        reward_positions=frozenset(reward_positions),
        entrance=entrance,
    )


def find_outpost_map(start: Path | None = None) -> Path | None:
    """Locate ``lib/edit/towns/01_Outpost_Full.txt`` by walking up from ``start``.

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
            candidate = directory / "lib" / "edit" / "towns" / "01_Outpost_Full.txt"
            if candidate.is_file():
                return candidate
    return None
