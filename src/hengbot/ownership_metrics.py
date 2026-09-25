"""Session ledger (S0) and per-decision claim ledger (S1).

``SOL-DESIGN-ownership-contract.md`` section 6 stage S0: measure, change
nothing.  The ledger is written beside the decision log as its own file
(``jsonlog/ownership-metrics.jsonl``) because the state log is truncated when
the game relaunches and ``sol-events.jsonl`` is a tracked repository file.
Nothing here is read by the policy or the driver's control flow; the driver
calls it after a decision row is written and when it stops.

One JSON object per line:

``session-start``
    The recorder's own session-start record (``flight_recorder``) with the
    process id and a session id added.  It is not rebuilt here, so the
    decision log and this ledger describe the same start.

``decision-progress``
    A heartbeat: the time and sequence of the last decision row, and the
    running counts.  It exists because the bot is usually killed with
    Stop-Process (the operator skill's stop also quits the game), so a session
    often has no ``session-end`` at all.

``stop``
    The driver's stop: its kind, the classified shape and the evidence that
    decided it (``hengbot.stop_shape``).

``session-end``
    Written on a clean exit only.

Runtime of a session.  **``session-end`` is authoritative when it exists**;
otherwise the runtime is recovered from the last decision row the session
recorded -- the ``decision_time`` of its last ``decision-progress`` or
``stop`` -- and the reader says which of the two it used.  The heartbeat
interval bounds how much of a killed session's runtime can be lost.

The S1 claim ledger is a **sibling file** (``jsonlog/ownership-claims.jsonl``),
not more record kinds in this one.  Why: the file above holds a handful of
records per session (one start, one heartbeat a minute, one stop, one end) and
its reader scans it whole to produce the baseline; the claim ledger holds one
record per *decision*, three orders of magnitude more.  Folding them together
would make the S0 baseline read the whole decision stream, would tie the
rotation of one to the other, and would make a torn high-volume append able to
hide a session record.  Both files are written from the same point -- the
driver, after the decision row it is describing has been written -- and the
report reads both.  Their rate: a claim record is roughly a quarter of a
kilobyte, so an hour of live play at the bot's observed decision rate is under
a megabyte.

``claim``
    One decision's declared claim, copied out of the decision row that
    ``choose_key`` wrote: its id, owner, goal, state, ``closed``, budget and
    measured distance to the goal, plus the row's own reason, key, turn and
    sequence, and ``producer`` -- ``stop_shape.producer_identity`` of the same
    reason.  The producer existed because two of the arbiter's twenty families
    (``misc`` and ``unregistered``) were catch-alls holding every dungeon
    producer, so a family-only breakdown could not see a ``seek-loot`` /
    ``melee`` handoff.  Stage S2a registered those producers, so the two
    answers now coincide on every reason the package can emit; the field stays
    because a reason no registration claims must still be told apart from
    every other such reason.  It is the identity the S0 classifier already
    uses; the claim's own ``owner`` stays one of the families that exist
    today.

Concurrency.  The live bot may be writing its own files while a reader runs,
and a rotation may rename this file between two appends (the precedent is the
decision-log rotation of round 8f2c689): no handle is held between writes,
every write opens in append mode and closes, and a failure is warned about and
dropped rather than raised into the driver.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time

from hengbot.claim_goal_typing import goal_typing, is_survival
from hengbot.claim_ladder import (
    PREEMPTION,
    SURVIVAL_DISPLACED,
    SCOPE_IN,
    SCOPE_S3,
    VIOLATION,
    owner_change,
    pair_scope,
    rung_of,
)
from hengbot.stop_shape import SHAPES, classify_stop, producer_identity
from hengbot.town_arbiter import reason_owner_family


OWNERSHIP_METRICS_NAME = "ownership-metrics.jsonl"
OWNERSHIP_CLAIMS_NAME = "ownership-claims.jsonl"
# Recording cadence only: it bounds how much runtime a killed session can lose
# and changes no decision, key or reason.
PROGRESS_INTERVAL_SECONDS = 60.0

RECORD_SESSION_START = "session-start"
RECORD_DECISION_PROGRESS = "decision-progress"
RECORD_STOP = "stop"
RECORD_SESSION_END = "session-end"
RECORD_CLAIM = "claim"

# How many distinct claimless reasons the session ledger names before it stops
# adding new ones.  It bounds a counter over an unbounded label space; the
# claim ledger itself carries every reason that did declare one.
CLAIMLESS_REASON_LIMIT = 64

RUNTIME_SOURCE_SESSION_END = "session-end"
RUNTIME_SOURCE_LAST_DECISION = "last-decision-row"
RUNTIME_SOURCE_NONE = "none"


class OwnershipMetricsLedger:
    """Append-only session ledger; never raises into the driver."""

    def __init__(
        self,
        path: Path,
        *,
        claims_path: Path | None = None,
        progress_interval_seconds: float = PROGRESS_INTERVAL_SECONDS,
        clock=time.strftime,
        elapsed=time.monotonic,
    ) -> None:
        self.path = Path(path)
        self.claims_path = (
            Path(claims_path)
            if claims_path is not None
            else self.path.with_name(OWNERSHIP_CLAIMS_NAME)
        )
        self.progress_interval_seconds = progress_interval_seconds
        self._clock = clock
        self._elapsed = elapsed
        self._session: str | None = None
        self._decisions = 0
        self._town_decisions = 0
        self._arbiter_owner_changes = 0
        self._last_arbiter_owner: str | None = None
        self._last_decision: Mapping | None = None
        self._last_decision_time: str | None = None
        self._last_decision_sequence = None
        self._last_progress_at: float | None = None
        self._ended = False
        self._claims = 0
        self._last_claim: dict | None = None
        self._implicit_handoffs = 0
        self._handoff_pairs: Counter[str] = Counter()
        self._claimless_reasons: Counter[str] = Counter()
        # S2b.2: decisions whose owner and goal met a standing bar, per owner.
        self._would_bars: Counter[str] = Counter()

    # -- writing ---------------------------------------------------------

    def _time(self) -> str:
        return self._clock("%Y-%m-%dT%H:%M:%S%z")

    def _append(self, record: dict, path: Path | None = None) -> None:
        target = self.path if path is None else path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as file:
                json.dump(record, file, ensure_ascii=False)
                file.write("\n")
        except OSError as exc:
            print(f"ownership metrics ledger: {exc}", file=sys.stderr)

    def _counts(self) -> dict:
        return {
            "decisions": self._decisions,
            "town_decisions": self._town_decisions,
            "arbiter_owner_changes": self._arbiter_owner_changes,
            "claims": self._claims,
            "implicit_handoffs": self._implicit_handoffs,
            "implicit_handoff_pairs": dict(self._handoff_pairs),
            "claimless_reasons": dict(self._claimless_reasons),
            "would_bars": sum(self._would_bars.values()),
            "would_bar_owners": dict(self._would_bars),
            "decision_sequence": self._last_decision_sequence,
            "decision_time": self._last_decision_time,
        }

    def note_session_start(
        self, marker: Mapping | None, *, pid: int | None = None
    ) -> None:
        """Record the start of this bot process from the recorder's own marker."""
        record = dict(marker or {})
        record["kind"] = RECORD_SESSION_START
        record.setdefault("time", self._time())
        record["pid"] = os.getpid() if pid is None else pid
        self._session = f"{record['pid']}-{record['time']}"
        record["session"] = self._session
        self._append(record)

    def _note_claim(self, row: Mapping) -> None:
        """Copy the row's declared claim into the sibling claim ledger."""
        claim = row.get("claim")
        reason = row.get("reason") or ""
        if not isinstance(claim, Mapping) or claim.get("claim_id") is None:
            if len(self._claimless_reasons) < CLAIMLESS_REASON_LIMIT or (
                reason in self._claimless_reasons
            ):
                self._claimless_reasons[reason] += 1
            return
        self._claims += 1
        record = {
            "kind": RECORD_CLAIM,
            "session": self._session,
            "time": row.get("time"),
            "decision_sequence": row.get("decision_sequence"),
            "turn": row.get("turn"),
            "reason": reason,
            "key": row.get("key"),
            "producer": producer_identity(reason),
            # S2a.1: the decision row's own position, so metric (d) can see a
            # Terminal claim that kept its id while the player moved.
            "position": row.get("position"),
            **{
                name: claim.get(name)
                for name in (
                    "claim_id",
                    "owner",
                    "goal",
                    "state",
                    "closed",
                    "closed_reason",
                    "budget",
                    "non_discardable",
                    "distance",
                    "closed_claim",
                    "goal_missing",
                    "goal_note",
                    "survival",
                    # S2b.1 (design rev 10.1): the ladder's record.
                    "rank",
                    "rung",
                    "violation",
                    "resumed",
                    "suspended_closed",
                    "suspended_depth",
                    "trigger_monsters",
                    "last_perceived_turn",
                    # S2b.2 (design 3.2 / 3.3): the bar table's record.
                    "would_bar",
                    "would_skip",
                    "bars_set",
                    "bars_lifted",
                    "bars_active",
                    "bar_skipped",
                )
            },
        }
        would_bar = record.get("would_bar")
        if isinstance(would_bar, Mapping):
            self._would_bars[str(would_bar.get("owner"))] += 1
        if is_implicit_handoff(self._last_claim, record):
            self._implicit_handoffs += 1
            self._handoff_pairs[
                handoff_pair(self._last_claim["owner"], record["owner"])
            ] += 1
        self._last_claim = record
        self._append(record, self.claims_path)

    def note_decision(self, row: Mapping) -> None:
        """Observe one decision row exactly as it was written to the log."""
        self._decisions += 1
        self._note_claim(row)
        arbiter = row.get("arbiter")
        if isinstance(arbiter, Mapping):
            self._town_decisions += 1
            owner = arbiter.get("owner")
            if (
                self._last_arbiter_owner is not None
                and owner != self._last_arbiter_owner
            ):
                self._arbiter_owner_changes += 1
            self._last_arbiter_owner = owner
        else:
            # The arbiter only runs in town and clears itself outside it, so
            # the owner across a dungeon trip is undefined, not changed.
            self._last_arbiter_owner = None
        self._last_decision = row
        self._last_decision_time = row.get("time")
        self._last_decision_sequence = row.get("decision_sequence")
        now = self._elapsed()
        if (
            self._last_progress_at is None
            or now - self._last_progress_at >= self.progress_interval_seconds
        ):
            self._last_progress_at = now
            self._append(
                {
                    "time": self._time(),
                    "kind": RECORD_DECISION_PROGRESS,
                    "session": self._session,
                    "turn": row.get("turn"),
                    **self._counts(),
                }
            )

    def note_stop(
        self,
        kind: str,
        reasons: Sequence[str],
        *,
        markers: Sequence[str] = (),
    ) -> dict:
        """Record and classify the driver's stop; returns the written record."""
        shape = classify_stop(
            kind=kind,
            reasons=list(reasons),
            terminal=self._last_decision,
            markers=list(markers),
        )
        record = {
            "time": self._time(),
            "kind": RECORD_STOP,
            "session": self._session,
            "stop_kind": kind,
            **shape.as_dict(),
            **self._counts(),
        }
        self._append(record)
        return record

    def note_session_end(self, how: str) -> None:
        """Record a clean end.  Only the first call for a session is written."""
        if self._ended:
            return
        self._ended = True
        self._append(
            {
                "time": self._time(),
                "kind": RECORD_SESSION_END,
                "session": self._session,
                "how": how,
                **self._counts(),
            }
        )


