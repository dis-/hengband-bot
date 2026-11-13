"""The cells an owner stepped away from, and the one reader every walker asks.

Owner 2026-11-13 (「同型のループが多いが再発防止できないのか？」, the proposal's parts 1 and 2:
「1と2だけ。試験は新規実装に対して無力だしコストだけかかるのでやらない。」).  About 130 of the
viewing bots' stops of 2026-11-06..13 were loop-detected, and nearly every capture was one owner
stepping away from a cell and another owner stepping straight back on the next board
(threat:avoid-engagement / explore, hazard:step-off / explore, detected:prepare-choke /
seek-loot, unseen:reverse-choke / stuck:seek-stairs, ...).  Each owner decided from scratch on
every board, knowing nothing of who moved last, from where and why; each pair was then fixed
on its own (``policy._engagement_route_veto`` 11-08, the immobile summoner's zone 11-13).

This module is part 1: one record of the cells left, one registration, one reader.

- ``leave(policy, snapshot, cells, owner=..., ...)`` records the cells an owner left, with the
  owner and the lifetime of its reason.  The retreat lifetimes are the engagement claim's
  (until the monsters left are gone, retreat_veto_life; with none named, the floor visit):
  those cells stay in the claim's storage (``_engagement_owned_avoid_cells``, mirrored into
  ``_engagement_avoid_cells``), which the older readers and the checkpoints already hold.
  The bounded lifetimes (``game_turns``: an unseen attacker's window; ``boards``: the
  ping-pong guard's window) are kept here.  With ``step`` (the cell the owner stepped onto),
  a cell whose record would seal the player in is not recorded (engagement_avoid_seal
  ``seals``, the claim's only-way-out rule).
- ``refused(policy, snapshot)`` is the union of every record whose reason holds.  The walks'
  one veto (``policy._walk_veto``) contains it, so every walker that already asks that veto
  (explore, loot, descent, stairs and goal walks, hunts, the anaguma walk, choke routes) reads
  it; the quest plan walks that route on their own maps (quest25_battle, quest_room_sweep,
  kill_all_patrol) read it through this function.  A survival walk (the emergency and combat
  layers, ``survival_walks``) does not read the bounded records, and a bounded record that
  would leave the player no way on (engagement_avoid_seal ``_way_on``) is not read either.

What stays out: the cells around a monster (the danger cells, a remembered disenchanter's or
sleeper's area, an unseen attacker's area, the immobile summoner's line of fire) are areas the
walks keep off, not cells an owner left; they stay in ``_walk_veto`` beside this record, read
by the same walkers as before.

Adding the next retreating owner is one ``leave`` call where it steps; the next walker that
routes on its own map is one ``refused`` call in its route search.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field

from hengbot import engagement_avoid_seal, retreat_veto_life
from hengbot.model import Position

MEMORY = "_left_cells"
SURVIVAL = "_left_cells_survival"


@dataclass(frozen=True)
class Bounded:
    """A record whose reason ends by the clock: at game turn ``until_turn`` or after decision
    ``until_decision`` (whichever is set)."""
    owner: str
    until_turn: int | None = None
    until_decision: int | None = None

    def holds(self, turn: int, decision: int) -> bool:
        if self.until_turn is not None and turn >= self.until_turn:
            return False
        return self.until_decision is None or decision <= self.until_decision


@dataclass
class Registry:
    floor_key: tuple | None = None
    bounded: dict = field(default_factory=dict)   # Position -> [Bounded]
    owners: dict = field(default_factory=dict)    # Position -> {owner}: who left it (diagnostics)
    sealed: tuple | None = None                   # (decision, position, cells) -> encloses, cached


def _registry(policy, snapshot) -> Registry:
    registry = getattr(policy, MEMORY, None)  # restored checkpoints predate it
    floor = getattr(snapshot, "floor_key", None) if snapshot is not None else None
    if registry is None or (floor is not None and registry.floor_key != floor):
        registry = Registry(floor_key=floor)
        setattr(policy, MEMORY, registry)
    return registry


def decision_of(policy) -> int:
    """The policy's decision count (the bounded records' clock; the ping-pong guard's)."""
    return int(getattr(policy, "_decision_sequence", 0) or 0)


