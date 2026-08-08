import base64
import io
import json
import pickle
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _observe_home_entry_capture
from hengbot.home_entry_capture import HomeEntryCapture, STATE_FIELDS
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.model import STORE_HOME, StoreState
from tests import test_policy


class HomeEntryCaptureTest(unittest.TestCase):
    def test_reports_each_distinct_failure_to_stderr_and_capture_once(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "home-entry-capture.jsonl"
            capture = HomeEntryCapture(path)
            stderr = io.StringIO()
            with patch("sys.stderr", stderr):
                capture.report_failure(
                    "before_decision", TypeError("bad value"), "policy._field"
                )
                capture.report_failure(
                    "before_decision", TypeError("bad value"), "policy._field"
                )
            markers = [json.loads(line) for line in path.read_text().splitlines()]

        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["exception_type"], "TypeError")
        self.assertEqual(markers[0]["exception_message"], "bad value")
        self.assertEqual(markers[0]["field"], "policy._field")
        self.assertEqual(stderr.getvalue().count("policy._field"), 1)

    def test_writes_joined_fields_and_replays_each_record_through_choose_key(self):
        harness = test_policy.HomeOneOperationPerEntryTest()
        policy = test_policy.HengbotPolicy()
        target = test_policy.store_item(
            "a", test_policy.TVAL_POTION, 9999, name="capture target"
        )
        policy._calibration_phase = "restore-supplies"
        policy._calibration_restore_signatures = [policy._item_signature(target)]
        policy._home_candidate_waiting = True
        decision_snapshot = replace(
            harness._entrance_snapshot(harness._real_pack(), turn=3200200),
            equipment=[
                test_policy.item(
                    "light", test_policy.TVAL_LITE, 0, name="a light"
                )
            ],
            messages=("Home entrance.",),
        )
        next_snapshot = replace(
            decision_snapshot,
            turn=3200201,
            store=StoreState(
                STORE_HOME, [], stock_num=105, page_top=52, page_size=52
            ),
            messages=("page changes",),
        )

        with TemporaryDirectory() as directory:
            path = Path(directory) / "home-entry-capture.jsonl"
            capture = HomeEntryCapture(path)
            policy._home_entry_capture = capture
            key = policy.choose_key(decision_snapshot)
            reason = policy.last_reason
            for character in key:
                capture.record_posted_character(
                    policy._decision_sequence, character
                )
            _observe_home_entry_capture(capture, [next_snapshot])
            second_key = policy.choose_key(next_snapshot)
            second_reason = policy.last_reason
            _observe_home_entry_capture(
                capture, [replace(next_snapshot, turn=next_snapshot.turn + 1)]
            )
            records = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]
            record = records[0]

        self.assertEqual(len(records), 2)
        self.assertEqual(
            [(item["key"], item["last_reason"]) for item in records],
            [(key, reason), (second_key, second_reason)],
        )

        self.assertEqual(record["decision_index"], 1)
        self.assertEqual(record["last_reason"], reason)
        self.assertEqual(record["key"], key)
        self.assertEqual(record["posted_characters"], list(key))
        self.assertEqual(set(record["scan_entry_state"]), set(STATE_FIELDS))
        self.assertIsNone(record["decision_snapshot"]["store"])
        self.assertEqual(
            record["next_snapshot"]["store"],
            {
                "store_type": STORE_HOME,
                "stock_num": 105,
                "page_top": 52,
                "page_size": 52,
                "item_count": 0,
            },
        )
        self.assertEqual(record["next_snapshot"]["type"], "Snapshot")
        self.assertEqual(record["next_snapshot"]["turn"], next_snapshot.turn)
        self.assertEqual(record["next_snapshot"]["messages"], ["page changes"])
        self.assertEqual(
            record["next_snapshot"]["player_position"],
            [next_snapshot.player.position.y, next_snapshot.player.position.x],
        )
        self.assertEqual(record["next_snapshot"]["store"]["page_top"], 52)

        replay = restore_checkpoint(
            type(policy), record["predecision_policy_checkpoint_pickle_b64"]
        )
        replay_snapshot = pickle.loads(
            base64.b64decode(record["decision_snapshot_pickle_b64"])
        )
        self.assertEqual(
            (replay.choose_key(replay_snapshot), replay.last_reason),
            (key, reason),
        )


if __name__ == "__main__":
    unittest.main()