# -- the implicit-handoff metric (design 5.2) ----------------------------


def handoff_pair(previous_owner: object, owner: object) -> str:
    """One breakdown key, ``from>to``, JSON keys being strings."""
    return f"{previous_owner}>{owner}"


CLOSURE_TERMINAL_POSTED = "terminal-posted"
CLOSURE_SUSPENDED = "suspended"
GOAL_KINDS_THAT_SPAN = ("Reach", "Observe")


def _goal_kind(row: Mapping) -> str | None:
    goal = row.get("goal")
    return goal.get("kind") if isinstance(goal, Mapping) else None


def _closure_of(previous: Mapping, current: Mapping | None) -> str | None:
    """What ended ``previous``: a closing event, a suspension, or its post.

    A claim can close on its own row (it ran out of budget and was recorded
    ``retired``) or on the row after it -- that row carries the closed claim
    in ``closed_claim``, because arrival, a confirmed effect, a producer's
    release and the survival preemption are all only seen while the *next*
    decision is being made.  S2a.1 (design rev 9.1 item 3) adds two readings:

    * a ``Terminal`` claim completes when its key is posted, so a previous
      row whose goal is Terminal is closed (``terminal-posted``); and
    * a claim the survival preemption suspended is ended explicitly
      (``suspended``) -- design 3.2 keeps its goal, and it is not a drop.

    ``is_implicit_handoff``, ``implicit_handoffs`` and the four gate numbers
    all read this one function, so the live writer and the report agree.
    """
    closed = previous.get("closed")
    if closed:
        return str(closed)
    if current is not None:
        finished = current.get("closed_claim")
        if (
            isinstance(finished, Mapping)
            and finished.get("claim_id") == previous.get("claim_id")
        ):
            if finished.get("closed"):
                return str(finished["closed"])
            if finished.get("state") == CLOSURE_SUSPENDED:
                return CLOSURE_SUSPENDED
    if _goal_kind(previous) == "Terminal":
        return CLOSURE_TERMINAL_POSTED
    return None


