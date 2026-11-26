"""The per-instance strategy profile (``strategy-profile.json``) and the skipped fixed quests.

Owner 2026-11-26 「2度勝利したので戦略を変える。n1-cはこのままゾンビ魔道具術師で勝率と時間効率改善を
進める。n1-aとn1-bは自由なキャラクタと戦略で勝利を目指すこと。いずれも、ゲーム内選択に関して私の
以前の指示を破ることを許可する。」.  The supervisor's decision on it: over the last 83 Magic-Eater
lives the optional town quests cost 14 lives and 88.6 hours (Q25 7 stuck and 1 death, Q33 2 deaths
in its last 7 attempts, Q18 1 death, Q31 1 stuck), and none is needed to win (only the guardians of
Angband 99F and 100F, ``WIN_QUEST_IDS``).  So every character skips Q18 and Q33
(``DEFAULT_SKIPPED_QUESTS``), and an instance may skip more.

A skipped quest is never requested, never travelled to and, when it is taken anyway, ignored: it
is never entered and no town stage waits or buys for it.  ``quest_skipped`` is the one answer;
``HengbotPolicy._known_fixed_quests`` leaves a skipped quest out and
``HengbotPolicy.approved_quest_strategy`` gives it no strategy, the two doors every quest consumer
goes through (``HengbotPolicy.fixed_quest_supported`` for the few that read the board's quests
directly).  The in-dungeon random quests and the 99F/100F guardian quests are never skipped.

The profile is read-only configuration, read once when the bot starts (``for_run``):

 * ``HENGBOT_STRATEGY_PROFILE`` (``PROFILE_ENV``), when set, names the file;
 * otherwise the first ``strategy-profile.json`` found in the decision log's directory and its two
   parents.  On the Linux soak the decision log is ``~/hengbot-soak/<instance>/life-NNN/jsonlog/
   bot-decisions.jsonl``, so the instance's profile is ``~/hengbot-soak/<instance>/
   strategy-profile.json``, shared by all its lives (a file in ``life-NNN/`` or ``jsonlog/`` would
   win for that life alone).  With no decision log the runtime directory
   (``HENGBOT_RUNTIME_DIR``) stands in for its directory.

Keys (unknown keys are ignored, so a later feature can add its own here):

 * ``name``: a string, logged once at the start (the decision log's session marker, stderr);
 * ``skip_quests``: quest numbers skipped on top of ``DEFAULT_SKIPPED_QUESTS``;
 * ``skip_all_optional_fixed_quests_from_level``: every optional fixed (town-given) quest whose
   quest level (``QuestInfo.level``) is this or more is skipped too.

No file is the defaults.  A file that cannot be read or parsed, or a key of the wrong type, is the
defaults (for that key) and a warning in ``InstanceProfile.warnings``; it never stops the bot.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from hengbot.policy_constants import WIN_QUEST_IDS

PROFILE_FILE_NAME = "strategy-profile.json"
PROFILE_ENV = "HENGBOT_STRATEGY_PROFILE"
RUNTIME_DIR_ENV = "HENGBOT_RUNTIME_DIR"
# The policy attribute holding the instance's profile (state_registry row, set by cli).
POLICY_ATTRIBUTE = "_instance_profile"

DEFAULT_SKIPPED_QUESTS = frozenset({18, 33})
# The decision log's directory and its two parents: jsonlog/, life-NNN/, the instance.
_SEARCH_DEPTH = 3
# quest_knowledge.QUEST_TYPE_RANDOM (not imported: quest_knowledge loads the monster tables).
_QUEST_TYPE_RANDOM = 7


@dataclass(frozen=True)
class InstanceProfile:
    """One instance's strategy profile; ``skipped_quests`` already holds the defaults."""

    name: str = "default"
    skipped_quests: frozenset = DEFAULT_SKIPPED_QUESTS
    skip_from_level: int | None = None
    source: str | None = None
    warnings: tuple[str, ...] = field(default=())

    def summary(self) -> dict:
        """What the start logs: the name, where it came from, what it skips."""
        record: dict[str, Any] = {
            "name": self.name,
            "source": self.source,
            "skipped_quests": sorted(self.skipped_quests),
            "skip_all_optional_fixed_quests_from_level": self.skip_from_level,
        }
        if self.warnings:
            record["warnings"] = list(self.warnings)
        return record


