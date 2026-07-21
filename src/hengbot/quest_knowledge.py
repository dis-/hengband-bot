"""Static fixed-quest facts from Hengband's ``lib/edit`` data."""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hengbot.monrace_knowledge import _strip_jsonc


QUEST_FLAG_SILENT = 0x01
QUEST_FLAG_PRESET = 0x02
QUEST_FLAG_ONCE = 0x04
QUEST_FLAG_TOWER = 0x08
_FLAG_BITS = {"SILENT": QUEST_FLAG_SILENT, "PRESET": QUEST_FLAG_PRESET, "ONCE": QUEST_FLAG_ONCE, "TOWER": QUEST_FLAG_TOWER}
_QUEST_TYPES = {"NONE": 0, "KILL_LEVEL": 1, "KILL_ANY_LEVEL": 2, "FIND_ARTIFACT": 3, "FIND_EXIT": 4, "KILL_NUMBER": 5, "KILL_ALL": 6, "RANDOM": 7, "TOWER": 8}
QUEST_TYPE_KILL_NUMBER = _QUEST_TYPES["KILL_NUMBER"]
QUEST_TYPE_KILL_LEVEL = _QUEST_TYPES["KILL_LEVEL"]
QUEST_TYPE_RANDOM = _QUEST_TYPES["RANDOM"]
QUEST_TYPE_TOWER = _QUEST_TYPES["TOWER"]


@dataclass(frozen=True)
class QuestBattlefield:
    """Coordinate-level facts from a fixed quest's D-map.

    Terrain features are reduced to planning classes: FLOOR and stairs become
    ``floor``; shallow/deep water remain distinct for quest pathing; permanent/granite
    features become ``wall``; TREE becomes walkable ``tree``; CLOSED/OPEN_DOOR
    becomes ``door``; PASSAGE becomes ``passage``; and RUBBLE features become
    ``rubble``. Unknown legacy glyphs are conservatively walls. Chokepoints are walkable tiles with at most two
    orthogonal neighbours whose removal disconnects those neighbours.
    """

    terrain: dict[tuple[int, int], str] = field(default_factory=dict)
    monster_placements: tuple[tuple[tuple[int, int], int], ...] = ()
    player_start: tuple[int, int] | None = None
    entrance: tuple[int, int] | None = None
    exit: tuple[int, int] | None = None
    searchable: tuple[tuple[int, int], ...] = ()
    reward_tile: tuple[int, int] | None = None
    chokepoints: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class QuestInfo:
    id: int
    name: str
    type: int
    level: int
    flags: int
    name_en: str = ""
    dungeon: int = 0
    num_mon: int = 0
    cur_num: int = 0
    max_num: int = 0
    monrace_id: int = 0
    baseitem_id: int = 0
    reward_artifact_id: int | None = None
    reward_artifact_ids: tuple[int, ...] = ()
    reward_baseitem_id: int = 0
    placed_monsters: tuple[tuple[int, int], ...] = ()
    battlefield: QuestBattlefield | None = None

    @property
    def placed_monster_count(self) -> int:
        return sum(count for _, count in self.placed_monsters)

    @property
    def threat_roster(self) -> tuple[tuple[int, int], ...]:
        """Monsters used by the shared fixed-quest readiness projection."""
        target_count = self.num_mon or self.max_num
        if self.type in {QUEST_TYPE_KILL_LEVEL, QUEST_TYPE_KILL_NUMBER} and self.monrace_id > 0 and target_count > 0:
            return ((self.monrace_id, target_count),)
        return self.placed_monsters

    @property
    def threat_roster_count(self) -> int:
        return sum(count for _, count in self.threat_roster)