def is_implicit_handoff(previous: Mapping | None, current: Mapping) -> bool:
    """Design 5.2: the owner changed and nothing ended the previous claim."""
    if not isinstance(previous, Mapping):
        return False
    if previous.get("session") != current.get("session"):
        return False
    if previous.get("owner") == current.get("owner"):
        return False
    return _closure_of(previous, current) is None


def implicit_handoffs(rows: Sequence[Mapping], *, by: str = "owner") -> dict:
    """Count implicit handoffs over claim rows, in file order.

    ``by`` names the identity compared: ``owner`` is the design's family
    breakdown; ``producer`` refines the two catch-all families by the reason's
    own leading segment (``stop_shape.producer_identity``), which is the only
    way a ``seek-loot`` / ``melee`` handoff is visible at all; ``claim_id``
    counts every unended claim that gave way to another, whatever its family.
    """
    total = 0
    pairs: Counter[str] = Counter()
    previous: Mapping | None = None
    for row in rows:
        if row.get("kind") not in (None, RECORD_CLAIM):
            continue
        if previous is not None and previous.get("session") == row.get("session"):
            changed = previous.get(by) != row.get(by)
            if changed and _closure_of(previous, row) is None:
                total += 1
                pairs[handoff_pair(previous.get(by), row.get(by))] += 1
        previous = row
    return {
        "by": by,
        "rows": sum(
            1 for row in rows if row.get("kind") in (None, RECORD_CLAIM)
        ),
        "implicit_handoffs": total,
        "pairs": dict(pairs.most_common()),
    }


# -- the S2b gate: four numbers (design rev 9.1 item 4) --------------------

ENDING_COMPLETE = "complete"
ENDING_RELEASE = "release"
ENDING_RETIRED = "retired"
# Rev 9.2: an Observe claim older than its ``within`` -- its own ending.
ENDING_EXPIRED = "expired"
ENDING_SUSPENDED = CLOSURE_SUSPENDED
ENDING_ABANDONED = "abandoned"
# A claim still open on the last row of its session: it did not end at all
# inside the ledger, so it is neither closed nor abandoned.
ENDING_OPEN = "open-at-end"
REACH_NOTE_BUCKETS = frozenset({"one-step", "last-known"})
ENDINGS = (
    ENDING_COMPLETE,
    ENDING_RELEASE,
    ENDING_RETIRED,
    ENDING_EXPIRED,
    ENDING_SUSPENDED,
    ENDING_ABANDONED,
    ENDING_OPEN,
)


def row_is_survival(row: Mapping) -> bool:
    """Whether a claim row is survival, by the one survival constant.

    A row written from S2a.1 on carries the policy's own answer (it knows the
    return trigger); an older row is judged by its reason alone, which is the
    same constant without the ``return:`` danger-trigger clause.
    """
    flag = row.get("survival")
    if isinstance(flag, bool):
        return flag
    return is_survival(row.get("reason"))


def _claim_rows_by_session(rows: Iterable[Mapping]) -> list[list[Mapping]]:
    sessions: list[list[Mapping]] = []
    current: list[Mapping] = []
    session = object()
    for row in rows:
        if row.get("kind") not in (None, RECORD_CLAIM):
            continue
        if row.get("session") != session:
            if current:
                sessions.append(current)
            current = []
            session = row.get("session")
        current.append(row)
    if current:
        sessions.append(current)
    return sessions