def leave(policy, snapshot, cells, *, owner: str, threats=(), game_turns: int | None = None,
          boards: int | None = None, step: Position | None = None) -> frozenset:
    """Record that ``owner`` left ``cells`` for a reason that holds until: the monsters
    ``threats`` are gone (none named: the floor visit), or ``game_turns`` game turns, or
    ``boards`` decisions.  With ``step``, a cell whose record would seal the player stepping
    onto ``step`` is not recorded.  Returns the cells recorded."""
    cells = set(cells)
    if step is not None and snapshot is not None:
        cells = {cell for cell in cells
                 if not engagement_avoid_seal.seals(policy, snapshot, cell, step)}
    if not cells:
        return frozenset()
    registry = _registry(policy, snapshot)
    for cell in cells:
        registry.owners.setdefault(cell, set()).add(owner)
    if game_turns is None and boards is None:
        # The retreat lifetimes, in the engagement claim's storage (module docstring).
        policy._engagement_owned_avoid_cells |= cells
        policy._engagement_avoid_cells |= cells
        retreat_veto_life.claim(policy, snapshot, cells, tuple(threats))
        return frozenset(cells)
    record = Bounded(
        owner,
        until_turn=None if game_turns is None else snapshot.turn + game_turns,
        until_decision=None if boards is None else decision_of(policy) + boards)
    for cell in cells:
        registry.bounded.setdefault(cell, []).append(record)
    registry.sealed = None
    return frozenset(cells)


def _bounded_cells(policy, snapshot) -> frozenset:
    """The bounded records whose clock has not run out (expired ones are dropped)."""
    registry = getattr(policy, MEMORY, None)
    if registry is None or not registry.bounded or registry.floor_key != snapshot.floor_key:
        return frozenset()
    turn, decision = snapshot.turn, decision_of(policy)
    for cell, records in list(registry.bounded.items()):
        live = [record for record in records if record.holds(turn, decision)]
        if live:
            registry.bounded[cell] = live
        else:
            del registry.bounded[cell]
    return frozenset(registry.bounded)


def _encloses(policy, snapshot, cells: frozenset) -> bool:
    """Whether the bounded records alone leave the player no way on that the walk over them
    would have (engagement_avoid_seal's reading; cached for the decision)."""
    registry = getattr(policy, MEMORY)
    here = snapshot.player.position
    key = (decision_of(policy), here, cells)
    if registry.sealed is not None and registry.sealed[0] == key:
        return registry.sealed[1]
    closed = cells - {here}
    sealed = (not engagement_avoid_seal._way_on(policy, snapshot, here, closed)
              and engagement_avoid_seal._way_on(policy, snapshot, here, frozenset()))
    registry.sealed = (key, sealed)
    return sealed


def refused(policy, snapshot) -> frozenset:
    """The cells no walk steps back into: every recorded left cell whose reason holds.

    The retreat lifetimes' cells always; the bounded records unless the walk is a survival
    rung's (``survival_walks``) or they would leave the player no way on."""
    claimed = frozenset(getattr(policy, "_engagement_owned_avoid_cells", ()))
    if getattr(policy, SURVIVAL, False):
        return claimed
    bounded = _bounded_cells(policy, snapshot)
    if bounded and _encloses(policy, snapshot, bounded):
        return claimed
    return claimed | bounded


def refused_yx(policy, snapshot) -> frozenset:
    """``refused`` as (y, x) cells, for the quest plan walks' maps."""
    return frozenset((cell.y, cell.x) for cell in refused(policy, snapshot))


def who_left(policy, cell: Position) -> frozenset:
    """The owners that left ``cell`` on this floor visit (diagnostics)."""
    registry = getattr(policy, MEMORY, None)
    return frozenset(registry.owners.get(cell, ())) if registry is not None else frozenset()


@contextmanager
def survival_walks(policy):
    """The survival rungs' walks inside: they do not read the bounded records."""
    previous = getattr(policy, SURVIVAL, False)
    setattr(policy, SURVIVAL, True)
    try:
        yield
    finally:
        setattr(policy, SURVIVAL, previous)


def forget_floor_visit(policy) -> None:
    setattr(policy, MEMORY, None)
