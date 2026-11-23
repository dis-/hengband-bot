"""Dives that end at once on the means-spent Recall: a round-trip loop, a named stop.

n1-a life-530 (2026-11-18 10:29-12:50): the town counted the Home's *Destruction* staves for the
50F+ destination (destruction_use.holds_means) and the departure carried none, so every dive
landed at 51F/52F without the means and read Word of Recall on the arrival board
(destruction_use.means_spent_recall_key, owner 2026-11-14 「敵への対処以前に手段が尽きた時点で
帰還させる。」).  About 250 such round trips ran for over two hours and nothing named them; the
last one was fatal.

The departure no longer leaves for 50F+ without the means carried (destruction_means.
departure_carried; owner 2026-11-18 「破壊を持っていないのに50F以降にいるのが不具合」).  This is
the net under it: a dive whose arrival board starts the means-spent return is *spent at once*;
two such dives in a row to the same arrival (dungeon, level), with no other dive between,
stop the next 50F+ departure under ``STOP_REASON`` (a policy final stop) rather than inventing
another destination: such a pair is a defect of the town's choice, not a state to live with.

The record (``MEMORY``, state_registry): the floor the last board stood on and the game turn it
was entered, the last spent-at-once arrival and the streak, and whether the current dive was
counted.  ``observe`` reads every board; ``note_return`` is called where the means-spent return
starts; ``looping`` is read by the town-to-dungeon boundary (policy_navigation.
_dungeon_entry_allowed).
"""
from __future__ import annotations

from dataclasses import dataclass

from hengbot import deep_admission

MEMORY = "_means_spent_loop"
STOP_REASON = "town:blocked:destruction-means-spent-loop"
STOP_MESSAGE = ("two dives in a row to the same 50F+ arrival read the means-spent Recall on "
                "their arrival board (no *Destruction* means carried)")
STREAK_STOP = 2


@dataclass
class Loop:
    floor: tuple | None = None        # the floor the last board stood on
    entered_turn: int | None = None   # the game turn of that floor's first board
    arrival: tuple | None = None      # (dungeon_id, level) of the last spent-at-once dive
    streak: int = 0                   # spent-at-once dives in a row to ``arrival``
    counted: bool = False             # the current dive was spent at once


def _memory(policy) -> Loop:
    loop = getattr(policy, MEMORY, None)
    if loop is None:
        loop = Loop()
        setattr(policy, MEMORY, loop)
    return loop


def observe(policy, snapshot) -> None:
    """Every board: a new floor is entered on this board.  Back in town, a dive that was not
    spent at once breaks the streak."""
    loop = _memory(policy)
    floor = tuple(snapshot.floor_key)
    if loop.floor == floor:
        return
    if snapshot.in_town and loop.floor is not None and not loop.counted:
        loop.streak = 0
        loop.arrival = None
    if snapshot.in_town:
        loop.counted = False
    loop.floor, loop.entered_turn = floor, snapshot.turn


def note_return(policy, snapshot) -> None:
    """The means-spent return starts on this board: on the floor's first board the dive is
    spent at once (its arrival counted); later on the floor it is an ordinary dive."""
    loop = _memory(policy)
    if loop.floor != tuple(snapshot.floor_key) or loop.entered_turn != snapshot.turn:
        loop.streak, loop.arrival = 0, None
        return
    if loop.counted:
        return
    arrival = tuple(snapshot.floor_key)[:2]
    loop.streak = loop.streak + 1 if arrival == loop.arrival else 1
    loop.arrival, loop.counted = arrival, True


def looping(policy, destination_depth: int) -> bool:
    """A 50F+ departure after ``STREAK_STOP`` spent-at-once dives in a row."""
    loop = getattr(policy, MEMORY, None)
    return (deep_admission.verdict(None, destination_depth, "departure-loop").deep
            and loop is not None
            and loop.streak >= STREAK_STOP)
