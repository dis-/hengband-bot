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

Owner 2026-11-18 (review Q2, 「先の用事を待って続ける」): 「『道が無い』とは扱わず、先の用事が終わる
のを待ってから続ける。決まった回数待っても空かなければ、誰を待っていたかを名前に入れて止まる。」
The call sites that named a stop right after an empty answer ask ``after_empty`` instead.  A
yield is no stop: the site answers nothing this board (the holder, the earlier errand, takes
it) and counts the board against its holder (``WAITS``, one count per site and holder: the
holder's family and its claim, this visit).  Once ``WAIT_LIMIT`` yielded boards pass for one
holder, the site stops under ``WAIT_STOP_PREFIX`` + ``<stop>:waiting-for:<holder>``.  A holder
that finishes leaves its claim: the next yield at the site (to another holder or claim) starts
again, as does a new visit.  A key at the site does not end the count: a wait that steps off
the entrance and walks back each lap (the c7e2f1a4c1 case with its opening taken back) answers
a key every other board and would otherwise never reach the bound.  No route keeps today's
stop.  A mutual wait (the holder itself proceeds only through this site) cannot resolve: the
pair seen so far (the equipment transaction and the Home errand's take, c7e2f1a4c1) stays open
in town_hold.home_route_opened_for, and the bound turns any other into the named stop.  The
waits are in town, where the cell loop guard does not look (cli._cell_loop_guard_applies), so
no stationary reason is registered for them.
The two equipment ``home-approach-unavailable`` no-steps were never stops (they answer
nothing already) and keep recording only (``note_stop``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

LAST = "_approach_answer_last"      # (decision sequence, ApproachAnswer, reason, store); record only
NOTES = "_approach_yield_notes"     # (decision sequence, [row]); the decision log's field
WAITS = "_approach_yield_waits"     # {(site, holder, claim): (yielded boards, decision seq)}; visit

# Yielded boards one site waits for one holder (one claim) before its named stop.  A holder's
# errand is bounded by the town stage deadlines (town_visit_plan.STAGE_DEADLINES: at most 22
# operations without progress outside departure) and its walks are native travel legs of a
# board or a few each; a site waits on every board of that errand, store pages included.  60
# boards is twice the town block fuse (cli.TOWN_BLOCKED_STOP_LIMIT, 30) and covers a Home
# errand plus the equipment stage (22 + 18 operations) with its walks, so a holder that makes
# progress finishes inside it, and a wait nobody can end is named within one fuse's length more.
WAIT_LIMIT = 60
WAIT_STOP_PREFIX = "town:blocked:approach-yielded:"
WAIT = "wait"                       # after_empty's verdict: answer nothing this board


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


def answer_stamp(policy):
    """The approach record before a call (pass it to ``since`` after the call)."""
    return getattr(policy, LAST, None)


def since(policy, before) -> ApproachAnswer | None:
    """The latest answer of this decision if an approach answered after ``answer_stamp``, else None."""
    stamp = getattr(policy, LAST, None)
    return None if stamp is before else latest(policy)


def note_stop(policy, stop: str) -> None:
    """A stop named after an empty approach answer: record who held the town when it yielded.

    The answer read is the latest one of this decision (the caller's own approach, or the
    one its producer called before returning empty).  Logging only.
    """
    answer = latest(policy)
    if answer is None or answer.kind is not ApproachKind.YIELDED:
        return
    _note(policy, stop, answer)


def _note(policy, stop: str, answer: ApproachAnswer, **extra) -> None:
    """Append this decision's ``approach_yielded`` row for a yield read at ``stop``."""
    _sequence, _answer, travel_reason, store_type = getattr(policy, LAST)
    sequence = getattr(policy, "_decision_sequence", None)
    notes = getattr(policy, NOTES, None)
    if notes is None or notes[0] != sequence:
        notes = (sequence, [])
        setattr(policy, NOTES, notes)
    notes[1].append({"stop": stop, "yielded_to": answer.yielded_to,
                     "holder_claim_id": answer.holder_claim_id,
                     "travel_reason": travel_reason, "store_type": store_type, **extra})


def report(policy) -> list | None:
    """The decision log's ``approach_yielded`` field of this decision, else None."""
    notes = getattr(policy, NOTES, None)
    if notes is None or notes[0] != getattr(policy, "_decision_sequence", None):
        return None
    return list(notes[1]) or None


def holder_name(answer: ApproachAnswer) -> str:
    """Who a yielded answer waits for: the town hold's holder family, else the yield's name."""
    to = answer.yielded_to or "unknown"
    return to[len("town-hold:"):] if to.startswith("town-hold:") else to


def stop_name(stop: str, holder: str) -> str:
    """The named stop of a wait that did not end (owner 2026-11-18 Q2)."""
    return f"{WAIT_STOP_PREFIX}{stop}:waiting-for:{holder}"


def forget_visit(policy) -> None:
    """The town visit began or ended: no wait carries over."""
    if getattr(policy, WAITS, None):
        setattr(policy, WAITS, {})


def after_empty(policy, site: str, answer: ApproachAnswer | None) -> str | None:
    """The verdict at a site that names the stop ``site`` after an empty approach answer.

    ``answer`` is the site's own approach answer of this decision (``latest`` right after the
    call), or None when the site called no approach.  None: not a yield, the site stops as
    before.  ``WAIT``: the approach yielded; the site answers nothing this board so the holder
    proceeds.  Otherwise the named stop (``stop_name``) after ``WAIT_LIMIT`` yielded boards.
    The decision log's ``approach_yielded`` row carries the count and the verdict.
    """
    if answer is None or answer.kind is not ApproachKind.YIELDED:
        return None
    holder = holder_name(answer)
    waits = getattr(policy, WAITS, None)
    if waits is None:
        waits = {}
        setattr(policy, WAITS, waits)
    entry = (site, holder, answer.holder_claim_id)
    for other in [other for other in waits if other[0] == site and other != entry]:
        del waits[other]    # another holder or claim: the earlier one's wait ended
    sequence = getattr(policy, "_decision_sequence", None)
    count, stamp = waits.get(entry, (0, None))
    if stamp is None or stamp != sequence:
        count += 1
    waits[entry] = (count, sequence)
    verdict = WAIT if count < WAIT_LIMIT else stop_name(site, holder)
    _note(policy, site, answer, waited=count, verdict=verdict)
    return verdict
