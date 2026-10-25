"""Policy-action pacing pins through the real follow loop."""

import tests  # noqa: F401
import gzip
import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hengbot.cli import PostingContract, _build_argument_parser
from hengbot.policy import HengbotPolicy
from hengbot.spectator import SpectatorWriter
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.run_follow_hygiene import run_follow


class ExchangeDone(Exception):
    pass


class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def read(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def module(self):
        return SimpleNamespace(
            monotonic=self.read, perf_counter=self.read, sleep=self.sleep,
            strftime=time.strftime,
        )


class ScriptPolicy(HengbotPolicy):
    def __init__(self, clock, elapsed):
        super().__init__()
        self.clock = clock
        self.elapsed = elapsed
        self.calls = 0

    def choose_key(self, snapshot):
        self.calls += 1
        self.clock.now += self.elapsed
        self.last_reason = "rest"
        return "R1\r"


def board(turn):
    return json.dumps({
        "turn": turn,
        "player": {"y": 5, "x": 5, "hp": 10, "max_hp": 10},
        "floor": {"dungeon_id": 0, "level": 1},
    }) + "\n"


class RefuseOnce(PostingContract):
    def __init__(self):
        super().__init__()
        self.refused = False

    def allow(self, snapshot, key, owner, **kwargs):
        if not self.refused:
            self.refused = True
            self.last_incident = {
                "marker": "test-refusal", "owner": owner, "key": key,
            }
            return False
        return super().allow(snapshot, key, owner, **kwargs)


class ActionPacingTest(unittest.TestCase):
    def exchange(self, minimum=None, elapsed=0.05, recorded=False,
                 send_duration=0.0, refuse_once=False):
        clock = Clock()
        knowledge = (
            load_monrace_knowledge(Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc"))
            if recorded else {}
        )
        policy = (HengbotPolicy(monrace_knowledge=knowledge)
                  if recorded else ScriptPolicy(clock, elapsed))
        if recorded:
            fixture = Path(__file__).parent / "fixtures" / "esp-threat-rest-20260921.jsonl.gz"
            with gzip.open(fixture, "rt", encoding="utf-8") as stream:
                lines = [
                    line for line in stream
                    if (json.loads(line).get("type") == "player_turn"
                        and json.loads(line).get("floor", {}).get("level", 0) > 0)
                ][2:5]
        else:
            lines = [board(turn) for turn in (1, 2, 3)]
        posts = []
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.jsonl"
            state.write_text(lines[0], encoding="utf-8", newline="\n")
            arguments = [
                "--state-file", str(state),
                "--decision-log", str(root / "decisions.jsonl"),
                "--spectate-file", str(root / "spectate.json"),
                "--game-save-path", str(root / "absent-save"),
                "--dump-interval-seconds", "0",
            ]
            if minimum is not None:
                arguments += ["--min-action-seconds", str(minimum)]
            args = _build_argument_parser().parse_args(arguments)
            args.wait_telemetry = Mock()
            appended = 0

            def poll():
                nonlocal appended
                if len(posts) == 2:
                    raise ExchangeDone
                if appended <= len(posts):
                    with state.open("a", encoding="utf-8", newline="\n") as stream:
                        stream.write(lines[appended + 1])
                    appended += 1
                    if recorded:
                        clock.now += elapsed

            def send(key, **kwargs):
                posts.append((key, kwargs["decision"]["reason"], clock.now))
                clock.now += send_duration
                return True

            with (
                patch("hengbot.cli.time", clock.module()),
                # The viewer throttle must share the follow loop's fake clock.
                patch("hengbot.cli.SpectatorWriter",
                      lambda path: SpectatorWriter(path, clock=clock.read)),
                patch("hengbot.cli._arm_decision_watchdog", side_effect=poll),
            ):
                with self.assertRaises(ExchangeDone):
                    run_follow(
                        args, policy, send, knowledge,
                        posting_contract=RefuseOnce() if refuse_once else None,
                    )
            rows = [
                json.loads(line)
                for line in args.decision_log.read_text(encoding="utf-8").splitlines()
            ]
            spectator = json.loads((root / "spectate.json").read_text(encoding="utf-8"))
        return clock, posts, rows, spectator

    def test_short_interval_waits_only_the_remainder(self):
        clock, posts, rows, _ = self.exchange(0.25)
        self.assertEqual(len(posts), 2)
        self.assertEqual(len(clock.sleeps), 1)
        self.assertAlmostEqual(clock.sleeps[0], 0.20)
        self.assertAlmostEqual(posts[1][2] - posts[0][2], 0.25)
        self.assertEqual([row["timing"]["choose_key_ms"] for row in rows], [50.0, 50.0])
        self.assertEqual([row["timing"]["send_ms"] for row in rows], [0.0, 0.0])
        self.assertEqual([row["timing"]["total_ms"] for row in rows], [50.0, 50.0])

    def test_late_post_does_not_wait(self):
        clock, posts, _, _ = self.exchange(0.25, elapsed=0.30)
        self.assertEqual(clock.sleeps, [])
        self.assertAlmostEqual(posts[1][2] - posts[0][2], 0.30)

    def test_default_never_waits(self):
        clock, posts, _, _ = self.exchange()
        self.assertEqual(clock.sleeps, [])
        self.assertAlmostEqual(posts[1][2] - posts[0][2], 0.05)
        args = _build_argument_parser().parse_args(["--state-file", "unused"])
        self.assertEqual(args.min_action_seconds, 0.0)

    def test_elapsed_action_counts_from_post_start(self):
        clock, posts, _, _ = self.exchange(0.25, send_duration=0.30)
        self.assertEqual(clock.sleeps, [])
        self.assertAlmostEqual(posts[1][2] - posts[0][2], 0.35)

    def test_retry_post_sets_the_next_action_deadline(self):
        clock, posts, _, _ = self.exchange(0.25, refuse_once=True)
        self.assertEqual(len(posts), 2)
        self.assertEqual(len(clock.sleeps), 1)
        self.assertAlmostEqual(clock.sleeps[0], 0.20)
        self.assertAlmostEqual(posts[1][2] - posts[0][2], 0.25)

    def test_recorded_follow_keeps_keys_and_reasons(self):
        plain = self.exchange(recorded=True)
        paced = self.exchange(0.25, recorded=True)
        self.assertEqual(
            [(key, reason) for key, reason, _ in plain[1]],
            [(key, reason) for key, reason, _ in paced[1]],
        )
        self.assertEqual(
            [(row["key"], row["reason"]) for row in plain[2]],
            [(row["key"], row["reason"]) for row in paced[2]],
        )
        self.assertEqual(len(paced[1]), 2)
        self.assertEqual(len(paced[0].sleeps), 1)
        self.assertEqual(plain[3]["key"], paced[3]["key"])


if __name__ == "__main__":
    unittest.main()
