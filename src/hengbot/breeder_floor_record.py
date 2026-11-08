"""The floor's breeder judgement, carried across a bot restart.

The breakthrough latch (``_breeder_breakthrough_floor``, "state 2") lived in
the process only.  n1-c life-098 (鉄獄24階 random quest 41, 2026-11-02): the
loop-detected restart of 00:10:40 began the latched floor in state 1 again
and fired about 97 bolts into a Software bug swarm already 22 strong before
the latch re-armed at 00:11:00.

The record beside the decision log keeps the floor, its latch and its
breeder engagement window (breeder_stalemate: the count and turn at the
window's start and the player actions counted since), so a restart neither
re-opens the 20-action window nor forgets the flight it decided.  Like the
unseen attack and the town visit's purchases (policy_identification,
policy_home), the first board of a process restores it only on the same
dungeon floor at the same or a later game turn: the game does not advance
between the two processes, and every board the previous process saw on
another floor rewrote the record.  The observation and the combat outcome of
every later board rewrite it when the carried state changed.
"""
from __future__ import annotations

import json
from pathlib import Path


_ENGAGEMENT_FIELDS = (
    "_breeder_engagement_start_count",
    "_breeder_engagement_start_turn",
    "_breeder_engagement_actions",
    "_breeder_engagement_last_turn",
    "_breeder_engagement_race",
    "_breeder_engagement_killed",
    "_breeder_attack_sent",
)


def _carried(policy, snapshot) -> dict:
    engaged = (
        policy._breeder_engagement_floor == snapshot.floor_key
        and policy._breeder_engagement_start_count is not None
    )
    return {
        "breakthrough": policy._breeder_breakthrough_floor == snapshot.floor_key,
        "engagement": (
            [getattr(policy, name) for name in _ENGAGEMENT_FIELDS]
            if engaged else None
        ),
    }


def _restore(policy, snapshot, path) -> None:
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        floor_key = tuple(record["floor"])
        turn = int(record["turn"])
        carried = record["state"]
        latched = bool(carried["breakthrough"])
        engagement = carried["engagement"]
        if engagement is not None:
            # A record written before the race field counts every breeder.
            count, start_turn, actions, last_turn, race, killed, sent = (
                None if value is None else int(value)
                for value in (*engagement, None, None)[:len(_ENGAGEMENT_FIELDS)]
            )
            actions = actions or 0
    except (OSError, ValueError, KeyError, TypeError):
        return
    if (snapshot.in_town or floor_key != tuple(snapshot.floor_key)
            or snapshot.turn < turn):
        return
    if latched:
        policy._breeder_breakthrough_floor = snapshot.floor_key
    if engagement is not None and count is not None:
        policy._breeder_engagement_floor = snapshot.floor_key
        policy._breeder_engagement_start_count = count
        policy._breeder_engagement_start_turn = start_turn
        policy._breeder_engagement_actions = actions
        policy._breeder_engagement_last_turn = last_turn
        policy._breeder_engagement_race = race
        policy._breeder_engagement_killed = bool(killed)
        policy._breeder_attack_sent = bool(sent)


def carry(policy, snapshot, first_board: bool) -> None:
    """Observation: restore on the process's first board, then record.

    Recording here keeps the record of a floor change (the latch and the
    window forgotten); ``record`` after the combat outcome keeps the
    decision's own latch and action count.
    """
    path = getattr(policy, "_breeder_floor_record_path", None)
    if path is None:
        return
    if first_board:
        _restore(policy, snapshot, path)
    _write(policy, snapshot, path, force=first_board)


def record(policy, snapshot) -> None:
    """Record the state the decision's combat outcome left."""
    path = getattr(policy, "_breeder_floor_record_path", None)
    if path is not None:
        _write(policy, snapshot, path, force=False)


def _write(policy, snapshot, path, *, force: bool) -> None:
    carried = _carried(policy, snapshot)
    previous = getattr(policy, "_breeder_floor_record", None)
    if not force and previous == (snapshot.floor_key, carried):
        return
    policy._breeder_floor_record = (snapshot.floor_key, carried)
    record = {"floor": list(snapshot.floor_key), "turn": snapshot.turn,
              "state": carried}
    try:
        Path(path).write_text(json.dumps(record) + "\n", encoding="utf-8")
    except OSError:
        pass
