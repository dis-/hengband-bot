from __future__ import annotations

import json
import os
from pathlib import Path

from hengbot.monrace_knowledge import _strip_jsonc


# TerrainType::can_damage_player() lists these flags; the matching branches in
# action/run-execution.cpp confirm their unprotected elemental/poison damage.
DAMAGING_FLAGS = frozenset(
    {"LAVA", "COLD_PUDDLE", "ELEC_PUDDLE", "ACID_PUDDLE", "POISON_PUDDLE"}
)


def load_damaging_terrain_ids(path: Path) -> frozenset[int]:
    data = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    result: set[int] = set()
    for terrain in data.get("terrains", []):
        flags = set(terrain.get("flags", []))
        # TerrainType::can_damage_player() also lists WATER + DEEP.
        # run-execution.cpp confirms an unprotected overloaded non-swimmer can
        # drown there, so conservatively include every such terrain definition.
        if flags.intersection(DAMAGING_FLAGS) or {"WATER", "DEEP"} <= flags:
            result.add(int(terrain["id"]))
    return frozenset(result)


def find_terrain_definitions(state_file: Path) -> Path | None:
    configured = os.environ.get("HENGBAND_TERRAIN_DEFINITIONS")
    if configured:
        return Path(configured)
    relative = Path("lib") / "edit" / "TerrainDefinitions.jsonc"
    candidates = [Path.cwd() / relative]
    candidates.extend(parent / relative for parent in state_file.resolve().parents)
    return next((candidate for candidate in candidates if candidate.is_file()), None)
