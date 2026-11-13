"""The Q25 phase battle (``quest25_battle.Battle``), carried across a bot restart.

``QuestFloorNavigator.phase_battle`` lived in the process only.  n1-a life-494 (Q25 phase 1,
the ambush, 2026-11-07 20:06-20:09): the hound, the skeletal and spectral tyrannosaurs, two
spectres and a shadow demon were killed, then a restart began the floor at phase 0 with no
kills and the ambush's quiet count at 0.  The ambush ends only after 5000 quiet actions
(QUEST_25 ``wait_limits``, owner 2026-11-06), so every restart started that wait over, and the
later phases' kill counts (the stragglers, the sweep's 撃破カウント against the roster) no longer
held the kills read before it.

The record beside the decision log keeps the floor, the game turn and the battle every decision
left (written at the ``choose_key`` exit).  Like breeder_floor_record, the first decision of a
process restores it only on the same quest floor at the same or a later game turn: the game does
not advance between the two processes, and every decision the previous process made on another
floor (the town, another dungeon level) rewrote the record without a battle, so a new visit to
Q25 starts clean.  Nothing is invented: the kills restored are the ones the previous process read
from the game's kill lines.  The board the previous process last decided is recorded by its turn
and messages; when the restarted process is shown that board again, its kill lines and its quiet
action were already counted and are not counted twice.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from hengbot import quest25_geometry as geo

VERSION = 1
# Never carried: ``observed`` names a board of the previous process by its object id.
_NOT_CARRIED = frozenset({"observed"})


def _encode(value):
    if isinstance(value, frozenset):
        return {"set": sorted((_encode(item) for item in value), key=json.dumps)}
    if isinstance(value, tuple):
        return {"tuple": [_encode(item) for item in value]}
    if isinstance(value, dict):
        return {"dict": [[_encode(key), _encode(item)] for key, item in value.items()]}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(type(value).__name__)


def _decode(value):
    if isinstance(value, dict):
        (kind, items), = value.items()
        if kind == "set":
            return frozenset(_decode(item) for item in items)
        if kind == "tuple":
            return tuple(_decode(item) for item in items)
        if kind == "dict":
            return {_decode(key): _decode(item) for key, item in items}
        raise ValueError(kind)
    if isinstance(value, list):
        raise ValueError("list")
    return value


def _board(snapshot) -> list:
    return [int(snapshot.turn), [str(message) for message in snapshot.messages]]


def _battle_of(policy, snapshot):
    """The battle the policy holds for this floor visit, else None."""
    if snapshot.floor_key[2] != geo.QUEST_ID or getattr(snapshot, "in_town", False):
        return None
    navigator = (getattr(policy, "_quest_navigators", None) or {}).get(geo.QUEST_ID)
    if navigator is not None and navigator.floor_key == tuple(snapshot.floor_key) \
            and navigator.phase_battle is not None:
        return navigator.phase_battle
    pending = getattr(policy, "_q25_battle_restored", None)
    if pending is not None and pending[0] == tuple(snapshot.floor_key):
        return pending[1]
    return None


def observe(policy, snapshot) -> None:
    """The first decision of the process: read the previous process's record once."""
    path = getattr(policy, "_q25_battle_record_path", None)
    if path is None or getattr(policy, "_q25_battle_record_read", False):
        return
    policy._q25_battle_record_read = True
    from hengbot.quest25_battle import Battle
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(record["version"]) != VERSION or record["battle"] is None:
            return
        floor_key = tuple(int(part) for part in record["floor"])
        turn = int(record["turn"])
        names = {field.name for field in dataclasses.fields(Battle)} - _NOT_CARRIED
        fields = {name: _decode(value) for name, value in record["battle"].items() if name in names}
        if record["battle"].get("tome_gone"):   # a record written before ``gone`` (2026-11-13)
            fields["gone"] = fields.get("gone", frozenset()) | {geo.TOME}
        battle = Battle(**fields)
        board = record.get("board")
        board = None if board is None else (int(board[0]), tuple(str(text) for text in board[1]))
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return
    if (snapshot.in_town or floor_key != tuple(snapshot.floor_key)
            or floor_key[2] != geo.QUEST_ID or snapshot.turn < turn):
        return
    policy._q25_battle_restored = (floor_key, battle, board)


def take(policy, snapshot):
    """The restored battle for a navigator that has none on this floor (once), else None.

    Shown the board the previous process last decided, the battle marks it observed
    (``quest25_battle._observe`` keys a board by its turn and the snapshot's id).
    """
    pending = getattr(policy, "_q25_battle_restored", None)
    if pending is None:
        return None
    policy._q25_battle_restored = None
    floor_key, battle, board = pending
    if floor_key != tuple(snapshot.floor_key):
        return None
    if board is not None and board == (int(snapshot.turn), tuple(str(m) for m in snapshot.messages)):
        battle.observed = (snapshot.turn, id(snapshot))
    return battle


def record(policy, snapshot) -> None:
    """The ``choose_key`` exit: write the battle this decision left (None off the Q25 floor)."""
    path = getattr(policy, "_q25_battle_record_path", None)
    if path is None:
        return
    battle = _battle_of(policy, snapshot)
    try:
        carried = None if battle is None else {
            field.name: _encode(getattr(battle, field.name))
            for field in dataclasses.fields(battle) if field.name not in _NOT_CARRIED}
    except TypeError:
        carried = None
    previous = getattr(policy, "_q25_battle_record", None)
    if carried is None and previous is not None and previous["battle"] is None:
        return   # every record without a battle restores nothing
    # The board, only when the battle read it: a board the plan did not read never had its
    # kill lines counted, and the restarted process may read them.
    observed = None if battle is None else battle.observed
    entry = {"version": VERSION, "floor": list(snapshot.floor_key), "turn": int(snapshot.turn),
             "battle": carried,
             "board": _board(snapshot) if observed is not None and observed[0] == snapshot.turn
             else None}
    if previous == entry:
        return
    policy._q25_battle_record = entry
    try:
        Path(path).write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass
