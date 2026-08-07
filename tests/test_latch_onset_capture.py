import base64
import json
import pickle
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import hengbot.policy as policy_module
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.model import (
    STORE_ALCHEMIST,
    STORE_ARMOURY,
    STORE_BLACK,
    STORE_GENERAL,
    STORE_HOME,
    STORE_MAGIC,
    STORE_TEMPLE,
    STORE_WEAPON,
)
from tests import test_policy
from absorbing_state_catalog import TownWorld


class LatchOnsetCaptureTest(unittest.TestCase):
    @staticmethod
    def _exhaust_town_work(policy):
        policy._town_errand_plan = None
        for store_type in (
            STORE_GENERAL,
            STORE_ARMOURY,
            STORE_WEAPON,
            STORE_TEMPLE,
            STORE_ALCHEMIST,
            STORE_MAGIC,
            STORE_BLACK,
            STORE_HOME,
        ):
            policy._town_visit_ledger.approach_fails[store_type] = (
                policy_module.TOWN_STOP_PASS_LIMIT
            )

    def test_none_to_value_captures_bounded_replayable_four_decision_window(self):
        policy, snapshot = test_policy.NoSafeRecallDestinationTest()._fixture()
        # This capture exercises a genuine no-work terminal. Equipment blockers
        # are now outstanding work and intentionally cannot install it.
        snapshot = replace(snapshot, player=replace(snapshot.player, class_id=1))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "latch-onset.jsonl"
            policy._latch_capture_path = path
            before_key = policy.choose_key(snapshot)
            before_reason = policy.last_reason
            policy._equipment_optimization_preparation = None
            self._exhaust_town_work(policy)
            installing_snapshot = replace(snapshot, turn=snapshot.turn + 1)
            installing_key = policy.choose_key(installing_snapshot)
            installing_reason = policy.last_reason
            following = [
                replace(snapshot, turn=snapshot.turn + offset) for offset in (2, 3)
            ]
            following_decisions = []
            for current in following:
                following_decisions.append((policy.choose_key(current), policy.last_reason))

            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual([record["relative_decision"] for record in records], [-1, 0, 1, 2])
        self.assertEqual(
            (records[0]["emitted_key"], records[0]["last_reason"]),
            (before_key, before_reason),
        )
        onset = records[1]
        self.assertEqual(onset["town_blocked_reason"], {
            "before": None,
            "after": "no-safe-recall-destination",
        })
        self.assertTrue(onset["assignment"]["assigning_file"].endswith("policy.py"))
        self.assertIsInstance(onset["assignment"]["assigning_line"], int)
        self.assertTrue(onset["assignment"]["caller_chain"])
        for record in records:
            self.assertEqual(
                set(record),
                {
                    "format", "relative_decision", "turn", "snapshot", "emitted_key",
                    "last_reason", "town_blocked_reason", "assignment", "calibration",
                    "town_claims", "town_store_attempted", "visit_ledger",
                    "errand_current_stop", "fundraising_mode",
                    "equipment_transaction_session", "home_pending_item",
                    "recall_destination_candidates",
                    "predecision_policy_checkpoint_pickle_b64", "snapshot_pickle_b64",
                },
            )
            self.assertEqual(len(record["recall_destination_candidates"]), 3)

        replay = restore_checkpoint(
            type(policy), onset["predecision_policy_checkpoint_pickle_b64"]
        )
        replay_installing_snapshot = pickle.loads(
            base64.b64decode(onset["snapshot_pickle_b64"])
        )
        self.assertEqual(
            (replay.choose_key(replay_installing_snapshot), replay.last_reason),
            (installing_key, installing_reason),
        )
        following_record = records[2]
        replay = restore_checkpoint(
            type(policy), following_record["predecision_policy_checkpoint_pickle_b64"]
        )
        replay_following_snapshot = pickle.loads(
            base64.b64decode(following_record["snapshot_pickle_b64"])
        )
        self.assertEqual(
            (replay.choose_key(replay_following_snapshot), replay.last_reason),
            following_decisions[0],
        )

    def test_non_none_transition_and_steady_state_do_not_fire(self):
        policy, snapshot = test_policy.NoSafeRecallDestinationTest()._fixture()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "latch-onset.jsonl"
            policy._latch_capture_path = path
            policy._town_blocked_reason = "first"
            policy._town_blocked_reason = "second"
            policy.choose_key(snapshot)
            policy._town_blocked_reason = "second"
            policy.choose_key(replace(snapshot, turn=snapshot.turn + 1))
            self.assertFalse(path.exists())

    def test_enabled_capture_is_decision_pure_for_150_paired_decisions(self):
        disabled, snapshot = test_policy.NoSafeRecallDestinationTest()._fixture()
        enabled, _ = test_policy.NoSafeRecallDestinationTest()._fixture()
        self._exhaust_town_work(disabled)
        self._exhaust_town_work(enabled)
        disabled_world = TownWorld(snapshot)
        enabled_world = TownWorld(snapshot)
        with TemporaryDirectory() as directory:
            enabled._latch_capture_path = Path(directory) / "latch-onset.jsonl"
            disabled_results = []
            enabled_results = []
            for offset in range(150):
                disabled_key = disabled.choose_key(disabled_world.snapshot(offset))
                enabled_key = enabled.choose_key(enabled_world.snapshot(offset))
                disabled_results.append((disabled_key, disabled.last_reason))
                enabled_results.append((enabled_key, enabled.last_reason))
                disabled_world.apply(disabled_key)
                enabled_world.apply(enabled_key)

        self.assertEqual(enabled_results, disabled_results)


if __name__ == "__main__":
    unittest.main()
