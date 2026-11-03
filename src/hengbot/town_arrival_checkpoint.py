"""A restorable policy checkpoint at every town arrival (owner 2026-11-03).

The viewing bots run one process for most of a life, so an incident capture's
``policy-state.json`` and decision tail cannot rebuild a town visit: a fresh
policy decides the visit's first board differently.  On the first board of a
fresh visit (``town_visit.is_fresh_visit``, the test that begins the
``TownVisit``), and on the first board a process decides in town (its visit
began in ``prime`` at start-up), this records, under
``<jsonlog>/town-arrival/<visit>/``:

* ``policy.pkl`` - the exact pre-decision checkpoint
  (``latch_onset_capture.checkpoint_bytes``; ``restore_checkpoint_bytes``);
* ``board.json`` - the state line that board was decided on;
* ``arrival.json`` - turn, floor, the decision sequence before the arrival;
* ``journal.jsonl.gz`` - one row per decision of the visit, the arrival
  included: the response lines the CLI delivered to the policy since the
  previous decision (``inputs``), the CLI timer latches and store-screen
  verification it set, the decided state line (``line``; None when it is the
  last input), and what ``choose_key`` returned (``key``, ``reason``,
  ``decision_sequence``).  The decision log's sequence is no row identity:
  a decision answered before ``_choose_key`` keeps the previous one.

Only the newest ``KEEP_VISITS`` visits are kept.  An incident capture copies
the newest visit and the decision-log rows from its arrival on
(``copy_latest_into``); ``tests/replay_town_arrival.py`` replays them.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from hengbot.flight_recorder import jsonable
from hengbot.latch_onset_capture import checkpoint_bytes
from hengbot.town_visit import is_fresh_visit


DIRECTORY = "town-arrival"
KEEP_VISITS = 3
POLICY_FILE = "policy.pkl"
BOARD_FILE = "board.json"
ARRIVAL_FILE = "arrival.json"
JOURNAL_FILE = "journal.jsonl.gz"
DECISIONS_FILE = "decisions.jsonl"
# The latches the CLI's wall-clock timers set on the policy between decisions
# (cli._request_due_dump, cli._request_due_me_powers_refresh).
CLI_LATCHES = (
    "_periodic_dump_requested",
    "_periodic_save_requested",
    "_me_power_refresh_pending",
)
# A visit's journal stops growing past this size (a looping visit is stopped
# long before; the cap only bounds a pathological one).
JOURNAL_LIMIT_BYTES = 64 * 1024**2
_DECISION_SEQUENCE = re.compile(rb'"decision_sequence":\s*(\d+)')


def _warn(operation: str, exc: Exception) -> None:
    print(f"town arrival checkpoint failed to {operation}: {exc}", file=sys.stderr)


def decision_sequence_of(line: bytes) -> int | None:
    """The ``decision_sequence`` of a decision-log row, without parsing it."""
    match = _DECISION_SEQUENCE.search(line)
    return int(match.group(1)) if match else None


class TownArrivalRecorder:
    """Write the arrival checkpoint and the visit's decision journal."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.visit: Path | None = None
        self._inputs: list[str] = []
        self._pending: dict[str, Any] | None = None
        self._first_board = True
        self.last_write_ms: float | None = None

    def take_write_ms(self) -> float | None:
        """The last arrival write's duration, once (the decision's timing)."""
        value, self.last_write_ms = self.last_write_ms, None
        return value

    def note_inputs(self, lines: list[str]) -> None:
        """Response lines the CLI delivers to the policy (an open visit only)."""
        if self.visit is not None:
            self._inputs.extend(line.rstrip("\r\n") for line in lines)

    def before_decision(self, policy, snapshot, line: str, store_screen_verified) -> None:
        """Called just before ``choose_key`` on the board ``line`` encodes."""
        inputs, self._inputs, self._pending = self._inputs, [], None
        first_board, self._first_board = self._first_board, False
        if not snapshot.in_town:
            self.visit = None
            return
        if first_board or is_fresh_visit(policy, snapshot):
            # The arrival's inputs are already inside the checkpoint.
            self._begin(policy, snapshot, line)
            inputs = []
        if self.visit is None:
            return
        self._pending = {
            "inputs": inputs,
            "cli_latches": {name: jsonable(getattr(policy, name, None))
                            for name in CLI_LATCHES},
            "store_screen_verified": store_screen_verified,
            "line": None if inputs and inputs[-1] == line else line,
        }

    def decided(self, policy, key) -> None:
        """Journal what ``choose_key`` just returned on the pending board."""
        row, self._pending = self._pending, None
        if row is None or self.visit is None:
            return
        journal = self.visit / JOURNAL_FILE
        try:
            if journal.exists() and journal.stat().st_size >= JOURNAL_LIMIT_BYTES:
                return
            row = {**row, "key": key, "reason": policy.last_reason,
                   "decision_sequence": policy._decision_sequence}
            with gzip.open(journal, "at", encoding="utf-8", compresslevel=1) as file:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError as exc:
            _warn("append the visit journal", exc)

    def _begin(self, policy, snapshot, line: str) -> None:
        started = time.perf_counter()
        # Names sort by time to the nanosecond: the rotation keeps the last.
        now = time.time_ns()
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now // 10**9))
        visit = self.root / f"{stamp}.{now % 10**9:09d}-turn{snapshot.turn}"
        temporary = self.root / f".{visit.name}.tmp"
        try:
            temporary.mkdir(parents=True)
            (temporary / POLICY_FILE).write_bytes(checkpoint_bytes(policy))
            (temporary / BOARD_FILE).write_text(line, encoding="utf-8")
            arrival = {
                "format": 1,
                "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "turn": snapshot.turn,
                "floor": jsonable(snapshot.floor_key),
                "decision_sequence_before": policy._decision_sequence,
            }
            (temporary / ARRIVAL_FILE).write_text(
                json.dumps(arrival, ensure_ascii=False), encoding="utf-8")
            temporary.rename(visit)
            self.visit = visit
        except Exception as exc:  # a diagnostic never stops the bot (e.g. an unpicklable field)
            _warn("write the arrival checkpoint", exc)
            shutil.rmtree(temporary, ignore_errors=True)
            self.visit = None
            return
        for old in visits(self.root)[:-KEEP_VISITS]:
            shutil.rmtree(old, ignore_errors=True)
        self.last_write_ms = round((time.perf_counter() - started) * 1000, 3)


