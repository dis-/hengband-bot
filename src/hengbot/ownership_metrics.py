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

from hengbot.stop_shape import SHAPES, classify_stop, producer_identity


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
            **{
                name: claim.get(name)
                for name in (
                    "claim_id",
                    "owner",
                    "goal",
                    "state",
                    "closed",
                    "budget",
                    "non_discardable",
                    "distance",
                    "closed_claim",
                )
            },
        }
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


def _closure_of(previous: Mapping, current: Mapping | None) -> str | None:
    """The ``release``/``complete``/``retired`` that ended ``previous``.

    A claim can close on its own row (it ran out of budget and was recorded
    ``retired``) or on the row that observes its goal reached -- that row
    carries the closed claim in ``closed_claim``, because arrival is only
    visible on the board after the step.  Both count as explicit.
    """
    closed = previous.get("closed")
    if closed:
        return str(closed)
    if current is None:
        return None
    finished = current.get("closed_claim")
    if (
        isinstance(finished, Mapping)
        and finished.get("claim_id") == previous.get("claim_id")
        and finished.get("closed")
    ):
        return str(finished["closed"])
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