DEFAULT_PROFILE = InstanceProfile()
# Every fixed quest played as before 2026-11-26: the unit tests' policies (tests/__init__.py), whose
# Q18/Q33 cases drive the quest strategies themselves.
ALL_FIXED_QUESTS = InstanceProfile(name="all-fixed-quests", skipped_quests=frozenset())

# What a new policy starts with before cli gives it the run's profile.
_policy_default = DEFAULT_PROFILE


def policy_default() -> InstanceProfile:
    return _policy_default


def set_policy_default(profile: InstanceProfile) -> None:
    """The profile new policies start with (tests/__init__.py sets ``ALL_FIXED_QUESTS``)."""
    global _policy_default
    _policy_default = profile


def _quest_numbers(value: Any) -> tuple[frozenset, str | None]:
    if not isinstance(value, list) or not all(
        isinstance(number, int) and not isinstance(number, bool) for number in value
    ):
        return frozenset(), f"skip_quests is not a list of quest numbers: {value!r}"
    return frozenset(value), None


def parse(data: Any, source: str | None = None) -> InstanceProfile:
    """The profile of a decoded file; never raises."""
    if not isinstance(data, dict):
        return InstanceProfile(source=source, warnings=(f"not a JSON object: {type(data).__name__}",))
    warnings: list[str] = []
    name = data.get("name", "default")
    if not isinstance(name, str):
        warnings.append(f"name is not a string: {name!r}")
        name = "default"
    skipped = DEFAULT_SKIPPED_QUESTS
    if "skip_quests" in data:
        extra, warning = _quest_numbers(data["skip_quests"])
        if warning is not None:
            warnings.append(warning)
        skipped = skipped | extra
    level = data.get("skip_all_optional_fixed_quests_from_level")
    if level is not None and (not isinstance(level, int) or isinstance(level, bool)):
        warnings.append(f"skip_all_optional_fixed_quests_from_level is not an integer: {level!r}")
        level = None
    return InstanceProfile(name=name, skipped_quests=skipped, skip_from_level=level,
                           source=source, warnings=tuple(warnings))


def load(path: Path) -> InstanceProfile:
    """The profile of ``path``: the defaults with a warning when it cannot be read."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        return InstanceProfile(source=str(path), warnings=(f"unreadable: {exc}",))
    try:
        data = json.loads(text)
    except ValueError as exc:
        return InstanceProfile(source=str(path), warnings=(f"malformed JSON: {exc}",))
    return parse(data, str(path))


def locate(decision_log: Path | None, environ: Mapping[str, str] | None = None) -> Path | None:
    """The profile file of this run, None for the defaults (the lookup of the module doc)."""
    environ = os.environ if environ is None else environ
    named = environ.get(PROFILE_ENV, "").strip()
    if named:
        return Path(named)
    if decision_log is not None:
        directory = Path(decision_log).parent
    else:
        runtime = environ.get(RUNTIME_DIR_ENV, "").strip()
        if not runtime:
            return None
        directory = Path(runtime)
    for candidate in (directory, *directory.parents[:_SEARCH_DEPTH - 1]):
        path = candidate / PROFILE_FILE_NAME
        if path.is_file():
            return path
    return None


_CACHE: dict[str | None, InstanceProfile] = {}


def for_run(decision_log: Path | None, environ: Mapping[str, str] | None = None) -> InstanceProfile:
    """The run's profile, read once per file (cached)."""
    path = locate(decision_log, environ)
    key = None if path is None else str(path)
    cached = _CACHE.get(key)
    if cached is None:
        cached = DEFAULT_PROFILE if path is None else load(path)
        _CACHE[key] = cached
    return cached


def quest_skipped(profile: InstanceProfile, quest_id: int, info: Any = None) -> bool:
    """Whether the instance skips this optional fixed quest (``info``: its ``QuestInfo``)."""
    if quest_id in WIN_QUEST_IDS:
        return False
    if info is not None and getattr(info, "type", None) == _QUEST_TYPE_RANDOM:
        return False
    if quest_id in profile.skipped_quests:
        return True
    return (profile.skip_from_level is not None and info is not None
            and int(getattr(info, "level", 0)) >= profile.skip_from_level)
