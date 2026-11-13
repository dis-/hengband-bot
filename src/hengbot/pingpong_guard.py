"""Two owners stepping opposite ways in turn: the move stays with the higher-priority one.

Owner 2026-11-13 (「同型のループが多いが再発防止できないのか？」 -> 「1と2だけ」), part 2.  The left-cell
registry (left_cells, part 1) holds the cells the retreating owners record.  A pair of owners
neither of which retreats (seek-loot / explore, esp-threat:hunt-weak / explore, anaguma:walk /
seek-loot, quest25:walk / quest-patrol:walk, ...) still walked p->q, q->p, p->q, q->p until the
loop detector (cli ``_is_looping``) stopped the bot, and so did a retreating owner whose record
was not made.  This guard sees the alternation before the detector does.

Rule.  Every board (``observe``, before the ladder) reads the previous board's move: the cell
the player stood on, the cell it stands on now (one step) and the previous decision's owner
(its reason) and ladder rung.  When the last ``2 * ROUND_TRIPS`` moves on the floor are
A p->q, B q->p, A p->q, B q->p with two different owners A and B:

- the winner is the owner whose rung ranks higher in the ladder (town_hold's rank: the ladder
  asks it first, so its reason is the higher-priority one); with no rank to compare (a rung the
  census does not know) it is the owner that moved first, A;
- a survival reason (reasons.survival: the counted escapes and the walking retreats) is never
  the loser: such a pair is left to the survival rungs, which always win;
- the cell the winner left is recorded in the registry for ``GUARD_BOARDS`` decisions, owner
  ``pingpong:<A>/<B>`` (left_cells ``leave`` with ``boards``, its only-way-out rule included),
  so the loser's walk refuses the step back for that window while the winner keeps its move;
- the event ``pingpong:<A>/<B>`` is this board's ``report`` (the decision log's ``pingpong``);
- inside the window the driver's loop detector does not stop the bot (``holds_loop_stop``).

The guard does not hide a stuck state.  The same pair alternating again on the same floor,
inside or after its window, is escalated (``pingpong-escalate:<A>/<B>``): the navigation is
marked exhausted, so the existing livelock leave (policy_navigation ``_navigation_livelock_key``:
recall, up stairs, teleport, else the visible ``livelock:exhausted`` stop) answers, on this board
already unless the ladder decided a survival reason (``after_ladder``).  No new leave.

GUARD_BOARDS is the loop detector's own window (loop_detection.LOOP_WINDOW, 40 decisions): the
time the driver already allows a confined walk before calling it stuck.  The guard holds the
step back that long and no longer; a pair that would alternate after it is the stuck state the
detector was for.  ROUND_TRIPS is the brief's "twice" (A p->q, B q->p, twice): one round trip is
an ordinary hand-over between owners.  No other number.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from hengbot import left_cells, reasons
from hengbot.loop_detection import LOOP_WINDOW
from hengbot.model import Position

MEMORY = "_pingpong_guard"
EVENT = "pingpong"
ESCALATE_EVENT = "pingpong-escalate"
GUARD_BOARDS = LOOP_WINDOW
ROUND_TRIPS = 2


@dataclass(frozen=True)
class Move:
    origin: Position
    step: Position
    owner: str
    rank: int | None   # the owner's ladder rank (lower: asked first), None unknown


@dataclass
class Guard:
    floor_key: tuple | None = None
    last: Position | None = None               # where the previous board stood
    moves: deque = field(default_factory=lambda: deque(maxlen=2 * ROUND_TRIPS))
    windows: dict = field(default_factory=dict)  # (A, B) -> last decision of the pair's window
    escalated: str | None = None               # this board's escalation event
    report: str | None = None                  # this board's event (decision log)


def _guard(policy, snapshot) -> Guard:
    guard = getattr(policy, MEMORY, None)  # restored checkpoints predate it
    if guard is None or guard.floor_key != snapshot.floor_key:
        guard = Guard(floor_key=snapshot.floor_key)
        setattr(policy, MEMORY, guard)
    return guard


def _decision(policy) -> int:
    return int(getattr(policy, "_decision_sequence", 0) or 0)


def _previous_rank(policy) -> int | None:
    """The ladder rank of the previous decision's rung (town_hold), None when unknown."""
    from hengbot.town_hold import decision_rung, rung_named

    rung = rung_named(decision_rung(policy))
    return rung.rank if rung is not None and rung.rank >= 0 else None


