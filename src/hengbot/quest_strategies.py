"""Approval-driven fixed-quest strategy profile loading."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hengbot import quest25_plan
from hengbot.model import SV_POTION_CURE_CRITICAL, SV_POTION_HEALING, TVAL_POTION
from hengbot.monrace_knowledge import _strip_jsonc


def acceptance_dps_floor(force: dict[str, Any], class_id: int) -> float:
    """Resolve a class-specific melee floor for an acceptance tier only."""
    overrides = force.get("min_expected_dps_by_class", {})
    return float(overrides.get(str(class_id), force.get("min_expected_dps", 0)) or 0)


def acceptance_hp_floor(force: dict[str, Any], class_id: int) -> int:
    """Resolve a class-specific maximum-HP floor for an acceptance tier only."""
    overrides = force.get("min_hp_by_class", {})
    return int(overrides.get(str(class_id), force.get("min_hp", 0)) or 0)


def torch_throw_output(force: dict[str, Any], class_id: int) -> float:
    """A reviewed class's per-action thrown lit-torch output (QUEST_1 class 16), else 0."""
    return float(force.get("torch_throw_output_by_class", {}).get(str(class_id), 0) or 0)


def class_throwing_items(force: dict[str, Any], class_id: int) -> dict[str, Any]:
    """Resolve a reviewed class-specific throwing plan (QUEST_1 class 16)."""
    overrides = force.get("throwing_items_by_class", {}).get(str(class_id))
    return dict(overrides) if overrides is not None else dict(force.get("throwing_items", {}))


# The potion a strategy's ``heal_potions`` counts: required_force
# ``heal_potion_kind`` (default Potion of Healing).  QUEST_14 names Cure
# Critical Wounds (owner 2026-10-31 「致命傷の治癒でよい」).
HEAL_POTION_KIND_SVALS = {
    "healing": SV_POTION_HEALING,
    "cure_critical": SV_POTION_CURE_CRITICAL,
}


def heal_potion_sval(force: dict[str, Any]) -> int:
    """The potion sval that counts toward ``force``'s ``heal_potions``."""
    return HEAL_POTION_KIND_SVALS[force.get("heal_potion_kind", "healing")]


def is_heal_potion_for(item: Any, force: dict[str, Any]) -> bool:
    """Whether ``item`` (pack or shelf) is ``force``'s heal_potions kind."""
    return item.tval == TVAL_POTION and item.sval == heal_potion_sval(force)


# The carries a strategy may lower when the full kit cannot be afforded:
# required_force name -> where the force keeps its required count.
LOWERABLE_CARRIES = ("lit_torch", "heal_potions", "speed_potions")


def carry_floor(force: dict[str, Any], class_id: int) -> dict[str, int]:
    """The reviewed lower carry counts (QUEST_1 ``carry_floor``), class rows first."""
    floor = dict(force.get("carry_floor", {}))
    floor.update(force.get("carry_floor_by_class", {}).get(str(class_id), {}))
    return {name: int(value) for name, value in floor.items() if name in LOWERABLE_CARRIES}


def lower_carries(force: dict[str, Any], lowered: dict[str, int]) -> dict[str, Any]:
    """``force`` with each lowerable carry at most its ``lowered`` count."""
    force = dict(force)
    if "lit_torch" in lowered:
        throwing = dict(force.get("throwing_items", {}))
        throwing["lit_torch"] = min(int(throwing.get("lit_torch", 0)), lowered["lit_torch"])
        force["throwing_items"] = throwing
    for name in ("heal_potions", "speed_potions"):
        if name in lowered:
            force[name] = min(int(force.get(name, 0)), lowered[name])
    return force


# ``required_force.resist_alternatives``: a required ability another one stands in for.
# Telepathy is a player ability; the ESP kinds are an identified worn item's flags only
# (bot-json-output.cpp ability_sources names no ESP kind): object-enchant/tr-types.h.
ESP_ALTERNATIVE_FLAGS = {"esp_undead": 105, "esp_evil": 112}


def has_ability_or_alternative(force: dict[str, Any], name: str, abilities, equipment) -> bool:
    """``name`` (a resolved ability name) is had, or one of its reviewed alternatives.

    QUEST_25 owner 2026-11-06 「どれか1つでよい」: See Invisible, telepathy, undead ESP or
    evil ESP each lets the plan see the invisible dreadmaster."""
    if name in abilities:
        return True
    for alternative in force.get("resist_alternatives", {}).get(name, ()):
        flag = ESP_ALTERNATIVE_FLAGS.get(alternative)
        if alternative in abilities or (flag is not None and any(
                flag in item.known_flags for item in equipment)):
            return True
    return False


def valid_force_alternatives(force: dict[str, Any]) -> bool:
    """The schema of ``force_alternatives`` (quest_force_rows reads the rows)."""
    rows = force.get("force_alternatives", [])
    names = ("min_hp", "min_expected_dps", "heal_potions", "speed_potions")
    return isinstance(rows, list) and all(
        isinstance(row, dict) and all(
            isinstance(row.get(name), (int, float)) and not isinstance(row.get(name), bool)
            and row[name] >= 0 for name in names)
        for row in rows
    )


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
    alternatives = force.get("resist_alternatives", {})
    if not isinstance(alternatives, dict) or not all(
            isinstance(names, list) and all(isinstance(name, str) for name in names)
            for names in alternatives.values()):
        raise ValueError("resist_alternatives must map an ability to a list of ability names")
    if not valid_force_alternatives(force):
        raise ValueError("force_alternatives rows must give min_hp, min_expected_dps, "
                         "heal_potions and speed_potions as non-negative numbers")
    carry_names = {
        "throwing_items": {
            "lit_torch", "shot", "arrow", "bolt", "launcher_ammo",
        },
        "required_scrolls": {"light", "teleport"},
        "required_potions": {"restore_exp", "restore_str"},
        "utility_tools": {"wall_breach"},
    }
    if force.get("heal_potion_kind", "healing") not in HEAL_POTION_KIND_SVALS:
        raise ValueError(
            "heal_potion_kind must be one of: "
            + ", ".join(sorted(HEAL_POTION_KIND_SVALS))
        )
    floors = [force.get("carry_floor", {}), *force.get("carry_floor_by_class", {}).values()]
    if not all(isinstance(floor, dict) and set(floor) <= set(LOWERABLE_CARRIES)
               and all(isinstance(v, int) and not isinstance(v, bool) and v >= 0
                       for v in floor.values()) for floor in floors):
        raise ValueError("carry_floor must map lowerable carries to non-negative integers")
    by_class = force.get("throwing_items_by_class", {})
    if not isinstance(by_class, dict) or not all(isinstance(v, dict) for v in by_class.values()):
        raise ValueError("throwing_items_by_class must map class ids to objects")
    groups = [(group, force.get(group, {}), allowed) for group, allowed in carry_names.items()]
    groups += [("throwing_items", values, carry_names["throwing_items"]) for values in by_class.values()]
    for group, values, allowed in groups:
        if not isinstance(values, dict):
            raise ValueError(f"{group} must be an object")
        if set(values) - allowed:
            raise ValueError(f"unknown {group}: {', '.join(sorted(set(values) - allowed))}")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in values.values()
        ):
            raise ValueError(f"{group} quantities must be non-negative integers")
    quest25_plan.check_profile(data)
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
