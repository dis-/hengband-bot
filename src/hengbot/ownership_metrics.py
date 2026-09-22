"""Session ledger for the ownership-contract S0 measurement.

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

Concurrency.  The live bot may be writing its own files while a reader runs,
and a rotation may rename this file between two appends (the precedent is the
decision-log rotation of round 8f2c689): no handle is held between writes,
every write opens in append mode and closes, and a failure is warned about and
dropped rather than raised into the driver.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time

from hengbot.stop_shape import SHAPES, classify_stop


OWNERSHIP_METRICS_NAME = "ownership-metrics.jsonl"
# Recording cadence only: it bounds how much runtime a killed session can lose
# and changes no decision, key or reason.
PROGRESS_INTERVAL_SECONDS = 60.0

RECORD_SESSION_START = "session-start"
RECORD_DECISION_PROGRESS = "decision-progress"
RECORD_STOP = "stop"
RECORD_SESSION_END = "session-end"

RUNTIME_SOURCE_SESSION_END = "session-end"
RUNTIME_SOURCE_LAST_DECISION = "last-decision-row"
RUNTIME_SOURCE_NONE = "none"


class OwnershipMetricsLedger:
    """Append-only session ledger; never raises into the driver."""

    def __init__(
        self,
        path: Path,
        *,
        progress_interval_seconds: float = PROGRESS_INTERVAL_SECONDS,
        clock=time.strftime,
        elapsed=time.monotonic,
    ) -> None:
        self.path = Path(path)
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

    # -- writing ---------------------------------------------------------

    def _time(self) -> str:
        return self._clock("%Y-%m-%dT%H:%M:%S%z")

    def _append(self, record: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as file:
                json.dump(record, file, ensure_ascii=False)
                file.write("\n")
        except OSError as exc:
            print(f"ownership metrics ledger: {exc}", file=sys.stderr)

    def _counts(self) -> dict:
        return {
            "decisions": self._decisions,
            "town_decisions": self._town_decisions,
            "arbiter_owner_changes": self._arbiter_owner_changes,
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

    def note_decision(self, row: Mapping) -> None:
        """Observe one decision row exactly as it was written to the log."""
        self._decisions += 1
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
        for name in ("decisions", "town_decisions", "arbiter_owner_changes"):
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
        "stops": dict(shapes),
        "stops_total": sum(shapes.values()),
        "stops_per_hour": (
            {shape: count / hours for shape, count in shapes.items()}
            if hours > 0
            else None
        ),
        "arbiter_owner_changes_per_hour": changes / hours if hours > 0 else None,
    }
