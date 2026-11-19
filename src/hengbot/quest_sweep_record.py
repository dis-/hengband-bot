"""The room sweep's kill lines of its tracked races (quest_alignment_split), carried across a bot restart.

``QuestFloorNavigator.split_kills`` lived in the process only.  n1-c life-217 (Quest 33, 2026-11-19):
the three Its (18:30), the three Dagons and the three Bokrugs (20:24-20:30) were killed and counted from
the game's kill lines, then the process was restarted after the 20:59 halt.  The resumed process
(22:46) began the floor with no kills: quest_alignment_split ``living`` read every placement of those
races as alive, so the 段2 lure (quest_lure_approach, ``after_races_dead`` [393, 595, 489]) never ran,
the stands waited for the dead (quest_wait_placement), and the sweep stopped by name at [14,30]
(quest:blocked:sweep-nothing-comes) until the loop detector halted it at 22:46.

The design is quest25_battle_record's (the Q25 phase battle's kills, n1-a life-494 2026-11-07): a record
beside the decision log keeps the floor, the game turn and the kills every decision left, written at the
``choose_key`` exit.  The first decision of a process restores it only on the same quest floor; a game
reloaded from an older save of the floor keeps only the kills read at or before the save's turn (they
happened in the game the save holds, the later ones did not).  Nothing is invented: each kill restored
is one the previous process read from the game's kill line (q2_kill_credit ``_killed``) with the turn it
read it.  The board the previous process last read is recorded by its turn and messages: shown it again,
the restarted process does not count its kill lines twice.

The game itself shows no per-race kill count on the board (bot-json-output.cpp gives a race's level only
once r_tkills > 0, the lore of every life, not of this floor), and the telepathy reaches 20 grids
(monster-update.cpp decide_sight_invisible_monster), not the 31 x 80 map, so neither tells this floor's
dead from the board.
"""
from __future__ import annotations

import json
from pathlib import Path

VERSION = 1


def _navigator_of(policy, snapshot):
    if getattr(snapshot, "in_town", False):
        return None
    quest_id = snapshot.floor_key[2]
    navigator = (getattr(policy, "_quest_navigators", None) or {}).get(quest_id)
    if navigator is None or navigator.floor_key != tuple(snapshot.floor_key):
        return None
    return navigator


def observe(policy, snapshot) -> None:
    """The first decision of the process: read the previous process's record once."""
    path = getattr(policy, "_sweep_kill_record_path", None)
    if path is None or getattr(policy, "_sweep_kill_record_read", False):
        return
    policy._sweep_kill_record_read = True
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(record["version"]) != VERSION or not record["kills"]:
            return
        floor_key = tuple(int(part) for part in record["floor"])
        kills = tuple((int(race), int(turn)) for race, turn in record["kills"])
        board = record.get("board")
        board = None if board is None else (int(board[0]), tuple(str(text) for text in board[1]))
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return
    if snapshot.in_town or floor_key != tuple(snapshot.floor_key):
        return
    if snapshot.turn < int(record.get("turn", 0)):
        # An older save of the same floor: only the kills read at or before its turn.
        kills, board = tuple(kill for kill in kills if kill[1] <= snapshot.turn), None
        if not kills:
            return
    policy._sweep_kills_restored = (floor_key, kills, board)


def take(policy, snapshot, navigator) -> None:
    """Every board a sweep reads: the restored kills, once, into a navigator holding none on this
    floor; the recorded board marked read."""
    pending = getattr(policy, "_sweep_kills_restored", None)
    if pending is None:
        return
    floor_key, kills, board = pending
    if floor_key != tuple(snapshot.floor_key) or navigator.floor_key != floor_key:
        return
    policy._sweep_kills_restored = None
    if navigator.split_kill_turns:
        return
    counts: dict = {}
    for race, _turn in kills:
        counts[race] = counts.get(race, 0) + 1
    navigator.split_kills = counts
    navigator.split_kill_turns = kills
    if board is not None and board == (int(snapshot.turn), tuple(str(m) for m in snapshot.messages)):
        navigator.split_board = board


def record(policy, snapshot) -> None:
    """The ``choose_key`` exit: write the kills this decision left (none off a sweep's floor)."""
    path = getattr(policy, "_sweep_kill_record_path", None)
    if path is None:
        return
    navigator = _navigator_of(policy, snapshot)
    kills = [] if navigator is None else [list(kill) for kill in navigator.split_kill_turns]
    previous = getattr(policy, "_sweep_kill_record", None)
    if not kills and (previous is None or not previous["kills"]):
        return  # every record without kills restores nothing
    read = None if navigator is None else navigator.split_board
    entry = {"version": VERSION, "floor": list(snapshot.floor_key), "turn": int(snapshot.turn),
             "kills": kills,
             "board": [int(read[0]), list(read[1])] if read is not None and read[0] == snapshot.turn else None}
    if previous == entry:
        return
    policy._sweep_kill_record = entry
    try:
        Path(path).write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass
