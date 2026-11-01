"""The floor's breeder judgement, carried across a bot restart.

The breakthrough latch (``_breeder_breakthrough_floor``, "state 2") lived in
the process only.  n1-c life-098 (鉄獄24階 random quest 41, 2026-11-02): the
loop-detected restart of 00:10:40 began the latched floor in state 1 again
and fired about 97 bolts into a Software bug swarm already 22 strong before
the latch re-armed at 00:11:00.

The record beside the decision log keeps the floor and its latch.  Like the
unseen attack and the town visit's purchases (policy_identification,
policy_home), the first board of a process restores it only on the same
dungeon floor at the same or a later game turn: the game does not advance
between the two processes, and every board the previous process saw on
another floor rewrote the record.  Every later board rewrites it when the
carried state changed.
"""
from __future__ import annotations

import json
from pathlib import Path


def _carried(policy, snapshot) -> dict:
    return {
        "breakthrough": policy._breeder_breakthrough_floor == snapshot.floor_key,
    }


def _restore(policy, snapshot, path) -> None:
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        floor_key = tuple(record["floor"])
        turn = int(record["turn"])
        carried = record["state"]
        latched = bool(carried["breakthrough"])
    except (OSError, ValueError, KeyError, TypeError):
        return
    if (snapshot.in_town or floor_key != tuple(snapshot.floor_key)
            or snapshot.turn < turn):
        return
    if latched:
        policy._breeder_breakthrough_floor = snapshot.floor_key


def carry(policy, snapshot, first_board: bool) -> None:
    """Restore on the process's first board; record the state otherwise."""
    path = getattr(policy, "_breeder_floor_record_path", None)
    if path is None:
        return
    if first_board:
        _restore(policy, snapshot, path)
    carried = _carried(policy, snapshot)
    previous = getattr(policy, "_breeder_floor_record", None)
    if not first_board and previous == (snapshot.floor_key, carried):
        return
    policy._breeder_floor_record = (snapshot.floor_key, carried)
    record = {"floor": list(snapshot.floor_key), "turn": snapshot.turn,
              "state": carried}
    try:
        Path(path).write_text(json.dumps(record) + "\n", encoding="utf-8")
    except OSError:
        pass
