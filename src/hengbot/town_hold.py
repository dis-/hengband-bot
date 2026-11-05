"""The town hold: who holds the town board between decisions (structure stage 2 B).

Owner 2026-10-28 「B: 場面の終点に一本化」.  ``town_terminal`` answers whether
an owner may take a board (its terminal's admission); this module keeps what
a later decision reads of the owner that holds it:

* the claim records (``Goal`` / ``Claim`` / ``ClaimRegister`` / ``Bar``) and
  the goal typing of each producer reason;
* the hold's state (``TownHold``, one per policy in ``_town_hold``) and its
  readers (``standing_claim``, ``decision_reach``, ``offered_steps`` ...);
* the ladder (``CLAIM_LADDER`` / ``rung_of``): the rank a decision's claim
  holds, which decides preemption and resumption;
* the per-decision step (``advance_hold``) and the town errand hold
  (``errand_hold``) and the cross-area Home hold.

Checkpoints pickled before this module existed name these classes under
``hengbot.town_terminal``; ``town_terminal`` keeps those names importable.
"""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from hengbot.model import STORE_HOME, Position
from hengbot.policy_constants import (
    DETECTED_THREAT_HOLD_MAX_GAME_TURNS,
    EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
    HOME_KNOWLEDGE_MACRO,
    LEAVE_STORE_KEY,
    STORE_STUCK_LIMIT,
)
from hengbot.policy_types import (
    EXPECTATION_POP_SATISFIED,
    OWNER_EXPECTATION_MAX_TURNS,
    OwnerProgressCore,
    StoreVisitPhase,
)
from hengbot.retired_values import retired_module
from hengbot.town_arbiter import (
    RECALL_ACTIVATION_MAX_GAME_TURNS,
    ClaimOwner,
    owner_of,
    reason_owner_family,
)



# --- The town hold's records (structure stage 2 B, slice 4) ---------------
# The claim types the hold keeps (formerly claim_register): a claim names its
# owner family (``town_arbiter.ClaimOwner``), its goal (Reach / Observe /
# Terminal) and its state; the register keeps the standing claim, the
# suspended stack and the bars.  Plain data only: a goal holds a ``(y, x)``
# tuple, never a ``Position``, so the hold pickles into every checkpoint.

# A closing call that names no cell closes any Reach goal of its owners.
CLAIM_ANY_CELL = object()

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
# The release label of a suspended claim a floor change ended (design rev 10.1
# item 6, rule i); written by ``claim_suspended_exit``.
SUSPENDED_EXPIRED = "suspended-expired"

GOAL_REACH = "Reach"
GOAL_OBSERVE = "Observe"
GOAL_TERMINAL = "Terminal"


