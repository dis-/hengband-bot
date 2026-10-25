"""Spectator snapshot file (``--spectate-file``, owner request 2026-10-23).

Substrate: tests/fixtures/equip-swap-20260826.snapshots.jsonl.gz (recorded
snapshots of a level-15 character on dungeon 2, 13F), served in order by the
faithful fake game to the real operation executor, follow loop and policy.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from hengbot import cli
from hengbot.cli import _ExecutorInputPort
from hengbot.model import parse_snapshot
from hengbot.spectator import (
    SPECTATE_WRITE_INTERVAL_SECONDS, SpectatorWriter, merge_seen_messages, printable_key,
    spectator_screen,
)
from tests import test_input_executor as executor_pins
from tests.run_follow_hygiene import run_follow as _run_follow
from tests.test_home_light_alternation import _fresh_policy


FIXTURES = Path(__file__).with_name("fixtures")
SNAPSHOTS = FIXTURES / "equip-swap-20260826.snapshots.jsonl.gz"
REPLAYED = 6
TERMINAL_REASON = "equipment-transaction:restore-blocked-terminal"


def _recorded_lines(count=REPLAYED):
    with gzip.open(SNAPSHOTS, "rt", encoding="utf-8") as stream:
        return [next(stream) for _ in range(count)]


class _Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


class SpectatorFollowReplayTest(executor_pins.ProductionHarness):
    """The real follow loop and executor over recorded states, with and without the flag.

    The faithful fake game serves the recorded snapshots in order: the first as
    the bootstrap board, each later one after the next posted command.
    """

    def _replay(self, sandbox: Path, *, spectate: bool, clock=None):
        recorded = [json.loads(line) for line in _recorded_lines()]
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(recorded[0])
        game.screen = executor_pins.command_screen(recorded[0]["turn"])
        game.states = copy.deepcopy(recorded[1:])
        # The bootstrap board drains the JSONL row the game wrote for it.
        game.jsonl.append(copy.deepcopy(recorded[0]))
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        state = sandbox / "state.jsonl"
        decisions = sandbox / "decisions.jsonl"
        state.write_text("", encoding="utf-8")
        argv = [
            "--state-file", str(state), "--decision-log", str(decisions),
            "--poll-interval", "0.001", "--stall-timeout", "0.5",
        ]
        if spectate:
            argv += ["--spectate-file", str(sandbox / "spectate.json")]
        args = cli._build_argument_parser().parse_args(argv)
        args.wait_telemetry = Mock()
        policy = _fresh_policy(sandbox)
        choose_key = policy.choose_key

        def choose(snapshot):
            if not game.states:
                policy._decision_sequence += 1
                policy.last_reason = TERMINAL_REASON
                return ""
            return choose_key(snapshot)

        policy.choose_key = Mock(side_effect=choose)
        patches = [patch("hengbot.cli._freeze_incident_safely")]
        if clock is not None:
            patches.append(patch(
                "hengbot.cli.SpectatorWriter",
                lambda path: SpectatorWriter(path, clock=clock)))
        for active in patches:
            active.start()
        try:
            result = _run_follow(args, policy, port, {})
        finally:
            for active in reversed(patches):
                active.stop()
        rows = [json.loads(line) for line in decisions.read_text(encoding="utf-8").splitlines()]
        return result, list(game.accepted), rows, recorded, game

    @staticmethod
    def _decided(rows):
        return [(row.get("decision_sequence"), row.get("turn"), row.get("reason"), row.get("key"))
                for row in rows if "decision_sequence" in row]

    def test_without_the_flag_no_file_and_the_same_keys_as_with_it(self):
        with TemporaryDirectory() as off_dir, TemporaryDirectory() as on_dir:
            off_result, off_keys, off_rows, _recorded, _game = self._replay(
                Path(off_dir), spectate=False)
            on_result, on_keys, on_rows, _recorded, _game = self._replay(
                Path(on_dir), spectate=True)
            off_files = sorted(path.name for path in Path(off_dir).iterdir())
            on_files = sorted(path.name for path in Path(on_dir).iterdir())
        self.assertEqual(off_result, on_result)
        self.assertEqual(off_keys, on_keys)
        self.assertEqual(len(off_keys), REPLAYED - 1)
        self.assertEqual(self._decided(off_rows), self._decided(on_rows))
        self.assertEqual(len(self._decided(off_rows)), REPLAYED)
        self.assertNotIn("spectate.json", off_files)
        self.assertNotIn("spectate-frames.jsonl", off_files)
        self.assertEqual(sorted(off_files + ["spectate.json", "spectate-frames.jsonl"]), on_files)

    def test_recorded_replay_writes_every_field_of_the_last_written_decision(self):
        clock = _Clock()

        def ticking():
            clock.now += 1.0
            return clock.now

        with TemporaryDirectory() as directory:
            sandbox = Path(directory)
            _result, _keys, rows, recorded, game = self._replay(
                sandbox, spectate=True, clock=ticking)
            written = json.loads((sandbox / "spectate.json").read_text(encoding="utf-8"))
            leftovers = [path.name for path in sandbox.iterdir() if path.name.endswith(".tmp")]
        decided = self._decided(rows)
        final = recorded[-1]
        self.assertEqual(leftovers, [])
        self.assertEqual(written["decision_sequence"], decided[-1][0])
        self.assertEqual(written["reason"], TERMINAL_REASON)
        self.assertEqual(written["key"], "")
        self.assertEqual(written["time"], clock.now)
        self.assertEqual(written["level"], final["player"]["level"])
        self.assertEqual(written["depth"], 13)
        self.assertEqual(written["dungeon"], 2)
        self.assertEqual(written["hp"], [final["player"]["hp"], final["player"]["max_hp"]])
        # The executor's last screen reply, as the game sent it (no attrs requested).
        screen = written["screen"]
        self.assertEqual(
            (screen["width"], screen["height"], screen["lines"]),
            (game.screen["width"], game.screen["height"], game.screen["lines"]))
        self.assertIn("cursor", game.screen)
        self.assertNotIn("cursor", screen)
        self.assertNotIn("attrs", screen)
        # Each recorded snapshot carries only its new lines: all are kept, oldest first.
        seen = [message for line in recorded for message in line["messages"]]
        self.assertGreater(len(seen), 0)
        self.assertEqual(written["messages"], seen[-20:])

    def test_an_earlier_decision_is_written_with_its_own_key(self):
        clock = _Clock()
        with TemporaryDirectory() as directory:
            sandbox = Path(directory)
            # A clock that never advances: only the first decision is written.
            _result, keys, rows, recorded, _game = self._replay(
                sandbox, spectate=True, clock=clock)
            written = json.loads((sandbox / "spectate.json").read_text(encoding="utf-8"))
        first = self._decided(rows)[0]
        self.assertEqual(written["decision_sequence"], first[0])
        self.assertEqual(written["reason"], first[2])
        self.assertEqual(written["key"], printable_key(first[3]))
        self.assertNotEqual(written["key"], "")
        self.assertEqual(written["messages"], recorded[0]["messages"])


class SpectatorWriterTest(unittest.TestCase):
    @staticmethod
    def _snapshot(messages=(), turn=1):
        line = _recorded_lines(1)[0]
        raw = json.loads(line)
        raw["messages"] = list(messages)
        raw["turn"] = turn
        return parse_snapshot(raw, {})

    def test_two_decisions_within_one_interval_write_once(self):
        clock = _Clock()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spectate.json"
            writer = SpectatorWriter(path, clock=clock)
            self.assertTrue(writer.observe(self._snapshot(["a"]), "5", "first", 1, None))
            clock.now += SPECTATE_WRITE_INTERVAL_SECONDS / 2
            self.assertFalse(writer.observe(self._snapshot(["b"]), "6", "second", 2, None))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["reason"], "first")
            clock.now += SPECTATE_WRITE_INTERVAL_SECONDS / 2
            self.assertTrue(writer.observe(self._snapshot(["c"]), "\x1b\r", "third", 3, None))
            written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            (written["decision_sequence"], written["key"], written["reason"]),
            (3, "\\e\\r", "third"))
        # Messages of the throttled decision are still kept.
        self.assertEqual(written["messages"], ["a", "b", "c"])

    def test_write_failure_is_swallowed_and_reported_once_per_hour(self):
        clock = _Clock()
        stderr = io.StringIO()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "missing-directory" / "spectate.json"
            writer = SpectatorWriter(path, clock=clock, stderr=stderr)
            self.assertFalse(writer.observe(self._snapshot(), "5", "first", 1, None))
            clock.now += 10.0
            self.assertFalse(writer.observe(self._snapshot(), "5", "second", 2, None))
            self.assertEqual(stderr.getvalue().count("spectate file write failed"), 1)
            clock.now += 3600.0
            self.assertFalse(writer.observe(self._snapshot(), "5", "third", 3, None))
            self.assertEqual(stderr.getvalue().count("spectate file write failed"), 2)
            # The directory appears: the next decision writes normally.
            path.parent.mkdir()
            clock.now += 1.0
            self.assertTrue(writer.observe(self._snapshot(), "5", "fourth", 4, None))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["reason"], "fourth")

    def test_replace_failure_is_swallowed(self):
        stderr = io.StringIO()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spectate.json"
            writer = SpectatorWriter(path, clock=_Clock(), stderr=stderr)
            with patch("hengbot.spectator.os.replace", side_effect=PermissionError("locked")):
                self.assertFalse(writer.observe(self._snapshot(), "5", "first", 1, None))
            self.assertFalse(path.exists())
        self.assertIn("locked", stderr.getvalue())

    def test_history_replies_are_not_duplicated(self):
        history = [f"m{index}" for index in range(32)]
        seen = merge_seen_messages([], history)[-20:]
        self.assertEqual(merge_seen_messages(seen, history)[-20:], history[-20:])
        grown = history[3:] + ["n1", "n2", "n3"]
        self.assertEqual(merge_seen_messages(seen, grown)[-20:], grown[-20:])
        self.assertEqual(merge_seen_messages(["x", "y"], ["z"]), ["x", "y", "z"])
        self.assertEqual(merge_seen_messages(["x", "y"], []), ["x", "y"])

    def test_screen_copy_keeps_attrs_only_when_the_reply_has_them(self):
        reply = {"width": 3, "height": 1, "lines": ["abc"], "cursor": {"x": 0},
                 "input_context": None, "term": 0}
        self.assertEqual(spectator_screen(reply), {"width": 3, "height": 1, "lines": ["abc"]})
        reply["attrs"] = [[1, 2, 3]]
        self.assertEqual(spectator_screen(reply)["attrs"], [[1, 2, 3]])
        self.assertIsNone(spectator_screen(None))

    def test_printable_key(self):
        self.assertEqual(printable_key(None), "")
        self.assertEqual(printable_key(">\ry"), ">\\ry")
        self.assertEqual(printable_key("\x01"), "^A")
        self.assertEqual(printable_key("あ"), "\\u3042")


if __name__ == "__main__":
    unittest.main()