def _claim_runs(session_rows: Sequence[Mapping]):
    """Consecutive rows sharing one claim id, with the row that follows."""
    start = 0
    while start < len(session_rows):
        claim_id = session_rows[start].get("claim_id")
        end = start
        while (
            end + 1 < len(session_rows)
            and session_rows[end + 1].get("claim_id") == claim_id
        ):
            end += 1
        following = (
            session_rows[end + 1] if end + 1 < len(session_rows) else None
        )
        yield session_rows[start:end + 1], following
        start = end + 1


def _ending(run: Sequence[Mapping], following: Mapping | None) -> str:
    closure = _closure_of(run[-1], following)
    if closure in (ENDING_COMPLETE, ENDING_RELEASE, ENDING_RETIRED, ENDING_EXPIRED):
        return closure
    if closure == CLOSURE_SUSPENDED:
        return ENDING_SUSPENDED
    return ENDING_OPEN if following is None else ENDING_ABANDONED


def _position_of(row: Mapping):
    position = row.get("position")
    if isinstance(position, Mapping):
        return (position.get("y"), position.get("x"))
    return None


def gate_numbers(rows: Sequence[Mapping], *, owner_of=None) -> dict:
    """The four numbers S2b's gate reads (design rev 9.1 item 4).

    (a) ``dropped_by_other_owner``: rows whose owner differs from the previous
        row's while the previous claim was a Reach/Observe claim that nothing
        closed (``_closure_of``), both rows outside survival.
    (b) ``retargets``: the same owner opening a new claim while its previous
        Reach/Observe claim was not closed (the choke retreat that forgot its
        cell), both rows outside survival -- invisible to (a).
    (c) ``endings``: per ``owner/kind``, how each Reach/Observe claim ended --
        complete / release / retired / expired / suspended / abandoned, plus
        ``open-at-end`` for a claim the session's last row still held (a
        Reach goal noted ``one-step`` or ``last-known`` is counted under
        ``owner/Reach:<note>``); S2b.1 (rev 10.1 item 7): one final ending
        per claim id, so a claim suspended and resumed under its id counts
        once, and one that closed while suspended counts that closing -- and
        ``goal_missing`` rows per owner, per reason (``no-slot`` /
        ``owner-mismatch``), and ``owner_mismatch`` rows per owner (every row
        whose producer's slot belonged to another owner, Observe included).
    (d) ``mistyped_terminal``: per owner, Terminal claims that kept one id
        over several rows while the player's position changed (the
        ``fundraise:dig-to-treasure`` shape).  ``declare`` keeps the id while
        owner and goal are unchanged, so no new field is needed beyond the
        row's own position; a multi-row Terminal claim whose rows carry no
        position is counted in ``position_unknown`` instead.  Rev 9.2: rows
        with ``goal_missing`` are excluded -- a Reach row that declared
        Terminal for want of a slot is counted in (c), not here.

    ``owner_of`` re-derives a row's owner (for example the S2a census over a
    ledger written before it); by default the recorded ``owner`` is used.
    """
    owner_of = owner_of or (lambda row: row.get("owner"))
    dropped = 0
    dropped_pairs: Counter[str] = Counter()
    retargets = 0
    retarget_owners: Counter[str] = Counter()
    endings: dict[str, Counter[str]] = {}
    goal_missing: Counter[str] = Counter()
    goal_missing_reasons: Counter[str] = Counter()
    owner_mismatch: Counter[str] = Counter()
    mistyped = 0
    mistyped_owners: Counter[str] = Counter()
    position_unknown = 0
    total = 0
    for session_rows in _claim_rows_by_session(rows):
        total += len(session_rows)
        for row in session_rows:
            if row.get("goal_missing"):
                goal_missing[str(owner_of(row))] += 1
                goal_missing_reasons[str(row.get("goal_note") or "no-slot")] += 1
            if row.get("goal_note") == "owner-mismatch":
                owner_mismatch[str(owner_of(row))] += 1
        for previous, current in zip(session_rows, session_rows[1:]):
            if previous.get("claim_id") == current.get("claim_id"):
                continue
            if _goal_kind(previous) not in GOAL_KINDS_THAT_SPAN:
                continue
            if _closure_of(previous, current) is not None:
                continue
            if row_is_survival(previous) or row_is_survival(current):
                continue
            before, after = owner_of(previous), owner_of(current)
            if before != after:
                dropped += 1
                dropped_pairs[handoff_pair(before, after)] += 1
            else:
                retargets += 1
                retarget_owners[str(before)] += 1
        # S2b.1 (design rev 10.1 item 7): one final ending per claim id.  A
        # resumed claim spans several runs under one id; its earlier runs end
        # ``suspended`` and only its last one counts, unless it closed while
        # suspended (``suspended_closed`` on a later row), which then counts.
        final: dict[object, tuple[str, str]] = {}
        for run, following in _claim_runs(session_rows):
            first = run[0]
            kind = _goal_kind(first)
            owner = str(owner_of(first))
            if kind in GOAL_KINDS_THAT_SPAN:
                # Round 4 (F2): a Reach goal noted ``one-step`` (a flee or
                # least-visited step, a step-off) or ``last-known`` ends in
                # its own bucket, so S2b can tell it from a far-target walk
                # under the same owner (and the same reason).
                note = first.get("goal_note")
                name = (
                    f"{owner}/{kind}:{note}"
                    if kind == "Reach" and note in REACH_NOTE_BUCKETS
                    else f"{owner}/{kind}"
                )
                identity = first.get("claim_id")
                if identity is None:
                    identity = ("run", id(first))
                final.pop(identity, None)
                final[identity] = (name, _ending(run, following))
            elif kind == "Terminal":
                kept = [row for row in run if not row.get("goal_missing")]
                if len(kept) < 2:
                    continue
                positions = [_position_of(row) for row in kept]
                if any(position is None for position in positions):
                    position_unknown += 1
                elif len(set(positions)) > 1:
                    mistyped += 1
                    mistyped_owners[owner] += 1
        for row in session_rows:
            for entry in row.get("suspended_closed") or ():
                if not isinstance(entry, Mapping):
                    continue
                identity = entry.get("claim_id")
                if identity in final and entry.get("closed") in ENDINGS:
                    final[identity] = (final[identity][0], str(entry["closed"]))
        for name, ending in final.values():
            endings.setdefault(name, Counter())[ending] += 1
    return {
        "rows": total,
        "dropped_by_other_owner": {
            "count": dropped,
            "pairs": dict(dropped_pairs.most_common()),
        },
        "retargets": {
            "count": retargets,
            "by_owner": dict(retarget_owners.most_common()),
        },
        "endings": {
            name: {ending: bucket.get(ending, 0) for ending in ENDINGS}
            for name, bucket in sorted(endings.items())
        },
        "goal_missing": dict(goal_missing.most_common()),
        "goal_missing_by_reason": dict(goal_missing_reasons.most_common()),
        "owner_mismatch": dict(owner_mismatch.most_common()),
        "mistyped_terminal": {
            "count": mistyped,
            "by_owner": dict(mistyped_owners.most_common()),
            "position_unknown": position_unknown,
        },
    }


