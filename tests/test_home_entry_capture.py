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
from hengbot.home_entry_capture import HomeEntryCapture, STATE_FIELDS, _home_owned
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.model import STORE_HOME, StoreState
from tests import test_policy


class HomeEntryCaptureTest(unittest.TestCase):
    def test_non_home_decision_takes_no_checkpoint_and_writes_no_row(self):
        class NonHomePolicy:
            _decision_sequence = 0
            last_reason = ""
            _home_candidate_waiting = False
            _shopping_approach_store_type = None
            _store_entry_wait_owner = None
            _store_entry_posted_owner = None

            def _choose_key_with_latch_capture(self, snapshot):
                self._decision_sequence += 1
                self.last_reason = "explore"
                return "6"

        harness = test_policy.HomeOneOperationPerEntryTest()
        snapshot = harness._entrance_snapshot(harness._real_pack(), turn=3200100)
        policy = NonHomePolicy()
        self.assertFalse(_home_owned(policy, snapshot))

        with TemporaryDirectory() as directory:
            path = Path(directory) / "home-entry-capture.jsonl"
            capture = HomeEntryCapture(path)
            with patch(
                "hengbot.home_entry_capture.checkpoint",
                side_effect=AssertionError("non-Home decision checkpointed"),
            ) as checkpoint_mock:
                self.assertEqual(capture.choose_key(policy, snapshot), "6")

            checkpoint_mock.assert_not_called()
            self.assertIsNone(capture.pending)
            self.assertFalse(path.exists())

    def test_home_owned_decision_still_takes_full_checkpoint_row(self):
        harness = test_policy.HomeOneOperationPerEntryTest()
        policy = test_policy.HengbotPolicy()
        policy._shopping_approach_store_type = STORE_HOME
        snapshot = harness._entrance_snapshot(harness._real_pack(), turn=3200100)
        next_snapshot = replace(snapshot, turn=snapshot.turn + 1)

        with TemporaryDirectory() as directory:
            path = Path(directory) / "home-entry-capture.jsonl"
            capture = HomeEntryCapture(path)
            policy._home_entry_capture = capture
            policy.choose_key(snapshot)
            capture.observe_snapshot(next_snapshot)
            record = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(record["format"], 1)
        self.assertTrue(record["predecision_policy_checkpoint_pickle_b64"])
        self.assertTrue(record["decision_snapshot_pickle_b64"])
        self.assertTrue(record["next_snapshot_pickle_b64"])
        replay = restore_checkpoint(
            type(policy), record["predecision_policy_checkpoint_pickle_b64"]
        )
        self.assertEqual(replay._shopping_approach_store_type, STORE_HOME)

    def test_home_approach_onset_still_takes_full_checkpoint_row(self):
        harness = test_policy.HomeOneOperationPerEntryTest()
        policy = test_policy.HengbotPolicy()
        policy._home_candidate_waiting = True
        snapshot = harness._entrance_snapshot(harness._real_pack(), turn=3200100)

        with TemporaryDirectory() as directory:
            path = Path(directory) / "home-entry-capture.jsonl"
            capture = HomeEntryCapture(path)
            policy._home_entry_capture = capture
            policy.choose_key(snapshot)
            capture.observe_snapshot(replace(snapshot, turn=snapshot.turn + 1))
            record = json.loads(path.read_text(encoding="utf-8"))

        replay = restore_checkpoint(
            type(policy), record["predecision_policy_checkpoint_pickle_b64"]
        )
        self.assertTrue(replay._home_candidate_waiting)
        self.assertEqual(record["last_reason"], "shop:travel:await-entry")

    def test_gate1_substrate_replays_fixed_digger_arming_and_composed_key(self):
        path = Path(__file__).parent / "fixtures" / "digger-withdraw-gate1.jsonl"
        if not path.exists():
            self.skipTest("committed Gate-1 fixture is not present")
        with path.open(encoding="utf-8") as stream:
            record = json.loads(stream.readline())
        policy = restore_checkpoint(
            test_policy.HengbotPolicy,
            record["predecision_policy_checkpoint_pickle_b64"],
        )
        inside = pickle.loads(
            base64.b64decode(record["decision_snapshot_pickle_b64"])
        )
        outside = pickle.loads(
            base64.b64decode(record["next_snapshot_pickle_b64"])
        )

        self.assertEqual(record["key"], "\x1b")
        self.assertEqual(record["posted_characters"], ["\x1b"])
        self.assertGreaterEqual(len(inside.store.items), 34)
        expected = max(
            (item for item in inside.store.items if item.is_digging_tool),
            key=lambda item: item.sval,
        )
        self.assertEqual(policy.choose_key(inside), "\x1b")
        self.assertEqual(policy.last_reason, "home:queue-digging-tool-withdraw")
        self.assertEqual(policy.choose_key(outside), "5")
        self.assertEqual(
            policy._store_visit.operation_key,
            f"p{expected.letter}\x1b",
        )
        self.assertEqual(policy.last_reason, "home:atomic-withdraw")

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

    def test_writer_crossing_threshold_rotates_and_keeps_writing(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "home-entry-capture.jsonl"
            path.write_text("old\n", encoding="utf-8")
            capture = HomeEntryCapture(path, rotate_bytes=4, generations=3)

            capture._write({"new": True})

            self.assertEqual(
                path.with_name(f"{path.name}.1").read_text(encoding="utf-8"),
                "old\n",
            )
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")), {"new": True}
            )

    def test_rotation_failure_does_not_propagate(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "home-entry-capture.jsonl"
            path.write_text("old\n", encoding="utf-8")
            capture = HomeEntryCapture(path, rotate_bytes=4, generations=3)

            with patch(
                "hengbot.flight_recorder.os.replace", side_effect=OSError("locked")
            ):
                capture._write({"new": True})

            self.assertEqual(
                [
                    json.loads(line)
                    for line in path.read_text(encoding="utf-8").splitlines()[1:]
                ],
                [{"new": True}],
            )

    def test_writes_joined_fields_and_replays_each_record_through_choose_key(self):
        harness = test_policy.HomeOneOperationPerEntryTest()
        policy = test_policy.HengbotPolicy()
        target = test_policy.store_item(
            "a", test_policy.TVAL_POTION, 9999, name="capture target"
        )
        policy._calibration_phase = "restore-supplies"
        policy._calibration_restore_signatures = [policy._item_signature(target)]
        policy._home_candidate_waiting = True
        policy._home_atomic_withdraw_procurement_class = (39, 0)
        policy._home_atomic_withdraw_posted_turn = 3200199
        policy._home_pending_quantities = {("item", 39, 0): 3}
        policy._home_procurement_batch_active = True
        policy._deferred_home_item_sites = {
            ("item", 39, 0): "town-item-processing-missing-pending"
        }
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
        self.assertEqual(
            record["scan_entry_state"]["_home_pending_quantities"],
            {"['item', 39, 0]": 3},
        )
        self.assertTrue(record["scan_entry_state"]["_home_procurement_batch_active"])
        self.assertEqual(
            record["scan_entry_state"]["_deferred_home_item_sites"],
            {"['item', 39, 0]": "town-item-processing-missing-pending"},
        )
        self.assertEqual(
            record["scan_entry_state"]["_home_atomic_withdraw_posted_turn"],
            3200199,
        )
        self.assertEqual(
            record["scan_entry_state"]["_home_atomic_withdraw_procurement_class"],
            [39, 0],
        )
        replay = restore_checkpoint(
            type(policy), record["predecision_policy_checkpoint_pickle_b64"]
        )
        self.assertEqual(replay._home_atomic_withdraw_procurement_class, (39, 0))
        self.assertEqual(replay._home_pending_quantities, {("item", 39, 0): 3})
        self.assertTrue(replay._home_procurement_batch_active)
        self.assertEqual(
            replay._deferred_home_item_sites,
            {("item", 39, 0): "town-item-processing-missing-pending"},
        )
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
        self.assertEqual(replay._home_atomic_withdraw_posted_turn, 3200199)
        replay_snapshot = pickle.loads(
            base64.b64decode(record["decision_snapshot_pickle_b64"])
        )
        self.assertEqual(
            (replay.choose_key(replay_snapshot), replay.last_reason),
            (key, reason),
        )


if __name__ == "__main__":
    unittest.main()
