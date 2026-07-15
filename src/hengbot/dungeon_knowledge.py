"""Static dungeon facts loaded from Hengband's ``lib/edit/DungeonDefinitions.jsonc``.

Like the town maps and monrace definitions, a dungeon's depth range and its
recommended entry level are FIXED design data — prior knowledge a returning
player already has. The bot uses it to pick a recall destination that matches the
character's current level instead of over-extending in a dungeon far past its
recommended level (a clvl-23 warrior in Angband, recommended level 30, collects
nothing and just emergency-teleports out). This reads only the static definition;
it injects no live per-snapshot information.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hengbot.monrace_knowledge import _strip_jsonc


@dataclass(frozen=True)
class DungeonInfo:
    id: int
    name: str
    min_depth: int
    max_depth: int
    min_player_level: int
    flags: frozenset[str] = frozenset()
    guardian_id: int = 0


def load_dungeon_knowledge(path: Path) -> dict[int, DungeonInfo]:
    data: dict[str, Any] = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    result: dict[int, DungeonInfo] = {}
    for dungeon in data.get("dungeons", []):
        generation = dungeon.get("generation", {})
        name = dungeon.get("name", {})
        dungeon_id = int(dungeon["id"])
        result[dungeon_id] = DungeonInfo(
            id=dungeon_id,
            name=str(name.get("en", name.get("ja", ""))),
            min_depth=int(generation.get("minDepth", 0)),
            max_depth=int(generation.get("maxDepth", 0)),
            min_player_level=int(generation.get("minPlayerLevel", 0)),
            flags=frozenset(str(flag) for flag in dungeon.get("flags", [])),
            guardian_id=int(dungeon.get("final_floor", {}).get("guardian", 0)),
        )
    return result


def find_dungeon_definitions(state_file: Path, override: Path | None = None) -> Path | None:
    """Locate ``lib/edit/DungeonDefinitions.jsonc`` — mirrors find_monrace_definitions."""
    if override is not None:
        return override

    configured = os.environ.get("HENGBAND_DUNGEON_DEFINITIONS")
    if configured:
        return Path(configured)

    relative = Path("lib") / "edit" / "DungeonDefinitions.jsonc"
    candidates = [Path.cwd() / relative]
    candidates.extend(parent / relative for parent in state_file.resolve().parents)
    return next((candidate for candidate in candidates if candidate.is_file()), None)
