"""The claim register: who owns a decision, declared as plain data.

``SOL-DESIGN-ownership-contract.md`` section 3.1 (the claim), section 4
(declaration at ``choose_key``) and section 6 **stage S1** -- attribution and
the inventory.  S1 records; it enforces nothing.  There is no priority ladder,
no violation class and no bar table here, and no decision, key or reason is
read back out of the register.

What a claim is
---------------
``owner``            one of the owner families that exist today.  The enum is
                     built from ``town_arbiter.owner_families()`` plus
                     ``town_arbiter.UNREGISTERED_FAMILY``, the other answer
                     the census can give, so no family is invented here and
                     none can silently drift away from the arbiter's
                     registrations.  From stage S2a that list includes the
                     census-only families -- the producers behind the two
                     catch-alls -- which the arbiter registers but does not
                     arbitrate.
``goal``             ``Reach(cell)`` | ``Observe(expectation, within)`` |
                     ``Terminal(effect)``.
``budget``           the registered family's own budget (each one already
                     derived from a policy constant); ``None`` for the
                     unregistered family, which has no registration, and for
                     the census-only families of stage S2a, which nothing
                     arbitrates until S2b brings the ladder.
``state``            ``active | awaiting | suspended | complete | retired``.
``non_discardable``  design 3.1: stripped equipment and a pending Home atomic
                     withdraw may not be dropped.  Nothing sets it in S1.

Plain data only (design 5.4).  A goal holds a ``(y, x)`` tuple, never a
``Position``; a claim holds no ``DecisionCandidate`` and no snapshot.  The
register lives in the policy's ``__dict__``, so it is pickled into every
checkpoint: it keeps the current claim and a counter, never a history, and
the history lives in the ledger file instead.

``closed`` and the five states
------------------------------
Design 5.2 counts owner changes that happen "without a ``release`` /
``complete`` / ``retired`` on the previous row".  ``complete`` and ``retired``
are states; a *release* is an act by a holder that is still in whichever state
it was in.  So a claim carries both: ``state`` stays one of the design's five,
and ``closed`` names the event that ended the claim legitimately -- ``None``,
``"release"``, ``"complete"`` or ``"retired"``.  The metric reads ``closed``.

Stage S2a.1 (design rev 9.1 items 2-3) gives the closing calls their callers:
``complete(label)`` from the exit (a Reach cell reached, a floor changed, a
posted expectation satisfied) and from a producer's own arrival or
confirmation branch, ``release(label)`` where a producer already drops its
goal, and ``suspend(label)`` from the survival preemption only.  A ``Terminal``
claim needs no call: it is closed on the reading side
(``ownership_metrics._closure_of``).  Still no decision, key or reason reads
anything back out of the register.

Stage S2b.1 (design rev 10.1 items 5-6) makes suspension a stack: ``suspend``
-- now called for a preemption by a strictly higher rung of
``claim_ladder.CLAIM_LADDER`` as well as for survival -- pushes the holder onto
``_suspended``; ``resume`` brings a suspended claim back under its own id when
its owner returns to the same goal, and ``close_suspended`` ends one that the
floor changed under, whose goal was met, or that another owner displaced.
Record-only, like the rest.

Continuity
----------
``declare`` continues the current claim while the owner, the goal and
``non_discardable`` are unchanged and the claim has not been closed; the claim
id is then the same on consecutive rows.  Anything else opens a new claim with
a new id.  Ids come from one monotonic counter per register (design 4 names one
monotonic source read by both the policy and the driver), so two runs over the
same recorded boards allocate the same ids.

The marker
----------
Design 5.1 needs a syntactic marker the lint can see.  ``claims(owner)``
decorates a producer and ``ClaimScope`` backs ``with policy.claim(owner,
goal):``.  In S1 ``claims`` is an annotation only: it records the owner on the
function object and returns that same function, so a marked producer is
bytecode-identical to an unmarked one.  Migrating producers to declare through
the marker is S2/S3 work.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from hengbot.town_arbiter import (
    UNREGISTERED_FAMILY,
    owner_families,
    owner_family_budgets,
)


CLAIM_OWNER_ATTRIBUTE = "__hengbot_claim_owner__"

# Family name -> enum member name, without ``str.upper``: no composer in this
# package may uppercase anything (a pack label selector is case-sensitive and
# ``tests/test_policy.py`` forbids the call outright), and a table says exactly
# which characters change.
_MEMBER_NAME = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz-", "ABCDEFGHIJKLMNOPQRSTUVWXYZ_"
)

ClaimOwner = Enum(
    "ClaimOwner",
    [
        (name.translate(_MEMBER_NAME), name)
        for name in (*owner_families(), UNREGISTERED_FAMILY)
    ],
    module=__name__,
    qualname="ClaimOwner",
    type=str,
)
ClaimOwner.__doc__ = "An owner family that exists today (town_arbiter)."

ClaimState = Enum(
    "ClaimState",
    [
        ("ACTIVE", "active"),
        ("AWAITING", "awaiting"),
        ("SUSPENDED", "suspended"),
        ("COMPLETE", "complete"),
        ("RETIRED", "retired"),
    ],
    module=__name__,
    qualname="ClaimState",
    type=str,
)
ClaimState.__doc__ = "The five claim states of design section 3.1."

CLOSED_BY_RELEASE = "release"
CLOSED_BY_COMPLETE = "complete"
CLOSED_BY_RETIRED = "retired"
# Rev 9.2: an Observe claim older than its ``within`` closes as ``expired`` --
# neither a completion nor an abandonment.
CLOSED_BY_EXPIRED = "expired"
CLOSING_EVENTS = frozenset(
    {CLOSED_BY_RELEASE, CLOSED_BY_COMPLETE, CLOSED_BY_RETIRED, CLOSED_BY_EXPIRED}
)

GOAL_REACH = "Reach"
GOAL_OBSERVE = "Observe"
GOAL_TERMINAL = "Terminal"

_FAMILY_BUDGETS = owner_family_budgets()


def owner_of(family: str | ClaimOwner | None) -> ClaimOwner:
    """The owner enum for an arbiter family name; unregistered when unknown."""
    if isinstance(family, ClaimOwner):
        return family
    try:
        return ClaimOwner(family)
    except ValueError:
        return ClaimOwner(UNREGISTERED_FAMILY)


def owner_budget(owner: ClaimOwner) -> int | None:
    """The registered budget of an owner family, or ``None`` if it has none."""
    return _FAMILY_BUDGETS.get(owner.value)


@dataclass(frozen=True)
class Goal:
    """One of the three declared goal kinds, as plain data.

    ``source`` (S2a.1) names where an ``Observe`` goal came from: the owner
    expectation a producer posted on this decision (its registry name), or
    the content label of the goal-typing row that declared it
    (``claim_goal_typing``).  The floor-change and expectation completions
    read it.  A goal pickled before S2a.1 has no ``source`` in its state and
    reads the class default ``None``.

    Rev 9.2 adds two Reach forms beside the cell:

    ``monster``  a moving target -- hunt, ``clear-descent``,
                 ``town:kill-mob-approach`` -- named by ``(index, race_id)``,
                 never by the cell it stood on; the claim continues while the
                 identity is unchanged.
    ``place``    a named place with no local-map cell (the wilderness walk to a
                 town), completed by its producer's own arrival test only.

    Both default to ``None``, so an older pickle reads them from the class.
    """

    kind: str
    cell: tuple[int, int] | None = None
    expectation: tuple[str, ...] = ()
    within: int | None = None
    effect: str | None = None
    source: str | None = None
    monster: tuple[int, int] | None = None
    place: str | None = None

    def as_dict(self) -> dict:
        if self.kind == GOAL_REACH:
            if self.monster is not None:
                return {"kind": GOAL_REACH, "monster": list(self.monster)}
            if self.place is not None:
                return {"kind": GOAL_REACH, "place": self.place}
            return {"kind": GOAL_REACH, "cell": list(self.cell or ())}
        if self.kind == GOAL_OBSERVE:
            row = {
                "kind": GOAL_OBSERVE,
                "expectation": list(self.expectation),
                "within": self.within,
            }
            if self.source is not None:
                row["source"] = self.source
            return row
        return {"kind": GOAL_TERMINAL, "effect": self.effect}


def reach(cell: tuple[int, int]) -> Goal:
    """Arrive at one cell, named as ``(y, x)`` rather than as a ``Position``."""
    return Goal(GOAL_REACH, cell=(int(cell[0]), int(cell[1])))


def reach_monster(index: int, race_id: int) -> Goal:
    """Close with one monster, named by identity (rev 9.2, moving targets)."""
    return Goal(GOAL_REACH, monster=(int(index), int(race_id)))


def reach_place(place: str) -> Goal:
    """Arrive at a named place that has no local-map cell (rev 9.2)."""
    return Goal(GOAL_REACH, place=str(place))


def observe(
    expectation, within: int | None, source: str | None = None
) -> Goal:
    """See one of the named observable changes within a bound."""
    return Goal(
        GOAL_OBSERVE,
        expectation=tuple(sorted(str(name) for name in expectation)),
        within=None if within is None else int(within),
        source=None if source is None else str(source),
    )


def terminal(effect: str) -> Goal:
    """Produce one effect; the decision ends with it."""
    return Goal(GOAL_TERMINAL, effect=str(effect))


@dataclass(frozen=True)
class Claim:
    """One declared claim.  Frozen: a transition replaces it.

    S2a.1 adds three recorded facts, all defaulted so that a claim pickled
    before them (a restored checkpoint's register) unpickles with the class
    defaults -- a frozen dataclass restores its ``__dict__`` and reads a
    missing field from the class:

    ``floor``          ``snapshot.floor_key`` when the claim was opened; the
                       floor-change ``Observe`` goal completes when the board's
                       floor differs from it, and a ``Reach`` cell is only
                       compared on this floor.
    ``closed_reason``  the label the closing call gave (``release(label)``,
                       ``complete(label)``, ``suspend(label)``).
    ``survival``       the latest decision that owned the claim was survival
                       (``claim_goal_typing.is_survival``); S2b.1 round 2
                       updates it on a continuing declaration.
    ``opened_turn``    (rev 9.2) the game turn the claim was opened on; the
                       floor-change ``Observe`` expires on it.

    S2b.1 (design rev 10.1) adds, with the same defaults-from-the-class cover:

    ``rank`` / ``rung``        the ladder rank and rung of the decision that
                               opened (or resumed) the claim
                               (``claim_ladder.rung_of``); ``None`` on a claim
                               pickled before the ladder.
    ``suspended_sequence`` /   the decision sequence and game turn at which the
    ``suspended_turn``         claim was suspended; ``None`` while it is not.
    ``suspended_decisions`` /  (item 6) the decisions and game turns it spent
    ``suspended_turns``        suspended, summed over its suspensions; a resumed
                               ``Observe`` claim's ``within`` does not count
                               them.
    ``trigger_monsters``       (item 9) the ``(index, race_id)`` pairs of the
                               hostiles perceived when the claim opened, for a
                               Reach/Observe claim of a trigger family.
    ``last_perceived_turn``    (item 9) the game turn of the latest decision the
                               claim owned on which one of them was perceived.
    """

    claim_id: int
    owner: ClaimOwner
    goal: Goal
    budget: int | None = None
    state: ClaimState = ClaimState.ACTIVE
    non_discardable: bool = False
    closed: str | None = None
    opened_sequence: int | None = None
    floor: tuple[int, ...] | None = None
    closed_reason: str | None = None
    survival: bool = False
    opened_turn: int | None = None
    rank: int | None = None
    rung: str | None = None
    suspended_sequence: int | None = None
    suspended_turn: int | None = None
    suspended_decisions: int = 0
    suspended_turns: int = 0
    trigger_monsters: tuple[tuple[int, int], ...] = ()
    last_perceived_turn: int | None = None

    def as_dict(self, *, distance: int | None = None) -> dict:
        """The row form: plain JSON types only."""
        return {
            "claim_id": self.claim_id,
            "owner": self.owner.value,
            "goal": self.goal.as_dict(),
            "state": self.state.value,
            "closed": self.closed,
            "closed_reason": self.closed_reason,
            "budget": self.budget,
            "non_discardable": self.non_discardable,
            "distance": distance,
        }

    def closing_dict(self) -> dict:
        """What the row after a closing records about the claim it closed."""
        return {
            "claim_id": self.claim_id,
            "owner": self.owner.value,
            "goal_kind": self.goal.kind,
            "state": self.state.value,
            "closed": self.closed,
            "closed_reason": self.closed_reason,
        }

    @property
    def is_open(self) -> bool:
        """Not ended by an event and not suspended: it still owns its goal."""
        return self.closed is None and self.state not in (
            ClaimState.SUSPENDED,
            ClaimState.COMPLETE,
            ClaimState.RETIRED,
        )


class ClaimRegister:
    """The policy's own claim register: one current claim and one counter.

    S2a.1: a closing call (``complete``, ``release``, ``suspend``) made while
    a decision is being produced -- a producer's arrival branch, a goal it
    drops, a confirmed store effect -- is kept in ``_closing`` until the
    declaration point takes it (``take_closing``) and writes it into the row
    as ``closed_claim``: the claim that closed belongs to the *previous* row,
    which is already written.  A register pickled before S2a.1 has no
    ``_closing`` attribute; every reader goes through ``getattr``.
    """

    def __init__(self) -> None:
        self._next_id = 1
        self._claim: Claim | None = None
        self._closing: Claim | None = None
        # S2b.1 (design rev 10.1 item 5): the claims a preemption suspended,
        # the most recent last, and the suspended claims that closed since the
        # last declaration.  A register pickled before S2b.1 has neither; every
        # reader goes through ``getattr``.
        self._suspended: list[Claim] = []
        self._suspended_closings: list[dict] = []

    # -- allocation ------------------------------------------------------

    def allocate(self) -> int:
        """The next id from this register's one monotonic source."""
        claim_id = self._next_id
        self._next_id += 1
        return claim_id

    @property
    def current(self) -> Claim | None:
        return self._claim

    # -- declaration -----------------------------------------------------

    def continues(
        self, owner: str | ClaimOwner, goal: Goal, non_discardable: bool = False
    ) -> bool:
        """Whether ``declare`` would keep the current claim's id."""
        claim = self._claim
        return (
            claim is not None
            and claim.closed is None
            and claim.state != ClaimState.SUSPENDED
            and claim.owner == owner_of(owner)
            and claim.goal == goal
            and claim.non_discardable == non_discardable
        )

    def declare(
        self,
        owner: str | ClaimOwner,
        goal: Goal,
        *,
        non_discardable: bool = False,
        opened_sequence: int | None = None,
        floor: tuple[int, ...] | None = None,
        survival: bool = False,
        opened_turn: int | None = None,
        rank: int | None = None,
        rung: str | None = None,
        trigger_monsters: tuple[tuple[int, int], ...] = (),
        perceived_turn: int | None = None,
    ) -> Claim:
        """Declare (or continue) the claim that owns the decision being made.

        Rev 9.2's "a suspended claim does not continue" stands for the current
        claim: a declaration after its suspension does not continue it.  From
        S2b.1 a suspended claim comes back only through ``resume`` (design rev
        10.1 item 5), under its own id.

        S2b.1 record-only facts: ``rank`` / ``rung`` and ``trigger_monsters``
        of a newly opened claim; ``survival`` follows the latest decision;
        ``perceived_turn`` -- the game turn, when one of the claim's trigger
        monsters is perceived on this board -- moves ``last_perceived_turn``
        forward.
        """
        declared_owner = owner_of(owner)
        claim = self._claim
        if self.continues(declared_owner, goal, non_discardable):
            # The same owner pursuing the same goal keeps its id, so a reader
            # can see one claim spanning the boards it took to reach the goal.
            changes: dict = {}
            if claim.state != ClaimState.ACTIVE:
                changes["state"] = ClaimState.ACTIVE
            # Round 2 (F2): a continuing claim records whether the decision
            # that continues it is survival.  Its rank and rung stay the ones
            # it was opened or resumed at: every push is then by a strictly
            # higher rank than the claim it suspends, which bounds the stack.
            if claim.survival != bool(survival):
                changes["survival"] = bool(survival)
            if perceived_turn is not None:
                changes["last_perceived_turn"] = int(perceived_turn)
            if changes:
                claim = replace(claim, **changes)
                self._claim = claim
            return claim
        self._claim = Claim(
            claim_id=self.allocate(),
            owner=declared_owner,
            goal=goal,
            budget=owner_budget(declared_owner),
            state=ClaimState.ACTIVE,
            non_discardable=non_discardable,
            opened_sequence=opened_sequence,
            floor=None if floor is None else tuple(floor),
            survival=bool(survival),
            opened_turn=None if opened_turn is None else int(opened_turn),
            rank=rank,
            rung=rung,
            trigger_monsters=tuple(
                (int(index), int(race)) for index, race in trigger_monsters
            ),
            last_perceived_turn=(
                None if perceived_turn is None else int(perceived_turn)
            ),
        )
        return self._claim

    # -- the suspended stack (design rev 10.1 items 5-6) -----------------

    @property
    def suspended(self) -> tuple[Claim, ...]:
        """The suspended claims, the most recently suspended last."""
        return tuple(getattr(self, "_suspended", None) or ())

    def resume(
        self,
        claim_id: int,
        *,
        sequence: int | None = None,
        turn: int | None = None,
        rank: int | None = None,
        rung: str | None = None,
        perceived_turn: int | None = None,
    ) -> Claim | None:
        """The owner came back to a suspended claim: it continues, same id.

        The decisions and game turns it spent suspended are added to its
        ``suspended_decisions`` / ``suspended_turns``, so that its ``within``
        does not count them (item 6).
        """
        stack = list(self.suspended)
        for position in range(len(stack) - 1, -1, -1):
            claim = stack[position]
            if claim.claim_id != claim_id:
                continue
            del stack[position]
            self._suspended = stack
            decisions = claim.suspended_decisions or 0
            turns = claim.suspended_turns or 0
            if sequence is not None and claim.suspended_sequence is not None:
                decisions += max(0, int(sequence) - int(claim.suspended_sequence))
            if turn is not None and claim.suspended_turn is not None:
                turns += max(0, int(turn) - int(claim.suspended_turn))
            changes: dict = {
                "state": ClaimState.ACTIVE,
                "closed": None,
                "closed_reason": None,
                "suspended_sequence": None,
                "suspended_turn": None,
                "suspended_decisions": decisions,
                "suspended_turns": turns,
            }
            if rank is not None:
                changes["rank"] = rank
            if rung is not None:
                changes["rung"] = rung
            if perceived_turn is not None:
                changes["last_perceived_turn"] = int(perceived_turn)
            self._claim = replace(claim, **changes)
            return self._claim
        return None

    def close_suspended(
        self, claim_id: int, closed: str, label: str | None = None, **recorded
    ) -> dict | None:
        """A suspended claim ends while suspended (item 6, rules i-iii).

        ``closed`` is ``complete`` or ``release``.  The closing is kept for the
        declaration point (``take_suspended_closings``), together with anything
        the caller recorded about it (a displacement's violation).
        """
        stack = list(self.suspended)
        for position, claim in enumerate(stack):
            if claim.claim_id != claim_id:
                continue
            del stack[position]
            self._suspended = stack
            ended = replace(claim, closed=closed, closed_reason=label)
            record = {**ended.closing_dict(), **recorded}
            closings = list(getattr(self, "_suspended_closings", None) or ())
            closings.append(record)
            self._suspended_closings = closings
            return record
        return None

    def take_suspended_closings(self) -> list[dict]:
        """The suspended claims that closed since the last declaration, once."""
        closings = list(getattr(self, "_suspended_closings", None) or ())
        self._suspended_closings = []
        return closings

    # -- transitions -----------------------------------------------------

    def _transition(self, state: ClaimState, closed: str | None) -> Claim | None:
        claim = self._claim
        if claim is None:
            return None
        self._claim = replace(claim, state=state, closed=closed)
        return self._claim

    def await_observation(self) -> Claim | None:
        """The claim emitted no command and is waiting for its observation."""
        return self._transition(ClaimState.AWAITING, self._closed())

    def keep_active(self) -> Claim | None:
        return self._transition(ClaimState.ACTIVE, self._closed())

    def _close(
        self, state: ClaimState, closed: str | None, label: str | None
    ) -> Claim | None:
        claim = self._claim
        if claim is None:
            return None
        self._claim = replace(
            claim, state=state, closed=closed, closed_reason=label
        )
        self._closing = self._claim
        return self._claim

    def suspend(
        self,
        label: str | None = None,
        *,
        sequence: int | None = None,
        turn: int | None = None,
    ) -> Claim | None:
        """Preempted with its goal intact (design 3.2).

        ``closed`` stays ``None``: a suspension is not an end.  From S2b.1
        (design rev 10.1 item 5) the suspended claim is also pushed onto the
        suspended stack with the decision sequence and game turn it was
        suspended at, so that ``resume`` can bring it back under its id.
        """
        claim = self._claim
        if claim is None:
            return None
        self._claim = replace(
            claim,
            suspended_sequence=None if sequence is None else int(sequence),
            suspended_turn=None if turn is None else int(turn),
        )
        suspended = self._close(ClaimState.SUSPENDED, self._closed(), label)
        stack = list(self.suspended)
        stack.append(suspended)
        self._suspended = stack
        return suspended

    def complete(self, label: str | None = None) -> Claim | None:
        """The declared goal was observed reached."""
        return self._close(ClaimState.COMPLETE, CLOSED_BY_COMPLETE, label)

    def retire(self) -> Claim | None:
        """Out of budget: the claim emits nothing further (design 3.3)."""
        return self._transition(ClaimState.RETIRED, CLOSED_BY_RETIRED)

    def release(self, label: str | None = None) -> Claim | None:
        """The holder handed the decision back of its own accord."""
        claim = self._claim
        if claim is None:
            return None
        return self._close(claim.state, CLOSED_BY_RELEASE, label)

    def expire(self, label: str | None = None) -> Claim | None:
        """An Observe claim outlived its ``within`` (rev 9.2)."""
        claim = self._claim
        if claim is None:
            return None
        return self._close(claim.state, CLOSED_BY_EXPIRED, label)

    def take_closing(self) -> Claim | None:
        """The claim a closing call ended since the last declaration, once."""
        closing = getattr(self, "_closing", None)
        self._closing = None
        return closing

    def _closed(self) -> str | None:
        claim = self._claim
        return None if claim is None else claim.closed


class ClaimScope:
    """``with policy.claim(owner, goal):`` -- the marker of design 5.1.

    Entering declares; leaving normally does **not** release, because a
    producer that returns a key is still pursuing its goal on the next board.
    ``scope.release()`` ends the claim explicitly.
    """

    def __init__(
        self,
        register: ClaimRegister,
        owner: str | ClaimOwner,
        goal: Goal,
        *,
        non_discardable: bool = False,
        opened_sequence: int | None = None,
    ) -> None:
        self._register = register
        self._owner = owner
        self._goal = goal
        self._non_discardable = non_discardable
        self._opened_sequence = opened_sequence
        self.claim: Claim | None = None

    def __enter__(self) -> "ClaimScope":
        self.claim = self._register.declare(
            self._owner,
            self._goal,
            non_discardable=self._non_discardable,
            opened_sequence=self._opened_sequence,
        )
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def release(self) -> None:
        self.claim = self._register.release()


def claims(owner: str | ClaimOwner):
    """Mark a producer as belonging to one owner family (design 5.1).

    S1 records the owner on the function and returns the *same* function
    object, so marking a producer changes no bytecode and costs no runtime.
    The lint reads the decorator lexically; S2 turns it into a declaration.
    """
    declared = owner_of(owner)

    def mark(producer):
        setattr(producer, CLAIM_OWNER_ATTRIBUTE, declared)
        return producer

    return mark
