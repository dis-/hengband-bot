"""Approval-driven fixed-quest strategy profile loading."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hengbot.monrace_knowledge import _strip_jsonc


@dataclass(frozen=True)
class StrategyProfile:
    quest_id: int
    name: dict[str, str]
    approved: bool
    approved_note: str
    engagement_plan: dict[str, Any]
    priority_targets: tuple[int, ...]
    consumable_plan: dict[str, Any]
    abort_conditions: dict[str, Any]
    required_force: dict[str, Any]
    generated_by: str
    generated_at: str

    @property
    def execution_eligible(self) -> bool:
        return self.approved


def _profile(data: dict[str, Any]) -> StrategyProfile:
    required = ("quest_id", "name", "engagement_plan", "priority_targets",
                "consumable_plan", "abort_conditions", "required_force",
                "generated_by", "generated_at")
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"missing fields: {', '.join(missing)}")
    name = data["name"]
    if not isinstance(name, dict) or not {"ja", "en"} <= name.keys():
        raise ValueError("name must contain ja and en")
    if "approved" in data and not isinstance(data["approved"], bool):
        raise ValueError("approved must be a boolean")
    force = data["required_force"]
    if not isinstance(force, dict):
        raise ValueError("required_force must be an object")
    launcher = force.get("launcher")
    if launcher is not None and (
        not isinstance(launcher, dict)
        or launcher.get("ammo") not in {"shot", "arrow", "bolt", "equipped"}
        or launcher.get("equipped", True) is not True
    ):
        raise ValueError(
            "launcher must require an equipped shot/arrow/bolt launcher "
            "or the currently equipped launcher"
        )
    if isinstance(launcher, dict):
        min_average_damage = launcher.get("min_average_damage", 0)
        if (
            not isinstance(min_average_damage, (int, float))
            or isinstance(min_average_damage, bool)
            or min_average_damage < 0
        ):
            raise ValueError(
                "launcher min_average_damage must be a non-negative number"
            )
    carry_names = {
        "throwing_items": {
            "lit_torch", "shot", "arrow", "bolt", "launcher_ammo",
        },
        "required_scrolls": {"light", "teleport"},
        "utility_tools": {"wall_breach"},
    }
    for group, allowed in carry_names.items():
        values = force.get(group, {})
        if not isinstance(values, dict):
            raise ValueError(f"{group} must be an object")
        if set(values) - allowed:
            raise ValueError(f"unknown {group}: {', '.join(sorted(set(values) - allowed))}")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in values.values()
        ):
            raise ValueError(f"{group} quantities must be non-negative integers")
    return StrategyProfile(
        quest_id=int(data["quest_id"]), name={"ja": str(name["ja"]), "en": str(name["en"])},
        approved=bool(data.get("approved", False)), approved_note=str(data.get("approved_note", "")),
        engagement_plan=dict(data["engagement_plan"]),
        priority_targets=tuple(int(value) for value in data["priority_targets"]),
        consumable_plan=dict(data["consumable_plan"]), abort_conditions=dict(data["abort_conditions"]),
        required_force=dict(force), generated_by=str(data["generated_by"]),
        generated_at=str(data["generated_at"]),
    )


def load_quest_strategies(directory: Path) -> dict[int, StrategyProfile]:
    """Load all profiles; malformed files warn and do not disable good ones."""
    if not directory.is_dir():
        return {}
    result: dict[int, StrategyProfile] = {}
    for path in sorted(directory.glob("QUEST_*.jsonc")):
        try:
            data = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
            profile = _profile(data)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"could not load quest strategy ({path}): {exc}", file=sys.stderr)
            continue
        result[profile.quest_id] = profile
    return result


def find_quest_strategies(state_file: Path, override: Path | None = None) -> Path | None:
    if override is not None:
        return override
    configured = os.environ.get("HENGBAND_QUEST_STRATEGIES")
    if configured:
        return Path(configured)
    for root in [Path.cwd(), *state_file.resolve().parents]:
        candidate = root / "strategy" / "quests"
        if candidate.is_dir():
            return candidate
    return None
