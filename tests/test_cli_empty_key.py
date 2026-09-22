"""CLI regression pin for empty decisions that command nothing."""

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import json
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from hengbot.cli import _build_argument_parser, _run_follow
from hengbot.policy import HengbotPolicy


def snapshot_line(turn):
    return json.dumps({
        "turn": turn,
        "player": {"y": 5, "x": 5, "hp": 10, "max_hp": 10},
        "floor": {"dungeon_id": 0, "level": 1},
    }) + "\n"


class CliEmptyKeyTest(unittest.TestCase):
    def test_two_empty_keys_reach_existing_no_key_exhausted_stop(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.jsonl"
            decision_path = root / "decisions.jsonl"
            state_path.write_text(snapshot_line(1), encoding="utf-8")
            args = _build_argument_parser().parse_args([
                "--state-file", str(state_path),
                "--decision-log", str(decision_path),
                "--poll-interval", "0.001",
            ])
            args.wait_telemetry = Mock()
            policy = HengbotPolicy()
            decisions = 0

            def choose(_snapshot):
                nonlocal decisions
                decisions += 1
                if decisions > 2:
                    self.fail("follow consumed a third empty-key decision")
                policy.last_reason = "store:entry-await-observation"
                return ""

            policy.choose_key = Mock(side_effect=choose)

            def append_snapshots():
                time.sleep(0.05)
                with state_path.open("a", encoding="utf-8") as stream:
                    for turn in (2, 3, 4):
                        stream.write(snapshot_line(turn))
                        stream.flush()
                        time.sleep(0.02)

            producer = threading.Thread(target=append_snapshots)
            producer.start()
            try:
                with (
                    patch("hengbot.cli._append_capture_ledger"),
                    patch("hengbot.cli._freeze_incident_safely") as freeze,
                    patch("builtins.print") as output,
                ):
                    result = _run_follow(
                        args, policy,
                        lambda *_args, **_kwargs: self.fail("posted a key"),
                        {},
                    )
            finally:
                producer.join()

            rows = [
                json.loads(line)
                for line in decision_path.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            self.assertEqual(result, 0)
            self.assertEqual(policy.choose_key.call_count, 2)
            self.assertEqual([row["key"] for row in rows], ["", ""])
            self.assertEqual(policy._cli_no_key_streak, 2)
            self.assertEqual(freeze.call_args.args[1], "no-key-exhausted")
            self.assertTrue(any(
                call.args
                and str(call.args[0]).startswith("<no-key-exhausted>")
                for call in output.call_args_list
            ))


if __name__ == "__main__":
    unittest.main()
