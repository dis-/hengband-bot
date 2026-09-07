import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hengbot.home_disposal import (
    HomeDisposalCandidate, HomeDisposalReadError, HomeDisposalState, signature_key,
)
from hengbot.model import (
    STORE_ALCHEMIST, STORE_GENERAL, STORE_HOME, STORE_MAGIC,
    TVAL_FOOD, TVAL_POTION, TVAL_SCROLL, TVAL_STAFF, TVAL_SWORD,
    InventoryItem, StoreItem,
)
from hengbot.policy import HengbotPolicy


class HomeDisposalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        root = Path(self.temporary.name)
        self.paths = (
            root / "home-withdraw-history.jsonc",
            root / "home-disposal-decisions.jsonc",
            root / "jsonlog" / "home-disposal-queue.json",
            root / "jsonlog" / "sol-events.jsonl",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def state(self):
        return HomeDisposalState(*self.paths)

    @staticmethod
    def candidate(signature=("a Potion", TVAL_POTION, 3), count=1):
        return HomeDisposalCandidate(signature, signature[0], signature[1], signature[2], count, False, False)

    def test_tracker_persists_withdraw_history_and_recall_cadence_across_restart(self):
        state = self.state()
        signature = ("a Potion", TVAL_POTION, 3)
        state.record("deposit", signature, 100)
        for _ in range(4):
            self.assertFalse(state.note_dungeon_recall())

        restarted = self.state()
        self.assertEqual(restarted.recall_count, 4)
        self.assertTrue(restarted.is_idle(signature))
        restarted.record("withdraw", signature, 200)
        self.assertTrue(restarted.note_dungeon_recall())

        restarted_again = self.state()
        self.assertFalse(restarted_again.is_idle(signature))
        self.assertEqual(restarted_again.recall_count, 5)

    def test_history_save_retries_transient_windows_replace_denial(self):
        state = self.state()
        real_replace = Path.replace
        attempts = 0

        def deny_once(path, target):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise PermissionError("transient sharing violation")
            return real_replace(path, target)

        with patch.object(Path, "replace", deny_once), patch("hengbot.home_disposal.time.sleep") as sleep:
            state.record("deposit", ("a Potion", TVAL_POTION, 3), 100)

        self.assertEqual(attempts, 2)
        sleep.assert_called_once_with(0.05)
        self.assertEqual(json.loads(self.paths[0].read_text(encoding="utf-8"))["transactions"][0]["turn"], 100)

    def test_reader_retries_oserror_then_fails_loudly(self):
        with (
            patch.object(Path, "read_text", side_effect=PermissionError("locked")) as read,
            patch("hengbot.home_disposal.time.sleep") as sleep,
        ):
            with self.assertRaises(HomeDisposalReadError):
                HomeDisposalState._read_json(self.paths[0])
        self.assertEqual(read.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.05, 0.1])

    def test_history_save_refuses_to_shrink_newer_disk_history(self):
        state = self.state()
        existing = {"version": 1, "dungeon_recall_count": 9, "transactions": [
            {"action": "deposit", "signature": [f"potion {index}", TVAL_POTION, index], "turn": index}
            for index in range(4)
        ]}
        self.paths[0].write_text(json.dumps(existing), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "refusing to shrink"):
            state.record("deposit", ("new potion", TVAL_POTION, 99), 100)
        self.assertEqual(len(json.loads(self.paths[0].read_text(encoding="utf-8"))["transactions"]), 4)

    def test_malformed_history_does_not_dead_latch_recall_or_get_lost(self):
        malformed = [
            "not an object",
            {"action": "deposit", "signature": ["broken"]},
            {"action": "discard", "signature": ["wrong action", TVAL_POTION, 2]},
        ]
        valid = {
            "action": "deposit", "signature": ["valid potion", TVAL_POTION, 3], "turn": 7,
        }
        self.paths[0].write_text(json.dumps({
            "version": 1, "dungeon_recall_count": 0,
            "transactions": [*malformed, valid],
        }), encoding="utf-8")

        state = self.state()
        self.assertFalse(state.note_dungeon_recall())
        saved = json.loads(self.paths[0].read_text(encoding="utf-8"))["transactions"]
        self.assertEqual(saved, [*malformed, valid])

    def test_environment_override_is_policy_default_and_unset_uses_cwd(self):
        override = Path(self.temporary.name) / "isolated"
        live = Path(self.temporary.name) / "live"
        live.mkdir()
        sentinel = live / "home-withdraw-history.jsonc"
        sentinel.write_text('{"sentinel": true}', encoding="utf-8")
        before = (sentinel.stat().st_mtime_ns, sentinel.read_bytes())
        with patch.dict(os.environ, {"HENGBOT_HOME_HISTORY_DIR": str(override)}), patch("pathlib.Path.cwd", return_value=live):
            state = HomeDisposalState.in_repo()
            self.assertEqual(state.history_path.parent, override)
            self.assertEqual(state.decisions_path, override / "home-disposal-decisions.jsonc")
            self.assertEqual(state.queue_path, override / "jsonlog" / "home-disposal-queue.json")
            self.assertEqual(state.events_path, override / "jsonlog" / "sol-events.jsonl")
            policy = HengbotPolicy()
            policy._home_disposal.note_dungeon_recall()
        self.assertTrue((override / "home-withdraw-history.jsonc").exists())
        self.assertEqual((sentinel.stat().st_mtime_ns, sentinel.read_bytes()), before)
        with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.cwd", return_value=live):
            self.assertEqual(HomeDisposalState.in_repo().history_path, sentinel)

    def test_bare_policy_unittest_does_not_touch_repository_history(self):
        repository = Path(__file__).resolve().parents[1]
        history = repository / "home-withdraw-history.jsonc"
        before = hashlib.sha256(history.read_bytes()).digest()
        environment = os.environ.copy()
        environment.pop("HENGBOT_HOME_HISTORY_DIR", None)
        source_root = repository / "src"
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(None, (str(source_root), environment.get("PYTHONPATH", "")))
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "test_policy.HistoryIsolationProbeTest.test_policy_history_writer_uses_fixture_default",
            ],
            cwd=repository / "tests",
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(hashlib.sha256(history.read_bytes()).digest(), before)

    def test_queue_is_real_data_shaped_and_collapses_duplicate_signatures(self):
        state = self.state()
        duplicate = self.candidate(count=4)
        armour = self.candidate(("a Long Sword", TVAL_SWORD, 5))
        state.emit_queue([duplicate, duplicate, armour], 321)
        queue = json.loads(self.paths[2].read_text(encoding="utf-8"))
        self.assertEqual(len(queue["items"]), 1)
        self.assertEqual(queue["items"][0]["count"], 4)
        self.assertEqual(queue["items"][0]["proposed_default_action"], "identify-then-sell")
        event = json.loads(self.paths[3].read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(event["event"], "question")

    def test_queue_read_failure_prevents_atomic_replacement(self):
        state = self.state()
        self.paths[2].parent.mkdir(parents=True)
        self.paths[2].write_text('{"old": true}', encoding="utf-8")
        before = self.paths[2].read_bytes()
        with patch.object(state, "_read_json", side_effect=HomeDisposalReadError("locked")):
            with self.assertRaises(HomeDisposalReadError):
                state.emit_queue([self.candidate()], 321)
        self.assertEqual(self.paths[2].read_bytes(), before)

    def test_queue_writer_uses_atomic_replace(self):
        state = self.state()
        real_replace = Path.replace
        targets = []

        def observe_replace(path, target):
            targets.append((path, target))
            return real_replace(path, target)

        with patch.object(Path, "replace", observe_replace):
            state.emit_queue([self.candidate()], 321)
        self.assertEqual(targets[-1][1], self.paths[2])
        self.assertNotEqual(targets[-1][0], self.paths[2])

    def test_decisions_hot_reload_and_keep_never_requeues(self):
        signature = ("a Potion", TVAL_POTION, 3)
        self.paths[1].write_text(json.dumps({"decisions": {signature_key(signature): "keep"}}), encoding="utf-8")
        state = self.state()
        self.assertEqual(state.decision(signature), "keep")
        self.assertEqual(state.pending([self.candidate(signature)]), [])
        self.paths[1].write_text(json.dumps({signature_key(signature): "destroy"}), encoding="utf-8")
        state.reload_decisions()
        self.assertEqual(state.decision(signature), "destroy")

    def test_approved_actions_and_store_routing_are_signature_scoped(self):
        decisions = {
            signature_key(("a Potion", TVAL_POTION, 3)): "sell",
            signature_key(("a Staff", TVAL_STAFF, 2)): "destroy",
        }
        self.paths[1].write_text(json.dumps(decisions), encoding="utf-8")
        state = self.state()
        policy = HengbotPolicy(home_disposal_state=state)
        potion = StoreItem("a", "a Potion", 1, TVAL_POTION, 3, 10, aware=False, known=False)
        staff = StoreItem("b", "a Staff", 1, TVAL_STAFF, 2, 10)
        undecided = StoreItem("c", "a Scroll", 1, TVAL_SCROLL, 9, 10)
        snapshot = SimpleNamespace(
            store=SimpleNamespace(store_type=STORE_HOME, items=(potion, staff, undecided)),
            inventory=(), turn=50,
        )
        policy._home_disposal_pass = True
        self.assertEqual(policy._home_disposal_home_key(snapshot), "\x1b")
        self.assertEqual(policy._home_disposal_pending[1], "sell")
        self.assertEqual(policy._home_disposal_store(policy._item_signature(potion)), STORE_ALCHEMIST)
        self.assertEqual(policy._home_disposal_store(policy._item_signature(staff)), STORE_MAGIC)
        self.assertEqual(policy._home_disposal_store(("food", TVAL_FOOD, 1)), STORE_GENERAL)

        carried = InventoryItem("a", "a Staff", 1, TVAL_STAFF, 2, True, True)
        policy._home_disposal_pending = (policy._item_signature(staff), "destroy")
        outside = SimpleNamespace(in_town=True, store=None, inventory=(carried,))
        self.assertEqual(policy._home_disposal_processing_key(outside), "01ka")
        self.assertEqual(policy.last_reason, "home-disposal:destroy-approved")

        policy._home_disposal_pending = (policy._item_signature(undecided), "keep")
        self.assertIsNone(policy._home_disposal_processing_key(SimpleNamespace(in_town=True, store=None, inventory=())))

    def test_identification_rename_keeps_approved_sale_attached(self):
        state = self.state()
        policy = HengbotPolicy(home_disposal_state=state)
        original = ("a Metallic Red Potion", TVAL_POTION, 7)
        identified = InventoryItem("d", "a Potion of Speed", 1, TVAL_POTION, 7, True, True)
        policy._home_disposal_pending = (original, "sell")
        snapshot = SimpleNamespace(inventory=(identified,))
        self.assertIs(policy._home_disposal_inventory_item(snapshot), identified)

    def test_destroy_waits_for_exact_approved_signature(self):
        state = self.state()
        policy = HengbotPolicy(home_disposal_state=state)
        approved = ("a Metallic Red Potion", TVAL_POTION, 7)
        undecided = InventoryItem("b", "a Cloudy Potion", 1, TVAL_POTION, 7, True, False)
        policy._home_disposal_pending = (approved, "destroy")

        outside = SimpleNamespace(in_town=True, store=None, inventory=(undecided,))
        self.assertIsNone(policy._home_disposal_processing_key(outside))
        self.assertEqual(policy._home_disposal_pending, (approved, "destroy"))

        home = SimpleNamespace(
            store=SimpleNamespace(store_type=STORE_HOME, items=()),
            inventory=(undecided,),
        )
        self.assertIsNone(policy._home_disposal_home_key(home))
        self.assertEqual(policy._home_disposal_pending, (approved, "destroy"))

        withdrawn = InventoryItem("c", approved[0], 1, approved[1], approved[2], True, False)
        appeared = SimpleNamespace(in_town=True, store=None, inventory=(undecided, withdrawn))
        self.assertEqual(policy._home_disposal_processing_key(appeared), "01kc")


if __name__ == "__main__":
    unittest.main()