# -- the S2b.1 ladder metric (design rev 10 item 5, rev 10.1 items 7-8, 11) --

PREEMPTION_LABELS = ("preempted-by:", "survival-preemption")


def _family_of_row(row: Mapping) -> str:
    """The census family the live writer would declare for this row now.

    A row written before the ladder carries the family its census gave at
    the time (``misc`` / ``unregistered`` before S2a, ``pickup`` before round
    2); the writer declares ``reason_owner_family(reason)``, so the reader
    re-derives it the same way (rev 10.1 item 11).
    """
    return reason_owner_family(row.get("reason") or "")


def _rung_of_row(row: Mapping):
    return rung_of(
        _family_of_row(row),
        row.get("reason"),
        non_discardable=bool(row.get("non_discardable")),
    )


def classify_handoff(previous: Mapping, current: Mapping) -> dict:
    """Rev 10.1 item 11: the ladder's verdict on one (a)/(b) event of a row
    written before the ladder existed.

    ``previous`` held an open Reach/Observe claim that ``current`` left
    unclosed (``_closure_of`` is ``None``).  The verdict comes from the same
    functions the live writer uses (``claim_ladder.rung_of`` and
    ``owner_change``): the same owner is a retarget violation; another owner
    is a preemption when it ranks strictly higher (and the held claim is not a
    store-operation or transaction ``Observe``), else a violation.
    """
    held = _rung_of_row(previous)
    new = _rung_of_row(current)
    goal = previous.get("goal") if isinstance(previous.get("goal"), Mapping) else {}
    before, after = _family_of_row(previous), _family_of_row(current)
    if before == after:
        verdict, kind = VIOLATION, "retarget"
    else:
        verdict = owner_change(
            held_rank=held.rank,
            held_goal_kind=goal.get("kind"),
            held_goal_source=goal.get("source"),
            held_survival=row_is_survival(previous),
            new_rank=new.rank,
            new_survival=row_is_survival(current),
        )
        kind = "owner-change"
    return {
        "verdict": verdict,
        "kind": kind,
        "from": before,
        "to": after,
        "claim_id": previous.get("claim_id"),
        "from_rank": held.rank,
        "to_rank": new.rank,
        "scope": pair_scope(held, new),
        "survival": row_is_survival(previous) or row_is_survival(current),
    }


def _scoped() -> dict[str, Counter]:
    return {SCOPE_IN: Counter(), SCOPE_S3: Counter(), "survival": Counter()}


