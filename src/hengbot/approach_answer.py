"""The store approach's answer in three kinds: a key, yielded (to whom), or no route.

Whole-bot maintainability review 2026-11-18 (S2, (a)-3; owner 2026-11-09: behaviour-preserving
maintainability work goes ahead): ``ShopMixin._shopping_approach_key`` answers None (or "")
both when it yielded to the town's holder and when it found no way to the store.  Its 41
callers read one empty answer, and the ones that name a stop right after it (blocked,
terminal, unavailable ...) cannot tell the two apart.  c7e2f1a4c1 (n1-a life-530
2026-11-18, ``equipment-transaction:restore-blocked-terminal``) was that misreading: the town
hold had deferred the transaction's own Home approach, and the transaction stopped as if the
Home had no route.

``ShopMixin._shopping_approach_answer`` returns an ``ApproachAnswer``; the old name is a
wrapper that returns its ``key`` exactly as before and remembers the answer for this decision
(``LAST``).  A stop named right after an empty answer calls ``note_stop``: when that answer
was "yielded", the decision log's ``approach_yielded`` names the stop and who held the town.
Record only: no key, no reason and no winner changes here (which side wins is the owner's
question Q2 of the review, not yet answered).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

LAST = "_approach_answer_last"      # (decision sequence, ApproachAnswer, reason, store); record only
NOTES = "_approach_yield_notes"     # (decision sequence, [row]); the decision log's field


class ApproachKind(str, Enum):
    KEY = "key"              # a key to post (a walk, travel, an entry wait, a store operation)
    YIELDED = "yielded"      # the approach stood aside for another owner of the town
    NO_ROUTE = "no-route"    # the approach found no step toward the store


@dataclass(frozen=True)
class ApproachAnswer:
    kind: ApproachKind
    key: str | None          # exactly what the approach returned (None, "" or the key)
    yielded_to: str | None = None   # the holder (family, terminal or owner) when yielded
    holder_claim_id: int | None = None  # the holder's claim when the hold named one


def answered(key) -> ApproachAnswer:
    """The answer of a path that tried to produce a key: a key, or no route when empty."""
    return ApproachAnswer(ApproachKind.KEY if key else ApproachKind.NO_ROUTE, key)


def yielded(key, to: str, holder_claim_id: int | None = None) -> ApproachAnswer:
    """The answer of a path that stood aside for ``to``; a key it still made is a key."""
    if key:
        return ApproachAnswer(ApproachKind.KEY, key)
    return ApproachAnswer(ApproachKind.YIELDED, key, to, holder_claim_id)


def remember(policy, answer: ApproachAnswer, travel_reason: str) -> None:
    """The wrapper's record of the latest answer of this decision (and the route it named)."""
    setattr(policy, LAST, (getattr(policy, "_decision_sequence", None), answer, travel_reason,
                           getattr(policy, "_shopping_approach_store_type", None)))


def latest(policy) -> ApproachAnswer | None:
    """The latest approach answer of this decision, else None."""
    stamp = getattr(policy, LAST, None)
    if stamp is None or stamp[0] != getattr(policy, "_decision_sequence", None):
        return None
    return stamp[1]


def note_stop(policy, stop: str) -> None:
    """A stop named after an empty approach answer: record who held the town when it yielded.

    The answer read is the latest one of this decision (the caller's own approach, or the
    one its producer called before returning empty).  Logging only.
    """
    answer = latest(policy)
    if answer is None or answer.kind is not ApproachKind.YIELDED:
        return
    _sequence, _answer, travel_reason, store_type = getattr(policy, LAST)
    sequence = getattr(policy, "_decision_sequence", None)
    notes = getattr(policy, NOTES, None)
    if notes is None or notes[0] != sequence:
        notes = (sequence, [])
        setattr(policy, NOTES, notes)
    notes[1].append({"stop": stop, "yielded_to": answer.yielded_to,
                     "holder_claim_id": answer.holder_claim_id,
                     "travel_reason": travel_reason, "store_type": store_type})


def report(policy) -> list | None:
    """The decision log's ``approach_yielded`` field of this decision, else None."""
    notes = getattr(policy, NOTES, None)
    if notes is None or notes[0] != getattr(policy, "_decision_sequence", None):
        return None
    return list(notes[1]) or None
