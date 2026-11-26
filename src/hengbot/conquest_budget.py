"""A budget for each conquest target (the dungeon lord's hunt), carried across a bot restart.

Supervisor 2026-11-26, under the owner's leave of the same day 「…いずれも、ゲーム内選択に関して私の以前の
指示を破ることを許可する。」: it narrows the owner's 2026-11-19 「行き先を変えるのはダンジョンの主討伐の
みとする」 (angband_hold) -- the lord's hunt is no longer an open-ended destination.

Recorded: n1-c life-222 (Zombie Magic-Eater Lv43-46, Angband recall landing 80, its descent held
by the 81F speed +25 gate) took the Mountain's 50F, its last floor, as the conquest target
(policy_quest ``_conquest_target``) from 2026-11-25 07:40 to 15:05: 119 Recalls to the Mountain
50F, 7.4 hours, about 1.1 of them halted, until 大鷲王『ソロンドール』 (race 468, speed +35,
3,900 HP, ESCORTS, S_KIN) fell at 15:05.  The game places the guardian on the last floor of every
generation until it is killed (src/monster-floor/monster-generator.cpp alloc_guardian:
``dungeon.maxdepth == floor.dun_level`` and ``cur_num < max_num``; src/floor/cave-generator.cpp
fails the generation when it cannot), so every trip had him; the duel board read him T3 alone
(guardian_landing ``guardian_tier``), but his flock made the board T1 with an instant death
(13:19:55: 47 hostiles, the next action's p95 2,311 against HP 985) and the trips ended in
teleports, *Destruction* approaches toward the eagles and Recalls.  The reward was the
Mountain's final object, a Potion of New Life (lib/edit/DungeonDefinitions.jsonc final_floor
object 239), and the guardian's drops and experience -- nothing the 81F gate needed.

The budget (one dungeon at a time, ``_conquest_committed`` its target):

- a trip is a dive that stood on the target's last floor (its ``max_depth``) and ended without
  the conquest; the target is given up after ``TRIP_LIMIT`` of them;
- the guardian met: on its last floor it was shown and the hunt declined it
  (hunt_target ``guardian_declined``: not T2 or T3 from contact) or an escape was decided on a
  board that showed it (``ESCAPES``); once a dive, and the target is given up after
  ``MET_LIMIT`` such dives;
- a given-up target is never the conquest target again in this life; after ``GIVE_UP_LIMIT``
  given-up targets no new conquest is started in this life (the committed one may finish).

A life has its own decision log directory (jsonlog), so the record beside it is the life's; the
first board of a process restores it at the same or a later game turn, as the other restart
records do (alternate_dungeon_record).
"""
from __future__ import annotations

import json
from pathlib import Path

from hengbot.policy_constants import EMERGENCY_ESCAPE_REASONS, RELOCATING_ESCAPE_REASONS

STATE = "_conquest_ledger"
RECORD = "_conquest_ledger_record"
RECORD_PATH = "_conquest_ledger_record_path"
FILE_NAME = "conquest-budget.json"

TRIP_LIMIT = 6
MET_LIMIT = 2
GIVE_UP_LIMIT = 2
# The escapes that count as fleeing the shown guardian: the counted emergency and relocating
# escapes, and the 50F+ instant-death board's Recall in place of a self-teleport (deep_teleport).
ESCAPES = EMERGENCY_ESCAPE_REASONS | RELOCATING_ESCAPE_REASONS | frozenset({"deep-teleport:recall"})


def _fresh() -> dict:
    return {"trips": {}, "met": {}, "given_up": [], "dive": None}


def state(policy) -> dict:
    budget = getattr(policy, STATE, None)
    if budget is None:
        budget = _fresh()
        setattr(policy, STATE, budget)
    return budget


def given_up(policy, dungeon_id: int) -> bool:
    return int(dungeon_id) in state(policy)["given_up"]


def refuses_new(policy) -> bool:
    """No new conquest target in this life: ``GIVE_UP_LIMIT`` targets were given up."""
    return len(state(policy)["given_up"]) >= GIVE_UP_LIMIT


