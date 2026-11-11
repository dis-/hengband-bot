"""The decided recall-target switch, carried across a bot restart.

The over-extension valve's switch (``_alternate_dungeon``, its reason, the
depth that was too hard) and the streak counters of its lifecycle lived in the
process only.  n1-b life-362 (2026-11-09/10): every deploy restarted the bot,
the fresh process forgot the switch, the conquest target (the Mountain 50F)
and Angband 61-70F came back, and three more dives with emergency escapes
were needed before the valve switched again -- the dangerous dives redone
several times a day.

The record beside the decision log keeps that state.  Like the other restart
records (breeder_floor_record, town_end_mining), the first board of a process
restores it only at the same or a later game turn (the game does not advance
between the two processes), and only when no guardian fell meanwhile (a new
conquest ends the switch, ``policy_observation._observe``) and the alternate
is still an entered dungeon.  Every later board rewrites it when the carried
state changed.
"""
from __future__ import annotations

import json
from pathlib import Path

from hengbot.model import DUNGEON_ANGBAND


FIELDS = (
    "_alternate_dungeon",
    "_alternate_dungeon_reason",
    "_last_overextended_depth",
    "_target_empty_dives",
    "_guardian_bounce_dives",
    "_no_depth_progress_dives",
    # The lease of the switch (alternate_lease, owner 2026-11-11); absent from older records.
    "_alternate_lease",
    "_alternate_dives",
)
LEASE_FIELDS = ("_alternate_lease", "_alternate_dives")


def _carried(policy) -> dict:
    return {name: getattr(policy, name, None) for name in FIELDS}


def restore(policy, snapshot) -> None:
    """On the process's first board: adopt the previous process's switch."""
    path = getattr(policy, "_alternate_dungeon_record_path", None)
    if path is None:
        return
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        turn = int(record["turn"])
        conquered = frozenset(int(did) for did in record["conquered"])
        state = record["state"]
        alternate = state["_alternate_dungeon"]
        alternate = None if alternate is None else int(alternate)
        reason = state["_alternate_dungeon_reason"]
        reason = None if reason is None else str(reason)
        counters = {name: int((state.get(name) if name in LEASE_FIELDS else state[name]) or 0)
                    for name in FIELDS[2:]}
    except (OSError, ValueError, KeyError, TypeError):
        return
    if snapshot.turn < turn:
        return
    if not frozenset(snapshot.conquered_dungeon_ids) <= conquered:
        return  # a guardian fell meanwhile: the switch has ended
    if alternate is not None and not (
        alternate == DUNGEON_ANGBAND
        or alternate in (snapshot.entered_dungeon_ids or ())
    ):
        return
    policy._alternate_dungeon = alternate
    policy._alternate_dungeon_reason = reason
    for name, value in counters.items():
        setattr(policy, name, value)
    if alternate is not None:
        # The switch demoted the conquest latch when it was made.
        policy._conquest_committed = None


def record(policy, snapshot, *, force: bool = False) -> None:
    """Rewrite the record when the carried state changed."""
    path = getattr(policy, "_alternate_dungeon_record_path", None)
    if path is None:
        return
    carried = _carried(policy)
    if not force and getattr(policy, "_alternate_dungeon_record", None) == carried:
        return
    policy._alternate_dungeon_record = carried
    stored = {"turn": snapshot.turn,
              "conquered": sorted(snapshot.conquered_dungeon_ids),
              "state": carried}
    try:
        Path(path).write_text(json.dumps(stored) + "\n", encoding="utf-8")
    except OSError:
        pass