@dataclass(frozen=True)
class Goal:
    """One of the three declared goal kinds, as plain data.

    ``source`` (S2a.1) names where an ``Observe`` goal came from: the owner
    expectation a producer posted on this decision (its registry name), or
    the content label of the goal-typing row that declared it
    (the goal typing below).  The floor-change and expectation completions
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


def reach_goal(cell: tuple[int, int]) -> Goal:
    """Arrive at one cell, named as ``(y, x)`` rather than as a ``Position``."""
    return Goal(GOAL_REACH, cell=(int(cell[0]), int(cell[1])))


def reach_monster_goal(index: int, race_id: int) -> Goal:
    """Close with one monster, named by identity (rev 9.2, moving targets)."""
    return Goal(GOAL_REACH, monster=(int(index), int(race_id)))


def reach_place_goal(place: str) -> Goal:
    """Arrive at a named place that has no local-map cell (rev 9.2)."""
    return Goal(GOAL_REACH, place=str(place))


def observe_goal(
    expectation, within: int | None, source: str | None = None
) -> Goal:
    """See one of the named observable changes within a bound."""
    return Goal(
        GOAL_OBSERVE,
        expectation=tuple(sorted(str(name) for name in expectation)),
        within=None if within is None else int(within),
        source=None if source is None else str(source),
    )


def terminal_goal(effect: str) -> Goal:
    """Produce one effect; the decision ends with it."""
    return Goal(GOAL_TERMINAL, effect=str(effect))


@dataclass(frozen=True)
class ExecutionDeclaration:
    """Checkpoint-safe, producer-written work state, independent of lifecycle."""

    claim_id: int
    work_id: str
    revision: int
    producer: str
    state: str
    next_step: str | None = None
    arguments: tuple = ()
    operation_ref: str | None = None
    expected_effect: str | None = None
    continuation: str | None = None
    budget_ref: str | None = None
    evidence: str | None = None
    cause: str | None = None
    producer_entry: str | None = None


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
                       (``is_survival``); S2b.1 round 2
                       updates it on a continuing declaration.
    ``opened_turn``    (rev 9.2) the game turn the claim was opened on; the
                       floor-change ``Observe`` expires on it.

    S2b.1 (design rev 10.1) adds, with the same defaults-from-the-class cover:

    ``rank`` / ``rung``        the ladder rank and rung of the decision that
                               opened (or resumed) the claim
                               (``rung_of``); ``None`` on a claim
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
    # A pre-declaration checkpoint reads this class default after unpickling.
    execution: ExecutionDeclaration | None = None

    @property
    def is_open(self) -> bool:
        """Not ended by an event and not suspended: it still owns its goal."""
        return self.closed is None and self.state not in (
            ClaimState.SUSPENDED,
            ClaimState.COMPLETE,
            ClaimState.RETIRED,
        )


# -- S2b.2: the bar table (design 3.2, 3.3, 5.4.1) ---------------------------

# A preemptor barred by the 50-turn safety rule (design 3.2): the owner is one
# of the threat-triggered families (``TRIGGER_FAMILIES``).
BAR_THREAT = "threat"
# An errand owner barred by retirement (design 3.3): it lifts when the durable
# part of the existing retirement clearance key changes (user decision
# 2026-09-26), never by the player's own movement and never by a clock.
BAR_ERRAND = "errand"


@dataclass(frozen=True)
class Bar:
    """One bar: ``(owner, goal, trigger monsters)`` and when it was set.

    Plain data, like a claim.  ``triggers`` are ``(index, race_id)`` pairs,
    never an index alone: Hengband reuses a dead monster's index for a new
    one.  ``last_perceived_turn`` is the game turn of the latest board on
    which one of them was perceived (the bar's own start when none was).

    ``rung`` (round 2) is the ladder rung of the claim that earned the bar
    (``rung_of_claim``).  ``clearance`` and ``reason`` are, for an errand bar, the durable
    part of the retirement clearance key when the bar was set and the reason
    it was computed for (``claim_errand_clearance``).
    """

    owner: ClaimOwner
    goal: Goal
    kind: str
    triggers: tuple[tuple[int, int], ...] = ()
    since_turn: int | None = None
    since_sequence: int | None = None
    last_perceived_turn: int | None = None
    claim_id: int | None = None
    ending: str | None = None
    clearance: object = None
    rung: str | None = None
    reason: str | None = None


_UNREAD = object()


def bar_after_board(
    bar: Bar,
    *,
    turn: int | None,
    perceived: frozenset,
    hold: int,
    clearance_of=None,
) -> Bar | None:
    """The bar as this board leaves it, or ``None`` when the board lifts it.

    A pure function of the bar and the board (design 5.4.1: the bar match is
    a pure function of the current snapshot and the key):

    * ``threat``: a trigger ``(index, race_id)`` in ``perceived`` moves
      ``last_perceived_turn`` to ``turn``; the bar lifts once more than
      ``hold`` game turns have passed since then with none of them perceived
      (the comparison of the detected-threat choke release it shares its
      clock with).
    * ``errand``: ``clearance_of(bar)`` is the durable part of the owner's
      retirement clearance key on this board; the bar stands while it equals
      the one recorded when the bar was set and lifts when it changes.  No
      clock: an errand bar never lifts by waiting or by walking.

    Nothing else lifts a bar: not the player's movement, not a changed target,
    not the trigger set growing or shrinking, not the floor.
    """
    if bar.kind == BAR_ERRAND:
        now = clearance_of(bar) if clearance_of is not None else _UNREAD
        if now is _UNREAD or now == bar.clearance:
            return bar
        return None
    if turn is None:
        return bar
    if any(tuple(pair) in perceived for pair in bar.triggers):
        if bar.last_perceived_turn == turn:
            return bar
        return replace(bar, last_perceived_turn=int(turn))
    last = bar.last_perceived_turn
    if last is None:
        last = bar.since_turn
    if last is not None and turn - last > hold:
        return None
    return bar


class ClaimRegister:
    """The town hold's claim register: one current claim and one counter.

    A register pickled before a field below existed has no attribute for
    it; every reader goes through ``getattr``.
    """

    def __init__(self) -> None:
        self._next_id = 1
        self._claim: Claim | None = None
        # S2b.1 (design rev 10.1 item 5): the claims a preemption suspended,
        # the most recent last.
        self._suspended: list[Claim] = []
        # S2b.2: the bar table, and the claims that ended since the last
        # declaration (``claim_set_bars`` bars them).  Readers use
        # ``getattr``.  Both lists are rebound, never mutated in place, so the
        # telemetry observer's shallow copy of the register stays isolated.
        self._bars: list[Bar] = []
        self._ended: list[Claim] = []

    # -- allocation ------------------------------------------------------

    def allocate(self) -> int:
        """The next id from this register's one monotonic source."""
        claim_id = self._next_id
        self._next_id += 1
        return claim_id

    @property
    def current(self) -> Claim | None:
        return self._claim

    def declare_execution(self, claim_id: int, *, work_id: str,
                          producer: str, state: str, next_step: str | None = None,
                          arguments: tuple = (), operation_ref: str | None = None,
                          expected_effect: str | None = None,
                          continuation: str | None = None,
                          budget_ref: str | None = None,
                          evidence: str | None = None,
                          cause: str | None = None,
                          producer_entry: str | None = None) -> ExecutionDeclaration | None:
        """Replace the named current/child declaration without altering the claim."""
        if state not in {"acting", "awaiting", "done", "releasing"}:
            raise ValueError(state)
        claim = self._claim
        if claim is None or claim.claim_id != claim_id:
            return None
        old = claim.execution
        revision = old.revision + 1 if old is not None else 1
        declaration = ExecutionDeclaration(
            claim_id, str(work_id), revision, str(producer), state,
            next_step, tuple(arguments), operation_ref, expected_effect,
            continuation, budget_ref, evidence, cause, producer_entry,
        )
        self._claim = replace(claim, execution=declaration)
        return declaration

    @staticmethod
    def _execution_ending(claim: Claim, closed: str | None,
                          label: str | None) -> Claim:
        declaration = claim.execution
        if declaration is None or closed is None:
            return claim
        state = "done" if closed == CLOSED_BY_COMPLETE else "releasing"
        ending = replace(
            declaration, revision=declaration.revision + 1, state=state,
            next_step=None, arguments=(), operation_ref=None,
            evidence=label if state == "done" else None,
            cause=label if state == "releasing" else None,
        )
        return replace(claim, execution=ending)

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

        S2b.1 facts: ``rank`` / ``rung`` and ``trigger_monsters``
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
            if non_discardable and not claim.non_discardable:
                if rank is None or rung is None:
                    promoted_rung = rung_of(
                        declared_owner, None, non_discardable=True
                    )
                    rank = promoted_rung.rank if rank is None else rank
                    rung = promoted_rung.name if rung is None else rung
                changes["non_discardable"] = True
                changes["rank"] = rank
                changes["rung"] = rung
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

    def close_suspended(self, claim_id: int, closed: str, label: str | None = None) -> None:
        """A suspended claim ends while suspended (item 6, rules i-iii).

        ``closed`` is ``complete`` or ``release``.
        """
        stack = list(self.suspended)
        for position, claim in enumerate(stack):
            if claim.claim_id != claim_id:
                continue
            del stack[position]
            self._suspended = stack
            ended = self._execution_ending(
                replace(claim, closed=closed, closed_reason=label), closed, label
            )
            self._note_ended(ended)
            return

    def stamp_suspended_floor(
        self, claim_id: int, floor: tuple[int, ...]
    ) -> None:
        """Give a suspended claim with no recorded floor the board's floor.

        Round 3: a claim restored from a checkpoint pickled before ``floor``
        existed reads ``None``; stamped with the first board that sees it
        suspended, it expires on the first floor change after that.
        """
        stack = list(self.suspended)
        for position, claim in enumerate(stack):
            if claim.claim_id == claim_id and claim.floor is None:
                stack[position] = replace(claim, floor=tuple(floor))
                self._suspended = stack
                return

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
        self._claim = self._execution_ending(
            replace(claim, state=state, closed=closed, closed_reason=label),
            closed, label,
        )
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
        return self._note_ended(
            self._close(ClaimState.COMPLETE, CLOSED_BY_COMPLETE, label)
        )

    def retire(self) -> Claim | None:
        """Out of budget: the claim emits nothing further (design 3.3)."""
        claim = self._transition(ClaimState.RETIRED, CLOSED_BY_RETIRED)
        if claim is not None:
            self._claim = self._execution_ending(
                claim, CLOSED_BY_RETIRED, "retired"
            )
        return self._note_ended(
            self._claim
        )

    def release(self, label: str | None = None) -> Claim | None:
        """The holder handed the decision back of its own accord."""
        claim = self._claim
        if claim is None:
            return None
        return self._note_ended(
            self._close(claim.state, CLOSED_BY_RELEASE, label)
        )

    def expire(self, label: str | None = None) -> Claim | None:
        """An Observe claim outlived its ``within`` (rev 9.2)."""
        claim = self._claim
        if claim is None:
            return None
        return self._note_ended(
            self._close(claim.state, CLOSED_BY_EXPIRED, label)
        )

    # -- S2b.2: endings and the bar table ----------------------------------

    def _note_ended(self, claim: Claim | None) -> Claim | None:
        """Keep a claim a closing call ended for ``take_ended``; pass it on."""
        if claim is not None and claim.closed in CLOSING_EVENTS:
            self._ended = [*(getattr(self, "_ended", None) or ()), claim]
        return claim

    def take_ended(self) -> list[Claim]:
        """Every claim a closing call ended since the last call, once."""
        ended = list(getattr(self, "_ended", None) or ())
        self._ended = []
        return ended

    @property
    def bars(self) -> tuple[Bar, ...]:
        """The bar table (design 3.2 / 3.3), oldest first."""
        return tuple(getattr(self, "_bars", None) or ())

    def set_bar(self, bar: Bar) -> Bar:
        """Record a bar; a bar already standing on its owner and goal keeps
        its start and takes the union of the two trigger sets and the later
        perception."""
        bars = list(self.bars)
        for position, standing in enumerate(bars):
            if standing.owner == bar.owner and standing.goal == bar.goal:
                perceived = [
                    turn
                    for turn in (standing.last_perceived_turn, bar.last_perceived_turn)
                    if turn is not None
                ]
                merged = replace(
                    standing,
                    triggers=tuple(sorted({*standing.triggers, *bar.triggers})),
                    last_perceived_turn=max(perceived) if perceived else None,
                )
                bars[position] = merged
                self._bars = bars
                return merged
        bars.append(bar)
        self._bars = bars
        return bar

    def replace_bars(self, bars) -> None:
        """The table after a board's lift pass (rebound, never mutated)."""
        self._bars = list(bars)

    def _closed(self) -> str | None:
        claim = self._claim
        return None if claim is None else claim.closed


# --- Goal typing (formerly claim_goal_typing) -------------------------------
# One owner family can hold several kinds of work, so the unit of the table is
# the reason prefix of the family: ``goal_typing`` resolves a reason to the
# longest matching prefix of its own family.  ``claim_goal`` reads it:
# ``Reach`` needs the producer's target in the decision's goal slot,
# ``Observe`` the expectation it posted (or the row's own content),
# ``Terminal`` owns exactly the decision that emits it.

WALK_TARGET = "walk-target"        # Reach: the cell the producer walks to
ENTRANCE = "entrance"              # Reach: the entrance cell of a building
TRANSACTION = "transaction"        # Observe: a transaction's expected change
STORE_OPERATION = "store-operation"  # Observe: a posted store/Home effect
STORE_ENTRY = "store-entry"          # Observe: an entrance command awaiting a page
KNOWLEDGE = "knowledge"              # Observe: Home catalogue becomes current
FLOOR_CHANGE = "floor-change"      # Observe: the floor key changes
EFFECT = "effect"                  # Terminal: the effect label

OBSERVE_WITHIN = {
    TRANSACTION: OWNER_EXPECTATION_MAX_TURNS,
    STORE_OPERATION: STORE_STUCK_LIMIT,
    STORE_ENTRY: STORE_STUCK_LIMIT,
    KNOWLEDGE: STORE_STUCK_LIMIT,
    FLOOR_CHANGE: RECALL_ACTIVATION_MAX_GAME_TURNS,
}
# The observable a floor-change goal names (an ``OwnerProgressCore`` field).
FLOOR_EXPECTATION = ("floor",)


@dataclass(frozen=True)
class GoalTypingRow:
    family: str
    prefix: str
    kind: str
    content: str


def _rows(family: str, *entries: tuple[str, str, str]) -> tuple[GoalTypingRow, ...]:
    return tuple(
        GoalTypingRow(family, prefix, kind, content)
        for prefix, kind, content in entries
    )


R, O, T = GOAL_REACH, GOAL_OBSERVE, GOAL_TERMINAL

GOAL_TYPING: tuple[GoalTypingRow, ...] = (
    *_rows(
        "home-errand",
        ("home-errand:", O, STORE_OPERATION),
        ("home-errand:request-knowledge:", O, KNOWLEDGE),
        ("home-errand:await-fresh-knowledge:", O, KNOWLEDGE),
        ("home-errand:stopped:", T, EFFECT),
        ("home-errand:filed:", T, EFFECT),
    ),
    *_rows(
        "home-scan",
        ("home:request-knowledge", O, KNOWLEDGE),
        ("home:scan", O, KNOWLEDGE),
        ("home:scan-complete-from-open-page", T, EFFECT),
        ("home:scan-incomplete-open-page", T, EFFECT),
        ("home:seek-", T, EFFECT),
        ("home:scan-step-off", R, ENTRANCE),
        ("home:seek-quest-launcher-page", T, EFFECT),
    ),
    *_rows(
        "home-visit",
        ("home:", T, EFFECT),
        ("home:atomic-withdraw", O, STORE_OPERATION),
        ("home:atomic-withdraw-await-confirmation", O, STORE_OPERATION),
        ("home:atomic-withdraw-pending-hold", O, STORE_OPERATION),
        ("home:atomic-withdraw-page-probe", T, EFFECT),
        ("home:atomic-deposit", O, STORE_OPERATION),
        ("home:weight-overload-deposit", O, STORE_OPERATION),
        ("home:deposit", O, STORE_OPERATION),
        ("home:morivant-temporary-deposit", O, STORE_OPERATION),
        ("home:morivant-retry-temporary-deposit", O, STORE_OPERATION),
        ("home:morivant-restore-temporary-deposit", O, STORE_OPERATION),
        ("home:morivant-", T, EFFECT),
        ("home:withdraw-identify-staff-reserve", O, STORE_OPERATION),
        ("home:withdraw-surplus-identify-staff", O, STORE_OPERATION),
        ("home:defer-capacity", T, EFFECT),
        ("home:process-next-batch-item", T, EFFECT),
        ("home:route-claim-unfulfilled", T, EFFECT),
        ("home:withdraw-failed-deferred", T, EFFECT),
        ("home:atomic-withdraw-complete", T, EFFECT),
        ("home:atomic-withdraw-failed", T, EFFECT),
        ("home:atomic-withdraw-target-unobserved", T, EFFECT),
        ("home:atomic-withdraw-slot-unobserved", T, EFFECT),
        ("home:atomic-withdraw-address-invalid", T, EFFECT),
        ("home:deposit-rejected", T, EFFECT),
        ("home:deposit-unobserved-rescan", T, EFFECT),
        ("home:queue-", T, EFFECT),
        ("home:await-fresh-knowledge", T, EFFECT),
        ("home:await-page-size", T, EFFECT),
        ("home:leave-", T, EFFECT),
        ("home:store-context-exit", T, EFFECT),
        ("home:identify-staff-reserve-", T, EFFECT),
        ("home:no-", T, EFFECT),
        ("home:need-", T, EFFECT),
        ("home:processing-complete", T, EFFECT),
        ("home:full-space-ready", T, EFFECT),
        ("home:full-leave-with-surplus", T, EFFECT),
        ("home:full-leave-for-identification-effect", T, EFFECT),
        ("home:full-queue-surplus-withdraw", T, EFFECT),
        ("home:full-deposit-deferred-no-legal-relief", T, EFFECT),
        ("home:full-destroy-", O, EFFECT),
        ("home:junk-sweep:", O, EFFECT),
        ("home:junk-sweep-withdraw", T, EFFECT),
        ("home-visit:", T, EFFECT),
        ("home-disposal:", O, STORE_OPERATION),
        ("home-disposal:destroy-refused", T, EFFECT),
    ),
    *_rows(
        "shop-sell",
        ("shop:outpost-fare-earned-leave", T, EFFECT),
        ("shop:outpost-fare-seek-sale-leave", T, EFFECT),
        ("shop:outpost-fare-sale-approach", R, ENTRANCE),
        ("shop:outpost-fare-sale-approach:await-entry", O, STORE_ENTRY),
        ("shop:sale", T, EFFECT),
        ("shop:sell-", T, EFFECT),
        ("shop:batch-sale", T, EFFECT),
        ("shop:batch-sell", O, STORE_OPERATION),
        ("shop:batch-inscribe", T, EFFECT),
        ("shop:one-shot-sale", O, STORE_OPERATION),
        ("shop:one-shot-sell", O, STORE_OPERATION),
        # SOL-DESIGN-store-reentry-20261003 3.2: one Observe goal per
        # in-store operation, as the one-shot it replaces.
        ("shop:in-store-sell", O, STORE_OPERATION),
        ("shop:in-store-inscribe", O, STORE_OPERATION),
        ("shop:unsellable-", T, EFFECT),
        ("shop:defective-target-leave", T, EFFECT),
        ("shop:leave", O, STORE_OPERATION),
        ("shop:stuck-leave", T, EFFECT),
        ("shop:invalid", T, EFFECT),
        ("shop:retain-standing-digging-tool", T, EFFECT),
        ("town:overweight-surplus-", O, EFFECT),
        ("town:overweight-surplus-sold:", O, STORE_OPERATION),
        ("town:overweight-surplus-destroyed:", O, EFFECT),
        ("town:overweight-surplus-await-effect", O, EFFECT),
        ("town:destroy-overflow", T, EFFECT),
        ("equipment:sale", T, EFFECT),
    ),
    *_rows(
        "shop-buy",
        ("shop:one-shot-buy", O, STORE_OPERATION),
        ("shop:in-store-buy", O, STORE_OPERATION),
        # The in-store entry's own exit: emits the leave key inside the store.
        ("shop:in-store-done", T, EFFECT),
        ("shop:one-shot-in-flight", O, STORE_OPERATION),
        ("shop:one-shot-page-not-zero", T, EFFECT),
        ("shop:opening-route-page", T, EFFECT),
        ("shop:buy", O, STORE_OPERATION),
        ("shop:purchase-deferred", T, EFFECT),
        ("shop:await-", O, STORE_OPERATION),
        ("shop:observe", T, EFFECT),
        # Rev 9.2 (T2): ``shop:observe-and-leave`` emits the leave key inside
        # the store and never walks; rev 9 had listed it with the travel rows.
        ("shop:observe-and-leave", T, EFFECT),
        ("shop:home-first-before-purchase", T, EFFECT),
        ("shop:store-context-exit", O, STORE_OPERATION),
        ("town:wait-restock", T, EFFECT),
    ),
    *_rows(
        "store-router",
        ("shop:approach", R, ENTRANCE),
        ("shop:approach:await-entry", O, STORE_ENTRY),
        ("shop:travel", R, ENTRANCE),
        ("shop:travel:await-entry", O, STORE_ENTRY),
        ("store:", T, EFFECT),
        ("store:entry-await-observation", O, STORE_ENTRY),
        ("store:entry-failed-step-off", R, ENTRANCE),
        ("store:entry-interrupted-replan", R, ENTRANCE),
        ("town:travel", R, ENTRANCE),
        ("town-travel:", R, ENTRANCE),
        # The walk to the teleport building (its route's goal cell).
        ("town:teleport", R, ENTRANCE),
        ("town:teleport-refused-fare", T, EFFECT),
        # One step off the teleport building; the step is computed inside the
        # route helper, which no producer can name without recomputing it.
        ("town:teleport-step-off", T, EFFECT),
        ("store:entry-interrupted-replan:await-entry", O, STORE_ENTRY),
        ("wilderness:enter-town", T, EFFECT),
        ("wilderness:global-travel", R, WALK_TARGET),
        ("wilderness:enter-global", T, EFFECT),
    ),
    *_rows(
        "equipment-opt",
        ("equipment-optimization:", O, TRANSACTION),
        ("equipment:opt", O, TRANSACTION),
        ("optimizer:", O, TRANSACTION),
    ),
    *_rows(
        "equipment-txn",
        ("home:atomic-withdraw", O, STORE_OPERATION),
        ("home:atomic-deposit", O, STORE_OPERATION),
        ("home:leave-after-one-operation", O, STORE_OPERATION),
        ("home:atomic-withdraw-target-unobserved", T, EFFECT),
        ("equipment-transaction:", O, TRANSACTION),
        ("equipment-transaction:approach-home", R, ENTRANCE),
        ("equipment-transaction:travel-home", R, ENTRANCE),
        ("equipment-transaction:travel-home:await-entry", O, STORE_ENTRY),
        # Rev 9.2 (T2): it walks to the Home through the store router.
        ("equipment-transaction:acquire-home-catalog", R, ENTRANCE),
        ("equipment-transaction:home-route-unavailable", T, EFFECT),
        ("equipment-transaction:abandon", T, EFFECT),
        ("equipment-transaction:confirmation-stall-bound", T, EFFECT),
        ("equipment-transaction:retain-", T, EFFECT),
        ("equipment-transaction:defer-identification", T, EFFECT),
        ("equipment-transaction:stale-identity-invalidated:", T, EFFECT),
        ("equipment-transaction:deposit-missing", T, EFFECT),
        ("equipment-transaction:withdraw-missing", T, EFFECT),
        ("equipment-mutation:", T, EFFECT),
        ("equipment:", O, TRANSACTION),
        ("equipment:destroy-", T, EFFECT),
        ("town:restore-combat-weapon", O, TRANSACTION),
        ("town:remove-no-teleport-weapon", O, TRANSACTION),
        ("wield-light", T, EFFECT),
        ("opening-q1:equip-light", O, TRANSACTION),
        ("town:replace-no-teleport-weapon", O, TRANSACTION),
    ),
    *_rows(
        "identification",
        ("identify:", T, EFFECT),
        ("identification:", O, STORE_OPERATION),
        ("item-processing:", T, EFFECT),
        ("inventory:", T, EFFECT),
    ),
    *_rows(
        "fundraising",
        ("fundraise:", T, EFFECT),
        ("fundraise:dig-to-treasure", R, WALK_TARGET),
        ("fundraise:seek-treasure", R, WALK_TARGET),
        ("fundraise:seek-loot", R, WALK_TARGET),
        ("fundraise:seek-upstairs", R, WALK_TARGET),
        ("fundraise:sweep-explore", R, WALK_TARGET),
        ("fundraise:recall", O, FLOOR_CHANGE),
        ("fundraise:recall-stuck", T, EFFECT),
        ("fundraise:wait-recall", O, FLOOR_CHANGE),
        ("fundraise:ascend", O, FLOOR_CHANGE),
        ("fundraising:", T, EFFECT),
        ("mining:", T, EFFECT),
        ("town:recall-stockout-mining", T, EFFECT),
        ("town:identify-staff-stockout-mining", T, EFFECT),
    ),
    *_rows(
        "curse-enchant",
        ("town:remove-curse", T, EFFECT),
        ("town:enchant-launcher-", T, EFFECT),
        ("town:armor-smith:raise", T, EFFECT),
        ("town:armor-smith:approach", R, ENTRANCE),
        ("town:armor-smith:travel", R, ENTRANCE),
        ("town:armor-smith:travel-step-off", T, EFFECT),
        ("town:armor-smith:return", R, ENTRANCE),
        ("town:armor-smith:return-step-off", T, EFFECT),
        ("curse:", O, STORE_OPERATION),
        ("remove-curse:", O, STORE_OPERATION),
        ("enchant:", O, STORE_OPERATION),
    ),
    *_rows(
        "cross-town",
        ("town:cross-town", R, ENTRANCE),
        ("town:cross-town-shopping-needs-funds", T, EFFECT),
        ("town:morivant", R, ENTRANCE),
    ),
    *_rows(
        "survival",
        ("survival:", T, EFFECT),
        ("survival:mana-home-scan", O, KNOWLEDGE),
        ("survival:mana-home-await-operation", O, STORE_OPERATION),
        ("survival:mana-home-withdraw", O, STORE_OPERATION),
        ("survival:mana-home-approach", R, ENTRANCE),
        ("survival:mana-sale-approach", R, ENTRANCE),
        ("survival:mana-shop-approach", R, ENTRANCE),
        ("survival:shop-approach", R, ENTRANCE),
        # Rev 9.2 (T2): the survival errands' native-travel legs.
        ("survival:shop-travel", R, ENTRANCE),
        ("survival:mana-home-travel", R, ENTRANCE),
        ("survival:mana-sale-travel", R, ENTRANCE),
        ("survival:mana-shop-travel", R, ENTRANCE),
        ("survival:shop-travel:await-entry", O, STORE_ENTRY),
        ("survival:mana-home-travel:await-entry", O, STORE_ENTRY),
        ("survival:mana-sale-travel:await-entry", O, STORE_ENTRY),
        ("survival:mana-shop-travel:await-entry", O, STORE_ENTRY),
        ("survival:seek-exit", R, WALK_TARGET),
        ("weak-fainting", T, EFFECT),
        ("status-threat:", T, EFFECT),
        ("status-threat:retreat", R, WALK_TARGET),
        ("status-threat:stairs", O, FLOOR_CHANGE),
        ("town:kill-mob", R, WALK_TARGET),
        ("town:kill-mob-friendly", T, EFFECT),
        ("town:eat-before-travel", T, EFFECT),
        ("town:recover", T, EFFECT),
        ("town:seek-shelter", R, WALK_TARGET),
        ("confused:", T, EFFECT),
        ("item:", T, EFFECT),
        ("mana-food:", T, EFFECT),
        ("mana-food:seek-", R, WALK_TARGET),
        ("stat-gain:", T, EFFECT),
        ("experience:", T, EFFECT),
        ("wilderness:escape-scroll", T, EFFECT),
        ("wilderness:flee", T, EFFECT),
        # Loop 6 (owner 2026-10-31): a refused global map reads Recall and waits.
        ("wilderness:recall", O, FLOOR_CHANGE),
        ("wilderness:wait-recall", O, FLOOR_CHANGE),
        # Slice 1 (2026-10-06): the no-wait escapes are survival interrupts.
        ("no-wait:escape-scroll", T, EFFECT),
        ("no-wait:flee", T, EFFECT),
        ("refill-light", T, EFFECT),
        ("restore-lantern", T, EFFECT),
        ("eat", T, EFFECT),
        ("rest", T, EFFECT),
    ),
    *_rows(
        "departure",
        ("depart", T, EFFECT),
        ("descend", O, FLOOR_CHANGE),
        ("town:ascend", O, FLOOR_CHANGE),
        ("town:descend", O, FLOOR_CHANGE),
        ("recall", O, FLOOR_CHANGE),
        ("return:", T, EFFECT),
        ("return:recall", O, FLOOR_CHANGE),
        ("return:wait-recall", O, FLOOR_CHANGE),
        ("return:await-recall-confirmation", O, FLOOR_CHANGE),
        ("return:ascend", O, FLOOR_CHANGE),
        ("return:seek-upstairs", R, WALK_TARGET),
        # every producer of it emits the search key in place
        ("return:search-upstairs", T, EFFECT),
        ("return:seek-secret-wall", R, WALK_TARGET),
        ("return:explore", R, WALK_TARGET),
        ("return:seek-loot", R, WALK_TARGET),
        ("stair:", O, FLOOR_CHANGE),
        ("stair:observation-timeout-probe", T, EFFECT),
        ("postlevel:", T, EFFECT),
        ("repetition-depart", T, EFFECT),
        ("town:repetition-depart", T, EFFECT),
        ("town:repetition-depart:enter", O, FLOOR_CHANGE),
        ("town:repetition-depart:recall", O, FLOOR_CHANGE),
        ("town:entrance", T, EFFECT),
        ("town:entrance-step-off:", R, WALK_TARGET),
        ("town:wait-recall", O, FLOOR_CHANGE),
        ("town:wait-recall-step-off", R, WALK_TARGET),
        ("town:await-recall-confirmation", O, FLOOR_CHANGE),
        ("town:recall-to-", O, FLOOR_CHANGE),
        ("town:cancel-", T, EFFECT),
        ("town:unsafe-recall-fallback", T, EFFECT),
        ("wilderness:no-safe-route", T, EFFECT),
        ("esp-threat:leave-", O, FLOOR_CHANGE),
        ("seek-downstairs", R, WALK_TARGET),
        ("approach-descent", R, WALK_TARGET),
        ("clear-descent", R, WALK_TARGET),
    ),
    *_rows(
        "town-plan",
        ("town:blocked", T, EFFECT),
        ("town:procurement", T, EFFECT),
        ("procurement:", T, EFFECT),
        ("town-plan:", T, EFFECT),
        ("quest:readiness", T, EFFECT),
        ("town:repetition-required-shopping", T, EFFECT),
    ),
    *_rows(
        "rumor",
        ("town:rumor", R, ENTRANCE),
        ("town:rumor-batch", T, EFFECT),
        ("town:rumor-needs-funds", T, EFFECT),
        ("town:rumor-wait-supplies", T, EFFECT),
    ),
    *_rows(
        "quest-request",
        ("fixedquest:", T, EFFECT),
        ("fixedquest:q2-teleport", R, ENTRANCE),
        ("fixedquest:q2-teleport-step-off", T, EFFECT),
        ("fixedquest:q2-travel", R, ENTRANCE),
        ("fixedquest:q2-travel-needs-funds", T, EFFECT),
        ("fixedquest:approach", R, ENTRANCE),
        ("fixedquest:reward-approach", R, ENTRANCE),
        ("fixedquest:reward-approach:route-unavailable", T, EFFECT),
        ("fixedquest:claim:approach", R, ENTRANCE),
        ("fixedquest:claim:approach:route-unavailable", T, EFFECT),
        ("fixedquest:claim:approach:unsatisfiable", T, EFFECT),
        ("fixedquest:request:approach", R, ENTRANCE),
        ("fixedquest:request:approach:route-unavailable", T, EFFECT),
        ("fixedquest:request:approach:unsatisfiable", T, EFFECT),
        ("fixedquest:q22-travel", R, ENTRANCE),
        ("fixedquest:q22-travel:route-unavailable", T, EFFECT),
        ("fixedquest:q22-travel:unsatisfiable", T, EFFECT),
        ("fixedquest:prepare-return", R, WALK_TARGET),
        ("fixedquest:prepare-return:route-unavailable", T, EFFECT),
        ("fixedquest:prepare-return:unsatisfiable", T, EFFECT),
        ("fixedquest:seek-exit", R, WALK_TARGET),
        ("fixedquest:enter", O, FLOOR_CHANGE),
        ("fixedquest:exit", O, FLOOR_CHANGE),
        ("quest:", T, EFFECT),
        ("quest:enter:approach", R, ENTRANCE),
        ("quest:enter:approach:route-unavailable", T, EFFECT),
        ("quest:enter:approach:unsatisfiable", T, EFFECT),
        ("quest:regen:ascend", O, FLOOR_CHANGE),
        ("quest:regen:descend", O, FLOOR_CHANGE),
        ("opening-q34:", T, EFFECT),
        ("me-staff:", T, EFFECT),
        # The Tower trips' walks (me_staff_sequence / q2_tower_recharge
        # ``_travel`` through _town_teleport_key, and the Tower approach
        # through morivant_tower.building_step) declare their cell like
        # ``fixedquest:q2-teleport``; Terminal left every step uncounted as
        # progress (D49 n1-c life-067/068: owner-retired-burst two steps into
        # the walk to the inn, loop-detected 15 steps into the Tower walk).
        ("me-staff:travel-morivant", R, ENTRANCE),
        ("me-staff:travel-morivant-step-off", T, EFFECT),
        ("me-staff:return-to-shop", R, ENTRANCE),
        ("me-staff:return-to-shop-step-off", T, EFFECT),
        ("me-staff:search-staff", R, ENTRANCE),
        ("me-staff:search-staff-step-off", T, EFFECT),
        ("me-staff:return-for-funds", R, ENTRANCE),
        ("me-staff:return-for-funds-step-off", T, EFFECT),
        ("me-staff:return-outpost", R, ENTRANCE),
        ("me-staff:return-outpost-step-off", T, EFFECT),
        ("me-staff:approach-tower", R, ENTRANCE),
        ("fixedquest:q2-recharge:travel-morivant", R, ENTRANCE),
        ("fixedquest:q2-recharge:travel-morivant-step-off", T, EFFECT),
        ("fixedquest:q2-recharge:travel-telmora", R, ENTRANCE),
        ("fixedquest:q2-recharge:travel-telmora-step-off", T, EFFECT),
        ("fixedquest:q2-recharge:return-for-funds", R, ENTRANCE),
        ("fixedquest:q2-recharge:return-for-funds-step-off", T, EFFECT),
        ("fixedquest:q2-recharge:approach-tower", R, ENTRANCE),
        ("magic-eater:absorb", O, EFFECT),
        ("bounty:", T, EFFECT),
        ("bounty:cashout", T, EFFECT),
        ("bounty:approach", R, ENTRANCE),
        ("bounty:step-off", R, WALK_TARGET),
        ("bounty:leave", T, EFFECT),
    ),
    *_rows(
        "detectors",
        ("ownership:", T, EFFECT),
        ("livelock:", T, EFFECT),
        ("livelock:ascend", O, FLOOR_CHANGE),
        ("livelock:recall-escape", O, FLOOR_CHANGE),
        ("livelock:seek-", R, WALK_TARGET),
        # S2b.1b: a one-shot rewrite, not a walk.  It rebuilds the explore
        # path toward a window edge, records it as the *explore* goal and
        # clears ``_nav_exhausted``, so the next decision is ordinary
        # ``explore`` on that goal; typed Reach, its one-row claim was
        # dropped by explore on every firing (never two rows in a row in
        # any recorded ledger).
        ("livelock:seek-window-edge", T, EFFECT),
        ("town-progress-invariant:", T, EFFECT),
        ("town-liveness-invariant:", T, EFFECT),
        ("town:cycle-break", T, EFFECT),
        ("posting-contract:", T, EFFECT),
        ("stuck:", T, EFFECT),
        ("stuck:ascend", O, FLOOR_CHANGE),
        ("stuck:recall-escape", O, FLOOR_CHANGE),
        ("stuck:seek-stairs", R, WALK_TARGET),
        ("novel:", T, EFFECT),
        ("breakout", T, EFFECT),
        # S2b.1b: a one-shot rewrite, not a walk.  The oscillation branch of
        # ``_decide`` resumes the committed explore planner for one step and
        # clears ``_recent``, so the next decision is ordinary ``explore`` on
        # the same goal; typed Reach, its one-row claim was dropped by explore
        # on every firing (77 rows in the recorded ledgers, never two in a
        # row).
        ("breakout:seek-frontier", T, EFFECT),
        # a tunnel command toward a stair the reason site cannot name
        ("breakout:dig-to-stairs", T, EFFECT),
        ("no-wait:", T, EFFECT),
        ("nav:", T, EFFECT),
        ("warning:", T, EFFECT),
        ("dark:", R, WALK_TARGET),
        ("dark:locomotion-exhausted", T, EFFECT),
        ("dark:no-recovery:", T, EFFECT),
        ("dark:probe", T, EFFECT),
    ),
    *_rows(
        "positioning",
        ("detected:", R, WALK_TARGET),
        ("detected:hold-choke", T, EFFECT),
        ("melee:choke", T, EFFECT),
        ("melee:choke-reposition", R, WALK_TARGET),
        ("summoner:hold-choke", T, EFFECT),
        ("summoner:hold-reposition", R, WALK_TARGET),
        ("threat:reposition", R, WALK_TARGET),
        ("threat:avoid-engagement", R, WALK_TARGET),
        ("threat:paralyzer-avoid", R, WALK_TARGET),
        ("threat:paralyzer-avoid:blocked-step", T, EFFECT),
        ("paralyzer-guard:", R, WALK_TARGET),
    ),
    *_rows(
        "esp-threat",
        ("esp-threat:hunt-", R, WALK_TARGET),
        ("esp-threat:hunt-heal", T, EFFECT),
        ("esp-threat:hunt-speed", T, EFFECT),
        ("melee:esp-threat-hunt", T, EFFECT),
    ),
    *_rows(
        "escape",
        ("emergency:", T, EFFECT),
        ("emergency:recall", O, FLOOR_CHANGE),
        ("emergency:stairs", O, FLOOR_CHANGE),
        ("emergency:seek-upstairs", R, WALK_TARGET),
        ("flee", T, EFFECT),
        ("flee:stairs", O, FLOOR_CHANGE),
        ("combat:disengage", T, EFFECT),
        ("combat:disengage-recall", O, FLOOR_CHANGE),
        ("combat:disengage-stairs", O, FLOOR_CHANGE),
        ("combat:disengage-seek-upstairs", R, WALK_TARGET),
        ("combat:fruitless", T, EFFECT),
        ("unseen:", T, EFFECT),
        ("unseen-recall:", T, EFFECT),
        ("breeder-breakthrough:", T, EFFECT),
        ("breeder-breakthrough:ascend", O, FLOOR_CHANGE),
        ("breeder-breakthrough:recall", O, FLOOR_CHANGE),
        ("breeder-breakthrough:wait-recall", O, FLOOR_CHANGE),
        ("breeder-breakthrough:seek-", R, WALK_TARGET),
        ("breeder-item-damage:", T, EFFECT),
        ("breeder-item-damage:stairs", O, FLOOR_CHANGE),
        ("breeder-item-damage:teleport-level", O, FLOOR_CHANGE),
        ("breeder-item-damage:recall", O, FLOOR_CHANGE),
        ("breeder-item-damage:seek-stairs", R, WALK_TARGET),
        ("guardian:teleport-to-cover", T, EFFECT),
        ("summoner:retreat", T, EFFECT),
        ("summoner:stairs", O, FLOOR_CHANGE),
        ("summoner:hold-teleport", T, EFFECT),
        ("summons:", T, EFFECT),
        ("summons:recall", O, FLOOR_CHANGE),
        ("threat:scroll", T, EFFECT),
        ("threat:wait", T, EFFECT),
    ),
    *_rows(
        "combat",
        ("melee", T, EFFECT),
        ("ranged:", T, EFFECT),
        ("summoner:ranged-kill", T, EFFECT),
        ("summoner:cornered-approach", R, WALK_TARGET),
        ("summoner:seek-upstairs", R, WALK_TARGET),
        ("summoner:seek-downstairs", R, WALK_TARGET),
        ("summoner:teleport-level", O, FLOOR_CHANGE),
        ("summoner:recall", O, FLOOR_CHANGE),
        ("summoner:wait-recall", O, FLOOR_CHANGE),
        ("unique:quaff-", T, EFFECT),
    ),
    *_rows("hunt", ("hunt", R, WALK_TARGET)),
    *_rows(
        "explore",
        ("explore", R, WALK_TARGET),
        ("explore:", T, EFFECT),
        ("search", T, EFFECT),
        ("seek-secret-wall", R, WALK_TARGET),
        ("probe", T, EFFECT),
    ),
    *_rows(
        "floor-loot",
        ("seek-loot", R, WALK_TARGET),
        ("loot:", T, EFFECT),
        ("loot:seek-", R, WALK_TARGET),
        ("chest:", T, EFFECT),
        ("chest:approach", R, WALK_TARGET),
        ("chest:return-reserved-position", R, WALK_TARGET),
        ("chest:step-off", R, WALK_TARGET),
        ("victory:", R, WALK_TARGET),
        ("conquest:", R, WALK_TARGET),
        # S2b.1 round 2 (F5): picking up underfoot and the auto-destroy
        # trigger each own exactly the decision that emits them.
        ("pickup", T, EFFECT),
        ("trigger-autodestroy", T, EFFECT),
    ),
    *_rows(
        "quest-sweep",
        ("quest-strategy:", T, EFFECT),
        ("quest-strategy:approach-", R, WALK_TARGET),
        ("quest-strategy:placement-sweep", R, WALK_TARGET),
        ("quest-strategy:placement-sweep-repeat", T, EFFECT),
        # a route to the nearest of a set of vantages the navigator does not
        # name (rev 9.3: the target is not obtainable without a second route)
        ("quest-strategy:q2-approach-", T, EFFECT),
        ("quest-strategy:q2-blue-confirm-approach", R, WALK_TARGET),
        ("quest-strategy:q2-breach-approach", R, WALK_TARGET),
        ("quest-strategy:q2-final-patrol", R, WALK_TARGET),
        ("quest-strategy:q2-final-patrol-round-complete", T, EFFECT),
    ),
    *_rows(
        "bookkeeping",
        ("periodic:", T, EFFECT),
        ("town:character-dump", T, EFFECT),
    ),
    *_rows(
        "idle",
        ("policy:", T, EFFECT),
        ("wait", T, EFFECT),
    ),
    # ``misc`` keeps its registration (design 6/S2a) but the census answers
    # an earlier family for every prefix except ``town:misc:``; each still
    # needs its row so the table cannot silently lose one.
    *_rows(
        "misc",
        ("policy:", T, EFFECT),
        ("town:misc:", T, EFFECT),
        ("town:character-dump", T, EFFECT),
        ("periodic:", T, EFFECT),
        ("explore", R, WALK_TARGET),
        ("melee", T, EFFECT),
        ("hunt", R, WALK_TARGET),
        ("esp-threat:hunt-", R, WALK_TARGET),
        ("seek-loot", R, WALK_TARGET),
        ("wait", T, EFFECT),
    ),
)
del R, O, T

def owners_with(kind: str, content: str) -> frozenset[str]:
    """The families that have a row of this kind and content (rev 9.2 U)."""
    return frozenset(
        row.family for row in GOAL_TYPING
        if row.kind == kind and row.content == content and row.family != "misc"
    )


# The owners a shared store goal can belong to, derived from the table so the
# closing sites of rev 9.2 item U name owners without a hand-kept list.
ENTRANCE_OWNERS = owners_with(GOAL_REACH, ENTRANCE)
STORE_OPERATION_OWNERS = owners_with(GOAL_OBSERVE, STORE_OPERATION)
# The owners whose walks share one committed target, named by the closing
# sites that drop or reach that target (rev 9.2 U).  Each is the set of
# families whose producers write that target into the slot.
LOOT_OWNERS = frozenset(
    {"floor-loot", "fundraising", "departure"}  # seek-loot, fundraise:, return:
)
EXPLORE_GOAL_OWNERS = frozenset(
    # explore; return:explore; breakout:seek-frontier; the fundraising and
    # quest-sweep exploration legs
    {"explore", "departure", "detectors", "fundraising", "quest-sweep"}
)
MONSTER_CHASE_OWNERS = frozenset(
    {"hunt", "departure", "survival"}  # hunt, clear-descent, town:kill-mob-approach
)
# A confirmed Home withdrawal or deposit completes the Home operation of any
# owner that posts one, under the sources those owners declare it with: the
# store-operation and transaction table contents, and the expectation names
# they post.
HOME_EFFECT_OWNERS = frozenset(
    {"home-visit", "home-errand", "home-scan", "equipment-txn"}
)
# Rev 9.3 (R6): the withdraw and deposit names only -- not ``home:``, which
# also names ``home:store-context-exit`` / ``home:route-claim-unfulfilled``,
# whose leave a late withdraw/deposit confirmation must not complete.
HOME_EFFECT_SOURCES = (
    STORE_OPERATION,
    TRANSACTION,
    "equipment-transaction",
    "home-errand:",
    "home-withdrawal:",
)

# The note ``_town_teleport_key`` writes into the goal slot, which its caller
# may adopt (``_adopt_decision_goal``).
TELEPORT_WALK_NOTE = "teleport-walk"

_GOAL_ROWS_BY_FAMILY: dict[str, tuple[GoalTypingRow, ...]] = {}
for _row in GOAL_TYPING:
    _GOAL_ROWS_BY_FAMILY[_row.family] = (*_GOAL_ROWS_BY_FAMILY.get(_row.family, ()), _row)
del _row


def goal_typing(family: str, reason: str | None) -> GoalTypingRow | None:
    """The row of ``family`` whose prefix is the longest that ``reason`` has.

    ``reason`` is normalised exactly as the arbiter normalises it (an empty
    reason is ``policy:none``), so the census and this table read the same
    string.  ``None`` means the family has no row for the reason.
    """
    normalized = reason or "policy:none"
    best: GoalTypingRow | None = None
    for row in _GOAL_ROWS_BY_FAMILY.get(family, ()):
        if normalized.startswith(row.prefix) and (
            best is None or len(row.prefix) > len(best.prefix)
        ):
            best = row
    return best


# -- survival (design rev 9 item 3) ---------------------------------------

# The emergency ladder's output (P:5558-5562 enters them into EscapeState as
# ``emergency``), the disengage family, the unseen-attacker family and the
# ESP-threat floor exit.
SURVIVAL_REASON_PREFIXES = (
    "emergency:",
    "summons:",
    "unseen-recall:",
    "guardian:teleport-to-cover",
    "combat:disengage",
    "unseen:",
    "esp-threat:leave-",
    "town:seek-shelter",
    "town:recover",
)
# A ``return:`` decision is survival only while the trigger that started the
# return is a danger trigger (policy_combat.py ``_last_return_trigger``).
SURVIVAL_RETURN_PREFIX = "return:"
# Rev 9.3: ``guardian-reposition`` is not in it -- a guardian reposition never
# starts a return (policy_combat.py sets ``_returning_to_town`` only when not
# repositioning), so it can never be the trigger a return began with.
SURVIVAL_RETURN_TRIGGERS = frozenset({"esp-threat", "unseen-attacker"})
SURVIVAL_RETURN_TRIGGER_PREFIX = "emergency-"
def is_survival_return_trigger(trigger: str | None) -> bool:
    return bool(trigger) and (
        trigger in SURVIVAL_RETURN_TRIGGERS
        or trigger.startswith(SURVIVAL_RETURN_TRIGGER_PREFIX)
    )


def is_survival(reason: str | None, return_trigger: str | None = None) -> bool:
    """Whether a decision is survival in the sense of design rev 9 item 3."""
    reason = reason or ""
    if reason.startswith(SURVIVAL_REASON_PREFIXES):
        return True
    return reason.startswith(SURVIVAL_RETURN_PREFIX) and is_survival_return_trigger(
        return_trigger
    )



# --- The town hold's state (structure stage 2 B, slice 3) -------------------
# Everything of the former claim recording that a later decision still reads:
# the standing claim, the suspended stack and the bars (the claim register),
# the executor delegations, and the current decision's producer offers.  The
# policy keeps one ``TownHold`` in ``_town_hold``; every other module reaches
# it through the functions below and never through policy attributes.

@dataclass
class ExecutionDelegation:
    """Recorded, explicitly opened executor work; never inferred at a hold."""

    parent_claim_id: int | None
    parent_family: str
    delegate_family: str
    work_identity: tuple
    purpose_identity: tuple
    opening_decision: int
    expected_effect: str
    budget_reference: str
    lifecycle: str = "reserved"
    ending: str | None = None
    execution: object = None


@dataclass
class DecisionOffers:
    """Transient producer proposals, consumed only by the claim exit."""

    steps: list = field(default_factory=list)
    no_steps: list = field(default_factory=list)
    waits: list = field(default_factory=list)
    admitted_commands: dict = field(default_factory=dict)
    sequence: int = 0

    def next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence


class _OfferSlot:
    """The current decision's offers; shared by a hold and its observer copy."""

    __slots__ = ("buffer",)

    def __init__(self) -> None:
        self.buffer: DecisionOffers | None = None

    def __repr__(self) -> str:
        # No address: a checkpoint's record of the policy is compared byte by byte.
        return "_OfferSlot()"


class TownHold:
    """The town hold's live state.

    ``claims`` is the claim register (``None`` only when a caller switched
    the recording off).  ``delegations`` are the executor delegations.  The
    offers belong to one decision and to this process: they are never pickled
    or deep-copied (a restored or copied policy starts without offers), and a
    telemetry observer copy shares them, as the decision it observes does.

    ``last_reason``, ``last_reach`` and ``last_rung`` are what the latest
    ``advance_hold`` saw (all None when the register is off): the decision's
    reason (the next decision's seek-shelter release reads it), the Reach
    progress of its claim, ``(claim_id, distance)`` (the driver's town fuse),
    and the rung it ranked at (the decision log).  A hold pickled before
    slice 4 reads the class defaults until ``policy_state`` adopts them.
    """

    last_reason: str | None = None
    last_reach: tuple[int, int] | None = None
    last_rung: str | None = None

    def __init__(self, claims: ClaimRegister | None = None,
                 delegations: list | None = None) -> None:
        self.claims = claims
        self.delegations = delegations if delegations is not None else []
        self._offers = _OfferSlot()

    @classmethod
    def fresh(cls) -> "TownHold":
        return cls(ClaimRegister())

    def __getstate__(self) -> dict:
        state = dict(self.__dict__)
        del state["_offers"]
        return state

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        self._offers = _OfferSlot()

    def observer_copy(self) -> "TownHold":
        """A copy a telemetry observer may write: the register is copied
        shallowly (it rebinds its current claim on every transition), the
        delegation list is a new list, the offers are shared and the latest
        decision's record is the same."""
        duplicate = TownHold(copy(self.claims) if self.claims is not None else None,
                             list(self.delegations))
        duplicate._offers = self._offers
        duplicate.last_reason, duplicate.last_reach, duplicate.last_rung = (
            self.last_reason, self.last_reach, self.last_rung)
        return duplicate


# Checkpoints pickled before structure stage 2 B slice 4 name the claim
# records by their former module (claim_register); they load as these.
retired_module(
    "hengbot.claim_register", Bar=Bar, Claim=Claim, ClaimOwner=ClaimOwner,
    ClaimRegister=ClaimRegister, ClaimState=ClaimState,
    ExecutionDeclaration=ExecutionDeclaration, Goal=Goal,
)


def town_hold(policy: Any) -> TownHold | None:
    return getattr(policy, "_town_hold", None)


def decision_reach(policy: Any) -> tuple[int, int] | None:
    """The latest decision's Reach progress, ``(claim_id, distance)``, or None."""
    return getattr(town_hold(policy), "last_reach", None)


def decision_rung(policy: Any) -> str | None:
    """The rung the latest decision ranked at (for the decision log)."""
    return getattr(town_hold(policy), "last_rung", None)


def hold_claims(policy: Any) -> ClaimRegister | None:
    """The claim register of the town hold: the one place claims change."""
    return getattr(town_hold(policy), "claims", None)


def standing_claim(policy: Any):
    """The standing (current) claim, open or just closed, or None."""
    return getattr(hold_claims(policy), "current", None)


def suspended_claims(policy: Any) -> tuple:
    register = hold_claims(policy)
    return register.suspended if register is not None else ()


def hold_bars(policy: Any) -> tuple:
    register = hold_claims(policy)
    return register.bars if register is not None else ()


def hold_delegations(policy: Any) -> list:
    """The executor delegation records (an empty list without a hold)."""
    hold = town_hold(policy)
    return hold.delegations if hold is not None else []


def offer_buffer(policy: Any) -> DecisionOffers:
    """This decision's offer buffer, opened on first use."""
    slot = policy._town_hold._offers
    if slot.buffer is None:
        slot.buffer = DecisionOffers()
    return slot.buffer


def open_offers(policy: Any) -> DecisionOffers | None:
    """This decision's offer buffer if a producer opened one, else None."""
    hold = town_hold(policy)
    return hold._offers.buffer if hold is not None else None


def take_offers(policy: Any) -> DecisionOffers | None:
    """Close this decision's offer buffer and return it (None if unopened)."""
    hold = town_hold(policy)
    if hold is None:
        return None
    buffer, hold._offers.buffer = hold._offers.buffer, None
    return buffer


def offered_steps(policy: Any) -> tuple:
    """The step offers producers made on this decision, in order."""
    buffer = open_offers(policy)
    return tuple(buffer.steps) if buffer is not None else ()


# The town errand families whose store operation, exit or Reach/Observe errand
# names its acting owner (the ladder's S3 families).
TOWN_OWNER_FAMILIES = frozenset({
    "store-router",
    "shop-buy",
    "shop-sell",
    "home-visit",
    "home-errand",
    "home-scan",
    "equipment-txn",
    "identification",
    "curse-enchant",
    "cross-town",
    "rumor",
})
# The holders of the town errand hold: the town owners and the quest request.
_ERRAND_HOLD_FAMILIES = TOWN_OWNER_FAMILIES | {"quest-request"}


# --- The ladder (formerly claim_ladder) -------------------------------------
# The rank of each rung: the post-decision rewrites first, then every rung
# ``_decide`` consults in its order, then the town errands (one shared rank),
# then the fallbacks.  ``claim_owner_transition`` lets a strictly higher rung
# suspend a held Reach/Observe claim (``owner_change``), and a resumed claim
# keeps its own rank.

SECTION_REWRITE = "rewrite"
SECTION_DECIDE = "decide"
SECTION_TOWN = "town"
SECTION_FALLBACK = "fallback"

# Rev 10 item 1 / rev 10.1 item 2: the families that share one town rank.
TOWN_ERRAND_FAMILIES = frozenset({
    "home-errand",
    "home-scan",
    "home-visit",
    "shop-sell",
    "shop-buy",
    "store-router",
    "equipment-opt",
    "equipment-txn",
    "identification",
    "curse-enchant",
    "cross-town",
    "rumor",
})
# Rev 10.1 item 9: the families whose Reach/Observe claims record the monsters
# that triggered them.
TRIGGER_FAMILIES = frozenset({
    "positioning", "hunt", "esp-threat", "combat", "escape",
})

PREEMPTION = "preemption"
VIOLATION = "violation"
# Survival that does not outrank the holder replaces it (not a violation).
SURVIVAL_DISPLACED = "survival-displaced"


@dataclass(frozen=True)
class Rung:
    """One rung: a producer call site and the family its reasons belong to.

    ``reasons``           reason prefixes that identify this call site among
                          the family's rungs (empty: only its position).
    ``ordinary``          the family's rung for a reason no prefix claims.
    ``marked``            (``decide``) the call is an ``@claims``-marked
                          ``self`` method; otherwise ``producer`` is the call
                          as written (``navigator.decide``).
    ``owns_transaction``  (``equipment-txn``) the rung that holds a stripped
                          character; matched by ``non_discardable`` only.
    ``town``              a ``decide`` rung outside the town errand families
                          that still shares the town rank (fundraising's town
                          call).
    """

    producer: str
    family: str
    section: str
    reasons: tuple[str, ...] = ()
    ordinary: bool = False
    marked: bool = True
    owns_transaction: bool = False
    town: bool = False
    rank: int = field(default=-1, compare=False)
    # ``producer``, or ``producer#n`` for the n-th call site of a producer
    # ``_decide`` calls more than once: the rung's unique name in a row.
    name: str = field(default="", compare=False)

    @property
    def shares_town_rank(self) -> bool:
        if self.section == SECTION_TOWN:
            return True
        if self.section != SECTION_DECIDE or self.owns_transaction:
            return False
        return self.town or self.family in TOWN_ERRAND_FAMILIES


def _rewrite(producer, family, *reasons, ordinary=False):
    return Rung(producer, family, SECTION_REWRITE, tuple(reasons), ordinary)


def _decide(producer, family, *reasons, ordinary=False, marked=True,
            owns_transaction=False, town=False):
    return Rung(
        producer, family, SECTION_DECIDE, tuple(reasons), ordinary, marked,
        owns_transaction, town,
    )


def _town(producer, family, *reasons, ordinary=True):
    return Rung(producer, family, SECTION_TOWN, tuple(reasons), ordinary)


def _fallback(producer, family, *reasons):
    return Rung(producer, family, SECTION_FALLBACK, tuple(reasons), True)


# The line numbers in the comments are ``policy.py`` at 43802ae4; the test
# compares the order with the source itself, never with these numbers.
_RUNGS: tuple[Rung, ...] = (
    _town("absorb_key", "quest-request", "magic-eater:absorb", ordinary=False),
    # -- rewrite: after the ladder has spoken (design 3.3.1) ------------------
    _rewrite("_refuse_no_progress_cycle", "detectors", ordinary=True),
    _rewrite("_forbid_wait_while_damaged", "detectors", "no-wait:"),
    _rewrite("_break_positional_oscillation", "detectors", "nav:"),
    _rewrite("_break_livelock", "detectors"),
    _rewrite("_bound_escape_wait", "detectors"),
    _rewrite("_town_procurement_decision", "town-plan", ordinary=True),
    _rewrite("_skill_exp_request_key", "bookkeeping", "periodic:skill-exp"),
    _rewrite("_periodic_game_save_key", "bookkeeping", ordinary=True),
    _rewrite(
        "_periodic_character_dump_key", "bookkeeping",
        "periodic:character-dump", "town:character-dump",
    ),
    # -- decide: the order _decide consults them ------------------------------
    _decide("_home_errand_knowledge_key", "home-errand",
            "home-errand:request-knowledge:", "home-errand:await-fresh-knowledge:",
            "home-errand:leave-for-knowledge:"),
    _decide("_overweight_surplus_sale_key", "shop-sell", "town:overweight-surplus-"),
    _decide("_home_full_relief_key", "home-visit", "home:full-",
            "home:junk-sweep:", "home:junk-sweep-withdraw"),
    _decide("_equipment_transaction_town_key", "equipment-txn",
            owns_transaction=True),                                    # 5765
    _decide("_equipment_transaction_town_owner_key", "equipment-txn",
            owns_transaction=True),                                    # 5799
    _decide("_town_order_step4_key", "quest-request"),                 # 5883
    _decide("_esp_threat_hunt_key", "esp-threat", ordinary=True),      # 5986
    _decide("_summoner_ranged_kill_key", "combat",
            "summoner:ranged-kill"),                                   # 5991
    _decide("_emergency_item", "escape",
            "emergency:", "unseen-recall:", "guardian:teleport-to-cover",
            marked=False),                                             # 5996
    _decide("_item_destroying_breeder_leave_key", "escape",
            "breeder-item-damage:"),                                  # 6001
    _decide("_mana_food_survival_override_key", "survival",
            "survival:mana-", marked=False),                           # 6011
    _decide("_paralyzer_prevention_key", "positioning",
            "threat:paralyzer-avoid", "paralyzer-guard:",
            marked=False),                                             # 6015
    # The census-only immobile-summoner dispatcher's own step out of the
    # summoner's line-of-fire zone (its exits rank at the exit rung below).
    _decide("_immobile_summoner_key", "explore",
            "explore:avoid-immobile-summoner", marked=False),
    _decide("_unseen_retreat_intercept_key", "positioning"),           # 6021
    _decide("_unseen_retreat_key", "escape", "unseen:"),               # 6026
    _decide("_detected_threat_preparation_key", "positioning",
            "detected:", ordinary=True),                               # 6031
    _decide("_return_to_town_key", "departure"),                       # 6043
    _decide("_dark_locomotion_key", "detectors", "dark:"),             # 6056
    _decide("_breakout_restore_weapon_key", "detectors",
            "breakout:restore-combat-weapon"),                         # 6079
    _decide("_survival_gate_key", "survival"),                         # 6087
    _decide("_chest_processing_key", "floor-loot"),                    # 6116
    _decide("navigator.decide", "quest-sweep", "quest-strategy:",
            ordinary=True, marked=False),                              # 6125
    _decide("_town_kill_mob_key", "survival", "town:kill-mob"),        # 6156
    _decide("_breeder_breakthrough_key", "escape",
            "breeder-breakthrough:recall",
            "breeder-breakthrough:wait-recall",
            "breeder-breakthrough:teleport"),                          # 6170
    _decide("_choke_engagement_key", "positioning", "melee:choke"),    # 6178
    _decide("_ranged_attack_key", "combat"),                           # 6194
    _decide("_fruitless_disengage_key", "escape",
            "combat:disengage", "combat:fruitless"),                   # 6204
    _decide("_breeder_breakthrough_escape_key", "escape",
            "breeder-breakthrough:"),                                  # 6247
    _decide("_melee_swarm_combat_key", "positioning"),                 # 6264
    _decide("_flee_step", "survival", "status-threat:"),               # 6302
    _decide("_blocking_escape_melee_key", "escape",
            "combat:disengage-clear-path"),                            # 6351
    _decide("_flee_step", "escape", "flee", ordinary=True),            # 6362
    _decide("_direction_key", "escape", "flee:cornered-attack"),       # 6387
    _decide("_direction_key", "combat", "melee", ordinary=True),       # 6469
    _decide("_ranged_attack_key", "combat", "ranged:"),                # 6476
    _decide("_flee_step", "positioning", "threat:reposition"),         # 6494
    _decide("_hunt_step", "hunt", "hunt:quest-target"),                # 6513
    _decide("_survival_gate_key", "survival", "survival:",
            "weak-fainting", ordinary=True),                           # 6524
    _decide("_mana_food_loot_key", "survival", "mana-food:"),          # 6528
    _decide("_kill_quest_floor_recovery_key", "quest-request",
            "quest:regen:"),                                           # 6534
    _decide("_home_disposal_processing_key", "home-visit",
            "home-disposal:", ordinary=True),                          # 6538
    _decide("_town_restore_weapon_key", "equipment-txn"),              # 6598
    _decide("_fixed_quest_key", "quest-request"),                      # 6606
    _decide("_town_space_deposit_key", "store-router"),                # 6610
    _decide("_victory_loot_key", "floor-loot", "victory:"),            # 6614
    _decide("_conquest_loot_key", "floor-loot", "conquest:"),          # 6618
    _decide("_fixed_quest_key", "quest-request", "fixedquest:",
            ordinary=True),                                            # 6622
    _decide("_stat_restore_quaff_key", "survival", "restore:"),        # 6626
    _decide("_experience_potion_quaff_key", "survival",
            "experience:"),                                            # 6632
    _decide("_stat_gain_quaff_key", "survival", "stat-gain:"),         # 6638
    _decide("_town_order_step4_key", "quest-request", "bounty:"),      # 6642
    _decide("_fundraising_key", "fundraising", "fundraise:",
            ordinary=True),                                            # 6652
    _decide("_chest_processing_key", "floor-loot", "chest:"),          # 6690
    _decide("_normal_loot_key", "departure", "return:seek-loot"),      # 6709
    _decide("_navigation_livelock_key", "detectors",
            "livelock:ascend", "livelock:recall-escape",
            "livelock:seek-", "livelock:teleport-explore", "livelock:stone-to-mud"),            # 6726
    _decide("_return_to_town_key", "departure"),                       # 6739
    _decide("_return_to_town_key", "departure", "return:",
            ordinary=True),                                            # 6756
    # Step 3 D2a (2026-10-13): catalogue-only work asks the knowledge screen
    # where the character stands; same owner and position as the Home
    # approach below, which remains for physical Home work.
    _decide("_home_catalogue_work_key", "equipment-txn",
            "equipment-transaction:catalogue-request-knowledge",
            "equipment-transaction:catalogue-await-knowledge"),
    _decide("_shopping_approach_key", "equipment-txn",
            "equipment-transaction:acquire-home-catalog",
            "equipment-transaction:travel-home"),                      # 6788
    _decide("_town_equipped_identification_key", "identification",
            ordinary=True),                                            # 6796
    _decide("_town_device_processing_key", "identification",
            "identify:device"),                                        # 6804
    _decide("_heavy_curse_inscription_key", "equipment-txn"),          # 6818
    _decide("_town_remove_curse_key", "curse-enchant",
            ordinary=True),                                            # 6822
    _decide("_town_enchant_launcher_key", "curse-enchant"),            # 6826
    _decide("_town_random_teleport_suppression_key",
            "equipment-txn"),                                          # 6830
    _decide("_equipment_transaction_town_key", "equipment-txn",
            ordinary=True),                                            # 6847
    _decide("_normal_loot_key", "floor-loot", "seek-loot", "loot:",
            ordinary=True),                                            # 6855
    _decide("_home_full_knowledge_key", "home-scan"),  # posted named-take prerequisite
    _decide("_shopping_approach_key", "store-router",
            ordinary=True),                                            # 6923
    # Its own site writes ``town:blocked:overflow-no-legal-disposal``, which
    # ranks here, not at town-plan's rewrite rung; the shop-sell
    # ``town:destroy-overflow`` it passes to ``_verified_destroy_key`` ranks
    # at shop-sell's town rung below.
    _decide("_town_overflow_destroy_key", "town-plan",
            "town:blocked:overflow-no-legal-disposal"),                # 6940
    _decide("_fundraising_key", "fundraising", "town:",
            town=True),                                                # 6980
    _decide("_released_restock_store_key", "store-router"),            # 6993
    # S2b.1b: the uncommitted WEAK / MEDIUM hunt is produced only here (the
    # rest slot, ``policy_combat._esp_threat_rest_key``), below the combat
    # rungs; without its prefixes it ranked at the committed STRONG hunt's
    # rung (5986) and a swing that took the walk over read as a violation.
    # ``esp-threat:hunt-strong`` is emitted at both sites and keeps the
    # ordinary rung (see ``rung_of``).
    _decide("_esp_threat_rest_key", "esp-threat",
            "esp-threat:hunt-weak", "esp-threat:hunt-medium"),         # 7015
    _decide("_flee_step", "positioning",
            "threat:avoid-engagement"),                                # 7114
    _decide("_descent_step", "departure",
            "seek-downstairs", "approach-descent"),                    # 7128
    _decide("_hunt_step", "departure", "clear-descent"),               # 7135
    _decide("_hunt_step", "hunt", "hunt", ordinary=True),              # 7155
    _decide("_breakout_restore_weapon_key", "detectors"),              # 7202
    _decide("_explore_step", "detectors", "breakout:", "stuck:"),      # 7248
    _decide("_immobile_breeder_giveup_key", "explore", "explore:"),    # 7283
    _decide("_explore_step", "explore", "explore", "search", "probe",
            "seek-secret-wall", ordinary=True),                        # 7288
    _decide("_immobile_summoner_exit_key", "combat",
            "summoner:seek-downstairs", "summoner:seek-upstairs", "summoner:teleport-level",
            "summoner:recall", "summoner:wait-recall"),
    _decide("_start_kill_quest_regeneration", "quest-request",
            "quest:regen:exhausted"),                                  # 7344
    # -- town: errands no _decide call site names; departure in town --------
    _town("_home_full_skip_key", "home-visit", "home:full-skip:", ordinary=False),
    _town("town-errand:home-errand", "home-errand"),
    _town("town-errand:home-scan", "home-scan"),
    _town("town-errand:shop-buy", "shop-buy"),
    _town("town-errand:shop-sell", "shop-sell"),
    _town("town-errand:equipment-opt", "equipment-opt"),
    _town("town-errand:cross-town", "cross-town"),
    _town("town-errand:rumor", "rumor"),
    _town(
        "town-errand:departure", "departure",
        "town:", "depart", "repetition-depart", "wilderness:",
        ordinary=False,
    ),
    # -- fallback -------------------------------------------------------------
    _fallback("fallback:idle", "idle", "policy:", "wait"),
    _fallback("fallback:misc", "misc"),
    _fallback("fallback:unregistered", "unregistered"),
)


def _ranked(rungs: tuple[Rung, ...]) -> tuple[tuple[Rung, ...], int]:
    """Give every rung its rank; returns the ladder and ``TOWN_RANK``."""
    rewrite_families: list[str] = []
    for rung in rungs:
        if rung.section == SECTION_REWRITE and rung.family not in rewrite_families:
            rewrite_families.append(rung.family)
    next_rank = len(rewrite_families)
    dungeon: dict[int, int] = {}
    for position, rung in enumerate(rungs):
        if rung.section == SECTION_DECIDE and not rung.shares_town_rank:
            dungeon[position] = next_rank
            next_rank += 1
    town_rank = next_rank
    calls: dict[str, int] = {}
    for rung in rungs:
        calls[rung.producer] = calls.get(rung.producer, 0) + 1
    seen: dict[str, int] = {}
    ranked = []
    for position, rung in enumerate(rungs):
        seen[rung.producer] = seen.get(rung.producer, 0) + 1
        name = (
            rung.producer
            if calls[rung.producer] == 1
            else f"{rung.producer}#{seen[rung.producer]}"
        )
        if rung.section == SECTION_REWRITE:
            rank = rewrite_families.index(rung.family)
        elif position in dungeon:
            rank = dungeon[position]
        elif rung.shares_town_rank:
            rank = town_rank
        else:
            rank = town_rank + 1
        ranked.append(Rung(
            rung.producer, rung.family, rung.section, rung.reasons,
            rung.ordinary, rung.marked, rung.owns_transaction, rung.town, rank,
            name,
        ))
    return tuple(ranked), town_rank


CLAIM_LADDER, TOWN_RANK = _ranked(_RUNGS)
FALLBACK_RANK = TOWN_RANK + 1

_RUNGS_BY_FAMILY: dict[str, tuple[Rung, ...]] = {}
_RUNG_BY_NAME: dict[str, Rung] = {}
for _rung in CLAIM_LADDER:
    _RUNGS_BY_FAMILY[_rung.family] = (*_RUNGS_BY_FAMILY.get(_rung.family, ()), _rung)
    _RUNG_BY_NAME[_rung.name] = _rung
del _rung


def rung_named(name: str | None) -> Rung | None:
    """The rung a row or a claim names, if the ladder still has it."""
    return _RUNG_BY_NAME.get(name) if name else None


def ordinary_rung(family: str) -> Rung | None:
    for rung in _RUNGS_BY_FAMILY.get(family, ()):
        if rung.ordinary:
            return rung
    return None


def rung_of(
    family: object, reason: str | None, *, non_discardable: bool = False
) -> Rung:
    """The rung a decision of this census family and reason came from.

    The one function the live writer and the offline reader both use (rev
    10.1 item 11).  ``family`` may be a ``ClaimOwner`` or its string value.
    """
    name = str(getattr(family, "value", family) or "unregistered")
    rungs = _RUNGS_BY_FAMILY.get(name)
    if not rungs:
        return ordinary_rung("unregistered")
    if non_discardable:
        for rung in rungs:
            if rung.owns_transaction:
                return rung
    normalized = reason or "policy:none"
    best: Rung | None = None
    best_length = -1
    for rung in rungs:
        if rung.owns_transaction:
            continue
        for prefix in rung.reasons:
            if normalized.startswith(prefix) and len(prefix) > best_length:
                best, best_length = rung, len(prefix)
    if best is not None:
        return best
    return ordinary_rung(name) or ordinary_rung("unregistered")


def rung_of_claim(
    family: object, rung_name: str | None, *, non_discardable: bool = False
) -> Rung:
    """A held claim's rung: the one it recorded, else its family's ordinary.

    A claim restored from a checkpoint pickled before the ladder carries no
    rung name; its family's ordinary rung is the honest answer.
    """
    return rung_named(rung_name) or rung_of(
        family, None, non_discardable=non_discardable
    )


def never_suspended(goal_kind: str | None, goal_source: str | None) -> bool:
    """Rev 10.1 item 6: a store-operation or transaction Observe claim."""
    return goal_kind == GOAL_OBSERVE and goal_source not in (
        FLOOR_CHANGE, "store-entry", "knowledge"
    )


def owner_change(
    *,
    held_rank: int,
    held_goal_kind: str | None,
    held_goal_source: str | None,
    held_survival: bool,
    new_rank: int,
    new_survival: bool,
) -> str:
    """Preemption, survival displacement or violation, for a held open
    Reach/Observe claim given way to another owner.

    * Rev 10 item 2 / rev 10.1 item 5: only a strictly higher rank suspends
      the holder (``PREEMPTION``), survival or not -- every push is by a
      strictly higher rank, which is what bounds the stack by the number of
      ranks.
    * Survival that does not rank strictly higher cannot suspend the holder;
      it *replaces* it (``SURVIVAL_DISPLACED``): the holder is released, and
      because survival is exempt (design 3.2, rev 9 item 3) it is not a
      violation.
    * Rev 10.1 item 6: a store-operation or transaction Observe claim is
      never suspended nor exempted; giving it way is a violation.
    * Anything else is a violation (rev 10 item 4).

    ``held_survival`` is part of the signature for the reader's records; a
    held survival claim is suspended or dropped like any other.
    """
    del held_survival
    if never_suspended(held_goal_kind, held_goal_source):
        return VIOLATION
    if new_rank < held_rank:
        return PREEMPTION
    if new_survival:
        return SURVIVAL_DISPLACED
    return VIOLATION


def nests_over(*, top_rank: int, new_rank: int) -> bool:
    """Rule (iii): only a new owner ranked strictly above the top nests."""
    return new_rank < top_rank


def resumable_index(stack, owner, goal, non_discardable: bool = False):
    """Where in the stack a claim of this owner and goal is suspended.

    The topmost match anywhere in the stack, not only the top (a claim can be
    buried under ones a later decision outranks), or ``None``.
    """
    for index in range(len(stack) - 1, -1, -1):
        claim = stack[index]
        if (
            claim.owner == owner
            and claim.goal == goal
        ):
            return index
    return None


def claim_family_of(policy: Any, reason: str | None) -> str:
    """The census family of a reason, answered by the live arbiter."""
    if reason == "shop:in-store-done":
        # A sale's no-effect exit is still that seller's operation. The
        # acting owner declares it; the generic reason cannot turn it into
        # a competing buyer while the sale observation is outstanding.
        for offer in reversed(offered_steps(policy)):
            if offer[0] == LEAVE_STORE_KEY and offer[2] == "shop:in-store-leave":
                return offer[1]
    if reason == "home:request-knowledge-scan":
        # The scan can be a step of registered equipment catalogue work,
        # rather than a new errand. Require the producer's explicit offer.
        for offer in reversed(offered_steps(policy)):
            if (offer[2] == "equipment:acquire-home-catalog"
                    and offer[5] == "home-catalog-available"
                    and offer[0] == HOME_KNOWLEDGE_MACRO):
                return offer[1]
    if reason in {"shop:await-leave-confirmation", "shop:await-leave-generation"}:
        return visit_exit_family(policy)
    if reason and reason.startswith("town:entrance-step-off:"):
        return claim_family_of(policy, reason.split(":", 2)[2])
    if reason and reason.startswith((
        "home:atomic-withdraw-target-unobserved",
        "home:atomic-withdraw-slot-unobserved",
        "home:atomic-withdraw-address-invalid",
    )):
        previous = standing_claim(policy)
        if (previous is not None and previous.owner.value in {'equipment-txn'}):
            return previous.owner.value
    visit = getattr(policy, "_store_visit", None)
    if reason in {"shop:one-shot-in-flight", "store:entry-await-observation"}:
        family = (
            getattr(visit, "operation_producer_family", None)
            or getattr(visit, "claim_owner", None)
            or getattr(visit, "opened_producer_family", None)
        )
        if family in TOWN_OWNER_FAMILIES:
            return family
    if (reason and reason.startswith(('home:leave-', 'home:store-context-exit')) and (visit is not None) and (getattr(visit, 'operation_producer_family', None) in {'equipment-txn'})):
        return visit.operation_producer_family
    if (reason and reason.startswith(("home:leave-", "home:store-context-exit"))
            and visit is not None
            and visit.owner == "equipment-transaction"):
        return (
            'equipment-txn'
        )
    if (reason and reason.startswith(('home:leave-', 'home:store-context-exit')) and (visit is not None) and (getattr(visit, 'claim_operation_identity', None) is not None) and (visit.claim_owner in {'home-visit', 'equipment-txn'})):
        return visit.claim_owner
    current = standing_claim(policy)
    if (reason and reason.startswith(('home:leave-', 'home:store-context-exit')) and (current is not None) and current.is_open and (current.owner.value in {'equipment-txn'}) and (current.goal.source in {'transaction'})):
        return current.owner.value
    composing_family = getattr(visit, "operation_producer_family", None)
    if composing_family is None:
        composing_family = getattr(visit, "opened_producer_family", None)
    if (reason and reason.startswith('home:atomic-') and (composing_family in {'equipment-txn'})):
        return composing_family
    if reason and reason.startswith(('home:atomic-', 'home:deposit', 'home:withdraw-', 'home:weight-overload-deposit', 'home:morivant-temporary-deposit', 'home:morivant-retry-temporary-deposit', 'home:leave-', 'home:store-context-exit')) and (composing_family in {'equipment-txn'}) and (getattr(policy, '_home_atomic_deposit_pending', None) is not None or getattr(policy, '_home_atomic_withdraw_pending', None) is not None):
        return composing_family
    arbiter = getattr(policy, "_town_turn_arbiter", None)
    if arbiter is not None:
        return arbiter.ownership_family(reason or "")
    return reason_owner_family(reason or "")




def advance_hold(policy: Any, snapshot: Any, key: Any) -> None:
    """Advance the town hold on the ``choose_key`` exit (the state step).

    Closes the claim this board ends (a producer's own closing, the exit's
    completion or expiry test, a preemption or a survival displacement),
    ends the suspended claims the board ends, resumes or declares this
    decision's claim, sets the bars of the claims that ended without their
    goal, binds and retires the executor delegations and declares the
    execution the producer offered.  Later decisions read all of it (the
    errand hold, the bars, the delegation tokens), so it runs on every
    decision.  It also keeps what the next decision and the driver read
    (``TownHold.last_reason`` / ``last_reach`` / ``last_rung``); all three
    are None when the claim recording is switched off.
    """
    registry = getattr(policy, "_owner_expectations", None)
    pops = (
        registry.drain_pops()
        if registry is not None and hasattr(registry, "drain_pops")
        else []
    )
    hold = town_hold(policy)
    register = hold_claims(policy)
    if register is None:
        if hold is not None:
            hold.last_reason = hold.last_reach = hold.last_rung = None
        return
    previous_reason = hold.last_reason
    # S2b.2: the bars this board lifts (a pure function of the board).
    claim_bar_lift(policy, snapshot, register)
    reason = policy.last_reason or ""
    standing = register.current
    claim_exit_completion(policy, snapshot, standing, pops)
    standing = register.current
    if (
        standing is not None and standing.is_open
        and standing.goal.kind == GOAL_REACH
        and previous_reason == "town:seek-shelter"
        and not getattr(policy, "_took_damage", False)
    ):
        policy._release_claim_goal(
            "seek-shelter-trigger-gone", owners=(standing.owner,),
            kinds=(GOAL_REACH,),
        )
    # S2b.1 (rev 10.1 item 6, rules i-ii): the suspended claims this board
    # ends -- a floor change, or a goal the board shows met.
    claim_suspended_exit(policy, snapshot, register)
    policy._claim_home_knowledge_observed = False
    # Rev 9.2 (S): the danger trigger of *this* return, recorded where the
    # return began -- never ``_last_return_trigger``, which outlives it.
    survival = is_survival(
        reason, getattr(policy, "_survival_return_trigger", None)
    ) or reason == "town:kill-mob" or (
        snapshot.in_town and reason == "melee"
        and any(
            not monster.pet
            and snapshot.player.position.distance_to(monster.position) <= 1
            for monster in snapshot.visible_monsters
        )
    )
    # S2a: the claim records the **census** family -- who owns the
    # producer -- not the arbitration bucket its reason spends in town.
    # A posted combat-weapon Home withdrawal can pass through the generic
    # Home confirmation and one-shot wait exits.  Their reason strings
    # name the wrapper, while the still-open operation belongs to the
    # filed Home errand.  Keep its recorded claim through both waits.
    standing = register.current
    continuing_home_errand = (
        reason in {
            "home:atomic-withdraw-await-confirmation",
            "shop:one-shot-in-flight",
        }
        and standing is not None and standing.is_open
        and standing.owner.value == "home-errand"
        and standing.goal.source == STORE_OPERATION
        and getattr(policy, "_home_atomic_withdraw_pending", None) is not None
    )
    suspended_holder = next((claim for claim in reversed(register.suspended)
                             if claim.closed is None
                             and claim.state.value == "suspended"
                             and reason.endswith(f":{claim.owner.value}")), None)
    continuing_holder_wait = (
        reason.startswith(("ownership:holder-silent:",
                           "ownership:holder-await:",
                           "ownership:declaration-"))
        and ((standing is not None and standing.is_open
              and reason.endswith(f":{standing.owner.value}"))
             or suspended_holder is not None)
    )
    continuing_owner = (
        continuing_home_errand or continuing_holder_wait
    )
    continuation_claim = (
        suspended_holder
        if continuing_holder_wait and suspended_holder is not None
        and (standing is None or not standing.is_open
             or not reason.endswith(f":{standing.owner.value}"))
        else standing
    )
    owner = (
        continuation_claim.owner if continuing_owner
        else owner_of(claim_family_of(policy, reason))
    )
    if reason in {"shop:await-leave-confirmation", "shop:await-leave-generation"}:
        family = visit_exit_family(policy)
        if family != "barrier-provenance-missing":
            owner = owner_of(family)
    claim_refresh_non_discardable(policy, owner)
    # S2b.1 (rev 10.1 items 1-2): the rung and rank of this decision.
    non_discardable = (
        continuation_claim.non_discardable
        if continuing_owner
        else getattr(policy, "_decision_non_discardable", None) == owner.value
    ) and not reason.endswith(":await-entry")
    rung = rung_of(owner, reason, non_discardable=non_discardable)
    standing = register.current
    goal = (
        continuation_claim.goal
        if continuing_owner
        else claim_goal(policy, snapshot, key, owner, reason, standing)
    )
    if (
        standing is not None and standing.is_open
        and standing.owner == owner
        and reason.startswith("equipment-transaction:stale-identity-invalidated:")
    ):
        policy._release_claim_goal('transaction-identity-stale', owners=(owner,), kinds=(GOAL_OBSERVE,), sources=('transaction',))
        standing = register.current
    if (
        standing is not None and standing.is_open
        and standing.owner == owner
        and standing.goal.source == STORE_ENTRY
        and goal.kind == GOAL_TERMINAL
    ):
        policy._release_claim_goal(
            f"entry-abandoned:{reason}", owners=(owner,),
            kinds=(GOAL_OBSERVE,),
            sources=(STORE_ENTRY,),
        )
        standing = register.current
    if (
        standing is not None and standing.is_open
        and standing.owner == owner
        and standing.goal.source == STORE_OPERATION
        and goal.kind == GOAL_OBSERVE
        and standing.goal != goal
        and getattr(policy, "_home_atomic_withdraw_pending", None) is None
        and getattr(policy, "_home_atomic_deposit_pending", None) is None
    ):
        policy._release_claim_goal(
            "operation-identity-stale", owners=(owner,),
            kinds=(GOAL_OBSERVE,),
            sources=(STORE_OPERATION,),
        )
        standing = register.current
    action, label, dropped = claim_owner_transition(
        policy, register, standing, owner, goal, rung, survival, non_discardable,
        snapshot=snapshot,
    )
    if action == PREEMPTION:
        # Design 3.2 / rev 10 item 2: a strictly higher rung suspends the
        # holder with its goal intact.  The one caller of ``suspend``.
        register.suspend(
            label, sequence=policy._decision_sequence, turn=snapshot.turn
        )
        # Round 3: a holder restored with no floor takes this board's.
        register.stamp_suspended_floor(standing.claim_id, snapshot.floor_key)
    elif action == SURVIVAL_DISPLACED:
        # Survival that does not outrank the holder replaces it: released,
        # exempt, not a violation (round 2, F1/F2).
        register.release(label)
    if action is not None:
        # S2a.1's order: the goal is read after the holder closed, exactly
        # as it was when survival was the only preemptor.
        goal = claim_goal(
            policy, snapshot, key, owner, reason, register.current
        )
    resumed = claim_resolve_suspended(
        policy, register, owner, goal, rung, survival, non_discardable
    )
    if resumed is not None:
        # The resumed claim keeps its own rank unless this decision's rung
        # is strictly higher, so it still outranks nothing it sat under.
        outranks = resumed.rank is None or rung.rank < resumed.rank
        claim = register.resume(
            resumed.claim_id,
            sequence=policy._decision_sequence,
            turn=snapshot.turn,
            rank=rung.rank if outranks else resumed.rank,
            rung=rung.name if outranks else resumed.rung,
            perceived_turn=claim_trigger_perceived(
                snapshot, resumed.trigger_monsters
            ),
        )
    else:
        current = register.current
        continuing = register.continues(owner, goal, non_discardable)
        triggers = (
            current.trigger_monsters
            if continuing and current is not None
            else claim_trigger_monsters(policy, owner, goal)
        )
        register.declare(
            owner,
            goal,
            non_discardable=non_discardable,
            opened_sequence=policy._decision_sequence,
            floor=snapshot.floor_key,
            survival=survival,
            opened_turn=snapshot.turn,
            rank=rung.rank,
            rung=rung.name,
            trigger_monsters=triggers,
            perceived_turn=claim_trigger_perceived(snapshot, triggers),
        )
    if claim_owner_retired(policy, owner):
        claim = register.retire()
    elif key is None or key == "":
        claim = register.await_observation()
    else:
        claim = register.keep_active()
    # The store visit records which claim operates it (``claim_family_of``
    # reads ``claim_owner``).
    visit = getattr(policy, "_store_visit", None)
    if visit is not None and claim.is_open and claim.owner.value in TOWN_OWNER_FAMILIES:
        visit.claim_id = claim.claim_id
        visit.claim_owner = claim.owner.value
    claim_set_bars(policy, snapshot, register, dropped=standing if dropped else None)
    bind_execution_delegations(policy, claim)
    observe_execution_delegations(policy)
    record_execution_declaration(policy, claim, key, reason)
    declared = register.current
    distance = claim_goal_distance(policy, snapshot, declared.goal)
    hold.last_reason = reason
    hold.last_reach = (
        (declared.claim_id, distance)
        if declared.goal.kind == GOAL_REACH and isinstance(distance, int)
        else None
    )
    hold.last_rung = rung.name


def errand_hold(policy: Any, family: str, *, enforced: bool = False,
                arrival_board: Any = None) -> Any:
    """Return the open town errand that owns a different producer's turn.

    Callers ask before changing their own session, plan, or selection
    state. ON also restores a town errand suspended by a higher owner
    before a different errand can displace it.

    ``arrival_board``: a standing cell Reach whose arrival that board
    shows is finished work, not a holder.  S3.3 ON closes it on the same
    evidence before any town producer asks (``choose_key``); the
    cross-area Home hold reads that evidence without closing the claim.
    """
    def town_errand(claim):
        return claim.owner.value in _ERRAND_HOLD_FAMILIES

    register = hold_claims(policy)
    standing = getattr(register, "current", None)
    if (
        standing is not None
        and standing.is_open
        and town_errand(standing)
        and standing.owner.value != family
        and standing.goal.kind in {GOAL_REACH, GOAL_OBSERVE}
        and not (arrival_board is not None
                 and claim_reach_arrival(policy, arrival_board, standing)
                 is not None)
    ):
        return standing
    if enforced and register is not None:
        for claim in reversed(register.suspended):
            if (claim.closed is None
                    and claim.state.value == "suspended"
                    and town_errand(claim)
                    and claim.owner.value != family
                    and claim.goal.kind in {
                        GOAL_REACH, GOAL_OBSERVE
                    }
                    and not (claim.goal.source == KNOWLEDGE
                             and policy._home_knowledge_current)):
                return claim
    return None


def home_catalogue_sequence_enforced(policy: Any) -> bool:
    """Protect physical Home work under cross-area enforcement."""
    return bool(getattr(policy, "_crossarea_fundraising_enforced", False))


def home_catalogue_work_holder(policy: Any) -> Any:
    holder = errand_hold(policy, "__none__", enforced=True)
    declaration = getattr(holder, "execution", None)
    if (declaration is not None
            and declaration.work_id == "equipment:acquire-home-catalog"
            and declaration.expected_effect == "home-catalog-available"):
        return holder
    return None


def home_hold_board(policy: Any) -> Any:
    """The board whose observed arrival ends a route for the Home hold.

    S3.3 ON already closed that arrival before the producers ask, so ON
    passes no board and keeps its own verdicts unchanged.
    """
    return getattr(policy, "_map_predicate_snapshot", None)


def home_sequence_has_holder(policy: Any) -> bool:
    if not home_catalogue_sequence_enforced(policy):
        return False
    # A route that this board shows arrived (at the Home it reached) is
    # not a physical Home sequence; holding Home producers for it made
    # every routed Home pass leave unfulfilled (live 2026-10-02 06:16).
    holder = errand_hold(
        policy, "__none__", enforced=True, arrival_board=home_hold_board(policy))
    visit = getattr(policy, "_store_visit", None)
    return bool(holder is not None and (
        home_catalogue_work_holder(policy) is not None
        or (visit is not None and visit.store_type == STORE_HOME)
        or (holder.goal.source == STORE_OPERATION
            and str(STORE_HOME) in holder.goal.expectation)))


# --- Advancing the hold (moved from the policy, structure stage 2 B slice 4) -
# The steps ``advance_hold`` and the errand hold take on the policy's state:
# closing, suspending and resuming claims, the goal of a decision, the bars,
# and the executor delegations' lifecycle.

def visit_exit_family(policy) -> str:
    """Return the captured operation's owner for a store leave barrier."""
    visit = getattr(policy, "_store_visit", None)
    producer = getattr(visit, "operation_producer_family", None)
    if producer in TOWN_OWNER_FAMILIES:
        return producer
    requester = getattr(visit, "exit_requester", None)
    if (requester in TOWN_OWNER_FAMILIES
            and requester in getattr(visit, "requester_families", ())):
        return requester
    return "barrier-provenance-missing"


def record_execution_declaration(policy, claim, key, reason: str) -> None:
    register = hold_claims(policy)
    buffer = take_offers(policy)
    offers = buffer.steps if buffer is not None else ()
    no_steps = buffer.no_steps if buffer is not None else ()
    waits = buffer.waits if buffer is not None else ()
    offer = next((candidate for candidate in reversed(offers)
                  if key == candidate[0]
                  and claim.owner.value == candidate[1]), None)
    no_step = (
        next((candidate for candidate in reversed(no_steps)
              if claim.owner.value == candidate[0]), None)
        if key is None else None
    )
    wait = next((candidate for candidate in reversed(waits)
                 if key == candidate[0]
                 and claim.owner.value == candidate[1]), None)
    posted_wait = (
        key is None and claim.execution is not None
        and claim.execution.state == "awaiting"
        and claim.execution.operation_ref is not None
    )
    if posted_wait:
        # A producer's no-key result cannot settle an unresolved send.
        offer = None
        no_step = None
        wait = None
    if wait is not None and (offer is None or wait[6] > offer[12]) and (
        no_step is None or wait[6] > no_step[3]
    ):
        _, producer, work_id, operation_ref, effect, continuation, _ = wait
        current_execution = claim.execution
        if (current_execution is None
                or current_execution.state != "awaiting"
                or current_execution.operation_ref != operation_ref):
            register.declare_execution(
                claim.claim_id, work_id=work_id, producer=producer,
                state="awaiting", operation_ref=operation_ref,
                expected_effect=effect, continuation=continuation,
            )
        offer = None
        no_step = None
    if no_step is not None and (offer is None or no_step[3] > offer[12]):
        producer, work_id, fact, _, state = no_step
        if state == "done":
            register.declare_execution(
                claim.claim_id, work_id=work_id, producer=producer,
                state="done", evidence=fact,
            )
        else:
            register.declare_execution(
                claim.claim_id, work_id=work_id, producer=producer,
                state="releasing", cause=fact,
            )
        offer = None
    if offer is not None:
        (_, producer, work_id, step, args, effect, continuation, budget,
         state, evidence, cause, post_on_emit, _, entry) = offer
        register.declare_execution(
            claim.claim_id, work_id=work_id, producer=producer,
            state=state, next_step=step, arguments=args,
            expected_effect=effect, continuation=continuation,
            budget_ref=budget, evidence=evidence, cause=cause,
            producer_entry=entry,
        )
        # The driver alone can turn an emitted command into a posted wait.
        if state == "acting" and post_on_emit and key not in (None, ""):
            policy._execution_pending_post = (claim.claim_id, key, work_id)


def claim_refresh_non_discardable(policy, owner) -> None:
    """Refresh the producer's per-decision slot from its live obligation."""
    family = owner.value
    if family == "equipment-txn" and getattr(
        policy, "_equipment_transaction_owned_items", None
    ):
        policy._declare_non_discardable(family)
    elif family in {'home-visit', 'home-errand', 'equipment-txn'} and (getattr(policy, '_home_atomic_withdraw_pending', None) is not None or getattr(policy, '_home_atomic_deposit_pending', None) is not None or False) and (not (family == 'home-errand' and (policy.last_reason or '').startswith('home-errand:request-knowledge'))):
        policy._declare_non_discardable(family)
    else:
        chain = getattr(policy, "_staged_prompt_chain", None)
        if chain is not None and claim_family_of(policy, chain.get("owner")) == family:
            policy._declare_non_discardable(family)


def close_claim(
    policy,
    event: str,
    label: str,
    *,
    owners,
    cell=CLAIM_ANY_CELL,
    kinds: tuple[str, ...] | None = None,
    sources: tuple[str, ...] | None = None,
    monsters=None,
) -> None:
    """Close the standing claim when it is exactly the goal ended here.

    The standing claim is the one the previous decision declared.  Rev
    9.2 (U): every closing names the owners it may close, and closes
    nothing when the standing claim belongs to another; beyond that it
    closes only a claim that is still open and of one of ``kinds``, and

    * a site that names the ``cell`` it drops closes only a Reach goal
      aimed at exactly that cell (``None`` names no goal: nothing
      closes), and by default only Reach goals;
    * a site that names ``monsters`` closes only a Reach goal on one of
      those ``(index, race_id)`` identities;
    * an ``Observe`` goal closes only when ``sources`` is ``None`` or one
      of them is a prefix of its source.

    S2b.1b: a ``complete`` or ``release`` that names exactly the goal it
    ends (a ``cell`` or ``monsters``) also closes that goal while a
    preemption holds it on the suspended stack (design rev 10.1 item 5).
    The producer drops its goal where it always did; before, the closing
    found another owner's claim standing and closed nothing, so the
    suspended claim was later displaced and counted as a violation.
    """
    register = hold_claims(policy)
    if register is None:
        return
    names = {getattr(owner, "value", owner) for owner in owners}
    cell_named = cell is not CLAIM_ANY_CELL
    named_monsters = None if monsters is None else set(monsters)
    if kinds is None:
        kinds = (
            (GOAL_REACH,)
            if cell_named or named_monsters is not None
            else (GOAL_REACH, GOAL_OBSERVE)
        )

    def matches(claim) -> bool:
        if claim.owner.value not in names:
            return False
        goal = claim.goal
        if goal.kind not in kinds:
            return False
        if goal.kind == GOAL_REACH and cell_named:
            if not isinstance(cell, Position) or goal.cell != (cell.y, cell.x):
                return False
        if goal.kind == GOAL_REACH and named_monsters is not None:
            if goal.monster is None or goal.monster not in named_monsters:
                return False
        if goal.kind == GOAL_OBSERVE and sources is not None:
            if goal.source is None or not str(goal.source).startswith(
                tuple(sources)
            ):
                return False
        return True

    standing = register.current
    if standing is not None and standing.is_open and matches(standing):
        if event == "complete":
            register.complete(label)
        elif event == "expire":
            register.expire(label)
        else:
            register.release(label)
        return
    if event == "expire" or (
        event != "complete" and not (cell_named or named_monsters is not None)
    ):
        return
    for claim in reversed(register.suspended):
        if matches(claim):
            register.close_suspended(
                claim.claim_id,
                "complete" if event == "complete" else "release",
                label,
            )
            return


def claim_operation_goal(policy, snapshot, owner, reason, content):
    """The active operation's stable identity, independent of step posts."""
    if content == STORE_ENTRY:
        return None
    if owner.value == "equipment-txn" and content == "transaction":
        session = getattr(policy, "_equipment_transaction_session", None)
        if session is not None:
            opened = getattr(session, "opened_sequence", None)
            if opened is None:
                opened = policy._decision_sequence
                session.opened_sequence = opened
            return observe_goal(
                (opened, tuple(map(repr, session.plan.actions))),
                EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT,
                source="transaction",
            )
    if content == KNOWLEDGE:
        return observe_goal(
            (STORE_HOME, "knowledge",
             getattr(policy, "_home_knowledge_scan_epoch", None)
             or getattr(policy, "_town_visit_epoch", None)),
            STORE_STUCK_LIMIT, source=KNOWLEDGE,
        )
    if content != STORE_OPERATION:
        return None
    visit = getattr(policy, "_store_visit", None)
    if owner.value in {"shop-buy", "shop-sell"} and visit is not None:
        if visit.operation_key is not None:
            return observe_goal(
                (visit.store_type, visit.operation_key, visit.opened_sequence),
                STORE_STUCK_LIMIT, source=STORE_OPERATION,
            )
    if owner.value in {'home-visit', 'equipment-txn'} and reason.startswith(('home:atomic-', 'home:deposit', 'home:withdraw-', 'home:weight-overload-deposit', 'home:morivant-temporary-deposit', 'home:morivant-retry-temporary-deposit', 'home:morivant-restore-temporary-deposit', 'home:leave-', 'home:store-context-exit')) and (visit is not None) and (visit.store_type == STORE_HOME):
        withdrawal = getattr(policy, "_home_atomic_withdraw_pending", None)
        deposit = getattr(policy, "_home_atomic_deposit_pending", None)
        withdraw_step = "withdraw" in reason or reason.startswith(
            ("home:leave-", "home:store-context-exit")
        )
        identity = getattr(visit, "claim_operation_identity", None)
        if identity is None and visit.operation_key is not None:
            identity = (STORE_HOME, visit.opened_sequence, visit.operation_key)
        if withdrawal is not None and identity is not None and withdraw_step:
            return observe_goal(
                identity,
                STORE_STUCK_LIMIT, source=STORE_OPERATION,
            )
        if deposit is not None and identity is not None:
            return observe_goal(
                identity,
                STORE_STUCK_LIMIT, source=STORE_OPERATION,
            )
    if owner.value == "home-errand":
        request = getattr(getattr(policy, "_home_errand", None), "request", None)
        if request is not None:
            operation = (
                "knowledge",
                getattr(policy, "_home_knowledge_scan_epoch", None)
                or getattr(policy, "_town_visit_epoch", None),
            ) if reason.startswith("home-errand:request-knowledge") else (
                getattr(visit, "claim_operation_identity", None)
                if visit is not None and visit.store_type == STORE_HOME
                else None
            )
            return observe_goal(
                (STORE_HOME, "errand", repr(request.signature), operation),
                STORE_STUCK_LIMIT, source=STORE_OPERATION,
            )
    chain = getattr(policy, "_staged_prompt_chain", None)
    if chain is not None and owner.value in {"identification", "curse-enchant"}:
        return observe_goal(
            (chain.get("owner"), len(chain.get("gates", ()))),
            len(chain.get("gates", ())),
            source=STORE_OPERATION,
        )
    return None


def claim_goal(
    policy, snapshot: Snapshot, key, owner: ClaimOwner, reason: str, standing
) -> Goal:
    """This decision's goal from the slot.

    Design rev 9 item 2 and rev 9.2 (C).  The kind comes from the
    checked-in typing table (``goal_typing``); the content comes
    from what a producer wrote on this board, and only when that
    producer's family is the row's owner:

    * ``Reach``: the slot's goal (a cell, a monster, or a place) when its
      family is this owner; otherwise the decision declares ``Terminal``
      (no slot, or a slot of another owner).
    * ``Observe``: a floor change is always the table's own content; any
      other ``Observe`` takes the expectation posted on this board by
      this owner (another owner's is not used: ``owner-mismatch``), else
      the same owner's still-open ``Observe`` claim (a transaction's later
      keys continue it), else the table's content.
    * ``Terminal``: the effect label.
    """
    if reason.startswith("town:entrance-step-off:"):
        reason = reason.split(":", 2)[2]
    # Catalogue acquisition owns its observed result across entry and
    # scan steps. Opening the page alone cannot discharge that work.
    if any(offer[0] == key and offer[1] == owner.value
           and offer[5] == "home-catalog-available"
           for offer in offered_steps(policy)):
        if (standing is not None and standing.is_open
                and standing.owner == owner
                and (standing.goal.source == KNOWLEDGE
                     or (standing.goal.source == STORE_ENTRY
                         and standing.execution is not None
                         and standing.execution.expected_effect == "home-catalog-available"))):
            return standing.goal
        return observe_goal(
            (STORE_HOME, "knowledge", policy._town_visit_epoch),
            STORE_STUCK_LIMIT, source=KNOWLEDGE,
        )
    if (
        standing is not None and standing.is_open and (standing.owner == owner) and (reason == 'store:entry-await-observation' and standing.goal.source in {STORE_OPERATION, 'transaction'} or (reason == 'home:scan-incomplete-open-page' and standing.goal.source == KNOWLEDGE) or (reason == 'shop:one-shot-in-flight' and standing.goal.source == STORE_OPERATION))
    ):
        # Neither a lagged store entry nor an incomplete Home page ends
        # the operation or knowledge observation it is waiting for.
        return standing.goal
    if (reason in {"shop:await-leave-confirmation", "shop:await-leave-generation"}
            and standing is not None and standing.is_open
            and standing.owner == owner
            and standing.goal.kind == GOAL_OBSERVE
            and standing.goal.source == STORE_OPERATION
            and not getattr(getattr(policy, "_store_visit", None),
                            "operation_effect_observed", False)):
        return standing.goal
    visit = getattr(policy, "_store_visit", None)
    completed_transaction = (
        reason == "home:leave-after-one-operation"
        and hold_claims(policy) is not None
        and standing_claim(policy) is not None
        and standing_claim(policy).closed == "complete"
        and standing_claim(policy).closed_reason == "equipment-transaction-complete"
    )
    if (
        reason in {"shop:leave", "shop:store-context-exit",
                   "shop:await-leave-confirmation",
                   "shop:await-leave-generation"}
        or reason.startswith("home:leave-")
        or reason == "home:store-context-exit"
    ) and (completed_transaction or (visit is not None and visit.operation_effect_observed)):
        if (
            standing is not None and standing.is_open and (standing.owner == owner) and (standing.goal.kind == GOAL_OBSERVE) and (standing.goal.source in {STORE_OPERATION, 'transaction'})
        ):
            return standing.goal
        return terminal_goal(reason)
    if owner.value in {'equipment-txn'} and reason.startswith(('home:atomic-', 'home:deposit', 'home:withdraw-', 'home:weight-overload-deposit', 'home:morivant-temporary-deposit', 'home:morivant-retry-temporary-deposit', 'home:leave-', 'home:store-context-exit', 'equipment-transaction:await-confirmation', 'equipment-transaction:home-route-unavailable')):
        if (standing is not None and standing.is_open and (standing.owner == owner) and (standing.goal.source in {'transaction'})):
            return standing.goal
        operation = claim_operation_goal(policy, snapshot, owner, reason, "transaction")
        if operation is not None:
            return operation
    row = goal_typing(owner.value, reason)
    effect = terminal_goal(reason or "policy:none")
    chain = getattr(policy, "_staged_prompt_chain", None)
    if chain is not None and claim_family_of(policy, chain.get("owner")) == owner.value:
        staged = claim_operation_goal(
            policy, snapshot, owner, reason, STORE_OPERATION
        )
        if staged is not None:
            return staged
    if row is None or row.kind == GOAL_TERMINAL:
        if owner.value == "home-visit" and reason.startswith((
            "home:leave-", "home:store-context-exit",
        )):
            operation = claim_operation_goal(
                policy, snapshot, owner, reason, STORE_OPERATION
            )
            if operation is not None:
                return operation
        if (
            standing is not None and standing.is_open
            and standing.owner == owner
            and standing.goal.source == FLOOR_CHANGE
            and reason.startswith("town:wait-recall")
        ):
            return standing.goal
        return effect
    if (
        standing is not None and standing.is_open
        and standing.owner == owner
        and standing.goal.source == FLOOR_CHANGE
        and reason.startswith("town:wait-recall")
    ):
        return standing.goal
    # A route to the next transaction step is still the same open
    # session. The separately ruled await-entry wait keeps its own
    # store-entry goal once the entrance command has been posted.
    if (
        row.kind == GOAL_REACH and owner.value in {'equipment-txn'} and (not reason.endswith(':await-entry'))
    ):
        operation = claim_operation_goal(
            policy, snapshot, owner, reason, "transaction"
        )
        if operation is not None:
            return operation
    if row.kind == GOAL_REACH:
        slot = getattr(policy, "_decision_goal", None)
        if not (
            isinstance(slot, tuple)
            and len(slot) in (2, 3)
            and isinstance(slot[1], Goal)
            and slot[1].kind == GOAL_REACH
        ):
            return effect
        if slot[0] != owner.value:
            return effect
        return slot[1]
    within = OBSERVE_WITHIN.get(row.content, OWNER_EXPECTATION_MAX_TURNS)
    if row.content == STORE_ENTRY:
        visit = getattr(policy, "_store_visit", None)
        if (
            reason == "store:entry-await-observation"
            and visit is not None and visit.goal is not None
            and (snapshot.player.position.y, snapshot.player.position.x)
                != (visit.goal.y, visit.goal.x)
        ):
            return reach_goal((visit.goal.y, visit.goal.x))
        target = getattr(policy, "_store_entry_wait_owner", None)
        if target is None and visit is not None:
            target = visit.store_type
        return observe_goal(
            (STORE_ENTRY, target), within,
            source=STORE_ENTRY,
        )
    if row.content == FLOOR_CHANGE:
        return observe_goal(FLOOR_EXPECTATION, within, source=FLOOR_CHANGE)
    operation = claim_operation_goal(policy, snapshot, owner, reason, row.content)
    if operation is not None:
        return operation
    posted = getattr(policy, "_decision_expectation", None)
    if (
        isinstance(posted, tuple)
        and len(posted) == 2
        and isinstance(posted[1], Goal)
        and posted[1].kind == GOAL_OBSERVE
    ):
        if posted[0] == owner.value:
            return posted[1]
    if (
        standing is not None
        and standing.is_open
        and standing.owner == owner
        and standing.goal.kind == GOAL_OBSERVE
        and standing.goal.source != FLOOR_CHANGE
    ):
        return standing.goal
    return observe_goal((row.content,), within, source=row.content)


def claim_owner_retired(policy, owner) -> bool:
    """Whether the arbiter already holds this owner's claim as retired."""
    arbiter = getattr(policy, "_town_turn_arbiter", None)
    telemetry = getattr(arbiter, "telemetry", None) if arbiter else None
    if not isinstance(telemetry, dict):
        return False
    return bool(
        telemetry.get("retired")
        and telemetry.get("producer_owner") == owner.value
    )


def claim_perceived_monster(snapshot: Snapshot, identity):
    """The perceived monster with this ``(index, race_id)``, if any."""
    for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters):
        if (monster.index, monster.race_id) == tuple(identity):
            return monster
    return None


