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
  owner and the lifetime of its reason: until the monsters it left (``threats``) are gone
  (retreat_veto_life's reading: died, changed shape, or not shown for UNSEEN_GAME_TURNS), for
  ``game_turns`` game turns (an unseen attacker's window), for ``boards`` decisions (the
  ping-pong guard's window), else for the floor visit; or until the owner retires its episode
  (``lift``).  The owner's own walk passes its own
  records (``walking_as``): a retreat pushed back onto its way does not detour round the
  cells behind it.  ``shared=True`` is the engagement claim (``_claim_engagement_avoid_cells``):
  its cells stay in the claim's storage (``_engagement_owned_avoid_cells``, mirrored into
  ``_engagement_avoid_cells``) with the claim's lifetimes, which every walk keeps off, the
  claimant's included, and which the older readers and the checkpoints already hold.  With
  ``step`` (the cell the owner stepped onto), a cell whose record would seal the player in is
  not recorded (engagement_avoid_seal ``seals``, the claim's only-way-out rule).
- ``refused(policy, snapshot)`` is the union of every record whose reason holds.  The walks'
  one veto (``policy._walk_veto``) contains it, so every walker that already asks that veto
  (explore, loot, descent, stairs and goal walks, hunts, the anaguma walk, choke routes, the
  town monster approach) reads it; the walks that search on their own (quest25_battle,
  quest_room_sweep, kill_all_patrol, the quest target lap, the loot search, the descent step)
  read it through this function.  A survival walk (the emergency and combat layers,
  ``survival_walks``) does not read the registry's own records, and records that would leave
  the player no way on (engagement_avoid_seal ``_way_on``) are not read either.

What stays out: the cells around a monster (the danger cells, a remembered disenchanter's or
sleeper's area, an unseen attacker's area, the immobile summoner's line of fire) are areas the
walks keep off, not cells an owner left; they stay in ``_walk_veto`` beside this record, read
by the same walkers as before.

Adding the next retreating owner is one ``leave`` call where it steps (and ``walking_as``
round its own route search); the next walker that searches on its own is one ``refused`` call.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field

from hengbot import engagement_avoid_seal, retreat_veto_life
from hengbot.model import Position

MEMORY = "_left_cells"
SURVIVAL = "_left_cells_survival"
WALKER = "_left_cells_walker"


@dataclass(frozen=True)
class Record:
    """A left cell's record: its owner (the reason that left it) and the lifetime of the reason:
    the game turn ``until_turn``, the decision ``until_decision``, the monsters ``threats``
    ((index, race), tracked by retreat_veto_life), or none of them (the floor visit)."""
    owner: str
    until_turn: int | None = None
    until_decision: int | None = None
    threats: frozenset = frozenset()

    def holds(self, turn: int, decision: int, tracked) -> bool:
        if self.until_turn is not None and turn >= self.until_turn:
            return False
        if self.until_decision is not None and decision > self.until_decision:
            return False
        return not self.threats or bool(self.threats & tracked)


@dataclass
class Registry:
    floor_key: tuple | None = None
    records: dict = field(default_factory=dict)   # Position -> [Record]
    owners: dict = field(default_factory=dict)    # Position -> {owner}: who left it (diagnostics)
    sealed: tuple | None = None                   # ((decision, position, cells), encloses), cached


def _registry(policy, snapshot) -> Registry:
    registry = getattr(policy, MEMORY, None)  # restored checkpoints predate it
    floor = getattr(snapshot, "floor_key", None) if snapshot is not None else None
    if registry is None or (floor is not None and registry.floor_key != floor):
        registry = Registry(floor_key=floor)
        setattr(policy, MEMORY, registry)
    return registry


def decision_of(policy) -> int:
    """The policy's decision count (the records' clock; the ping-pong guard's)."""
    return int(getattr(policy, "_decision_sequence", 0) or 0)


def leave(policy, snapshot, cells, *, owner: str, threats=(), game_turns: int | None = None,
          boards: int | None = None, step: Position | None = None,
          shared: bool = False) -> frozenset:
    """Record that ``owner`` left ``cells`` for a reason that holds until the monsters
    ``threats`` are gone, or for ``game_turns`` game turns, or ``boards`` decisions (none: the
    floor visit).  ``shared``: the engagement claim (module docstring).  With ``step``, a cell
    whose record would seal the player stepping onto ``step`` is not recorded.  Returns the
    cells recorded."""
    cells = set(cells)
    if step is not None and snapshot is not None:
        cells = {cell for cell in cells
                 if not engagement_avoid_seal.seals(policy, snapshot, cell, step)}
    if not cells:
        return frozenset()
    registry = _registry(policy, snapshot)
    for cell in cells:
        registry.owners.setdefault(cell, set()).add(owner)
    if shared:
        policy._engagement_owned_avoid_cells |= cells
        policy._engagement_avoid_cells |= cells
        retreat_veto_life.claim(policy, snapshot, cells, tuple(threats))
        return frozenset(cells)
    keys = frozenset((monster.index, monster.race_id) for monster in threats)
    if keys:
        retreat_veto_life.claim(policy, snapshot, (), tuple(threats))  # it tracks them
    record = Record(
        owner,
        until_turn=None if game_turns is None else snapshot.turn + game_turns,
        until_decision=None if boards is None else decision_of(policy) + boards,
        threats=keys)
    for cell in cells:
        registry.records.setdefault(cell, []).append(record)
    registry.sealed = None
    return frozenset(cells)


def _live_records(policy, snapshot) -> dict:
    """Position -> the records whose reason holds (the ended ones are dropped)."""
    registry = getattr(policy, MEMORY, None)
    if registry is None or not registry.records or registry.floor_key != snapshot.floor_key:
        return {}
    life = getattr(policy, retreat_veto_life.MEMORY, None)
    tracked = frozenset(life.threats) if life is not None else frozenset()
    turn, decision = snapshot.turn, decision_of(policy)
    for cell, records in list(registry.records.items()):
        live = [record for record in records if record.holds(turn, decision, tracked)]
        if live:
            registry.records[cell] = live
        else:
            del registry.records[cell]
    return registry.records


def _encloses(policy, snapshot, cells: frozenset) -> bool:
    """Whether the records alone leave the player no way on that the walk over them would
    have (engagement_avoid_seal's reading; cached for the decision)."""
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

    The engagement claim's cells always; the registry's own records unless the walk is a
    survival rung's (``survival_walks``), the record is the walking owner's own
    (``walking_as``), or they would leave the player no way on."""
    claimed = frozenset(getattr(policy, "_engagement_owned_avoid_cells", ()))
    if getattr(policy, SURVIVAL, None):
        return claimed
    walker = getattr(policy, WALKER, None)
    cells = frozenset(cell for cell, records in _live_records(policy, snapshot).items()
                      if any(record.owner != walker for record in records))
    if cells and _encloses(policy, snapshot, cells):
        return claimed
    return claimed | cells


def refused_yx(policy, snapshot) -> frozenset:
    """``refused`` as (y, x) cells, for the quest plan walks' maps."""
    return frozenset((cell.y, cell.x) for cell in refused(policy, snapshot))


def lift(policy, owner: str) -> None:
    """``owner``'s reason ended (its episode retired): its records go."""
    registry = getattr(policy, MEMORY, None)
    if registry is None:
        return
    for cell, records in list(registry.records.items()):
        kept = [record for record in records if record.owner != owner]
        if kept:
            registry.records[cell] = kept
        else:
            del registry.records[cell]
    registry.sealed = None


def who_left(policy, cell: Position) -> frozenset:
    """The owners that left ``cell`` on this floor visit (diagnostics)."""
    registry = getattr(policy, MEMORY, None)
    return frozenset(registry.owners.get(cell, ())) if registry is not None else frozenset()


@contextmanager
def _flag(policy, name, value):
    previous = getattr(policy, name, None)
    setattr(policy, name, value)
    try:
        yield
    finally:
        setattr(policy, name, previous)


def survival_walks(policy):
    """The survival rungs' walks inside: they do not read the registry's own records."""
    return _flag(policy, SURVIVAL, True)


def walking_as(policy, owner: str):
    """``owner``'s own walk inside: it passes the records it made itself."""
    return _flag(policy, WALKER, owner)


def forget_floor_visit(policy) -> None:
    setattr(policy, MEMORY, None)
