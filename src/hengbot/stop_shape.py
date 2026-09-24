"""Classify a recorded stop into one ownership shape (S0 measurement only).

``SOL-DESIGN-ownership-contract.md`` section 6 stage S0 is measurement: this
module decides nothing and changes no key, reason or policy state.  It reads
what the driver already knows when it stops -- the stop kind, the driver's
``recent_reasons`` window and the last decision row it wrote -- and names the
shape of the stop so a baseline can be measured before S1 and compared after.

The four shapes:

``ownership-alternation``
    Two different producers took the decision from each other in turn without
    either reaching a goal.  The 2026-09-23 06:00 stop (``seek-loot`` in turn
    with ``detected:prepare-choke``) is this shape.

``no-exit``
    One producer held the decision and emitted the same thing forever, or the
    policy declared a final stop: nothing on the board could clear it.  The
    2026-09-23 03:44 stop (``town:blocked:equipment-calibration-required``
    repeated until the driver's fuse blew) is this shape.

``unobserved-effect``
    An operation was posted and its effect was never observed, so the producer
    waited for a board that could not arrive.  The 2026-09-23 01:43 stop
    (``store:entry-await-observation`` with a store visit still entering on a
    posted sequence) is this shape.

``other``
    Anything the three rules above do not decide.  Deliberately not a
    catch-all for "ownership": a stop counted into a shape must carry the
    evidence that put it there.

Rule order, and why.  The rules are tried in the order
``ownership-alternation`` -> ``unobserved-effect`` -> ``no-exit``, and the
first one whose evidence is present decides.  Alternation is first because it
needs two producers in the window and nothing else can produce that pattern.
``unobserved-effect`` is ahead of ``no-exit`` deliberately: a producer that
repeats one reason *while an operation of its own is still in flight* is
repeating because of the unobserved effect, and that is the fact a reader can
act on; classifying it by the repetition alone would hide the cause.  A
repetition with no operation in flight, a policy-declared final stop and a
retired owner still holding the decision are all ``no-exit``.

Producer identity.  The owner families are the town arbiter's own
registrations (``town_arbiter.reason_owner_family``), which keeps one source
of truth for the mapping.  Two of them, ``misc`` and ``unregistered``, are
catch-alls that used to hold every dungeon producer (the arbiter only runs in
town -- ``town_arbiter.py`` clears everything when ``not in_town``), so a
reason that lands in either is identified further by its own leading segment.
Without that refinement ``seek-loot`` and ``melee`` would have been the same
producer and the 06:00 alternation would have been invisible.

Stage S2a registered the families behind those two catch-alls, so
``reason_owner_family`` now names the producer directly and the refinement is
a fallback rather than the normal case.  It stays, because a reason nobody has
registered yet must still be distinguishable from every other such reason.

The stopping row's ``arbiter.owner`` and ``arbiter.producer_owner`` are
recorded with every verdict.  They are evidence rather than a trigger: they
differ whenever an emit is relabelled (01:43 decision 1905 emitted under
``detectors`` while ``town-errand`` held the turn), which is a different fact
from one producer taking the decision from another.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from hengbot.policy_constants import POLICY_FINAL_STOP_REASONS
from hengbot.town_arbiter import reason_owner_family


SHAPE_OWNERSHIP_ALTERNATION = "ownership-alternation"
SHAPE_NO_EXIT = "no-exit"
SHAPE_UNOBSERVED_EFFECT = "unobserved-effect"
SHAPE_OTHER = "other"
SHAPES = (
    SHAPE_OWNERSHIP_ALTERNATION,
    SHAPE_NO_EXIT,
    SHAPE_UNOBSERVED_EFFECT,
    SHAPE_OTHER,
)

# Three full cycles (six decisions) of two producers taking the decision from
# each other.  Two cycles is an ordinary interleave: a producer that emits,
# yields to one board of another producer and comes back is the normal ladder.
ALTERNATION_MIN_CYCLES = 3
# Six identical reasons is already past every producer's own repetition guard;
# the driver's own fuses (TOWN_BLOCKED_STOP_LIMIT 30, the loop window) are far
# longer, so this only ever reads a window the driver had already condemned.
NO_EXIT_MIN_REPEAT = 6

# The arbiter's two catch-all families; every dungeon producer lands in one.
CATCH_ALL_FAMILIES = frozenset({"misc", "unregistered"})

# cli.py ~1977/1990: the posting contract's own refusal markers.  Each one
# says the previous post's effect was never observed.
UNOBSERVED_POSTING_MARKERS = frozenset(
    {
        "posting-contract:identical-repost-unobserved",
        "posting-contract:prompt-owner-mismatch",
        "posting-contract:recall-already-active",
    }
)
# emit_ownership.in_flight_clause: every clause names a posted operation whose
# effect the visit has not observed yet.
IN_FLIGHT_CLAUSES = frozenset(
    {
        "operation-posted-not-released",
        "operation-released-effect-not-observed",
        "entering-with-posted-sequence",
        "leaving-with-posted-sequence",
    }
)
# Reason labels that say in words that the producer is waiting for an effect.
_AWAITING_REASON_MARKERS = ("await-observation", "await-entry", "unobserved")


@dataclass(frozen=True)
class StopShape:
    """One classified stop: the shape, the rule that decided it, the evidence."""

    shape: str
    rule: str
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"shape": self.shape, "rule": self.rule, "evidence": dict(self.evidence)}


def producer_identity(reason: str | None) -> str:
    """Name the producer of a reason label.

    The arbiter's registered family, except inside its two catch-all families
    where the reason's own leading segment separates the producers the arbiter
    never registered (every dungeon producer).
    """
    normalized = reason or ""
    family = reason_owner_family(normalized)
    if family not in CATCH_ALL_FAMILIES:
        return family
    head = normalized.split(":", 1)[0] or "policy:none"
    return f"{family}:{head}"


def terminal_evidence(row: Mapping | None) -> dict:
    """Project the stopping decision row onto the facts the rules read."""
    if not isinstance(row, Mapping):
        return {}
    arbiter = row.get("arbiter")
    arbiter = arbiter if isinstance(arbiter, Mapping) else {}
    visit = row.get("store_visit")
    visit = visit if isinstance(visit, Mapping) else {}
    emit = row.get("town_emit_ownership")
    emit = emit if isinstance(emit, Mapping) else {}
    return {
        "decision_sequence": row.get("decision_sequence"),
        "time": row.get("time"),
        "turn": row.get("turn"),
        "reason": row.get("reason"),
        "key": row.get("key"),
        "arbiter_owner": arbiter.get("owner"),
        "arbiter_producer_owner": arbiter.get("producer_owner"),
        "arbiter_retired": arbiter.get("retired"),
        "in_flight_clause": emit.get("in_flight_clause"),
        "operation_posted": visit.get("operation_posted"),
        "operation_released": visit.get("operation_released"),
        "operation_effect_observed": visit.get("operation_effect_observed"),
        "posted_sequence": visit.get("posted_sequence"),
        "posted_turn": visit.get("posted_turn"),
    }


def _alternating_suffix(identities: Sequence[str]) -> int:
    """Length of the longest suffix that alternates between two producers."""
    count = len(identities)
    if count < 2:
        return 0
    length = 1
    index = count - 1
    while index >= 1:
        if identities[index - 1] == identities[index]:
            break
        if index + 1 < count and identities[index - 1] != identities[index + 1]:
            break
        length += 1
        index -= 1
    return length if length >= 2 else 0


def _repeated_suffix(reasons: Sequence[str]) -> int:
    """Length of the longest suffix of one identical reason label."""
    if not reasons:
        return 0
    last = reasons[-1]
    length = 0
    for reason in reversed(reasons):
        if reason != last:
            break
        length += 1
    return length


def classify_stop(
    *,
    kind: str,
    reasons: Sequence[str],
    terminal: Mapping | None = None,
    markers: Sequence[str] = (),
) -> StopShape:
    """Name the shape of one stop.

    ``reasons`` is the driver's ``recent_reasons`` window, oldest first, and
    never holds the driver's own stop label.  ``terminal`` is the last decision
    row the driver wrote before it stopped.  ``markers`` are posting-contract
    markers recorded at the stop.
    """
    window = [reason or "" for reason in reasons]
    identities = [producer_identity(reason) for reason in window]
    row = terminal_evidence(terminal)
    common = {
        "kind": kind,
        "reasons": window,
        "producers": identities,
        "arbiter_owner": row.get("arbiter_owner"),
        "arbiter_producer_owner": row.get("arbiter_producer_owner"),
        "terminal_reason": row.get("reason"),
        "terminal_decision_sequence": row.get("decision_sequence"),
    }

    alternating = _alternating_suffix(identities)
    if alternating >= 2 * ALTERNATION_MIN_CYCLES:
        pair = sorted({*identities[-alternating:]})
        return StopShape(
            SHAPE_OWNERSHIP_ALTERNATION,
            "alternating-producer-suffix",
            {
                **common,
                "alternating_producers": pair,
                "alternating_decisions": alternating,
                "cycles": alternating // 2,
            },
        )

    marker = next((one for one in markers if one in UNOBSERVED_POSTING_MARKERS), None)
    if marker is None and kind in UNOBSERVED_POSTING_MARKERS:
        marker = kind
    clause = row.get("in_flight_clause")
    awaiting = next(
        (
            token
            for token in _AWAITING_REASON_MARKERS
            if token in (row.get("reason") or "")
        ),
        None,
    )
    posted_unobserved = (
        row.get("operation_effect_observed") is False
        and (
            row.get("operation_posted") is True
            or row.get("posted_sequence") is not None
            or row.get("posted_turn") is not None
        )
    )
    if (
        marker is not None
        or clause in IN_FLIGHT_CLAUSES
        or awaiting
        or posted_unobserved
    ):
        return StopShape(
            SHAPE_UNOBSERVED_EFFECT,
            "posted-operation-effect-unobserved",
            {
                **common,
                "posting_marker": marker,
                "in_flight_clause": clause,
                "awaiting_reason_marker": awaiting,
                "posted_sequence": row.get("posted_sequence"),
                "operation_effect_observed": row.get("operation_effect_observed"),
            },
        )

    repeated = _repeated_suffix(window)
    if repeated >= NO_EXIT_MIN_REPEAT:
        return StopShape(
            SHAPE_NO_EXIT,
            "repeated-reason-suffix",
            {
                **common,
                "repeated_reason": window[-1],
                "repeated_decisions": repeated,
                "repeated_producer": identities[-1],
                "arbiter_retired": row.get("arbiter_retired"),
            },
        )

    final_reason = next(
        (
            reason
            for reason in (kind, row.get("reason"), window[-1] if window else None)
            if reason in POLICY_FINAL_STOP_REASONS
        ),
        None,
    )
    if final_reason is not None:
        return StopShape(
            SHAPE_NO_EXIT,
            "policy-declared-final-stop",
            {**common, "final_reason": final_reason},
        )

    if row.get("arbiter_retired") is True:
        return StopShape(
            SHAPE_NO_EXIT,
            "retired-owner-still-holding",
            {**common, "arbiter_retired": True},
        )

    return StopShape(
        SHAPE_OTHER,
        "no-rule-matched",
        {
            **common,
            "alternating_decisions": alternating,
            "repeated_decisions": _repeated_suffix(window),
            "in_flight_clause": clause,
        },
    )