def claim_entered_store_at(policy, snapshot: Snapshot, cell) -> bool:
    """The board is inside the store whose entrance is ``cell``."""
    visit = getattr(policy, "_store_visit", None)
    entrance = getattr(visit, "goal", None)
    return (
        snapshot.store is not None
        and isinstance(entrance, Position)
        and tuple(cell) == (entrance.y, entrance.x)
    )


def claim_reach_arrival(policy, snapshot: Snapshot, claim) -> str | None:
    """The observed arrival that completes a cell Reach claim, read-only.

    The same evidence ``_claim_exit_completion`` closes the claim on: the
    player stands on the goal cell of the claim's own floor (never the
    open wilderness), or is inside the store whose entrance is the cell.
    """
    goal = claim.goal
    if (goal.kind != GOAL_REACH or goal.monster is not None
            or goal.cell is None):
        return None
    if claim.floor is not None and tuple(claim.floor) != tuple(snapshot.floor_key):
        return None
    if snapshot.on_open_wilderness:
        return None
    position = snapshot.player.position
    if goal.cell == (position.y, position.x):
        return "reached"
    if claim_entered_store_at(policy, snapshot, goal.cell):
        return "entered-store"
    return None


def claim_exit_completion(policy, snapshot: Snapshot, standing, pops) -> None:
    """Close the standing claim on what this board shows.

    * Reach, cell: the player stands on the goal cell on the claim's own
      floor (never on the open wilderness, whose grids are not local-map
      cells), or stands in the store whose entrance is the goal.
    * Reach, monster (rev 9.2 M): ``complete`` when the monster is
      adjacent, ``release`` when it is no longer perceived (it left
      perception or died).
    * Reach, place: only its producer's arrival test closes it.
    * Observe, floor change: ``snapshot.floor_key`` differs from the
      floor the claim was opened on; after 350 game turns it expires.
    * Observe, posted expectation: ``complete`` when the registry popped
      it as satisfied, or (rev 9.2 O) when the registry's own
      satisfaction test holds for it now, read-only and without a pop.
    * Observe older than its ``within`` (rev 9.2 E) closes ``expired``.
      ``within`` is counted in the unit its constant is defined in: game
      turns for the floor change (``RECALL_ACTIVATION_MAX_GAME_TURNS``),
      decisions for ``OWNER_EXPECTATION_MAX_TURNS`` and
      ``STORE_STUCK_LIMIT``, which both count decisions where they are
      defined.
    """
    if standing is None or not standing.is_open:
        return
    own = (standing.owner,)
    goal = standing.goal
    position = snapshot.player.position
    same_floor = standing.floor is None or tuple(standing.floor) == tuple(
        snapshot.floor_key
    )
    if goal.kind == GOAL_REACH:
        if goal.monster is not None:
            monster = claim_perceived_monster(snapshot, goal.monster)
            if monster is None or not same_floor:
                policy._release_claim_goal("target-lost", owners=own)
            elif position.distance_to(monster.position) <= 1:
                policy._complete_claim_goal("target-adjacent", owners=own)
            return
        if goal.cell is None:
            return
        if not same_floor or snapshot.on_open_wilderness:
            return
        arrival = claim_reach_arrival(policy, snapshot, standing)
        if arrival is not None:
            policy._complete_claim_goal(arrival, owners=own)
            return
        visit = getattr(policy, "_store_visit", None)
        entrance = getattr(visit, "goal", None)
        context = getattr(getattr(policy, "_home_visit", None), "context_token", None)
        if (
            entrance is not None
            and goal.cell == (entrance.y, entrance.x)
            and (
                (isinstance(context, tuple) and context[0] == "outside-ready")
                or getattr(policy, "_home_entry_operation_posted", False)
                or getattr(policy, "_intentional_entrance_activation", False)
            )
        ):
            policy._complete_claim_goal("entered-outside", owners=own)
        return
    if goal.kind != GOAL_OBSERVE:
        return
    if (
        goal.source == KNOWLEDGE
        and (getattr(policy, "_home_knowledge_current", False)
             or getattr(policy, "_claim_home_knowledge_observed", False))
    ):
        policy._complete_claim_goal("home-knowledge-current", owners=own)
        return
    session = getattr(policy, "_equipment_transaction_session", None)
    opened = getattr(session, "opened_sequence", None)
    session_replaced = (
        session is not None
        and any(part.isdecimal() for part in goal.expectation)
        and (opened is None or str(opened) not in goal.expectation)
    )
    if (
        goal.source in {'transaction'} and standing.owner.value in {'equipment-txn'} and (session_replaced or (session is None and (getattr(policy, '_equipment_transaction_owned_items', None) or False)))
    ):
        terminal = (
            getattr(policy, "_equipment_transaction_restore_terminal", None)
            or ("session-replaced" if session_replaced else None)
            or policy.last_reason or "session-cleared"
        )
        policy._release_claim_goal(
            f"abandoned:{terminal}", owners=own,
            kinds=(GOAL_OBSERVE,), sources=(goal.source,),
        )
        return
    if goal.source == FLOOR_CHANGE:
        if standing.floor is not None and not same_floor:
            policy._complete_claim_goal("floor-changed", owners=own)
        elif (
            goal.within is not None
            and standing.opened_turn is not None
            # S2b.1 (rev 10.1 item 6): the turns spent suspended do not
            # count against a resumed claim's ``within``.
            and snapshot.turn - standing.opened_turn
            - (standing.suspended_turns or 0) > goal.within
        ):
            close_claim(policy, "expire", "within-exceeded", owners=own)
        return
    if goal.source == STORE_ENTRY:
        # Restored pre-live23 declarations also named catalogue work,
        # although their goal was typed as entry. Honor the named effect.
        declaration = getattr(standing, "execution", None)
        catalogue_work = (declaration is not None
                          and declaration.expected_effect == "home-catalog-available")
        if catalogue_work and policy._home_knowledge_current:
            policy._complete_claim_goal("home-knowledge-current", owners=own)
            return
        visit = getattr(policy, "_store_visit", None)
        entrance = getattr(visit, "goal", None)
        if (
            not catalogue_work
            and snapshot.store is not None
            and str(snapshot.store.store_type) in goal.expectation
            and (
                entrance is None
                or claim_entered_store_at(
                    policy, snapshot, (entrance.y, entrance.x)
                )
            )
        ):
            policy._complete_claim_goal("entered-store", owners=own)
            return
    if any(
        owner == goal.source and why == EXPECTATION_POP_SATISFIED
        for owner, why in pops
    ):
        policy._complete_claim_goal("expectation-satisfied", owners=own)
        return
    registry = getattr(policy, "_owner_expectations", None)
    if (
        registry is not None
        and goal.source is not None
        and hasattr(registry, "verdict")
        and registry.pending(goal.source) is not None
        and registry.verdict(
            goal.source, policy._progress_core_of(snapshot)
        ) == EXPECTATION_POP_SATISFIED
    ):
        policy._complete_claim_goal("expectation-satisfied", owners=own)
        return
    if (
        goal.within is not None
        and standing.opened_sequence is not None
        # S2b.1 (rev 10.1 item 6): nor do the decisions spent suspended.
        and policy._decision_sequence - standing.opened_sequence
        - (standing.suspended_decisions or 0) >= goal.within
    ):
        close_claim(policy, "expire", "within-exceeded", owners=own)


