"""The fixed-quest attempts and their outcomes, one jsonl row per event (record only).

Owner 2026-11-27 (verbatim): 「Q33も高難度だが報酬は貴重な加速装備であり非常に強力である。安直に諦めることが
最善とは限らない。しっかり比較検討すること。」; the supervisor's brief: record each quest's attempts
and outcomes from now on, so the estimates of strategy/quests/quest-value.jsonc (``history``,
``min_cl``) can be counted again from the attempts themselves instead of from the end-of-life
character dumps.

A row (``quest-attempts.jsonl`` beside the decision log, ``FILE_NAME``) is written when a fixed
quest's status changes on the board (``taken``, ``completed``, ``failed``, ``rewarded``,
``finished``: ``quest_status_names``) and when the character enters or leaves a fixed quest's
floor (``entered`` / ``left``, with the HP it left with).  A death inside a quest is the life's
last ``entered`` row with no ``left`` after it (the life's dump says the killer).  Each row holds
what the over-match reads: the character level, the maximum HP, the permanent speed, the gold,
the deepest recall depth and quest_value's last verdict of the quest.

The last statuses seen (``STATE``) are rebuilt from the first board of a process without a row
(a transition during a restart is lost; the end-of-life dump still has the outcome).  Any failure
of the record is printed, never raised.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from hengbot.flight_recorder import rotate_log

STATE = "_quest_outcome_statuses"   # {quest id: status} last seen, and "floor": the quest floor
PATH = "_quest_outcome_ledger_path"
FILE_NAME = "quest-attempts.jsonl"
ROTATE_BYTES = 4 * 1024 ** 2
GENERATIONS = 2
# quest-type-definition.h QuestStatusType.
STATUS_NAMES = {0: "untaken", 1: "taken", 2: "completed", 3: "rewarded", 4: "finished",
                5: "failed", 6: "failed-done"}


def _row(policy: Any, snapshot: Any, quest_id: int, event: str, **extra) -> dict:
    from hengbot import attack_expectation, quest_value
    player = snapshot.player
    verdict = getattr(policy, quest_value.VERDICTS, {}).get(quest_id)
    return {"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "turn": snapshot.turn, "quest": quest_id,
            "event": event, "cl": player.level, "max_hp": player.max_hp, "hp": player.hp,
            "permanent_speed": attack_expectation.permanent_speed(snapshot) - 110,
            "gold": player.gold, "deepest_recall": quest_value.deepest_recall_depth(snapshot),
            "verdict": verdict, **extra}


def _write(policy: Any, rows: list) -> None:
    path = getattr(policy, PATH, None)
    if path is None or not rows:
        return
    try:
        rotate_log(path, ROTATE_BYTES, GENERATIONS)
        with open(path, "a", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError) as exc:
        print(f"quest attempt ledger: {exc}", file=sys.stderr)


def observe(policy: Any, snapshot: Any) -> None:
    """Every decision: the rows of the fixed quests' changes since the last board."""
    try:
        _observe(policy, snapshot)
    except Exception as exc:  # noqa: BLE001 -- a record never stops the decision
        print(f"quest attempt ledger: {type(exc).__name__}: {exc}", file=sys.stderr)


def _observe(policy: Any, snapshot: Any) -> None:
    statuses = {quest_id: quest.status for quest_id, quest in snapshot.quests.items() if quest.fixed}
    floor_quest = snapshot.floor_key[2] if snapshot.floor_key[2] in statuses else 0
    seen = getattr(policy, STATE, None)
    setattr(policy, STATE, {"statuses": statuses, "floor": floor_quest})
    if seen is None:
        return
    rows = []
    for quest_id, status in sorted(statuses.items()):
        before = seen["statuses"].get(quest_id, 0)
        if status != before:
            rows.append(_row(policy, snapshot, quest_id, STATUS_NAMES.get(status, str(status)),
                             before=STATUS_NAMES.get(before, str(before))))
    if seen["floor"] != floor_quest:
        if seen["floor"]:
            rows.append(_row(policy, snapshot, seen["floor"], "left"))
        if floor_quest:
            rows.append(_row(policy, snapshot, floor_quest, "entered"))
    _write(policy, rows)
