"""Locked doors: a failed pick is progress, so the only way on is not written off at three.

exe_open (action/open-close-execution.cpp) picks a lock with the chance
``skill_dis - door_power * 4`` percent, floored at 2 (``if (j < 2) j = 2``), and answers a
failed pick "鍵をはずせなかった。" (LOCK_PICK_FAILED_MESSAGE_FRAGMENTS).  A door terrain without
the OPEN flag answers "…はがっちりと閉じられているようだ。" instead and no pick opens it.
``_step_toward`` reads the answer to its previous 'o' on a door (``note_answer``) into
``_stuck_doors`` or ``_locked_doors``.

``_step_toward`` writes a closed door off after DOOR_OPEN_LIMIT (3) 'o' (``_blocked_doors``):
ordinary exploration then goes to the next frontier, which is right while other ground is
left.  Where the door is the only known way on, three picks are no proof: the Q34 doors, the
fundraising return's door to its up staircase (D19) and the random quest search (n1-b
life-348, Angband 50F, RANDOM quest 40, 2026-11-08: two locked doors picked three times each,
the rest of the floor behind them, and ``quest-search:loop`` over the ~110 cells left from game
turn 3034339 on, 6,245 decisions in the capture's last 13 minutes alone) each keep picking.
This module is their one reading of the answer: ``unanswered_pick`` (the Q34 bounds count
only picks the game did not answer as a failed pick), ``stuck`` (never picked again) and
``locked`` (a lock the game showed).

``pick_key`` is the quest search's (quest_target_search.loop_key, asked where ordinary
exploration answered nothing): a written-off closed door the game answered as a lock, that
opens onto ground the walk does not reach (``_opens_onto``) and is not out of picks, is walked to
and picked, nearest first, before the secret door search and the lap.  Its picks are counted
as Q34's, against QUEST_SEARCH_DOOR_PICK_LIMIT (owner 2026-11-08 「諦めない」 for a held floor).
Every survival rung is above the asker.  A door picked open is ordinary floor again, and the
explore, asked first, walks through it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hengbot.model import Position, Snapshot
from hengbot.policy_constants import (
    LOCK_PICK_FAILED_MESSAGE_FRAGMENTS, NEIGHBOR_OFFSETS, QUEST_SEARCH_DOOR_PICK_LIMIT,
    STUCK_DOOR_MESSAGE_FRAGMENTS,
)

PICK_REASON = "quest-search:pick-lock"
SEEK_REASON = "quest-search:seek-locked-door"
MEMORY = "_locked_door_picks"


@dataclass
class Picks:
    floor: tuple
    unanswered: dict = field(default_factory=dict)  # (y, x) -> picks not answered as failed


def _answered(snapshot: Snapshot, fragments) -> bool:
    return any(fragment in message for message in snapshot.messages for fragment in fragments)


def unanswered_pick(snapshot: Snapshot) -> int:
    """1 unless the game answered the previous pick "failed to pick the lock".

    Snapshot messages are the lines new since the previous board.  That answer proves the
    door is a lock with at least the 2% floor chance per pick, so it is progress.
    """
    return 0 if _answered(snapshot, LOCK_PICK_FAILED_MESSAGE_FRAGMENTS) else 1


def note_answer(policy, snapshot: Snapshot, yx: tuple) -> None:
    """``_step_toward``, about to post 'o' on the door at ``yx`` again: this board's lines
    answer the previous one, "appears to be stuck" or "failed to pick the lock"."""
    for name, fragments in (("_stuck_doors", STUCK_DOOR_MESSAGE_FRAGMENTS),
                            ("_locked_doors", LOCK_PICK_FAILED_MESSAGE_FRAGMENTS)):
        if _answered(snapshot, fragments):
            doors = getattr(policy, name, None)
            if doors is None:
                doors = set()
                setattr(policy, name, doors)
            doors.add((snapshot.floor_key, yx))


def _this_floor(policy, snapshot: Snapshot, name: str) -> set:
    return {yx for floor, yx in getattr(policy, name, ()) if floor == snapshot.floor_key}


def stuck(policy, snapshot: Snapshot) -> set:
    """The (y, x) of this floor's doors the game answered as stuck (no pick opens them)."""
    return _this_floor(policy, snapshot, "_stuck_doors")


def locked(policy, snapshot: Snapshot) -> set:
    """The (y, x) of this floor's doors the game answered "failed to pick the lock"."""
    return _this_floor(policy, snapshot, "_locked_doors")


def _picks(policy, snapshot: Snapshot) -> Picks:
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.floor != snapshot.floor_key:
        memory = Picks(snapshot.floor_key)
        setattr(policy, MEMORY, memory)
    return memory


def _opens_onto(policy, snapshot: Snapshot, door: Position, routes: dict) -> bool:
    """The door hides ground (the explore's ``_passage_hides_ground``), or remembered floor
    the walk cannot reach lies beside it: a magic mapping's corridor beyond a door is
    explored floor, the frontier past it no door route reaches once the door is written off."""
    if policy._passage_hides_ground(snapshot, door):
        return True
    return any(
        (beyond := Position(door.y + dy, door.x + dx)) not in routes
        and (beyond.y, beyond.x) in policy._floor_t
        for dy, dx in NEIGHBOR_OFFSETS)


def _written_off(policy, snapshot: Snapshot, memory: Picks, routes: dict) -> list:
    """The locks the three-pick cap wrote off that may still open onto ground."""
    held, locks = stuck(policy, snapshot), locked(policy, snapshot)
    doors = []
    for yx in sorted(policy._blocked_doors):
        grid = snapshot.grids.get(Position(*yx))
        if grid is not None and not grid.is_closed_door:
            continue  # opened, broken or gone since
        if (yx in held or yx not in locks or yx not in policy._remembered_door_t
                or memory.unanswered.get(yx, 0) >= QUEST_SEARCH_DOOR_PICK_LIMIT):
            continue
        if _opens_onto(policy, snapshot, Position(*yx), routes):
            doors.append(Position(*yx))
    return doors


def pick_key(policy, snapshot: Snapshot, routes: dict, walk) -> str | None:
    """Pick the nearest written-off locked door that opens onto ground, or walk beside it.

    ``routes`` is the asker's walkable cells -> (walking distance, first step); ``walk``
    its ``(goal, reason) -> key`` step as progress.  None when no such door is reachable.
    """
    memory = _picks(policy, snapshot)
    best = None
    for door in _written_off(policy, snapshot, memory, routes):
        for dy, dx in NEIGHBOR_OFFSETS:
            beside = Position(door.y + dy, door.x + dx)
            if beside in routes and (best is None or routes[beside][0] < routes[best[1]][0]):
                best = (door, beside)
    if best is None:
        return None
    door, beside = best
    if beside != snapshot.player.position:
        return walk(beside, SEEK_REASON)
    yx = (door.y, door.x)
    memory.unanswered[yx] = memory.unanswered.get(yx, 0) + unanswered_pick(snapshot)
    # Standing still at the door is not an oscillation (as a loop step, quest_target_search).
    policy._recent.clear()
    policy._nav_stall_count = 0
    policy.last_reason = PICK_REASON
    policy._declare_reach(door)
    return policy._step_toward(snapshot, door)