def claim_goal_distance(policy, snapshot: Snapshot, goal: Goal):
    position = snapshot.player.position
    if goal.kind != GOAL_REACH:
        return None
    if goal.cell is not None:
        return position.distance_to(Position(*goal.cell))
    if goal.monster is not None:
        monster = claim_perceived_monster(snapshot, goal.monster)
        return (
            position.distance_to(monster.position)
            if monster is not None
            else None
        )
    return None


def claim_suspended_exit(policy, snapshot: Snapshot, register) -> None:
    """Rules (i) and (ii) of rev 10.1 item 6, on the suspended stack.

    (i) After a floor change (a town departure is one) a suspended
    floor-change ``Observe`` completes and every other suspended claim is
    released ``suspended-expired``.  (ii) On the same floor, a suspended
    ``Reach`` completes when the board shows it met, by the tests an
    active claim uses: the player on its cell, or next to its monster; and
    (S2b.1b) a suspended chase whose monster is no longer perceived is
    released ``target-lost``, as an active one is.  No store-operation or
    transaction ``Observe`` is ever on the stack
    (``never_suspended``).
    """
    position = snapshot.player.position
    for claim in register.suspended:
        goal = claim.goal
        if (
            goal.kind == GOAL_OBSERVE
            and goal.source == KNOWLEDGE
            and (getattr(policy, "_home_knowledge_current", False)
                 or getattr(policy, "_claim_home_knowledge_observed", False))
        ):
            register.close_suspended(
                claim.claim_id, "complete", "home-knowledge-current"
            )
            continue
        if claim.floor is None:
            # Round 3: a claim restored from before ``floor`` existed.
            # The first board that sees it suspended is its floor, so it
            # expires on the first floor change from here.
            register.stamp_suspended_floor(claim.claim_id, snapshot.floor_key)
            continue
        if tuple(claim.floor) != tuple(
            snapshot.floor_key
        ):
            if (
                goal.kind == GOAL_OBSERVE
                and goal.source == FLOOR_CHANGE
            ):
                register.close_suspended(
                    claim.claim_id, "complete", "floor-changed"
                )
            else:
                register.close_suspended(
                    claim.claim_id, "release", SUSPENDED_EXPIRED
                )
            continue
        if goal.kind == GOAL_OBSERVE and goal.source == STORE_ENTRY:
            if (
                snapshot.store is not None
                and str(snapshot.store.store_type) in goal.expectation
            ):
                register.close_suspended(
                    claim.claim_id, "complete", "entered-store"
                )
            continue
        if goal.kind != GOAL_REACH:
            continue
        if goal.monster is not None:
            monster = claim_perceived_monster(snapshot, goal.monster)
            if monster is None:
                # S2b.1b: the active claim's own rule (rev 9.2 M,
                # ``_claim_exit_completion``): a chased monster that is
                # no longer perceived -- killed by the preemptor's shot,
                # or gone -- releases the chase, suspended or not.
                register.close_suspended(
                    claim.claim_id, "release", "target-lost"
                )
            elif position.distance_to(monster.position) <= 1:
                register.close_suspended(
                    claim.claim_id, "complete", "target-adjacent"
                )
        elif goal.cell is not None and not snapshot.on_open_wilderness:
            # Round 3: the same tests as an active Reach claim
            # (``_claim_exit_completion``): on the cell, or inside the
            # store whose entrance is the cell.
            if goal.cell == (position.y, position.x):
                register.close_suspended(
                    claim.claim_id, "complete", "reached"
                )
            elif claim_entered_store_at(policy, snapshot, goal.cell):
                register.close_suspended(
                    claim.claim_id, "complete", "entered-store"
                )