def ladder_numbers(rows: Sequence[Mapping]) -> dict:
    """The numbers S2b.1 replaces (a) and (b) with (design rev 10 item 5).

    * ``violations`` by pair, **scoped** (rev 10.1 item 8): ``in-scope``, the
      ``S3`` families (a pair with an S3 rung on either side), and
      ``survival`` (a survival claim on either side -- outside the gate, as
      (a) was);
    * ``retargets`` (retarget violations) by owner, scoped the same way;
    * ``preemptions`` by pair (informational);
    * ``displacements`` by pair -- suspended claims a lower owner displaced,
      also counted in ``violations``;
    * ``survival_displaced`` by pair (round 2) -- claims a survival decision
      that did not outrank them replaced; survival is exempt, so these are
      not violations;
    * ``suspended``: how suspended claims left the stack -- ``resumed`` and
      each closing label (``resume-goal-changed``, ``resume-displaced``,
      ``suspended-expired``, completions).

    Rows the S2b.1 writer wrote (they carry ``rank``) are read as recorded.
    Older rows are reclassified (rev 10.1 item 11), under the census family
    the writer would declare for their reason now: their (a)/(b) events --
    exactly the ones ``gate_numbers`` counts, survival excluded -- go through
    ``classify_handoff``; a suspension they recorded (S2a.1's survival
    preemption) is a preemption.  ``legacy_events`` counts the reclassified
    events.
    """
    violations = _scoped()
    retargets = _scoped()
    preemptions: Counter[str] = Counter()
    displacements: Counter[str] = Counter()
    survival_displaced: Counter[str] = Counter()
    suspended: Counter[str] = Counter()
    legacy = 0

    def count_violation(entry: Mapping) -> None:
        scope = (
            "survival"
            if entry.get("survival")
            else entry.get("scope") if entry.get("scope") in (SCOPE_IN, SCOPE_S3)
            else SCOPE_IN
        )
        if entry.get("kind") == "retarget":
            retargets[scope][str(entry.get("from"))] += 1
        else:
            violations[scope][handoff_pair(entry.get("from"), entry.get("to"))] += 1

    for session_rows in _claim_rows_by_session(rows):
        for previous, current in zip([None, *session_rows], session_rows):
            closed = current.get("closed_claim")
            if (
                isinstance(closed, Mapping)
                and closed.get("state") == CLOSURE_SUSPENDED
                and str(closed.get("closed_reason") or "").startswith(
                    PREEMPTION_LABELS
                )
            ):
                preemptions[handoff_pair(closed.get("owner"), current.get("owner"))] += 1
            if (
                isinstance(closed, Mapping)
                and closed.get("closed_reason") == SURVIVAL_DISPLACED
            ):
                survival_displaced[
                    handoff_pair(closed.get("owner"), current.get("owner"))
                ] += 1
            if current.get("rank") is not None:
                violation = current.get("violation")
                if isinstance(violation, Mapping):
                    count_violation(violation)
                if isinstance(current.get("resumed"), Mapping):
                    suspended["resumed"] += 1
                for entry in current.get("suspended_closed") or ():
                    if not isinstance(entry, Mapping):
                        continue
                    suspended[str(entry.get("closed_reason") or entry.get("closed"))] += 1
                    if entry.get("closed_reason") == SURVIVAL_DISPLACED:
                        survival_displaced[
                            handoff_pair(entry.get("owner"), current.get("owner"))
                        ] += 1
                    displaced = entry.get("violation")
                    if isinstance(displaced, Mapping):
                        displacements[
                            handoff_pair(displaced.get("from"), displaced.get("to"))
                        ] += 1
                        count_violation(displaced)
                continue
            if previous is None:
                continue
            if previous.get("claim_id") == current.get("claim_id"):
                continue
            if _goal_kind(previous) not in GOAL_KINDS_THAT_SPAN:
                continue
            if _closure_of(previous, current) is not None:
                continue
            if row_is_survival(previous) or row_is_survival(current):
                continue
            legacy += 1
            verdict = classify_handoff(previous, current)
            if verdict["verdict"] == PREEMPTION:
                preemptions[handoff_pair(verdict["from"], verdict["to"])] += 1
            elif verdict["verdict"] == SURVIVAL_DISPLACED:
                survival_displaced[handoff_pair(verdict["from"], verdict["to"])] += 1
            else:
                count_violation(verdict)

    def block(counter: Counter) -> dict:
        return {"count": sum(counter.values()), "pairs": dict(counter.most_common())}

    return {
        "violations": {scope: block(counter) for scope, counter in violations.items()},
        "retargets": {
            scope: {"count": sum(counter.values()), "by_owner": dict(counter.most_common())}
            for scope, counter in retargets.items()
        },
        "preemptions": block(preemptions),
        "displacements": block(displacements),
        "survival_displaced": block(survival_displaced),
        "suspended": dict(suspended.most_common()),
        "legacy_events": legacy,
    }


VERDICT_TERMINAL_NOW = "terminal-now"
VERDICT_NESTS = "nests"
VERDICT_HOLDER_UNKNOWN = "holder-unknown"


def rejudge_recorded_violations(rows: Sequence[Mapping]) -> dict:
    """S2b.1b: every violation a ladder-era row recorded, judged again.

    ``ladder_numbers`` reads a row that carries ``rank`` as it was recorded.
    This reads the same rows through today's goal-typing table and
    ``CLAIM_LADDER`` -- the two corrections a reader can see -- and says what
    each recorded violation (on the row, or on a displaced suspended claim)
    would be now:

    * ``terminal-now``: the held claim's reason is typed ``Terminal`` today,
      and a Terminal claim completes when its key is posted;
    * ``preemption``: an owner change whose new rung now ranks strictly above
      the held claim's rung (``claim_ladder.owner_change``);
    * ``nests``: a displacement whose displacer now ranks strictly above the
      suspended claim, so it nests over it instead;
    * ``violation``: still one -- for a missing ``release`` only the writer
      can tell (its pins replay the recorded sequence on synthetic boards);
    * ``holder-unknown``: the held claim's first row is not in ``rows``.

    The held claim is judged by its first row in the session (its reason
    opened it), the taker by the row that recorded the violation.
    """
    before = _scoped()
    after = _scoped()
    verdicts: dict[str, Counter[str]] = {}

    def scope_of(entry: Mapping) -> str:
        if entry.get("survival"):
            return "survival"
        scope = entry.get("scope")
        return scope if scope in (SCOPE_IN, SCOPE_S3) else SCOPE_IN

    def name_of(entry: Mapping) -> str:
        if entry.get("kind") == "retarget":
            return f"retarget:{entry.get('from')}"
        return handoff_pair(entry.get("from"), entry.get("to"))

    for session_rows in _claim_rows_by_session(rows):
        first_row: dict[object, Mapping] = {}
        for row in session_rows:
            first_row.setdefault(row.get("claim_id"), row)
        for row in session_rows:
            if row.get("rank") is None:
                continue
            entries = []
            if isinstance(row.get("violation"), Mapping):
                entries.append(row["violation"])
            for closing in row.get("suspended_closed") or ():
                if isinstance(closing, Mapping) and isinstance(
                    closing.get("violation"), Mapping
                ):
                    entries.append(closing["violation"])
            for entry in entries:
                scope = scope_of(entry)
                name = name_of(entry)
                before[scope][name] += 1
                held_row = first_row.get(entry.get("claim_id"))
                if held_row is None:
                    verdict = VERDICT_HOLDER_UNKNOWN
                else:
                    verdict = _rejudge(entry, held_row, row)
                verdicts.setdefault(verdict, Counter())[f"{scope}:{name}"] += 1
                if verdict in (VIOLATION, VERDICT_HOLDER_UNKNOWN):
                    after[scope][name] += 1

    def block(counter: Counter) -> dict:
        return {"count": sum(counter.values()), "pairs": dict(counter.most_common())}

    return {
        "before": {scope: block(counter) for scope, counter in before.items()},
        "after": {scope: block(counter) for scope, counter in after.items()},
        "verdicts": {
            verdict: block(counter) for verdict, counter in sorted(verdicts.items())
        },
    }


