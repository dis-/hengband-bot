"""The S0 ownership metrics ledger, its reader, and its neutrality.

``SOL-DESIGN-ownership-contract.md`` section 6 stage S0 is measurement only:
the ledger records and classifies, and no decision, key or reason may change
because it exists.  The pins here are:

M2  a session that was killed (Stop-Process, the ordinary way this bot ends)
    has no ``session-end``; its runtime must still be recoverable from the
    last decision row it recorded, and the reader must say that is where the
    runtime came from.  When both exist, ``session-end`` wins.
M3  behaviour neutrality: a recorded replay driven through
    ``cli._write_decision`` produces the same decision rows, byte for byte in
    key and reason, with the ledger attached and without it.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import tests  # noqa: F401  (bare runs stay isolated from runtime files)
from hengbot import cli
from hengbot.flight_recorder import append_session_marker
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.ownership_metrics import (
    OWNERSHIP_METRICS_NAME,
    RUNTIME_SOURCE_LAST_DECISION,
    RUNTIME_SOURCE_NONE,
    RUNTIME_SOURCE_SESSION_END,
    OwnershipMetricsLedger,
    aggregate,
    read_records,
    summarise_sessions,
)
from hengbot.policy import HengbotPolicy
from tests.run_follow_hygiene import run_follow

import ownership_metrics_report


ROOT = Path(__file__).resolve().parents[1]
EDIT = Path("C:/hengband/lib/edit")
REPLAY_FIXTURE = (
    ROOT / "tests" / "fixtures" / "calibration-visit-blocked-loop-20260923.jsonl.gz"
)


class _FakeClock:
    """Wall clock and monotonic clock the ledger can be driven with."""

    def __init__(self, start: int = 0) -> None:
        self.seconds = start

    def strftime(self, _pattern: str) -> str:
        minutes, secs = divmod(self.seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"2026-09-23T{hours:02d}:{minutes:02d}:{secs:02d}+0900"

    def monotonic(self) -> float:
        return float(self.seconds)

    def advance(self, seconds: int) -> None:
        self.seconds += seconds


def _row(sequence: int, when: str, *, owner: str | None = None, **extra) -> dict:
    row = {
        "time": when,
        "decision_sequence": sequence,
        "turn": 1000 + sequence,
        "reason": extra.pop("reason", "explore"),
        "key": extra.pop("key", "6"),
    }
    if owner is not None:
        row["arbiter"] = {"owner": owner, "producer_owner": owner}
    row.update(extra)
    return row


class LedgerWritingTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(
            tempfile.mkdtemp(prefix="hengbot-ownership-ledger-")
        )
        self.path = self.root / OWNERSHIP_METRICS_NAME
        self.clock = _FakeClock()

    def _ledger(self, **kwargs) -> OwnershipMetricsLedger:
        return OwnershipMetricsLedger(
            self.path,
            clock=self.clock.strftime,
            elapsed=self.clock.monotonic,
            **kwargs,
        )

    def test_session_start_reuses_the_recorders_own_record(self):
        """One start, described once: the ledger does not build its own."""
        decision_log = self.root / "bot-decisions.jsonl"
        marker = append_session_marker(decision_log, ["bot", "--live"])
        ledger = self._ledger()
        ledger.note_session_start(marker, pid=4242)
        logged = json.loads(decision_log.read_text(encoding="utf-8").strip())
        written = read_records(self.path)[0]
        self.assertEqual(logged["kind"], "session-start")
        for field in ("time", "argv", "git_commit"):
            self.assertEqual(written[field], logged[field])
        self.assertEqual(written["pid"], 4242)
        self.assertEqual(written["session"], f"4242-{logged['time']}")

    def test_the_first_decision_and_the_interval_write_progress(self):
        ledger = self._ledger(progress_interval_seconds=60.0)
        ledger.note_session_start({"time": self.clock.strftime("")}, pid=7)
        ledger.note_decision(_row(1, "2026-09-23T00:00:01+0900"))
        self.clock.advance(30)
        ledger.note_decision(_row(2, "2026-09-23T00:00:31+0900"))
        self.clock.advance(30)
        ledger.note_decision(_row(3, "2026-09-23T00:01:01+0900"))
        progress = [
            record
            for record in read_records(self.path)
            if record["kind"] == "decision-progress"
        ]
        self.assertEqual(len(progress), 2)
        self.assertEqual(
            [record["decision_sequence"] for record in progress], [1, 3]
        )
        self.assertEqual(progress[-1]["decisions"], 3)

    def test_owner_changes_count_consecutive_town_rows_only(self):
        """A dungeon trip is an undefined owner, not a change of one."""
        ledger = self._ledger(progress_interval_seconds=1e9)
        ledger.note_session_start({"time": self.clock.strftime("")}, pid=7)
        ledger.note_decision(_row(1, "t", owner="town-plan"))
        ledger.note_decision(_row(2, "t", owner="town-plan"))
        ledger.note_decision(_row(3, "t", owner="store-router"))  # a change
        ledger.note_decision(_row(4, "t"))  # dungeon: no arbiter at all
        ledger.note_decision(_row(5, "t", owner="home-visit"))  # not a change
        ledger.note_decision(_row(6, "t", owner="town-plan"))  # a change
        record = ledger.note_stop("loop-detected", ["explore"] * 20)
        self.assertEqual(record["arbiter_owner_changes"], 2)
        self.assertEqual(record["decisions"], 6)
        self.assertEqual(record["town_decisions"], 5)

    def test_a_rename_between_writes_is_tolerated(self):
        """Rotation precedent (round 8f2c689): no handle is held between writes."""
        ledger = self._ledger(progress_interval_seconds=0.0)
        ledger.note_session_start({"time": self.clock.strftime("")}, pid=7)
        ledger.note_decision(_row(1, "t"))
        self.path.rename(self.path.with_suffix(".jsonl.1"))
        ledger.note_decision(_row(2, "t"))
        ledger.note_session_end("process-exit")
        self.assertTrue(self.path.exists())
        kinds = [record["kind"] for record in read_records(self.path)]
        self.assertEqual(kinds, ["decision-progress", "session-end"])

    def test_a_failing_ledger_never_raises_into_the_driver(self):
        blocker = self.root / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        ledger = OwnershipMetricsLedger(
            blocker / "nested" / OWNERSHIP_METRICS_NAME,
            clock=self.clock.strftime,
            elapsed=self.clock.monotonic,
        )
        ledger.note_session_start({"time": "t"}, pid=7)
        ledger.note_decision(_row(1, "t"))
        ledger.note_stop("loop-detected", ["explore"] * 20)
        ledger.note_session_end("process-exit")

    def test_session_end_is_written_once(self):
        ledger = self._ledger(progress_interval_seconds=1e9)
        ledger.note_session_start({"time": self.clock.strftime("")}, pid=7)
        ledger.note_session_end("incident-stop:loop-detected")
        ledger.note_session_end("process-exit")
        ends = [
            record for record in read_records(self.path)
            if record["kind"] == "session-end"
        ]
        self.assertEqual([record["how"] for record in ends],
                         ["incident-stop:loop-detected"])


class RuntimeRecoveryTest(unittest.TestCase):
    """M2: a killed session still yields a runtime, and the reader says how."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="hengbot-ownership-runtime-"))
        self.path = self.root / OWNERSHIP_METRICS_NAME

    def _session(self, pid: int, start: int, *, decisions, end=None):
        clock = _FakeClock(start)
        ledger = OwnershipMetricsLedger(
            self.path,
            progress_interval_seconds=0.0,
            clock=clock.strftime,
            elapsed=clock.monotonic,
        )
        ledger.note_session_start({"time": clock.strftime("")}, pid=pid)
        for index, offset in enumerate(decisions, start=1):
            clock.advance(offset)
            ledger.note_decision(_row(index, clock.strftime(""), owner="town-plan"))
        if end is not None:
            clock.advance(end)
            ledger.note_stop("loop-detected", ["town:blocked:x"] * 20)
            ledger.note_session_end("incident-stop:loop-detected")
        return ledger

    def test_a_killed_session_is_measured_from_its_last_decision_row(self):
        self._session(11, 0, decisions=[600, 600, 600])  # killed: no end
        summary = summarise_sessions(read_records(self.path))[0]
        self.assertEqual(summary["runtime_source"], RUNTIME_SOURCE_LAST_DECISION)
        self.assertEqual(summary["runtime_seconds"], 1800.0)
        self.assertEqual(summary["last_decision_sequence"], 3)
        self.assertIsNone(summary["end_time"])

    def test_session_end_wins_when_both_are_present(self):
        self._session(12, 0, decisions=[600], end=600)
        summary = summarise_sessions(read_records(self.path))[0]
        self.assertEqual(summary["runtime_source"], RUNTIME_SOURCE_SESSION_END)
        self.assertEqual(summary["runtime_seconds"], 1200.0)
        self.assertGreater(summary["runtime_seconds"], 600.0)  # past the last row

    def test_a_session_with_no_decision_contributes_no_runtime(self):
        clock = _FakeClock(0)
        ledger = OwnershipMetricsLedger(
            self.path, clock=clock.strftime, elapsed=clock.monotonic
        )
        ledger.note_session_start({"time": clock.strftime("")}, pid=13)
        summary = summarise_sessions(read_records(self.path))[0]
        self.assertEqual(summary["runtime_source"], RUNTIME_SOURCE_NONE)
        self.assertIsNone(summary["runtime_seconds"])

    def test_stops_per_runtime_hour_is_read_off_the_ledger(self):
        self._session(21, 0, decisions=[900], end=900)  # 30 minutes, one stop
        self._session(22, 10_000, decisions=[900], end=900)  # another 30 min
        totals = aggregate(summarise_sessions(read_records(self.path)))
        self.assertEqual(totals["sessions"], 2)
        self.assertEqual(totals["runtime_seconds"], 3600.0)
        self.assertEqual(totals["stops_total"], 2)
        self.assertEqual(totals["stops_per_hour"]["no-exit"], 2.0)
        self.assertEqual(totals["stops_per_hour"]["ownership-alternation"], 0.0)