def claim_owner_transition(
    policy, register, standing, owner, goal, rung, survival, non_discardable,
    *, snapshot
):
    """How this decision treats the claim the previous one declared.

    Returns ``(action, label, dropped)``: ``dropped`` is True when this
    decision drops the held claim without closing it (a violation of the
    ladder; ``claim_set_bars`` bars it).  Only a held claim that is still
    open with a Reach or Observe goal matters:

    * an owner change to a strictly higher rung (rev 10 item 2) is a
      preemption -- the caller suspends the holder (``survival-preemption``
      when the new decision is survival, as S2a.1 labelled it);
    * survival that does not outrank the holder, or the same owner turning
      to another goal on a survival decision, replaces it -- the caller
      releases it ``survival-displaced``; survival is exempt, so this is
      not a violation (round 2 F1/F2);
    * the same owner replacing its own open goal otherwise is a retarget
      violation (rev 10 item 4) -- never a preemption followed by
      ``resume-goal-changed`` on the same decision;
    * any other owner change is a violation, and so is any ordinary
      change away from a store-operation or transaction ``Observe`` claim
      (rev 10.1 item 6). A town survival decision suspends an S3 holder;
      adjacent melee also suspends a pending town monster chase.

    Nothing stops.
    """
    if (
        standing is None
        or not standing.is_open
        or standing.goal.kind not in (GOAL_REACH, GOAL_OBSERVE)
    ):
        return None, None, None
    if register.continues(owner, goal, non_discardable):
        # The same owner pursuing the same goal keeps its claim, survival
        # or not (``declare`` updates its survival flag).
        return None, None, None
    if (standing.owner == owner and standing.goal.source in {'transaction'} and (goal.source == STORE_ENTRY) and (policy.last_reason or '').endswith(':await-entry')):
        return PREEMPTION, "transaction-entry-wait", None
    # S3 town operations survive an emergency even when their Observe
    # source normally forbids suspension.  Other owners keep the ladder's
    # bounded-rank preemption rule.
    if (survival and standing.owner != owner
            and snapshot.in_town
            and (standing.owner.value in TOWN_OWNER_FAMILIES
                 or (standing.owner.value == "survival"
                     and policy.last_reason == "melee"))):
        return PREEMPTION, "survival-preemption", None
    held = rung_of_claim(
        standing.owner, standing.rung,
        non_discardable=standing.non_discardable,
    )
    if standing.owner == owner:
        verdict = SURVIVAL_DISPLACED if survival else VIOLATION
    else:
        verdict = owner_change(
            held_rank=held.rank,
            held_goal_kind=standing.goal.kind,
            held_goal_source=standing.goal.source,
            held_survival=standing.survival,
            new_rank=rung.rank,
            new_survival=survival,
        )
    if verdict == PREEMPTION:
        return PREEMPTION, (
            "survival-preemption"
            if survival
            else f"preempted-by:{owner.value}"
        ), None
    if verdict == SURVIVAL_DISPLACED:
        return SURVIVAL_DISPLACED, SURVIVAL_DISPLACED, None
    return None, None, True


