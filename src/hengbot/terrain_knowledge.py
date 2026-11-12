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
STANDING_DAMAGE_ELEMENTS = {"LAVA": "fire", "COLD_PUDDLE": "cold", "ELEC_PUDDLE": "elec",
                            "ACID_PUDDLE": "acid", "POISON_PUDDLE": ""}


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


def load_damaging_terrain_elements(path: Path) -> dict[int, str]:
    """Terrain id -> the element its standing damage is: the immunity that stops it
    (hp-mp-processor.cpp), or "" for poison, which no immunity stops."""
    data = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    return {
        int(terrain["id"]): element
        for terrain in data.get("terrains", [])
        for flag, element in STANDING_DAMAGE_ELEMENTS.items()
        if flag in terrain.get("flags", [])
    }


def load_los_only_terrain_ids(path: Path) -> frozenset[int]:
    """Terrain seen through that stops a projection: LOS without PROJECTION (the glass
    walls and closed glass doors).  The board carries LOS and MOVE only, and
    projectable() stops a bolt on a grid without PROJECTION
    (projection-path-calculator.cpp:94)."""
    data = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    return frozenset(
        int(terrain["id"])
        for terrain in data.get("terrains", [])
        if "LOS" in terrain.get("flags", [])
        and "PROJECTION" not in terrain.get("flags", [])
    )


def load_deep_damaging_terrain_ids(path: Path) -> frozenset[int]:
    """Damaging terrain that still hurts a levitating player: deal_damege_by_feat
    (hp-mp-processor.cpp) deals DEEP terrain's damage to everyone, a fifth of it while
    levitating, and other damaging terrain's only to a player standing in it."""
    data = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    return frozenset(
        int(terrain["id"])
        for terrain in data.get("terrains", [])
        if "DEEP" in terrain.get("flags", [])
        and STANDING_DAMAGE_ELEMENTS.keys() & set(terrain.get("flags", []))
    )


def load_terrain_facts(path: Path) -> dict[str, object]:
    """Every HengbotPolicy keyword argument the terrain definitions give, by name: the
    live cli and the recorded-board harness build the policy from this one call."""
    return {
        "damaging_terrain_ids": load_damaging_terrain_ids(path),
        "damaging_terrain_elements": load_damaging_terrain_elements(path),
        "deep_damaging_terrain_ids": load_deep_damaging_terrain_ids(path),
        "los_only_terrain_ids": load_los_only_terrain_ids(path),
    }


def find_terrain_definitions(state_file: Path) -> Path | None:
    configured = os.environ.get("HENGBAND_TERRAIN_DEFINITIONS")
    if configured:
        return Path(configured)
    relative = Path("lib") / "edit" / "TerrainDefinitions.jsonc"
    candidates = [Path.cwd() / relative]
    candidates.extend(parent / relative for parent in state_file.resolve().parents)
    return next((candidate for candidate in candidates if candidate.is_file()), None)
