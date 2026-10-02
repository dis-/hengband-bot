import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import ast
import base64
import gzip
import hashlib
import inspect
import json
import pickle
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import hengbot.equipment_mutation as equipment_mutation_module
import hengbot.policy as policy_module
import hengbot.policy_calibration as policy_calibration_module
from hengbot.cli import POLICY_FINAL_STOP_REASONS
from hengbot.cli import _dispatch_response_lines
from hengbot.equipment_optimizer import (
    OwnedEquipment,
    equipment_identity,
    equipment_move_identity,
)
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.model import (
    GridState,
    PLAYER_CLASS_WARRIOR,
    Position,
    STORE_ALCHEMIST,
    STORE_HOME,
    STORE_TEMPLE,
    SV_LITE_FEANOR,
    SV_LITE_LANTERN,
    SV_POTION_CURE_CRITICAL,
    SV_POTION_RESTORE_CON,
    SV_SCROLL_IDENTIFY,
    SV_SCROLL_REMOVE_CURSE,
    SV_STAFF_IDENTIFY,
    Snapshot,
    StoreState,
    TVAL_LITE,
    TVAL_POTION,
    TVAL_RING,
    TVAL_SCROLL,
    TVAL_STAFF,
    TVAL_SWORD,
    parse_snapshot,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy, STORE_STUCK_LIMIT, WAIT_KEY
from hengbot.policy_constants import CHARACTER_DUMP_MACRO


class EquippedObservationLifecycleTest(unittest.TestCase):
    """Real response decoder and posted-dump lifecycle; no optimizer injection."""

    def envelope(self):
        fixtures = Path(__file__).parent / "fixtures/calib-equivalence"
        data = json.loads((fixtures / "0917-equipped.json").read_text(encoding="utf-8"))
        data["player"]["status_bar"] = []
        data["character"].update(race_title="Zombie", class_title="Warrior",
                                  personality_title="Mighty")
        return data

    def posted_policy(self, directory, *, preexisting=False):
        policy = HengbotPolicy(monrace_knowledge={})
        policy._character_dump_path = Path(directory) / "equipped.txt"
        policy._character_calibration_path = Path(directory) / "constants.json"
        raw = (Path(__file__).parent / "fixtures/calib-equivalence/0917-synthesized.txt").read_bytes()
        if preexisting:
            policy._character_dump_path.write_bytes(raw)
        policy._prepare_character_sheet_dump()
        self.assertTrue(policy.confirm_key_posted(CHARACTER_DUMP_MACRO))
        if not preexisting:
            policy._character_dump_path.write_bytes(raw)
        return policy

    def deliver(self, policy, data):
        """The C response, then the posted macro's completion boundary."""
        policy.observe_character_snapshot(data["character"], envelope=data)
        policy._complete_character_dump()

    def test_protocol3_character_response_uses_the_decision_board(self):
        """Live 2026-10-02 14:48-15:00: a protocol-3 C response is type
        ``character``, not a board; parsing it raised ProtocolSchemaError in
        choose_key and crashed the bot after every periodic dump."""
        with TemporaryDirectory() as directory:
            policy = self.posted_policy(directory)
            legacy = self.envelope()
            board = parse_snapshot(legacy, {})
            data = dict(legacy, protocol_version=3)
            policy.observe_character_snapshot(data["character"], envelope=data)
            policy._complete_character_dump(board)
            # The board was read (the protocol-2 fixture board lacks the
            # protocol-3 stat modifiers, so this board is rejected by name).
            self.assertEqual(policy._calibration_unavailable_reason,
                             "stat-modifiers-missing")
        with TemporaryDirectory() as directory:
            # Without a board the response is unavailable, never a crash (R1).
            policy = self.posted_policy(directory)
            data = dict(self.envelope(), protocol_version=3)
            policy.observe_character_snapshot(data["character"], envelope=data)
            policy._complete_character_dump()
            self.assertIsNone(policy._character_calibration)
            self.assertIn("ProtocolSchemaError", policy._calibration_unavailable_reason)

    def test_posted_dump_publishes_atomically_and_restore_drops_the_posted_request(self):
        with TemporaryDirectory() as directory:
            policy = self.posted_policy(directory)
            data = self.envelope()
            self.deliver(policy, data)
            record = policy._character_calibration
            self.assertIsNotNone(record)
            self.assertEqual((record.schema_version, record.base_stats, record.base_hp),
                             (2, (150, 3, 8, 48, 78, 11), 380))
            self.assertEqual(record.response_sequence, 1)
            self.assertIsNone(policy._equipment_transaction_session)
            saved = json.loads(policy._character_calibration_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["evidence_hash"], record.evidence_hash)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])
            fresh_keys = set(vars(HengbotPolicy(monrace_knowledge={})))
            # A copy (direct unpickle / deepcopy) decides as its original.
            copied = pickle.loads(pickle.dumps(policy))
            self.assertEqual(copied._character_calibration, record)
            self.assertEqual(copied._calibration_session_id, record.session_id)
            self.assertEqual(set(vars(copied)), fresh_keys)
            # A restored checkpoint never correlates the posting process's
            # request: the next periodic dump is its own.
            policy._prepare_character_sheet_dump()
            self.assertTrue(policy.confirm_key_posted(CHARACTER_DUMP_MACRO))
            policy.observe_character_snapshot(data["character"], envelope=data)
            self.assertIsNotNone(policy._calibration_dump_response)
            from hengbot.latch_onset_capture import checkpoint
            restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
            self.assertIsNone(restored._calibration_dump_pending)
            self.assertIsNone(restored._calibration_dump_prepared)
            self.assertIsNone(restored._calibration_dump_response)
            self.assertEqual(restored._character_calibration, record)
            # Every attribute of a fresh policy exists after the restore.
            self.assertEqual(fresh_keys - set(vars(restored)), set())

    def test_response_before_dump_file_is_read_at_the_completion_boundary(self):
        # Review P1: the game emits the C JSON on entering C, before it
        # accepts f and writes the file (cmd-draw.cpp do_cmd_player_status).
        with TemporaryDirectory() as directory:
            policy = HengbotPolicy(monrace_knowledge={})
            policy._character_dump_path = Path(directory) / "equipped.txt"
            policy._character_calibration_path = Path(directory) / "constants.json"
            policy._prepare_character_sheet_dump()
            self.assertTrue(policy.confirm_key_posted(CHARACTER_DUMP_MACRO))
            data = self.envelope()
            policy.observe_character_snapshot(data["character"], envelope=data)
            # The file does not exist yet: nothing is read, rejected or lost.
            self.assertFalse(policy._character_dump_path.exists())
            self.assertIsNone(policy._calibration_unavailable_reason)
            self.assertIsNone(policy._calibration_rejection)
            self.assertIsNone(policy._character_calibration)
            self.assertIsNotNone(policy._calibration_dump_pending)
            self.assertIsNotNone(policy._calibration_dump_response)
            # f + Enter writes the file; ESC returns to the main loop, whose
            # next board is the completion boundary.
            raw = (Path(__file__).parent
                   / "fixtures/calib-equivalence/0917-synthesized.txt").read_bytes()
            policy._character_dump_path.write_bytes(raw)
            policy.choose_key(parse_snapshot(data, {}))
            record = policy._character_calibration
            self.assertIsNotNone(record)
            self.assertEqual(record.base_stats, (150, 3, 8, 48, 78, 11))
            self.assertIsNone(policy._calibration_dump_pending)
            self.assertIsNone(policy._calibration_dump_response)
            self.assertTrue(policy._character_calibration_path.exists())

    def test_mutation_change_invalidates_the_cached_calibration(self):
        # Restored (review P5): the periodic C snapshot's mutation set, with
        # no dump pending, still invalidates the cached equipped constants.
        with TemporaryDirectory() as directory:
            policy = self.posted_policy(directory)
            data = self.envelope()
            self.deliver(policy, data)
            board = parse_snapshot(data, {})
            self.assertIsNotNone(policy._character_calibration)
            # An unchanged observation keeps the cache.
            self.assertIsNotNone(policy._validated_character_calibration(board))
            self.assertIsNone(policy._calibration_dump_pending)
            # A gained mutation reported by the next periodic snapshot
            # invalidates it.
            gained = (*(policy._mutation_signature or ()), 11)
            policy.observe_character_snapshot({"mutations": list(gained)})
            self.assertIsNone(policy._validated_character_calibration(board))
            self.assertIsNone(policy._character_calibration)

    def test_unposted_or_unchanged_file_never_publishes(self):
        with TemporaryDirectory() as directory:
            policy = self.posted_policy(directory, preexisting=True)
            data = self.envelope()
            self.deliver(policy, data)
            self.assertEqual(policy._calibration_unavailable_reason, "stale-dump-file")
            self.assertFalse(policy._character_calibration_path.exists())
            policy._calibration_unavailable_reason = None
            self.deliver(policy, data)
            self.assertIsNone(policy._character_calibration)
            self.assertIsNone(policy._calibration_unavailable_reason)

    def test_changed_old_file_and_unprepared_post_never_publish(self):
        import os
        for unprepared in (False, True):
            with self.subTest(unprepared=unprepared), TemporaryDirectory() as directory:
                policy = self.posted_policy(directory)
                if unprepared:
                    policy._calibration_dump_prepared = None
                    self.assertTrue(policy.confirm_key_posted(CHARACTER_DUMP_MACRO))
                    reason = "unprepared-character-dump"
                else:
                    # Different content/hash is insufficient if the file predates this request.
                    stamp = policy._calibration_dump_pending["started_ns"] - 1_000_000_000
                    os.utime(policy._character_dump_path, ns=(stamp, stamp))
                    reason = "stale-dump-file"
                data = self.envelope()
                self.deliver(policy, data)
                self.assertEqual(policy._calibration_unavailable_reason, reason)
                self.assertIsNone(policy._character_calibration)
                self.assertFalse(policy._character_calibration_path.exists())

    def test_unknown_effect_rejects_once_and_current_gear_can_depart(self):
        with TemporaryDirectory() as directory:
            policy = self.posted_policy(directory)
            data = self.envelope()
            data["player"]["status_bar"] = [{"key": "unimplemented-effect"}]
            self.deliver(policy, data)
            self.assertEqual(policy._calibration_unavailable_reason,
                             "unknown-timed-effect:unimplemented-effect")
            self.assertIsNone(policy._calibration_dump_pending)
            self.assertTrue(policy._equipment_departure_ready(parse_snapshot(data, {})))
            self.assertNotIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)

    def test_response_sequence_and_gear_identity_must_match(self):
        for change, reason in (("sequence", "uncorrelated-character-response"),
                               ("gear", "dump-equipment-mismatch")):
            with self.subTest(change=change), TemporaryDirectory() as directory:
                policy = self.posted_policy(directory)
                data = self.envelope()
                if change == "sequence":
                    policy._calibration_dump_pending["sequence"] = 10
                    data["sequence"] = 9
                else:
                    data["equipment"][0]["name"] = "Different weapon with identical numbers"
                self.deliver(policy, data)
                self.assertEqual(policy._calibration_unavailable_reason, reason)
                self.assertIsNone(policy._character_calibration)