def claim_resolve_suspended(
    policy, register, owner, goal, rung, survival, non_discardable
):
    """Rule (iii) of rev 10.1 item 6: resume, nest or displace.

    Unless this decision continues the current claim:

    * a claim of the same owner and goal suspended **anywhere** in the
      stack resumes (returned, for the caller to ``resume`` under its id);
      the claims above it that this decision outranks stay suspended, the
      others are displaced as below;
    * otherwise the stack is read from the top: the same owner with
      another goal releases it ``resume-goal-changed`` (rev 10 item 3), a
      new claim opens and the claims below are read on; a strictly
      higher rung nests over it (only a
      strictly higher rung: that is the bound on the depth); survival
      displaces it ``survival-displaced`` (exempt, no violation); any other
      owner displaces it -- a violation, recorded with the release
      ``resume-displaced`` -- and the next claim down is read the same
      way.
    """
    if register.continues(owner, goal, non_discardable):
        return None
    stack = register.suspended
    if survival and any(
        claim.owner.value in TOWN_OWNER_FAMILIES for claim in stack
    ):
        return None
    if (goal.source == STORE_ENTRY
            and (policy.last_reason or "").endswith(":await-entry")):
        return None
    match = resumable_index(stack, owner, goal, non_discardable)
    for index in range(len(stack) - 1, -1, -1):
        top = stack[index]
        if index == match:
            return top
        held = rung_of_claim(
            top.owner, top.rung, non_discardable=top.non_discardable
        )
        if match is None and top.owner == owner:
            register.close_suspended(
                top.claim_id, "release", "resume-goal-changed"
            )
            # the new claim opens here; the claims below are read the
            # same way, so it never sits above one it does not outrank
            continue
        if nests_over(top_rank=held.rank, new_rank=rung.rank):
            if match is None:
                return None
            continue
        if survival:
            register.close_suspended(
                top.claim_id, "release", SURVIVAL_DISPLACED
            )
            continue
        register.close_suspended(top.claim_id, "release", "resume-displaced")
    return None