def _alternation(moves) -> tuple | None:
    """(A, B, p, q) when the moves are A p->q, B q->p repeated ROUND_TRIPS times."""
    if len(moves) < 2 * ROUND_TRIPS:
        return None
    first, second = moves[0], moves[1]
    if first.owner == second.owner or first.step != second.origin or second.step != first.origin:
        return None
    for index, move in enumerate(moves):
        model = first if index % 2 == 0 else second
        if (move.owner, move.origin, move.step) != (model.owner, model.origin, model.step):
            return None
    return first, second


def _winner(first: Move, second: Move) -> tuple[Move, Move]:
    """(winner, loser): the higher-ranked rung, else the first mover."""
    if first.rank is not None and second.rank is not None and second.rank < first.rank:
        return second, first
    return first, second


def observe(policy, snapshot) -> None:
    """Every board, before the ladder: read the previous board's move; on ROUND_TRIPS round
    trips of two owners, record the winner's left cell (or escalate a pair seen before)."""
    guard = _guard(policy, snapshot)
    guard.report = guard.escalated = None
    if snapshot.in_town or snapshot.store is not None:
        guard.last = None
        guard.moves.clear()
        return
    here = snapshot.player.position
    previous, guard.last = guard.last, here
    if previous is None or previous == here:
        return  # no move: a wait, a cast, a bookkeeping key (the alternation goes on)
    owner = getattr(policy, "_decision_entry_reason", None) or ""
    if max(abs(here.y - previous.y), abs(here.x - previous.x)) != 1 or not owner:
        guard.moves.clear()  # a relocation, or a move no owner named: not a walk
        return
    guard.moves.append(Move(previous, here, owner, _previous_rank(policy)))
    pair = _alternation(guard.moves)
    if pair is None:
        return
    winner, loser = _winner(*pair)
    if reasons.survival(loser.owner):
        return  # the survival rungs always win; nothing is refused to them
    guard.moves.clear()
    names = (pair[0].owner, pair[1].owner)
    label = f"{names[0]}/{names[1]}"
    if names in guard.windows:
        guard.report = guard.escalated = f"{ESCALATE_EVENT}:{label}"
        policy._nav_exhausted = True
        return
    left_cells.leave(policy, snapshot, (winner.origin,), owner=f"{EVENT}:{label}",
                     boards=GUARD_BOARDS, step=winner.step)
    guard.windows[names] = _decision(policy) + GUARD_BOARDS
    guard.report = f"{EVENT}:{label}"


def after_ladder(policy, snapshot, key):
    """On an escalation board, the existing livelock leave answers in place of a key that is
    not a survival rung's (the survival rungs always win)."""
    guard = getattr(policy, MEMORY, None)
    if (guard is None or guard.escalated is None or guard.floor_key != snapshot.floor_key
            or reasons.survival(policy.last_reason)):
        return key
    leave = policy._navigation_livelock_key(snapshot)
    return key if leave is None else leave


def holds_loop_stop(policy, snapshot) -> bool:
    """Whether a pair's window holds on this floor: the loop detector does not stop the bot."""
    guard = getattr(policy, MEMORY, None)
    if guard is None or guard.floor_key != snapshot.floor_key:
        return False
    decision = _decision(policy)
    return any(decision <= end for end in guard.windows.values())


def report(policy) -> str | None:
    """This board's event for the decision log (``pingpong`` / ``pingpong-escalate``)."""
    guard = getattr(policy, MEMORY, None)
    return None if guard is None else guard.report


def forget_floor_visit(policy) -> None:
    setattr(policy, MEMORY, None)