def _flag_mask(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            return _FLAG_BITS.get(value.removeprefix("QUEST_FLAG_"), 0)
    if isinstance(value, list):
        return sum(_flag_mask(flag) for flag in value)
    return 0


def _localized_names(value: Any) -> tuple[str, str]:
    if isinstance(value, dict):
        return str(value.get("ja", value.get("en", ""))), str(value.get("en", ""))
    return str(value or ""), ""


def _legacy_quest_file(path: Path) -> dict[int, QuestInfo]:
    names: dict[int, str] = {}
    names_en: dict[int, str] = {}
    definitions: dict[int, QuestInfo] = {}
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    glyph_monsters: dict[str, int] = {}
    glyph_features: dict[str, str] = {
        "X": "PERMANENT", ".": "FLOOR", "D": "CLOSED_DOOR",
        "<": "UP_STAIR", "%": "GRANITE",
    }
    reward_glyphs: set[str] = set()
    explicit_monsters: list[int] = []
    map_rows: list[str] = []
    player_start: tuple[int, int] | None = None
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        # QuestPreferences.txt defines F as
        # F:glyph:terrain:cave_info:monster:object:ego:artifact:trap:special.
        # The roster count comes from occurrences of that glyph in D map rows.
        if parts[0] == "F" and len(parts) >= 5:
            glyph_features[parts[1]] = parts[2]
            try:
                r_idx = int(parts[4], 0)
            except ValueError:  # random-depth forms such as *10 are not placed races
                r_idx = 0
            if r_idx > 0:
                glyph_monsters[parts[1]] = r_idx
            if len(parts) >= 6:
                try:
                    if int(parts[5], 0) > 0:
                        reward_glyphs.add(parts[1])
                except ValueError:
                    pass
            continue
        if parts[0] == "F" and len(parts) >= 3:
            glyph_features[parts[1]] = parts[2]
            continue
        if parts[0] == "M" and len(parts) >= 2:
            # Some quest-map revisions use an explicit M:r_idx[:count] roster.
            try:
                r_idx = int(parts[1], 0)
                count = int(parts[2], 0) if len(parts) >= 3 else 1
            except ValueError:
                continue
            if r_idx > 0 and count > 0:
                explicit_monsters.extend([r_idx] * count)
            continue
        if parts[0] == "D" and len(parts) >= 2:
            map_rows.append(":".join(parts[1:]))
            continue
        if parts[0] == "P" and len(parts) >= 3:
            try:
                player_start = (int(parts[1], 0), int(parts[2], 0))
            except ValueError:
                pass
            continue
        if len(parts) < 3 or parts[0] != "Q":
            continue
        english = parts[1].startswith("$")
        try:
            quest_id = int(parts[1].removeprefix("$"))
        except ValueError:
            continue
        if len(parts) >= 4 and parts[2] == "N":
            (names_en if english else names)[quest_id] = ":".join(parts[3:])
        elif len(parts) >= 11 and parts[2] == "Q":
            values = [int(value, 0) for value in parts[3:11]]
            flags = int(parts[11], 0) if len(parts) >= 12 else 0
            definitions[quest_id] = QuestInfo(
                id=quest_id,
                name=names.get(quest_id, ""),
                type=values[0],
                num_mon=values[1],
                cur_num=values[2],
                max_num=values[3],
                level=values[4],
                monrace_id=values[5],
                reward_artifact_id=values[6] or None,
                dungeon=values[7],
                flags=flags,
            )
    placements = [
        ((y, x), glyph_monsters[ch])
        for y, row in enumerate(map_rows)
        for x, ch in enumerate(row)
        if ch in glyph_monsters
    ]
    # M records have no map coordinate. Preserve every placement using a stable
    # negative-y sentinel rather than inventing an in-map location.
    placements.extend(((-1, index), r_idx) for index, r_idx in enumerate(explicit_monsters))
    roster = Counter(r_idx for _, r_idx in placements)
    battlefield = _legacy_battlefield(
        map_rows, glyph_features, placements, player_start, reward_glyphs
    ) if map_rows else None
    return {
        quest_id: QuestInfo(
            **{
                **info.__dict__,
                "name": names.get(quest_id, info.name),
                "name_en": names_en.get(quest_id, ""),
                "placed_monsters": tuple(sorted(roster.items())),
                "battlefield": battlefield,
            }
        )
        for quest_id, info in definitions.items()
    }


def _terrain_class(feature: str) -> str:
    upper = feature.upper()
    if "QUEST_EXIT" in upper:
        return "exit"
    if "RUBBLE" in upper:
        return "rubble"
    if "DOOR" in upper:
        return "door"
    if "PASSAGE" in upper:
        return "passage"
    if "DEEP_WATER" in upper:
        return "deep_water"
    if "SHALLOW_WATER" in upper:
        return "shallow_water"
    if "TREE" in upper:
        return "tree"
    if any(word in upper for word in ("PERMANENT", "WALL", "GRANITE", "MAGMA", "QUARTZ")):
        return "wall"
    if any(word in upper for word in ("FLOOR", "STAIR", "WATER")):
        return "floor"
    return "wall"


def _legacy_battlefield(
    rows: list[str], features: dict[str, str],
    placements: list[tuple[tuple[int, int], int]],
    player_start: tuple[int, int] | None, reward_glyphs: set[str],
) -> QuestBattlefield:
    terrain = {
        (y, x): _terrain_class(features.get(ch, "UNKNOWN"))
        for y, row in enumerate(rows) for x, ch in enumerate(row)
    }
    entrance = next(((y, x) for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == "<"), None)
    exits = [
        (y, x) for y, row in enumerate(rows) for x, ch in enumerate(row)
        if "QUEST_EXIT" in features.get(ch, "").upper() or ch == "<"
    ]
    exit_position = exits[0] if exits else entrance
    reward = next(((y, x) for y, row in enumerate(rows) for x, ch in enumerate(row) if ch in reward_glyphs), None)
    walkable = {
        pos for pos, kind in terrain.items()
        if kind in {"floor", "exit", "door", "passage", "shallow_water", "tree"}
    }
    neighbours = lambda pos: {
        (pos[0] + dy, pos[1] + dx) for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))
        if (pos[0] + dy, pos[1] + dx) in walkable
    }
    chokepoints: list[tuple[int, int]] = []
    for pos in sorted(walkable):
        adjacent = neighbours(pos)
        if not (2 <= len(adjacent) <= 2):
            continue
        start, target = tuple(adjacent)
        seen = {pos, start}
        pending = [start]
        while pending:
            current = pending.pop()
            for nxt in neighbours(current) - seen:
                seen.add(nxt)
                pending.append(nxt)
        if target not in seen:
            chokepoints.append(pos)
    return QuestBattlefield(
        terrain=terrain, monster_placements=tuple(placements),
        player_start=player_start, entrance=entrance, exit=exit_position,
        searchable=tuple(sorted(pos for pos, kind in terrain.items() if kind == "door")),
        reward_tile=reward,
        chokepoints=tuple(chokepoints),
    )