def claim_trigger_monsters(policy, owner, goal):
    """Rev 10.1 item 9 / design 5.4.1: the monsters behind a new claim.

    For a Reach or Observe claim of positioning, hunt, esp-threat, combat
    or escape: the ``(index, race_id)`` pairs its producer declared on
    this board (``_declare_triggers``), plus the chased monster of a
    monster goal (hunt, whose target is its goal).  A producer that
    declared none records none -- never every perceived hostile.
    """
    if (
        owner.value not in TRIGGER_FAMILIES
        or goal.kind not in (GOAL_REACH, GOAL_OBSERVE)
    ):
        return ()
    found: set[tuple[int, int]] = set()
    slot = getattr(policy, "_decision_triggers", None)
    if (
        isinstance(slot, tuple)
        and len(slot) == 2
        and slot[0] == owner.value
    ):
        found.update(tuple(pair) for pair in slot[1])
    if goal.monster is not None:
        found.add((int(goal.monster[0]), int(goal.monster[1])))
    return tuple(sorted(found))


def claim_trigger_perceived(snapshot: Snapshot, triggers):
    """The game turn, when one of ``triggers`` is perceived on this board."""
    if not triggers:
        return None
    wanted = {tuple(pair) for pair in triggers}
    for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters):
        if (monster.index, monster.race_id) in wanted:
            return snapshot.turn
    return None