def visits(root: Path) -> list[Path]:
    """The recorded visits, oldest first (their names start with the time)."""
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.iterdir()
         if path.is_dir() and not path.name.startswith(".")),
        key=lambda path: path.name,
    )


def copy_latest_into(root: Path, capture: Path, decision_tail: bytes) -> str | None:
    """Copy the newest visit and its decision rows into an incident capture.

    Returns the copied visit's name, or None when no visit was recorded.
    ``decision_tail`` is the capture's decision tail; its rows from the
    arrival's decision on become ``decisions.jsonl``.
    """
    found = visits(root)
    if not found:
        return None
    source = found[-1]
    target = capture / DIRECTORY
    def link_or_copy(origin: str, destination: str) -> None:
        # The checkpoint files never change after the arrival: share them.
        # The journal still grows while the visit goes on: copy it.
        if Path(origin).name != JOURNAL_FILE:
            try:
                os.link(origin, destination)
                return
            except OSError:
                pass
        shutil.copy2(origin, destination)

    try:
        shutil.copytree(source, target, copy_function=link_or_copy)
        arrival = json.loads((target / ARRIVAL_FILE).read_text(encoding="utf-8"))
        # Inclusive: the arrival's decision may keep the previous sequence.
        first = int(arrival["decision_sequence_before"])
        with (target / DECISIONS_FILE).open("wb") as file:
            for row in decision_tail.splitlines(keepends=True):
                sequence = decision_sequence_of(row)
                if sequence is not None and sequence >= first:
                    file.write(row)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"town arrival checkpoint failed to copy {source}: {exc}", file=sys.stderr)
    return source.name