def _legacy_quests(path: Path) -> dict[int, QuestInfo]:
    result: dict[int, QuestInfo] = {}
    for quest_path in sorted((path.parent / "quests").glob("[0-9][0-9][0-9]*.txt")):
        result.update(_legacy_quest_file(quest_path))
    return result


def _json_quest(path: Path) -> QuestInfo:
    data: dict[str, Any] = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    definition = data.get("definition", data)
    quest_id = int(definition.get("id", data.get("id", int(path.name.split("_", 1)[0]))))
    reward = definition.get("reward", {})
    name, name_en = _localized_names(data.get("name", definition.get("name", "")))
    quest_type = definition.get("type", 0)
    if isinstance(quest_type, str):
        quest_type = _QUEST_TYPES.get(quest_type, 0)
    artifacts = reward.get("artifacts", [])
    if reward.get("artifact") is not None:
        artifacts = [reward["artifact"]]
    artifact_ids = tuple(int(value) for value in artifacts)
    roster = _json_placed_monsters(data)
    return QuestInfo(
        id=quest_id,
        name=name,
        name_en=name_en,
        type=int(quest_type),
        level=int(definition.get("level", 0)),
        flags=_flag_mask(definition.get("flags", [])),
        dungeon=int(definition.get("dungeon", definition.get("dungeonId", 0)) or 0),
        num_mon=int(definition.get("numMon", definition.get("num_mon", 0)) or 0),
        cur_num=int(definition.get("curNum", definition.get("cur_num", 0)) or 0),
        max_num=int(definition.get("maxNum", definition.get("max_num", 0)) or 0),
        monrace_id=int(definition.get("monster", 0) or 0),
        baseitem_id=int(definition.get("baseitemId", definition.get("k_idx", 0)) or 0),
        reward_artifact_id=artifact_ids[0] if artifact_ids else None,
        reward_artifact_ids=artifact_ids,
        reward_baseitem_id=int(reward.get("baseitemId", 0) or 0),
        placed_monsters=tuple(sorted(roster.items())),
    )


def _json_placed_monsters(data: dict[str, Any]) -> Counter[int]:
    """Read migrated fixed-map placements without treating the quest target as a placement.

    Migrated files have appeared with both explicit ``placed_monsters`` arrays and
    map feature/symbol objects.  Restrict recursion to map-shaped keys so a
    definition's ordinary ``monster`` field is never mistaken for a hand placement.
    """
    roster: Counter[int] = Counter()
    map_keys = {"map", "fixed_map", "layout", "floor", "placements", "placed_monsters", "features", "symbols"}

    def visit(value: Any, *, in_map: bool = False) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item, in_map=in_map)
            return
        if not isinstance(value, dict):
            return
        if in_map:
            raw_id = next(
                (value[key] for key in ("r_idx", "monrace_id", "monster_id", "monster") if key in value),
                None,
            )
            if raw_id is not None:
                try:
                    r_idx = int(raw_id)
                    count = int(value.get("count", value.get("quantity", 1)))
                except (TypeError, ValueError):
                    pass
                else:
                    if r_idx > 0 and count > 0:
                        roster[r_idx] += count
        for key, child in value.items():
            visit(child, in_map=in_map or key in map_keys)

    visit(data)
    return roster


def load_quest_knowledge(path: Path) -> dict[int, QuestInfo]:
    """Load the legacy list or a directory of migrated per-quest JSONC files."""
    if path.is_file() and path.name == "QuestDefinitionList.txt":
        return _legacy_quests(path)
    directory = path if path.is_dir() else path.parent
    result: dict[int, QuestInfo] = {}
    for quest_path in sorted(directory.glob("*.jsonc")):
        info = _json_quest(quest_path)
        result[info.id] = info
    return result


def find_quest_definitions(state_file: Path, override: Path | None = None) -> Path | None:
    if override is not None:
        return override
    configured = os.environ.get("HENGBAND_QUEST_DEFINITIONS")
    if configured:
        return Path(configured)
    roots = [Path.cwd(), *state_file.resolve().parents]
    for root in roots:
        edit = root / "lib" / "edit"
        legacy = edit / "QuestDefinitionList.txt"
        if legacy.is_file():
            return legacy
        migrated = edit / "quests"
        if migrated.is_dir() and any(migrated.glob("*.jsonc")):
            return migrated
    return None