def _spread(values: Sequence[int]) -> dict:
    """Count, min, median and max of a list of non-negative integers."""
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "min": None, "median": None, "max": None}
    middle = len(ordered) // 2
    median = (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / 2
    )
    return {
        "count": len(ordered),
        "min": ordered[0],
        "median": median,
        "max": ordered[-1],
    }


def _bar_identity(entry: Mapping) -> tuple[str, str]:
    """A bar is known by its owner and goal (``ClaimRegister.barring``)."""
    return (
        str(entry.get("owner")),
        json.dumps(entry.get("goal"), sort_keys=True, ensure_ascii=False),
    )


def bar_numbers(rows: Sequence[Mapping]) -> dict:
    """S2b.2 (design 3.2 / 3.3): what the bar table did, and would have done.

    * ``would_bar`` per owner: ``events`` -- decisions whose owner and goal
      met a standing bar (the rows that carry ``would_bar``) -- and
      ``claims``, the distinct claim ids among them;
    * ``bars_set`` per ``owner/kind`` (``threat`` or ``errand``);
    * ``lifetimes`` per owner, of the bars lifted inside the ledger: game
      turns and decisions from ``since`` to the lift (count / min / median /
      max);
    * ``still_barred`` per owner: bars standing on a session's last row,
      with the largest age in game turns there;
    * ``would_skip`` per rung (round 2): decisions of a gated rung made
      while a bar that rung earned stood -- what the switch, which decides
      before the rung runs, would have skipped;
    * ``skipped`` per owner: rungs the bar skipped (only with the switch on).

    A bar set again while it stands (``ClaimRegister.set_bar`` merges it) is
    counted as set once more, and its lifetime runs from its first start.
    """
    events: Counter[str] = Counter()
    claims: dict[str, set] = {}
    bars_set: Counter[str] = Counter()
    turns: dict[str, list] = {}
    decisions: dict[str, list] = {}
    still: dict[str, list] = {}
    skipped: Counter[str] = Counter()
    would_skip: Counter[str] = Counter()
    for session_rows in _claim_rows_by_session(rows):
        standing: dict[tuple[str, str], Mapping] = {}
        for row in session_rows:
            for entry in row.get("bars_lifted") or ():
                if not isinstance(entry, Mapping):
                    continue
                owner = str(entry.get("owner"))
                since = standing.pop(_bar_identity(entry), entry)
                start_turn = since.get("since_turn")
                start_sequence = since.get("since_sequence")
                if isinstance(start_turn, int) and isinstance(
                    entry.get("lifted_turn"), int
                ):
                    turns.setdefault(owner, []).append(
                        entry["lifted_turn"] - start_turn
                    )
                if isinstance(start_sequence, int) and isinstance(
                    entry.get("lifted_sequence"), int
                ):
                    decisions.setdefault(owner, []).append(
                        entry["lifted_sequence"] - start_sequence
                    )
            would_bar = row.get("would_bar")
            if isinstance(would_bar, Mapping):
                owner = str(would_bar.get("owner"))
                events[owner] += 1
                claims.setdefault(owner, set()).add(row.get("claim_id"))
            if isinstance(row.get("would_skip"), Mapping):
                would_skip[str(row["would_skip"].get("rung"))] += 1
            for entry in row.get("bars_set") or ():
                if not isinstance(entry, Mapping):
                    continue
                bars_set[f"{entry.get('owner')}/{entry.get('kind')}"] += 1
                standing.setdefault(_bar_identity(entry), entry)
            for entry in row.get("bar_skipped") or ():
                if isinstance(entry, Mapping):
                    skipped[str(entry.get("owner"))] += 1
        last_turn = session_rows[-1].get("turn") if session_rows else None
        for entry in standing.values():
            start = entry.get("since_turn")
            age = (
                last_turn - start
                if isinstance(last_turn, int) and isinstance(start, int)
                else None
            )
            still.setdefault(str(entry.get("owner")), []).append(age)
    owners = sorted({*events, *turns, *decisions})
    return {
        "would_bar": {
            "count": sum(events.values()),
            "by_owner": {
                owner: {"events": events[owner], "claims": len(claims[owner])}
                for owner, _count in events.most_common()
            },
        },
        "bars_set": {
            "count": sum(bars_set.values()),
            "by_owner_kind": dict(bars_set.most_common()),
        },
        "lifetimes": {
            owner: {
                "turns": _spread(turns.get(owner, [])),
                "decisions": _spread(decisions.get(owner, [])),
            }
            for owner in owners
            if turns.get(owner) or decisions.get(owner)
        },
        "still_barred": {
            owner: {
                "count": len(ages),
                "max_age_turns": max(
                    (age for age in ages if age is not None), default=None
                ),
            }
            for owner, ages in sorted(still.items())
        },
        "would_skip": {
            "count": sum(would_skip.values()),
            "by_rung": dict(would_skip.most_common()),
        },
        "skipped": {
            "count": sum(skipped.values()),
            "by_owner": dict(skipped.most_common()),
        },
    }