try:
    from policy_fixtures import grid, hostile, item, player, store_item
except ModuleNotFoundError:
    from tests.policy_fixtures import grid, hostile, item, player, store_item


class EquippedCalibrationRegressionTest(unittest.TestCase):
    HOME = Position(10, 12)

    def _grids(self):
        grids = {
            Position(10, x): grid(10, x) for x in range(9, 14)
        }
        grids[self.HOME] = GridState(
            position=self.HOME, known=True, passable=True, wall=False,
            has_monster=False, has_down_stairs=False, has_up_stairs=False,
            unsafe=False, store_number=STORE_HOME,
        )
        return grids


    def _snapshot(self, *, inventory=(), equipment=(), monsters=(),
                  store=None, hp=200, max_hp=200):
        base = player(
            10, 10, class_id=PLAYER_CLASS_WARRIOR, level=12,
            hp=hp, max_hp=max_hp,
        )
        base = replace(
            base,
            race_id=3, personality_id=1, ac=10,
            stat_cur=(18, 10, 10, 17, 16, 9),
            stat_use=(20, 10, 10, 18, 17, 9),
        )
        return Snapshot(
            base,
            self._grids(),
            list(monsters),
            floor_key=(0, 0, 0),
            town_flag=True,
            inventory=list(inventory),
            equipment=list(equipment),
            store=store,
        )


    def _scan_complete_policy(self):
        policy = HengbotPolicy()
        policy._equipment_catalog.observe_home_page([])
        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        return policy


    def test_unactionable_home_identification_routes_when_home_unblocked(self):
        policy = self._scan_complete_policy()
        snapshot = self._snapshot()
        target = store_item("a", TVAL_SWORD, 1, name="Home blade")
        policy._identification_need = "normal"
        policy._identification_candidate = policy._item_signature(target)
        policy._equipment_catalog._home = {
            "target": OwnedEquipment("target", target, "home")
        }
        with patch.object(
            policy, "_identification_need_actionable", return_value=False
        ):
            store_type = policy._next_required_store_type(snapshot)

        self.assertEqual(store_type, STORE_HOME)
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)


    def test_blocked_unactionable_home_identification_retires_once(self):
        policy = self._scan_complete_policy()
        snapshot = self._snapshot()
        target = store_item("a", TVAL_SWORD, 1, name="Home blade")
        policy._identification_need = "normal"
        policy._identification_candidate = policy._item_signature(target)
        policy._equipment_catalog._home = {
            "target": OwnedEquipment("target", target, "home")
        }
        policy._town_visit_ledger.approach_fails[STORE_HOME] = (
            policy._town_store_visit_limit(STORE_HOME)
        )
        with patch.object(
            policy, "_identification_need_actionable", return_value=False
        ), patch.object(
            policy, "_town_terminal_transitions"
        ) as retire:
            store_type = policy._next_required_store_type(snapshot)

        retire.assert_called_once_with(snapshot)
        self.assertNotEqual(store_type, STORE_HOME)


    def test_entry_telemetry_does_not_change_public_decision(self):
        def fixture():
            policy = self._scan_complete_policy()
            snapshot = self._snapshot()
            return policy, snapshot

        control, snapshot = fixture()
        observed, observed_snapshot = fixture()

        control_key = control.choose_key(snapshot)
        observed.calibration_entry_state(observed_snapshot)
        observed.equipment_transaction_entry_state(observed_snapshot)
        observed_key = observed.choose_key(observed_snapshot)

        self.assertEqual(observed_key, control_key)
        self.assertEqual(observed.last_reason, control.last_reason)


    def test_departure_unsatisfiable_is_an_immediate_cli_final_stop(self):
        self.assertIn(
            "town:blocked:departure-unsatisfiable", POLICY_FINAL_STOP_REASONS
        )