def give_up(policy, dungeon_id: int) -> None:
    budget = state(policy)
    if int(dungeon_id) not in budget["given_up"]:
        budget["given_up"].append(int(dungeon_id))
    if policy._conquest_committed == dungeon_id:
        policy._conquest_committed = None


def _count(policy, field: str, dungeon_id: int, limit: int) -> None:
    budget = state(policy)
    key = str(int(dungeon_id))
    budget[field][key] = budget[field].get(key, 0) + 1
    if budget[field][key] >= limit:
        give_up(policy, dungeon_id)


def _last_floor_guardian(policy, snapshot, target) -> int | None:
    """The target's guardian race when this board is the target's unconquered last floor."""
    if target is None or snapshot.in_town or snapshot.floor_key[0] != target:
        return None
    info = policy._dungeon_knowledge.get(target)
    if (info is None or info.guardian_id <= 0 or info.max_depth <= 0
            or snapshot.dungeon_level != info.max_depth
            or target in snapshot.conquered_dungeon_ids):
        return None
    return info.guardian_id


def observe(policy, snapshot, previous_floor) -> None:
    """Every board, after hunt_target.observe: count the trip and the guardian met."""
    from hengbot import hunt_target  # import cycle (hunt_target reads policy_observation's state)

    budget = state(policy)
    if snapshot.in_town:
        dive = budget["dive"]
        budget["dive"] = None
        if (dive is not None and dive.get("bottom")
                and dive["dungeon"] not in snapshot.conquered_dungeon_ids):
            _count(policy, "trips", dive["dungeon"], TRIP_LIMIT)
        return
    target = policy._conquest_committed
    dive = budget["dive"]
    if dive is None or (previous_floor is not None and previous_floor[0] == 0):
        dive = budget["dive"] = {"dungeon": snapshot.floor_key[0], "bottom": False,
                                 "met": False, "seen": False}
    if dive["dungeon"] != snapshot.floor_key[0]:
        dive.update(dungeon=snapshot.floor_key[0], bottom=False, met=False, seen=False)
    fled = dive["seen"] and policy.last_reason in ESCAPES
    guardian = _last_floor_guardian(policy, snapshot, target)
    seen = False
    declined = False
    if guardian is not None:
        dive["bottom"] = True
        seen = any(monster.race_id == guardian
                   for monster in policy._sighted_or_detected_hostiles(snapshot))
        visit = hunt_target._visit(policy, snapshot)
        declined = seen and visit is not None and visit.guardian_declined
    if (fled or declined) and not dive["met"]:
        dive["met"] = True
        _count(policy, "met", dive["dungeon"], MET_LIMIT)
    dive["seen"] = seen


def restore(policy, snapshot) -> None:
    """On the process's first board: adopt the previous process's budget."""
    path = getattr(policy, RECORD_PATH, None)
    if path is None:
        return
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        turn = int(record["turn"])
        stored = record["state"]
        budget = {
            "trips": {str(int(k)): int(v) for k, v in stored["trips"].items()},
            "met": {str(int(k)): int(v) for k, v in stored["met"].items()},
            "given_up": [int(did) for did in stored["given_up"]],
            "dive": None,
        }
        dive = stored.get("dive")
        if dive is not None:
            budget["dive"] = {"dungeon": int(dive["dungeon"]), "bottom": bool(dive["bottom"]),
                              "met": bool(dive["met"]), "seen": bool(dive["seen"])}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return
    if snapshot.turn < turn:
        return
    setattr(policy, STATE, budget)
    if policy._conquest_committed in budget["given_up"]:
        policy._conquest_committed = None


def record(policy, snapshot, *, force: bool = False) -> None:
    """Rewrite the record when the budget changed."""
    path = getattr(policy, RECORD_PATH, None)
    if path is None:
        return
    carried = json.loads(json.dumps(state(policy)))
    if not force and getattr(policy, RECORD, None) == carried:
        return
    setattr(policy, RECORD, carried)
    try:
        Path(path).write_text(json.dumps({"turn": snapshot.turn, "state": carried}) + "\n",
                              encoding="utf-8")
    except OSError:
        pass
