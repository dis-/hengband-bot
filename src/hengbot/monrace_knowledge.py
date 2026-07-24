from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


NON_HP_DAMAGE_BLOW_EFFECTS = frozenset({"FLAVOR", "DR_MANA", "HUNGRY"})


SUMMON_ABILITIES = frozenset(
    {
        "S_KIN",
        "S_CYBER",
        "S_MONSTER",
        "S_MONSTERS",
        "S_ANT",
        "S_SPIDER",
        "S_HOUND",
        "S_HYDRA",
        "S_ANGEL",
        "S_DEMON",
        "S_UNDEAD",
        "S_DRAGON",
        "S_HI_UNDEAD",
        "S_HI_DRAGON",
        "S_AMBERITES",
        "S_UNIQUE",
        "S_DEAD_UNIQUE",
    }
)


@dataclass(frozen=True)
class MonsterBlow:
    method: str
    effect: str
    dice_num: int = 0
    dice_sides: int = 0


@dataclass(frozen=True)
class MonraceKnowledge:
    max_hp: int
    speed: int
    can_summon: bool
    friendly: bool
    level: int = 0
    max_melee_damage: int = 0
    max_ranged_damage: int = 0
    can_multiply: bool = False
    average_hp: int = 0
    armor_class: int = 0
    rarity: int = 0
    flags: frozenset[str] = frozenset()
    abilities: frozenset[str] = frozenset()
    blows: tuple[MonsterBlow, ...] = ()
    spell_frequency: int = 0
    powerful: bool = False
    shoot_dice_num: int = 0
    shoot_dice_sides: int = 0


def _strip_jsonc(text: str) -> str:
    """Remove JSONC comments and trailing commas without touching strings."""
    without_comments: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        if in_string:
            without_comments.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            without_comments.append(char)
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = len(text) if newline < 0 else newline
            continue
        if text.startswith("/*", index):
            closing = text.find("*/", index + 2)
            if closing < 0:
                raise ValueError("unterminated JSONC block comment")
            index = closing + 2
            continue
        without_comments.append(char)
        index += 1

    cleaned = "".join(without_comments)
    without_trailing_commas: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(cleaned):
        char = cleaned[index]
        if in_string:
            without_trailing_commas.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
        if char == ",":
            lookahead = index + 1
            while lookahead < len(cleaned) and cleaned[lookahead].isspace():
                lookahead += 1
            if lookahead < len(cleaned) and cleaned[lookahead] in "]}":
                index += 1
                continue
        without_trailing_commas.append(char)
        index += 1

    return "".join(without_trailing_commas)


def _maximum_hp(hit_point: str) -> int:
    match = re.fullmatch(r"(\d+)d(\d+)", hit_point)
    if match is None:
        raise ValueError(f"invalid monster hit_point: {hit_point!r}")
    return int(match.group(1)) * int(match.group(2))


def _average_hp(hit_point: str, force_max_hp: bool) -> int:
    match = re.fullmatch(r"(\d+)d(\d+)", hit_point)
    if match is None:
        raise ValueError(f"invalid monster hit_point: {hit_point!r}")
    number, sides = (int(value) for value in match.groups())
    return number * sides if force_max_hp else number * (sides + 1) // 2


def _maximum_dice(dice: str | None) -> int:
    if not dice:
        return 0
    match = re.fullmatch(r"(\d+)d(\d+)", dice)
    if match is None:
        return 0
    return int(match.group(1)) * int(match.group(2))


def _parse_dice(dice: str | None) -> tuple[int, int]:
    if not dice:
        return 0, 0
    match = re.fullmatch(r"(\d+)d(\d+)", dice)
    if match is None:
        raise ValueError(f"invalid monster damage_dice: {dice!r}")
    return tuple(int(value) for value in match.groups())


