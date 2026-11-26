"""Whether a fixed quest is worth taking now: its reward against the character's needs and its risk.

Owner 2026-11-27 (verbatim): 「n1-cは長時間49Fで停滞している。これがQ25を放棄して確定入手テレパシーを
諦めた代償である。この結果を踏まえた上で固定クエストの取り扱いに関して作戦を立てると良い。」 and
「Q33も高難度だが報酬は貴重な加速装備であり非常に強力である。安直に諦めることが最善とは限らない。
しっかり比較検討すること。」.  The 2026-11-26 skip of Q18 and Q33 for every character
(strategy_profile) was decided from the losses alone; Q25 (its reward the telepathy of the 50F
depth gate) disappeared with Q18, and n1-c (CL41) sat at Angband 49F for about 8 hours.

The table is data, ``strategy/quests/quest-value.jsonc`` (``TABLE_FILE``): per quest its reward,
the depth-gate names the reward fills (``fills``, the names of
``_missing_required_abilities``), the quests finishing it unlocks (``unlocks``), the measured
attempts (``history``), and the character level from which a needed but risky quest is taken
(``min_cl``).  ``verdict`` is the one answer to "is this quest worth taking now":

- needed: a name it fills (or a name a quest it unlocks fills) is missing at the depth the
  character heads for, its deepest recall depth plus ``horizon_floors``, counting the carried and
  Home pieces (``_missing_required_abilities(owned=True)``).  Board facts, never the class: a
  Zombie's innate see-invisible counts, an Amberite has none;
- safe: the measured death rate is at most ``safe_death_rate`` over at least
  ``safe_min_attempts`` attempts (the cheap openers, Q31, Q32);
- a needed quest is taken from ``min_cl`` (below it, deferred: the character keeps levelling in
  the ordinary flow); a safe one whenever its acceptance rows are met; a quest neither needed nor
  safe is passed over.  "Binding" (the need is missing one floor below the deepest recall depth:
  the character is held at that gate now) is reported with the verdict.

``holds_back`` is what the fixed-quest order (``_build_fixed_quest_head``) and the town's quest
supplies (``_quest_strategy_for_errand_or_floor``) ask, next to quest_one_turn_kill's: a quest held
back is not requested, travelled to or bought for.  A taken quest is never held back.  Rule 2
(MAINTAINABILITY.md): a deferred or passed-over quest stops nothing, the ordinary flow goes on.
The instance's strategy profile (``skip_quests``) is asked before this (``fixed_quest_skipped``);
a profile with ``quest_value: false`` (the unit tests' ``ALL_FIXED_QUESTS``) is never held back here.
A missing or malformed table holds nothing back (every approved quest as before), with a warning.
"""

from __future__ import annotations

import functools
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hengbot.item_reservation import decision_memo
from hengbot.policy_constants import QUEST_STATUS_FINISHED, QUEST_STATUS_REWARDED, QUEST_STATUS_UNTAKEN

TABLE_FILE = Path(__file__).resolve().parents[2] / "strategy" / "quests" / "quest-value.jsonc"
DONE_STATUSES = frozenset({QUEST_STATUS_REWARDED, QUEST_STATUS_FINISHED})


@dataclass(frozen=True)
class QuestValue:
    quest_id: int
    fills: frozenset
    unlocks: tuple
    wins: int
    deaths: int
    fails: int
    min_cl: int


@dataclass(frozen=True)
class Table:
    horizon_floors: int
    safe_death_rate: float
    safe_min_attempts: int
    quests: dict = field(default_factory=dict)

    def safe(self, row: QuestValue) -> bool:
        attempts = row.wins + row.deaths + row.fails
        return attempts >= self.safe_min_attempts and row.deaths <= self.safe_death_rate * attempts


@dataclass(frozen=True)
class Verdict:
    quest_id: int
    take: bool
    why: str          # needed / safe / deferred / no-need / no-row
    needs: frozenset  # the missing names the quest (or a quest it unlocks) fills
    binding: bool     # a need is missing one floor below the deepest recall depth
    min_cl: int

    def record(self) -> dict:
        return {"quest": self.quest_id, "take": self.take, "why": self.why,
                "needs": sorted(self.needs), "binding": self.binding, "min_cl": self.min_cl}


def _strip_jsonc(text: str) -> str:
    from hengbot.quest_strategies import _strip_jsonc as strip
    return strip(text)


def parse(data: Any) -> Table:
    rows = {}
    for entry in data["quests"]:
        history = entry.get("history", {})
        rows[int(entry["quest_id"])] = QuestValue(
            quest_id=int(entry["quest_id"]), fills=frozenset(entry.get("fills", ())),
            unlocks=tuple(int(quest) for quest in entry.get("unlocks", ())),
            wins=int(history.get("wins", 0)), deaths=int(history.get("deaths", 0)),
            fails=int(history.get("fails", 0)), min_cl=int(entry.get("min_cl", 0)))
    return Table(horizon_floors=int(data["horizon_floors"]),
                 safe_death_rate=float(data["safe_death_rate"]),
                 safe_min_attempts=int(data["safe_min_attempts"]), quests=rows)


