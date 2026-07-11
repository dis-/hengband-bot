from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
class MonraceKnowledge:
    max_hp: int
    speed: int
    can_summon: bool
    friendly: bool


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


def load_monrace_knowledge(path: Path) -> dict[int, MonraceKnowledge]:
    data: dict[str, Any] = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    result: dict[int, MonraceKnowledge] = {}
    for monster in data.get("monsters", []):
        abilities = monster.get("skill", {}).get("list", [])
        flags = set(monster.get("flags", []))
        result[int(monster["id"])] = MonraceKnowledge(
            max_hp=_maximum_hp(monster["hit_point"]),
            speed=110 + int(monster.get("speed", 0)),
            can_summon=bool(SUMMON_ABILITIES.intersection(abilities)),
            friendly="FRIENDLY" in flags,
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