def _maximum_ranged_damage(
    abilities: set[str], level: int, max_hp: int, shoot: str | None
) -> int:
    """Conservative pre-resistance maximum for one ranged monster action."""
    maximum = _maximum_dice(shoot) if "SHOOT" in abilities else 0
    if any(ability.startswith("BR_") for ability in abilities):
        maximum = max(maximum, max_hp // 3)
    if "ROCKET" in abilities:
        maximum = max(maximum, max_hp // 4)
    if any(ability.startswith("BA_") for ability in abilities):
        maximum = max(maximum, level * 4 + 50)
    if any(ability.startswith(("BO_", "PSY_SPEAR")) for ability in abilities):
        maximum = max(maximum, level * 3 + 24)
    if any(ability.startswith("CAUSE_") for ability in abilities):
        maximum = max(maximum, level * 2 + 30)
    if abilities.intersection({"MIND_BLAST", "BRAIN_SMASH", "MISSILE"}):
        maximum = max(maximum, level * 2 + 20)
    if "HAND_DOOM" in abilities:
        # The spell is percentage based. A large sentinel makes it unconditionally
        # lethal without requiring hidden player data in the race definition.
        maximum = max(maximum, 100_000)
    return maximum


def load_monrace_knowledge(path: Path) -> dict[int, MonraceKnowledge]:
    data: dict[str, Any] = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    result: dict[int, MonraceKnowledge] = {}
    for monster in data.get("monsters", []):
        skill = monster.get("skill", {})
        abilities = set(skill.get("list", []))
        if skill.get("shoot"):
            abilities.add("SHOOT")
        flags = set(monster.get("flags", []))
        max_hp = _maximum_hp(monster["hit_point"])
        level = int(monster.get("level", 0))
        blows = tuple(
            MonsterBlow(
                method=str(blow.get("method", "")),
                effect=str(blow.get("effect", "")),
                dice_num=_parse_dice(blow.get("damage_dice"))[0],
                dice_sides=_parse_dice(blow.get("damage_dice"))[1],
            )
            for blow in monster.get("blows", [])
        )
        max_melee_damage = sum(
            blow.dice_num * blow.dice_sides
            for blow in blows
            if blow.effect not in NON_HP_DAMAGE_BLOW_EFFECTS
        )
        probability = str(skill.get("probability", ""))
        probability_match = re.fullmatch(r"1_IN_(\d+)", probability)
        spell_frequency = (
            100 // int(probability_match.group(1))
            if probability_match is not None
            else 0
        )
        shoot_num, shoot_sides = _parse_dice(skill.get("shoot"))
        result[int(monster["id"])] = MonraceKnowledge(
            max_hp=max_hp,
            speed=110 + int(monster.get("speed", 0)),
            can_summon=bool(SUMMON_ABILITIES.intersection(abilities)),
            friendly="FRIENDLY" in flags,
            level=level,
            max_melee_damage=max_melee_damage,
            max_ranged_damage=_maximum_ranged_damage(
                abilities, level, max_hp, skill.get("shoot")
            ),
            can_multiply="MULTIPLY" in flags,
            average_hp=_average_hp(
                monster["hit_point"], "FORCE_MAXHP" in flags
            ),
            armor_class=int(monster.get("armor_class", 0)),
            rarity=int(monster.get("rarity", 0)),
            flags=frozenset(flags),
            abilities=frozenset(abilities),
            blows=blows,
            spell_frequency=spell_frequency,
            powerful="POWERFUL" in flags,
            shoot_dice_num=shoot_num,
            shoot_dice_sides=shoot_sides,
        )
    return result


def find_monrace_definitions(state_file: Path, override: Path | None) -> Path | None:
    if override is not None:
        return override

    configured = os.environ.get("HENGBAND_MONRACE_DEFINITIONS")
    if configured:
        return Path(configured)

    relative = Path("lib") / "edit" / "MonraceDefinitions.jsonc"
    candidates = [Path.cwd() / relative]
    candidates.extend(parent / relative for parent in state_file.resolve().parents)
    return next((candidate for candidate in candidates if candidate.is_file()), None)