def load(path: Path = TABLE_FILE) -> Table | None:
    """The table, or None (with a warning) when it cannot be read: nothing is held back then."""
    try:
        return parse(json.loads(_strip_jsonc(Path(path).read_text(encoding="utf-8"))))
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"could not load the quest value table ({path}): {exc}", file=sys.stderr)
        return None


@functools.lru_cache(maxsize=1)
def table() -> Table | None:
    """The repository's table, read once per process."""
    return load()


def deepest_recall_depth(snapshot) -> int:
    depths = list(getattr(snapshot, "dungeon_recall_depths", {}).values())
    return max([int(getattr(snapshot, "recall_depth", 0) or 0), *depths], default=0)


def _done(snapshot, quest_id: int) -> bool:
    quest = snapshot.quests.get(quest_id)
    return quest is not None and quest.status in DONE_STATUSES


def _needs(policy, snapshot, values: Table, quest_id: int, missing: frozenset, seen: frozenset) -> frozenset:
    """The missing names ``quest_id``'s reward fills, and those of the approved quests it unlocks."""
    row = values.quests.get(quest_id)
    if row is None or quest_id in seen:
        return frozenset()
    needs = row.fills & missing
    for unlocked in row.unlocks:
        if not _done(snapshot, unlocked) and policy.approved_quest_strategy(unlocked) is not None:
            needs |= _needs(policy, snapshot, values, unlocked, missing, seen | {quest_id})
    return needs


def binding_gate_needs(policy, snapshot) -> frozenset:
    """The depth-gate names missing one floor below the deepest recall depth (the carried and
    Home pieces counted): what holds the character at its gate now (bm_tour reads it too)."""
    return frozenset(policy._missing_required_abilities(
        snapshot, deepest_recall_depth(snapshot) + 1, owned=True))


def _verdict(policy, snapshot, quest_id: int) -> Verdict:
    values = table()
    row = None if values is None else values.quests.get(quest_id)
    if row is None:
        return Verdict(quest_id, True, "no-row", frozenset(), False, 0)
    reached = deepest_recall_depth(snapshot)
    missing = frozenset(policy._missing_required_abilities(
        snapshot, reached + values.horizon_floors, owned=True))
    needs = _needs(policy, snapshot, values, quest_id, missing, frozenset())
    binding = bool(needs & binding_gate_needs(policy, snapshot))
    if values.safe(row):
        return Verdict(quest_id, True, "safe", needs, binding, 0)
    if not needs:
        return Verdict(quest_id, False, "no-need", needs, binding, row.min_cl)
    if snapshot.player.level >= row.min_cl:
        return Verdict(quest_id, True, "needed", needs, binding, row.min_cl)
    return Verdict(quest_id, False, "deferred", needs, binding, row.min_cl)


def verdict(policy, snapshot, quest_id: int) -> Verdict:
    """The one answer: is ``quest_id`` worth taking now (module docstring)."""
    key = (quest_id, snapshot.player.level, deepest_recall_depth(snapshot),
           tuple(sorted((qid, quest.status) for qid, quest in snapshot.quests.items())))
    return decision_memo(policy, "quest-value", snapshot, key,
                         lambda: _verdict(policy, snapshot, quest_id))


VERDICTS = "_quest_value_verdicts"   # {quest id: the last verdict's record}; life, the log's view


def holds_back(policy, snapshot, quest_id: int) -> bool:
    """An untaken quest the verdict passes over or defers (the fixed-quest order, the supplies)."""
    quest = snapshot.quests.get(quest_id)
    if quest is not None and quest.status != QUEST_STATUS_UNTAKEN:
        return False
    if not getattr(getattr(policy, "_instance_profile", None), "quest_value", True):
        return False
    found = verdict(policy, snapshot, quest_id)
    setattr(policy, VERDICTS, {**getattr(policy, VERDICTS, {}), quest_id: found.record()})
    return not found.take


def memo_key(snapshot) -> tuple:
    """What the verdicts read beside the quests and the level, for the callers' own memo keys."""
    from hengbot import ability_sources
    return (deepest_recall_depth(snapshot), snapshot.player.speed,
            frozenset(ability_sources.held_abilities(snapshot.player)))


def facts(policy) -> dict:
    """The decision log's view (``fixedquest_readiness.quest_value``): the last verdicts asked."""
    return {str(quest_id): record for quest_id, record in sorted(getattr(policy, VERDICTS, {}).items())}
