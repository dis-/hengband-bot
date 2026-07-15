"""Static fixed-quest facts from Hengband's ``lib/edit`` data."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hengbot.monrace_knowledge import _strip_jsonc


QUEST_FLAG_ONCE = 0x02
_FLAG_BITS = {"ONCE": QUEST_FLAG_ONCE, "PRESET": 0x04}


@dataclass(frozen=True)
class QuestInfo:
    id: int
    name: str
    type: int | str
    level: int
    flags: int
    dungeon: int = 0
    num_mon: int = 0
    cur_num: int = 0
    max_num: int = 0
    monrace_id: int = 0
    baseitem_id: int = 0
    reward_artifact_id: int | None = None
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


def _english_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("en", value.get("ja", "")))
    return str(value or "")


def _legacy_quests(path: Path) -> dict[int, QuestInfo]:
    names: dict[int, str] = {}
    definitions: dict[int, QuestInfo] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) >= 4 and parts[0] == "Q" and parts[2] == "N":
            names[int(parts[1])] = ":".join(parts[3:])
        elif len(parts) >= 11 and parts[0] == "Q" and parts[2] == "Q":
            quest_id = int(parts[1])
            values = [int(value, 0) for value in parts[3:10]]
            definitions[quest_id] = QuestInfo(
                id=quest_id,
                name=names.get(quest_id, ""),
                type=values[0],
                num_mon=values[1],
                cur_num=values[2],
                max_num=values[3],
                level=values[4],
                monrace_id=values[5],
                baseitem_id=values[6],
                flags=int(parts[10], 0),
            )
    # Some files place N after Q; apply names only after the whole file is read.
    return {
        quest_id: QuestInfo(**{**info.__dict__, "name": names.get(quest_id, info.name)})
        for quest_id, info in definitions.items()
    }


def _json_quest(path: Path) -> QuestInfo:
    data: dict[str, Any] = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    definition = data.get("definition", data)
    quest_id = int(definition.get("id", data.get("id", int(path.name.split("_", 1)[0]))))
    reward = definition.get("reward", {})
    return QuestInfo(
        id=quest_id,
        name=_english_name(data.get("name", definition.get("name", ""))),
        type=definition.get("type", 0),
        level=int(definition.get("level", 0)),
        flags=_flag_mask(definition.get("flags", [])),
        dungeon=int(definition.get("dungeon", definition.get("dungeonId", 0)) or 0),
        num_mon=int(definition.get("numMon", definition.get("num_mon", 0)) or 0),
        cur_num=int(definition.get("curNum", definition.get("cur_num", 0)) or 0),
        max_num=int(definition.get("maxNum", definition.get("max_num", 0)) or 0),
        monrace_id=int(definition.get("monraceId", definition.get("r_idx", 0)) or 0),
        baseitem_id=int(definition.get("baseitemId", definition.get("k_idx", 0)) or 0),
        reward_artifact_id=(int(reward["artifactId"]) if reward.get("artifactId") is not None else None),
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
