"""Static fixed-quest facts from Hengband's ``lib/edit`` data."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hengbot.monrace_knowledge import _strip_jsonc


QUEST_FLAG_SILENT = 0x01
QUEST_FLAG_PRESET = 0x02
QUEST_FLAG_ONCE = 0x04
QUEST_FLAG_TOWER = 0x08
_FLAG_BITS = {"SILENT": QUEST_FLAG_SILENT, "PRESET": QUEST_FLAG_PRESET, "ONCE": QUEST_FLAG_ONCE, "TOWER": QUEST_FLAG_TOWER}
_QUEST_TYPES = {"NONE": 0, "KILL_LEVEL": 1, "KILL_ANY_LEVEL": 2, "FIND_ARTIFACT": 3, "FIND_EXIT": 4, "KILL_NUMBER": 5, "KILL_ALL": 6, "RANDOM": 7, "TOWER": 8}


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


def _legacy_quest_file(path: Path) -> QuestInfo | None:
    primary_id = int(path.name.split("_", 1)[0])
    names: dict[int, str] = {}
    names_en: dict[int, str] = {}
    definitions: dict[int, QuestInfo] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) < 3 or parts[0] != "Q":
            continue
        english = parts[1].startswith("$")
        try:
            quest_id = int(parts[1].removeprefix("$"))
        except ValueError:
            continue
        if quest_id != primary_id:
            continue
        if len(parts) >= 4 and parts[2] == "N":
            (names_en if english else names)[quest_id] = ":".join(parts[3:])
        elif len(parts) >= 12 and parts[2] == "Q":
            values = [int(value, 0) for value in parts[3:12]]
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
                flags=values[8],
            )
    info = definitions.get(primary_id)
    if info is None:
        return None
    return QuestInfo(**{**info.__dict__, "name": names.get(primary_id, info.name), "name_en": names_en.get(primary_id, "")})


def _legacy_quests(path: Path) -> dict[int, QuestInfo]:
    result: dict[int, QuestInfo] = {}
    for quest_path in sorted((path.parent / "quests").glob("[0-9][0-9][0-9]_*.txt")):
        info = _legacy_quest_file(quest_path)
        if info is not None:
            result[info.id] = info
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
    )


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