def _rejudge(entry: Mapping, held_row: Mapping, row: Mapping) -> str:
    held_family = _family_of_row(held_row)
    typing = goal_typing(held_family, held_row.get("reason"))
    if typing is not None and typing.kind == "Terminal":
        return VERDICT_TERMINAL_NOW
    if entry.get("kind") == "retarget":
        return VIOLATION
    held = rung_of(
        held_family,
        held_row.get("reason"),
        non_discardable=bool(held_row.get("non_discardable")),
    )
    new = _rung_of_row(row)
    if entry.get("kind") == "displaced":
        return VERDICT_NESTS if new.rank < held.rank else VIOLATION
    goal = entry.get("goal") if isinstance(entry.get("goal"), Mapping) else {}
    return owner_change(
        held_rank=held.rank,
        held_goal_kind=goal.get("kind"),
        held_goal_source=goal.get("source"),
        held_survival=row_is_survival(held_row),
        new_rank=new.rank,
        new_survival=row_is_survival(row),
    )


# -- reading -------------------------------------------------------------


def read_records(path: Path) -> list[dict]:
    """Every intact record of a ledger, in file order.

    A torn last line (the live bot appending while a reader reads) is skipped
    rather than raised.
    """
    records: list[dict] = []
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return records
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _parsed_time(value: object) -> float | None:
    """Seconds since the epoch for a recorded timestamp, offset honoured."""
    if not isinstance(value, str) or not value:
        return None
    for pattern in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            stamp = datetime.strptime(value, pattern)
        except ValueError:
            continue
        return stamp.timestamp()
    return None


def summarise_sessions(records: Iterable[Mapping]) -> list[dict]:
    """One summary per session, in the order the sessions start.

    ``runtime_source`` names which end of the session the runtime came from:
    ``session-end`` when the session ended cleanly (authoritative), otherwise
    ``last-decision-row`` -- the last decision row the session recorded, which
    is all a killed process leaves behind -- or ``none`` when the session
    recorded no decision at all.
    """
    sessions: dict[str, dict] = {}
    order: list[str] = []

    def bucket(session: object) -> dict:
        key = session if isinstance(session, str) and session else "<unknown>"
        if key not in sessions:
            order.append(key)
            sessions[key] = {
                "session": key,
                "pid": None,
                "git_commit": None,
                "start_time": None,
                "end_time": None,
                "end_how": None,
                "last_decision_time": None,
                "last_decision_sequence": None,
                "decisions": 0,
                "town_decisions": 0,
                "arbiter_owner_changes": 0,
                "claims": 0,
                "implicit_handoffs": 0,
                "stops": [],
            }
        return sessions[key]

    for record in records:
        kind = record.get("kind")
        entry = bucket(record.get("session"))
        if kind == RECORD_SESSION_START:
            entry["start_time"] = record.get("time")
            entry["pid"] = record.get("pid")
            entry["git_commit"] = record.get("git_commit")
            continue
        for name in (
            "decisions",
            "town_decisions",
            "arbiter_owner_changes",
            "claims",
            "implicit_handoffs",
        ):
            value = record.get(name)
            if isinstance(value, int):
                entry[name] = max(entry[name], value)
        if record.get("decision_time"):
            entry["last_decision_time"] = record["decision_time"]
            entry["last_decision_sequence"] = record.get("decision_sequence")
        if kind == RECORD_STOP:
            entry["stops"].append(
                {
                    "time": record.get("time"),
                    "stop_kind": record.get("stop_kind"),
                    "shape": record.get("shape"),
                    "rule": record.get("rule"),
                }
            )
        elif kind == RECORD_SESSION_END:
            entry["end_time"] = record.get("time")
            entry["end_how"] = record.get("how")

    summaries = []
    for key in order:
        entry = sessions[key]
        start = _parsed_time(entry["start_time"])
        if entry["end_time"]:
            source = RUNTIME_SOURCE_SESSION_END
            end = _parsed_time(entry["end_time"])
        elif entry["last_decision_time"]:
            source = RUNTIME_SOURCE_LAST_DECISION
            end = _parsed_time(entry["last_decision_time"])
        else:
            source = RUNTIME_SOURCE_NONE
            end = None
        runtime = None
        if start is not None and end is not None and end >= start:
            runtime = end - start
        entry["runtime_source"] = source
        entry["runtime_seconds"] = runtime
        summaries.append(entry)
    return summaries


def aggregate(summaries: Sequence[Mapping]) -> dict:
    """Totals across sessions: runtime, stops per shape, owner changes."""
    runtime = sum(
        summary["runtime_seconds"] or 0.0 for summary in summaries
    )
    shapes = {shape: 0 for shape in SHAPES}
    for summary in summaries:
        for stop in summary["stops"]:
            shape = stop.get("shape")
            shapes[shape] = shapes.get(shape, 0) + 1
    hours = runtime / 3600.0
    decisions = sum(summary["decisions"] for summary in summaries)
    town = sum(summary["town_decisions"] for summary in summaries)
    changes = sum(summary["arbiter_owner_changes"] for summary in summaries)
    claims = sum(summary["claims"] for summary in summaries)
    handoffs = sum(summary["implicit_handoffs"] for summary in summaries)
    sources: dict[str, int] = {}
    for summary in summaries:
        sources[summary["runtime_source"]] = (
            sources.get(summary["runtime_source"], 0) + 1
        )
    return {
        "sessions": len(summaries),
        "runtime_seconds": runtime,
        "runtime_hours": hours,
        "runtime_sources": sources,
        "decisions": decisions,
        "town_decisions": town,
        "arbiter_owner_changes": changes,
        "claims": claims,
        "claim_share": claims / decisions if decisions else None,
        "implicit_handoffs": handoffs,
        "implicit_handoffs_per_hour": handoffs / hours if hours > 0 else None,
        "stops": dict(shapes),
        "stops_total": sum(shapes.values()),
        "stops_per_hour": (
            {shape: count / hours for shape, count in shapes.items()}
            if hours > 0
            else None
        ),
        "arbiter_owner_changes_per_hour": changes / hours if hours > 0 else None,
    }
