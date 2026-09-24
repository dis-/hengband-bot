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
CLOSING_EVENTS = frozenset(
    {CLOSED_BY_RELEASE, CLOSED_BY_COMPLETE, CLOSED_BY_RETIRED}
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
    """One of the three declared goal kinds, as plain data."""

    kind: str
    cell: tuple[int, int] | None = None
    expectation: tuple[str, ...] = ()
    within: int | None = None
    effect: str | None = None

    def as_dict(self) -> dict:
        if self.kind == GOAL_REACH:
            return {"kind": GOAL_REACH, "cell": list(self.cell or ())}
        if self.kind == GOAL_OBSERVE:
            return {
                "kind": GOAL_OBSERVE,
                "expectation": list(self.expectation),
                "within": self.within,
            }
        return {"kind": GOAL_TERMINAL, "effect": self.effect}


def reach(cell: tuple[int, int]) -> Goal:
    """Arrive at one cell, named as ``(y, x)`` rather than as a ``Position``."""
    return Goal(GOAL_REACH, cell=(int(cell[0]), int(cell[1])))


def observe(expectation, within: int | None) -> Goal:
    """See one of the named observable changes within a bound."""
    return Goal(
        GOAL_OBSERVE,
        expectation=tuple(sorted(str(name) for name in expectation)),
        within=None if within is None else int(within),
    )


def terminal(effect: str) -> Goal:
    """Produce one effect; the decision ends with it."""
    return Goal(GOAL_TERMINAL, effect=str(effect))


@dataclass(frozen=True)
class Claim:
    """One declared claim.  Frozen: a transition replaces it."""

    claim_id: int
    owner: ClaimOwner
    goal: Goal
    budget: int | None = None
    state: ClaimState = ClaimState.ACTIVE
    non_discardable: bool = False
    closed: str | None = None
    opened_sequence: int | None = None

    def as_dict(self, *, distance: int | None = None) -> dict:
        """The row form: plain JSON types only."""
        return {
            "claim_id": self.claim_id,
            "owner": self.owner.value,
            "goal": self.goal.as_dict(),
            "state": self.state.value,
            "closed": self.closed,
            "budget": self.budget,
            "non_discardable": self.non_discardable,
            "distance": distance,
        }


class ClaimRegister:
    """The policy's own claim register: one current claim and one counter."""

    def __init__(self) -> None:
        self._next_id = 1
        self._claim: Claim | None = None

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

    def declare(
        self,
        owner: str | ClaimOwner,
        goal: Goal,
        *,
        non_discardable: bool = False,
        opened_sequence: int | None = None,
    ) -> Claim:
        """Declare (or continue) the claim that owns the decision being made."""
        declared_owner = owner_of(owner)
        claim = self._claim
        if (
            claim is not None
            and claim.closed is None
            and claim.owner == declared_owner
            and claim.goal == goal
            and claim.non_discardable == non_discardable
        ):
            # The same owner pursuing the same goal keeps its id, so a reader
            # can see one claim spanning the boards it took to reach the goal.
            if claim.state != ClaimState.ACTIVE:
                claim = replace(claim, state=ClaimState.ACTIVE)
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
        )
        return self._claim

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

    def suspend(self) -> Claim | None:
        """Preempted with its goal intact (design 3.2).  Unused until S2."""
        return self._transition(ClaimState.SUSPENDED, self._closed())

    def complete(self) -> Claim | None:
        """The declared goal was observed reached."""
        return self._transition(ClaimState.COMPLETE, CLOSED_BY_COMPLETE)

    def retire(self) -> Claim | None:
        """Out of budget: the claim emits nothing further (design 3.3)."""
        return self._transition(ClaimState.RETIRED, CLOSED_BY_RETIRED)

    def release(self) -> Claim | None:
        """The holder handed the decision back of its own accord."""
        claim = self._claim
        if claim is None:
            return None
        self._claim = replace(claim, closed=CLOSED_BY_RELEASE)
        return self._claim

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