def claim_perceived_pairs(snapshot: Snapshot) -> frozenset:
    """Every ``(index, race_id)`` this board perceives (seen or detected)."""
    return frozenset(
        (int(monster.index), int(monster.race_id))
        for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
    )


def claim_durable_clearance(key):
    """The durable part of a retirement clearance key (round 2).

    User decision 2026-09-26: a town-errand bar lifts only when the
    durable part of the clearance key changes -- inventory, gold,
    equipment and the other durable facts of the progress vector, the
    quest and departure tuples -- never by the player's own movement.
    ``_town_retirement_clearance_key`` is the progress vector (its durable
    facts plus, for a walking owner, a ``("locomotion", ...)`` part that
    carries the distance to the goal), the departure tuple (whose last
    element is the same locomotion part), or the quest route-unavailable
    tuples (durable already).  So: the locomotion parts go, the departure
    tuple loses its last element, and the progress core -- position,
    turn and sequence already zeroed by the vector -- also forgets the
    hit points and the store the player stands in, which walking and
    waiting change without any errand being done.
    """
    if not isinstance(key, tuple):
        return key
    if key and key[0] == "departure":
        return key[:-1]
    durable = []
    for part in key:
        if isinstance(part, tuple) and part and part[0] == "locomotion":
            continue
        if isinstance(part, OwnerProgressCore):
            part = replace(
                part,
                position=Position(0, 0),
                turn=0,
                decision_sequence=0,
                hp=0,
                store_type=None,
            )
        durable.append(part)
    return tuple(durable)


def claim_errand_clearance(policy, snapshot: Snapshot, owner: str, reason):
    """The durable clearance key of an errand owner on this board."""
    return claim_durable_clearance(
        policy._town_retirement_clearance_key(snapshot, owner, reason)
    )


def claim_bar_after(
    policy, snapshot: Snapshot, bar: Bar, perceived=None
) -> Bar | None:
    """``bar`` as this board leaves it, ``None`` when the board lifts it."""
    return bar_after_board(
        bar,
        turn=snapshot.turn,
        perceived=(
            perceived
            if perceived is not None
            else claim_perceived_pairs(snapshot)
        ),
        hold=DETECTED_THREAT_HOLD_MAX_GAME_TURNS,
        clearance_of=lambda errand: claim_errand_clearance(
            policy, snapshot, errand.owner.value, errand.reason
        ),
    )


def claim_bar_lift(policy, snapshot: Snapshot, register) -> None:
    """Design 3.2 / 3.3: the lift pass of this board.

    A threat-triggered bar lifts once ``DETECTED_THREAT_HOLD_MAX_GAME_TURNS``
    game turns (the existing 50-turn clock of the detected-threat choke
    release) have passed with none of its trigger monsters perceived; an
    errand bar lifts when the durable part of its owner's retirement
    clearance key differs from the one recorded when it was set.
    """
    bars = register.bars
    if not bars:
        return
    perceived = claim_perceived_pairs(snapshot)
    kept = [after for after in (claim_bar_after(policy, snapshot, bar, perceived) for bar in bars)
            if after is not None]
    if kept != list(bars):
        register.replace_bars(kept)


def claim_bar_for(policy, snapshot: Snapshot, claim, ending: str):
    """The bar a claim that ended this way earns, or ``None``.

    Design 3.2: a preemptor that does not reach its own goal is barred;
    survival is exempt (the claim's ``survival`` flag, rev 10.1 item 3).
    Design 3.3: a retired claim bars its owner for the same goal.

    * Only a Reach or Observe claim, never a survival one, and never one
      that completed.
    * The preemptors are the threat-triggered owners (rev 10.1 item 9's
      ``TRIGGER_FAMILIES``: positioning, hunt, esp-threat, combat,
      escape) -- the owners that take the decision from the ordinary ones
      because of monsters.  Their claim is barred when it ends without
      its goal: released, expired, retired, dropped by another owner or by
      its own retarget (a violation), or displaced from the stack.  Two
      endings are not the claim's own failure and bar nothing: survival
      replacing it (``survival-displaced``, design 3.4) and a floor change
      while it was suspended (``suspended-expired``).
    * Any other owner is barred by retirement only, as an errand owner;
      the bar records the durable part of its retirement clearance key
      (round 2) and lifts when that changes.
    * A Terminal claim never ends abandoned, so combat melee is never
      barred (rev 10.1 item 4, the known gap).
    """
    if claim is None or claim.survival:
        return None
    if claim.goal.kind not in (GOAL_REACH, GOAL_OBSERVE):
        return None
    if ending == CLOSED_BY_COMPLETE:
        return None
    if claim.closed_reason in (
        SURVIVAL_DISPLACED, SUSPENDED_EXPIRED
    ):
        return None
    threat = claim.owner.value in TRIGGER_FAMILIES
    perceived_now = claim_trigger_perceived(
        snapshot, claim.trigger_monsters
    )
    common = {
        "owner": claim.owner,
        "goal": claim.goal,
        "rung": rung_of_claim(
            claim.owner, claim.rung, non_discardable=claim.non_discardable
        ).name,
        "since_turn": snapshot.turn,
        "since_sequence": policy._decision_sequence,
        "claim_id": claim.claim_id,
        "ending": (
            ending if claim.closed_reason is None
            else f"{ending}:{claim.closed_reason}"
        ),
    }
    if threat:
        return Bar(
            kind=BAR_THREAT,
            triggers=tuple(claim.trigger_monsters),
            last_perceived_turn=(
                perceived_now
                if perceived_now is not None
                else claim.last_perceived_turn
            ),
            **common,
        )
    no_step = (claim.closed_reason or "").startswith("no-step:")
    if ending != CLOSED_BY_RETIRED and not no_step:
        return None
    # The retirement is this decision's (``_claim_owner_retired``), so the
    # reason the key is computed for is the decision's own.
    reason = None if no_step else (
        policy.last_reason
        if claim_family_of(policy, policy.last_reason) == claim.owner.value
        else None
    )
    return Bar(
        kind=BAR_ERRAND,
        clearance=claim_errand_clearance(
            policy, snapshot, claim.owner.value, reason
        ),
        reason=reason,
        **common,
    )


def claim_set_bars(policy, snapshot: Snapshot, register, *, dropped=None):
    """Bar the claims that ended on this decision.

    ``register.take_ended`` gives every claim a closing call ended since
    the last declaration (a producer's release, the exit's expiry, a
    retirement, a suspended claim displaced or released); ``dropped`` is
    the held claim this decision dropped without a closing.
    """
    ended = [(claim, claim.closed) for claim in register.take_ended()]
    if dropped is not None:
        ended.append((dropped, "abandoned"))
    for claim, ending in ended:
        bar = claim_bar_for(policy, snapshot, claim, ending)
        if bar is not None:
            register.set_bar(bar)


def open_execution_delegation(
    policy, parent_family: str, delegate_family: str,
    work_identity: tuple, purpose_identity: tuple,
    expected_effect: str, budget_reference: str,
) -> ExecutionDelegation:
    """Reserve a named child before invoking its executor."""
    work_identity = tuple(work_identity)
    purpose_identity = tuple(purpose_identity)
    for record in hold_delegations(policy):
        if (record.lifecycle in {"reserved", "open"}
                and record.parent_family == parent_family
                and record.delegate_family == delegate_family
                and record.work_identity == work_identity
                and record.purpose_identity == purpose_identity):
            return record
    record = ExecutionDelegation(
        None, parent_family, delegate_family, work_identity,
        purpose_identity, policy._decision_sequence, expected_effect,
        budget_reference, "reserved",
    )
    hold_delegations(policy).append(record)
    return record


def end_execution_delegation(
    policy, delegate_family: str, work_identity: tuple,
    *, completed: bool, cause: str,
) -> None:
    for record in hold_delegations(policy):
        if (record.lifecycle in {"reserved", "open"}
                and record.delegate_family == delegate_family
                and record.work_identity == tuple(work_identity)):
            record.lifecycle = "completed" if completed else "released"
            record.ending = cause


def bind_execution_delegations(policy, claim) -> None:
    """Bind same-decision reservations or cancel an unmatched opening."""
    for record in hold_delegations(policy):
        if (record.lifecycle != "reserved"
                or record.opening_decision != policy._decision_sequence):
            continue
        if claim is not None and claim.is_open and (
            claim.owner.value == record.parent_family
        ):
            record.parent_claim_id = claim.claim_id
            record.lifecycle = "open"
            record.execution = ExecutionDeclaration(
                claim.claim_id, str(record.work_identity), 1,
                record.delegate_family, "acting",
                next_step="delegate.dispatch",
                arguments=record.work_identity,
                expected_effect=record.expected_effect,
                continuation="parent.resume",
                budget_ref=record.budget_reference,
            )
        else:
            record.lifecycle = "released"
            record.ending = "exit-owner-mismatch"


def cancel_unbound_execution_delegations(policy) -> None:
    """End reservations left behind by a decision without a claim exit."""
    for record in hold_delegations(policy):
        if record.lifecycle == "reserved":
            record.lifecycle = "released"
            record.ending = "exit-not-reached"


def observe_execution_delegations(policy) -> None:
    """Retire children only when their named source resolves."""
    session = policy._equipment_transaction_session
    visit = policy._store_visit
    for record in hold_delegations(policy):
        if record.lifecycle != "open":
            continue
        work = record.work_identity
        if work[:1] == ("session",):
            same_session = (
                session is not None
                and session.target_loadout_id == work[2]
                and tuple((action.kind, action.target_slot,
                           action.item_identity)
                          for action in session.plan.actions) == work[3]
            )
            if not same_session:
                record.lifecycle = "released"
                record.ending = "session-replaced-or-ended"
            elif session.complete:
                record.lifecycle = "completed"
                record.ending = "session-effect-observed"
        elif work[:1] in {("home-operation",), ("staged-tail",)}:
            identity = tuple(work[1:])
            if visit is not None and visit.claim_operation_identity == identity:
                if visit.operation_effect_observed:
                    record.lifecycle = "completed"
                    record.ending = "home-operation-effect-observed"
            elif visit is None or visit.phase == StoreVisitPhase.CLOSED:
                record.lifecycle = "released"
                record.ending = "home-operation-ended-unobserved"
        elif work[:1] == ("route",):
            if visit is not None and visit.opened_sequence == work[1]:
                parent = standing_claim(policy)
                arrived_claim = (
                    parent is not None
                    and parent.claim_id == record.parent_claim_id
                    and parent.closed == CLOSED_BY_COMPLETE
                )
                if arrived_claim or visit.phase in {
                    StoreVisitPhase.OPERATING, StoreVisitPhase.LEAVING,
                    StoreVisitPhase.CLOSED,
                }:
                    record.lifecycle = "completed"
                    record.ending = "route-arrived"
            elif visit is None:
                record.lifecycle = "released"
                record.ending = "route-ended-unobserved"
        elif record.delegate_family == "home-scan":
            if policy._home_knowledge_current:
                record.lifecycle = "completed"
                record.ending = "catalogue-adopted"
        elif work[:1] == ("filed",):
            request = policy._home_errand.request
            if request is None or (
                request.signature, request.quantity,
                request.origin, request.purpose
            ) != work[1:]:
                record.lifecycle = "released"
                record.ending = "filed-request-replaced"
            elif not policy._home_errand.active:
                record.lifecycle = "completed" if (
                    policy._home_errand.state.value == "done"
                ) else "released"
                record.ending = f"filed-request:{policy._home_errand.state.value}"
        if record.lifecycle == "open" and record.parent_claim_id is not None:
            register = hold_claims(policy)
            live = [register.current, *register.suspended]
            if not any(
                claim is not None and claim.claim_id == record.parent_claim_id
                and claim.is_open for claim in live
            ):
                record.lifecycle = "released"
                record.ending = "parent-claim-ended"
    for record in hold_delegations(policy):
        declaration = getattr(record, "execution", None)
        if declaration is None or record.lifecycle == "open":
            continue
        state = "done" if record.lifecycle == "completed" else "releasing"
        if declaration.state != state:
            record.execution = replace(
                declaration, revision=declaration.revision + 1,
                state=state, next_step=None, arguments=(),
                evidence=record.ending if state == "done" else None,
                cause=record.ending if state == "releasing" else None,
            )