def _snapshot_line(turn: int) -> str:
    return json.dumps(
        {
            "turn": turn,
            "player": {"y": 5, "x": 5, "hp": 10, "max_hp": 10},
            "floor": {"dungeon_id": 0, "level": 1},
        }
    ) + "\n"


class DriverWiringTest(unittest.TestCase):
    """The driver really reaches the ledger: one follow run, one stop.

    The ledger is created in ``main`` and used in ``_run_follow``, which is a
    different function; this drives the real follow loop so the two ends stay
    connected.
    """

    def test_a_policy_declared_final_stop_is_recorded_as_no_exit(self):
        final_reason = "equipment-transaction:restore-blocked-terminal"
        with tempfile.TemporaryDirectory(prefix="hengbot-ownership-follow-") as raw:
            root = Path(raw)
            state = root / "state.jsonl"
            state.write_text(_snapshot_line(1), encoding="utf-8")
            args = cli._build_argument_parser().parse_args([
                "--state-file", str(state),
                "--decision-log", str(root / "bot-decisions.jsonl"),
                "--poll-interval", "0.001",
                "--stall-timeout", "0.01",
                "--send-to-window",
            ])
            args.wait_telemetry = Mock()
            ledger = OwnershipMetricsLedger(root / OWNERSHIP_METRICS_NAME)
            ledger.note_session_start({"time": "2026-09-23T06:00:00+0900"}, pid=99)
            args.ownership_ledger = ledger
            policy = HengbotPolicy()

            def choose(_snapshot):
                policy.last_reason = final_reason
                return "5"

            policy.choose_key = Mock(side_effect=choose)
            # The follow loop seeks to EOF, so its one decision needs a board
            # appended from inside the loop (the pattern of test_cli).
            appended = False

            def append_one_snapshot():
                nonlocal appended
                if appended:
                    return
                appended = True
                with state.open("a", encoding="utf-8") as stream:
                    stream.write(_snapshot_line(2))
                    stream.flush()

            with (
                patch("hengbot.cli._arm_decision_watchdog",
                      side_effect=append_one_snapshot),
                patch("hengbot.cli._append_capture_ledger"),
                patch("hengbot.cli._freeze_incident_safely"),
            ):
                result = run_follow(
                    args, policy, lambda *_a, **_k: True, {}
                )

            self.assertEqual(result, 0)
            records = read_records(root / OWNERSHIP_METRICS_NAME)
            kinds = [record["kind"] for record in records]
            self.assertEqual(
                kinds,
                ["session-start", "decision-progress", "stop", "session-end"],
            )
            stop = records[2]
            self.assertEqual(stop["stop_kind"], final_reason)
            self.assertEqual(stop["shape"], "no-exit")
            self.assertEqual(stop["rule"], "policy-declared-final-stop")
            self.assertEqual(stop["evidence"]["final_reason"], final_reason)
            self.assertEqual(stop["decisions"], 1)
            self.assertEqual(records[3]["how"], f"incident-stop:{final_reason}")


class ReportScriptTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="hengbot-ownership-report-"))
        self.path = self.root / OWNERSHIP_METRICS_NAME
        clock = _FakeClock(0)
        ledger = OwnershipMetricsLedger(
            self.path,
            progress_interval_seconds=0.0,
            clock=clock.strftime,
            elapsed=clock.monotonic,
        )
        ledger.note_session_start({"time": clock.strftime(""),
                                   "git_commit": "a2f24cb"}, pid=31)
        for sequence in range(1, 4):
            clock.advance(600)
            ledger.note_decision(
                _row(sequence, clock.strftime(""),
                     owner="town-plan" if sequence < 3 else "store-router")
            )
        ledger.note_stop("loop-detected", ["town:blocked:x"] * 20)

    def test_the_report_names_the_runtime_source_and_the_blind_spot(self):
        output = self.root / "report.txt"
        self.assertEqual(
            ownership_metrics_report.main([str(self.path), "--output", str(output)]),
            0,
        )
        text = output.read_text(encoding="utf-8")
        self.assertIn(RUNTIME_SOURCE_LAST_DECISION, text)
        self.assertIn("no-exit", text)
        self.assertIn("per runtime hour", text)
        self.assertIn("arbiter.owner changes 1", text)
        self.assertIn("town_arbiter.py", text)  # the blind spot, in the output

    def test_the_report_writes_nothing_but_its_output(self):
        before = sorted(path.name for path in self.root.iterdir())
        output = self.root / "report.json"
        self.assertEqual(
            ownership_metrics_report.main(
                [str(self.path), "--json", "--output", str(output)]
            ),
            0,
        )
        after = sorted(path.name for path in self.root.iterdir())
        self.assertEqual(after, sorted([*before, "report.json"]))
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["totals"]["stops"]["no-exit"], 1)
        self.assertIn("blind_spot", payload)

    def test_a_missing_ledger_is_reported_not_created(self):
        missing = self.root / "absent.jsonl"
        self.assertEqual(ownership_metrics_report.main([str(missing)]), 2)
        self.assertFalse(missing.exists())


