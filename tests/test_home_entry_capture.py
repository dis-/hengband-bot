import base64
import json
import pickle
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.home_entry_capture import HomeEntryCapture, STATE_FIELDS
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.model import STORE_HOME, StoreState
from tests import test_policy


class HomeEntryCaptureTest(unittest.TestCase):
    def test_writes_joined_fields_and_replays_each_record_through_choose_key(self):
        policy, outside = test_policy.NoSafeRecallDestinationTest()._fixture()
        decision_snapshot = replace(
            outside,
            store=StoreState(
                STORE_HOME, [], stock_num=105, page_top=0, page_size=52
            ),
            messages=("Home opens.",),
        )
        next_snapshot = replace(
            decision_snapshot,
            turn=decision_snapshot.turn + 1,
            store=StoreState(
                STORE_HOME, [], stock_num=105, page_top=52, page_size=52
            ),
            messages=("page changes",),
        )

        with TemporaryDirectory() as directory:
            path = Path(directory) / "home-entry-capture.jsonl"
            capture = HomeEntryCapture(path)
            boundary = capture.before_decision(policy, decision_snapshot)
            key = policy.choose_key(decision_snapshot)
            reason = policy.last_reason
            capture.record_decision(
                policy, decision_snapshot, key, reason, *boundary
            )
            for character in key:
                capture.record_posted_character(
                    policy._decision_sequence, character
                )
            capture.observe_snapshot(next_snapshot)
            record = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(record["decision_index"], policy._decision_sequence)
        self.assertEqual(record["last_reason"], reason)
        self.assertEqual(record["key"], key)
        self.assertEqual(record["posted_characters"], list(key))
        self.assertEqual(set(record["scan_entry_state"]), set(STATE_FIELDS))
        self.assertEqual(
            record["decision_snapshot"]["store"],
            {
                "store_type": STORE_HOME,
                "stock_num": 105,
                "page_top": 0,
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
