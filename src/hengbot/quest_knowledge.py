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


def _build_battlefield(
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
    battlefield = _json_battlefield(data)
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
        battlefield=battlefield,
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
    legend = data.get("legend")
    rows = data.get("map")
    if isinstance(legend, dict) and isinstance(rows, list):
        for glyph, entry in legend.items():
            if not isinstance(glyph, str) or len(glyph) != 1 or not isinstance(entry, dict):
                continue
            try:
                r_idx = int(entry.get("monster", 0))
            except (TypeError, ValueError):
                continue
            if r_idx > 0:
                roster[r_idx] += sum(
                    row.count(glyph) for row in rows if isinstance(row, str)
                )
    return roster


def _json_battlefield(data: dict[str, Any]) -> QuestBattlefield | None:
    legend = data.get("legend")
    raw_rows = data.get("map")
    if not isinstance(legend, dict) or not isinstance(raw_rows, list):
        return None
    rows = [row for row in raw_rows if isinstance(row, str)]
    if not rows:
        return None

    features = {
        "X": "PERMANENT", ".": "FLOOR", "D": "CLOSED_DOOR",
        "<": "UP_STAIR", "%": "GRANITE", "T": "TREE",
    }
    reward_glyphs: set[str] = set()
    monster_glyphs: dict[str, int] = {}
    for glyph, entry in legend.items():
        if not isinstance(glyph, str) or len(glyph) != 1 or not isinstance(entry, dict):
            continue
        terrain = entry.get("terrain")
        if isinstance(terrain, str):
            features[glyph] = terrain
        try:
            r_idx = int(entry.get("monster", 0))
        except (TypeError, ValueError):
            r_idx = 0
        if r_idx > 0:
            monster_glyphs[glyph] = r_idx
        if "object" in entry:
            reward_glyphs.add(glyph)

    placements = [
        ((y, x), monster_glyphs[glyph])
        for y, row in enumerate(rows)
        for x, glyph in enumerate(row)
        if glyph in monster_glyphs
    ]
    raw_start = data.get("start")
    player_start: tuple[int, int] | None = None
    if isinstance(raw_start, dict):
        try:
            player_start = (int(raw_start["y"]), int(raw_start["x"]))
        except (KeyError, TypeError, ValueError):
            pass
    return _build_battlefield(
        rows, features, placements, player_start, reward_glyphs
    )


def load_quest_knowledge(path: Path) -> dict[int, QuestInfo]:
    """Load per-quest JSONC files from the migrated quests directory."""
    if path.is_file() and path.suffix.lower() != ".jsonc":
        raise ValueError(f"quest definitions must use JSONC: {path}")
    directory = path if path.is_dir() else path.parent
    result: dict[int, QuestInfo] = {}
    for quest_path in sorted(directory.glob("*.jsonc")):
        info = _json_quest(quest_path)
        result[info.id] = info
    return result


def find_quest_definitions(state_file: Path, override: Path | None = None) -> Path | None:
    def is_jsonc_source(path: Path) -> bool:
        if path.is_dir():
            return any(path.glob("*.jsonc"))
        return path.is_file() and path.suffix.lower() == ".jsonc"

    if override is not None:
        return override if is_jsonc_source(override) else None
    configured = os.environ.get("HENGBAND_QUEST_DEFINITIONS")
    if configured:
        candidate = Path(configured)
        return candidate if is_jsonc_source(candidate) else None
    roots = [Path.cwd(), *state_file.resolve().parents]
    for root in roots:
        edit = root / "lib" / "edit"
        migrated = edit / "quests"
        if is_jsonc_source(migrated):
            return migrated
    return None