def _volatile_free(record: dict) -> dict:
    """Drop the two wall-clock fields two independent runs cannot share.

    Declared normalisation: ``time`` (the row's own second-resolution stamp)
    and every ``elapsed_seconds`` (the equipment optimizer's timing).  Nothing
    else is normalised, so a key, a reason or any other recorded fact that
    differed between the two runs would fail the comparison.
    """
    def strip(value):
        if isinstance(value, dict):
            return {
                name: strip(item)
                for name, item in value.items()
                if name != "elapsed_seconds"
            }
        if isinstance(value, list):
            return [strip(item) for item in value]
        return value

    return strip({name: value for name, value in record.items() if name != "time"})


class LedgerNeutralityTest(unittest.TestCase):
    """M3: the same recorded boards decide the same way with and without it.

    Substrate: the 24 recorded town boards of the 2026-09-23 03:44 capture
    (tests/fixtures/calibration-visit-blocked-loop-20260923.jsonl.gz, role
    ``blocked-window``), driven through ``choose_key`` and written with
    ``cli._write_decision`` -- the one function the ledger is attached to.
    """

    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        with gzip.open(REPLAY_FIXTURE, "rb") as stream:
            cls.boards = [
                json.loads(line)["board"]
                for line in stream
                if json.loads(line)["role"] == "blocked-window"
            ]

    def _replay(self, root: Path, *, with_ledger: bool):
        decision_log = root / "bot-decisions.jsonl"
        ledger = (
            OwnershipMetricsLedger(root / OWNERSHIP_METRICS_NAME)
            if with_ledger
            else None
        )
        policy = HengbotPolicy(monrace_knowledge=self.monrace)
        trajectory = []
        for raw in self.boards:
            board = parse_snapshot(raw, self.monrace)
            policy.prime(board)
            key = policy.choose_key(board)
            key = policy.validate_read_key(board, key)
            cli._write_decision(
                decision_log, board, key, policy.last_reason, policy,
                ownership_ledger=ledger,
            )
            trajectory.append((key, policy.last_reason))
        rows = [
            json.loads(line)
            for line in decision_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return trajectory, rows

    def test_the_ledger_changes_no_key_and_no_reason(self):
        with tempfile.TemporaryDirectory(prefix="hengbot-neutral-a-") as plain, \
                tempfile.TemporaryDirectory(prefix="hengbot-neutral-b-") as noted:
            without, plain_rows = self._replay(Path(plain), with_ledger=False)
            with_, noted_rows = self._replay(Path(noted), with_ledger=True)
            self.assertEqual(len(without), len(self.boards))
            # Byte-identical keys and reasons.
            self.assertEqual(
                json.dumps(without, ensure_ascii=False),
                json.dumps(with_, ensure_ascii=False),
            )
            # And the rest of every decision row, bar the declared volatiles.
            self.assertEqual(
                [_volatile_free(row) for row in plain_rows],
                [_volatile_free(row) for row in noted_rows],
            )
            self.assertFalse((Path(plain) / OWNERSHIP_METRICS_NAME).exists())
            written = read_records(Path(noted) / OWNERSHIP_METRICS_NAME)
            self.assertTrue(written)
            self.assertEqual(written[0]["kind"], "decision-progress")


if __name__ == "__main__":
    unittest.main()
