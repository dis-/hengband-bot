import tests  # noqa: F401
import json
import pickle
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.policy import HengbotPolicy
from hengbot.policy_state import normalize_policy_state
from hengbot.policy_calibration import LegacyCalibrationDebtError, refuse_legacy_calibration_debt


class CalibrationCheckpointTest(unittest.TestCase):
    def test_empty_upgrade_has_exact_fresh_key_set_and_is_idempotent(self):
        fresh = HengbotPolicy(monrace_knowledge={})
        restored = HengbotPolicy.__new__(HengbotPolicy)
        normalize_policy_state(restored)
        self.assertEqual(set(vars(restored)), set(vars(fresh)))
        before = pickle.dumps(restored)
        normalize_policy_state(restored)
        self.assertEqual(pickle.dumps(restored), before)
        self.assertEqual(set(vars(pickle.loads(before))), set(vars(fresh)))

    def test_each_old_debt_is_named_and_never_executed(self):
        for name, value in (("_calibration_phase", "deposit"),
                            ("_calibration_suspended_phase", "strip"),
                            ("_calibration_stripped_unrestored", True),
                            ("_calibration_restore_signatures", [("oil", 77, 0)])):
            with self.subTest(name=name), self.assertRaisesRegex(LegacyCalibrationDebtError, name):
                refuse_legacy_calibration_debt({name: value})
        with TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            original = json.dumps({"redress_obligation": [["body", "identity"]]})
            path.write_text(original)
            with self.assertRaisesRegex(LegacyCalibrationDebtError, "redress_obligation"):
                refuse_legacy_calibration_debt({}, path)
            self.assertEqual(path.read_text(), original)

    def test_retired_home_visit_and_claim_restore_and_are_normalized_away(self):
        # Old checkpoints and recordings keep deciding: a retired value
        # unpickles to a pseudo-member that no live member equals, and the
        # shared upgrade drops it.  Nothing raises while restoring.
        from hengbot.claim_register import Claim, ClaimOwner, Goal
        from hengbot.home_visit import HomeVisitKind, HomeVisitRequest, HomeVisitState
        from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
        from hengbot.retired_values import is_retired
        restore_kind = HomeVisitKind("calibration-restore")
        family = ClaimOwner("calibration")
        self.assertTrue(is_retired(restore_kind) and is_retired(family))
        self.assertNotIn(restore_kind, list(HomeVisitKind))
        self.assertNotIn(family, list(ClaimOwner))
        policy = HengbotPolicy(monrace_knowledge={})
        visit = policy._home_visit
        visit.request = HomeVisitRequest(restore_kind, "calibration")
        visit.state = HomeVisitState.OPERATING
        visit.operation = ("take", ("oil", 77, 0))
        visit.queued.append(HomeVisitRequest(restore_kind, "calibration"))
        visit.queued.append(HomeVisitRequest(HomeVisitKind.SCAN, "home-scan"))
        visit.previous_completed_delta = (1, ("oil", 77, 0), restore_kind, "calibration")
        register = policy._claim_register
        register._claim = Claim(claim_id=7, owner=family, goal=Goal(kind="Observe"))
        register._ended.append(Claim(claim_id=6, owner=family, goal=Goal(kind="Observe")))
        policy.decision_claim = register._claim
        policy._calibration_phase = "restore-equip"
        policy._calibration_stripped_unrestored = True
        policy._calibration_restore_signatures = [("oil", 77, 0)]
        policy._home_atomic_withdraw_pending = (("oil", 77, 0), 0, None, 1, ((("oil", 77, 0), 0, None, 1, 0),))
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertEqual(restored._home_visit.state, HomeVisitState.IDLE)
        self.assertIsNone(restored._home_visit.request)
        self.assertIsNone(restored._home_visit.operation)
        self.assertEqual([r.kind for r in restored._home_visit.queued], [HomeVisitKind.SCAN])
        self.assertIsNone(restored._home_visit.previous_completed_delta)
        self.assertIsNone(restored._claim_register._claim)
        self.assertEqual(restored._claim_register._ended, [])
        self.assertIsNone(restored.decision_claim)
        self.assertIsNone(restored._home_atomic_withdraw_pending)
        for name in ("_calibration_phase", "_calibration_stripped_unrestored",
                     "_calibration_restore_signatures"):
            self.assertNotIn(name, vars(restored))
        fresh = set(vars(HengbotPolicy(monrace_knowledge={})))
        self.assertEqual(fresh - set(vars(restored)), set())

    def test_current_version_checkpoint_restores_every_transient_name(self):
        # A checkpoint omits per-decision derivations; restoring one taken
        # from a current-version policy must recreate every one of them.
        from hengbot.latch_onset_capture import (
            _CAPTURE_STATE_NAMES, checkpoint, restore_checkpoint)
        policy = HengbotPolicy(monrace_knowledge={})
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        fresh = set(vars(HengbotPolicy(monrace_knowledge={})))
        for name in ("_town_fact_snapshot", "_remembered_grid_sources",
                     "_remembered_grid_signatures", "_map_predicate_snapshot",
                     "_threat_prediction_memo", "_decision_input_snapshot",
                     "_equipment_mutation_counted_board", "_policy_state_version"):
            self.assertIn(name, vars(restored))
        self.assertEqual(fresh - set(vars(restored)), set())
        self.assertEqual((fresh & _CAPTURE_STATE_NAMES) - set(vars(restored)), set())
        # A manual __dict__ restore of the same state upgrades on first use.
        manual = HengbotPolicy.__new__(HengbotPolicy)
        manual.__dict__.update(pickle.loads(__import__("base64").b64decode(checkpoint(policy))))
        manual._monrace_knowledge = {}
        normalize_policy_state(manual)
        self.assertEqual(fresh - set(vars(manual)), set())

    def test_persisted_debt_never_raises_after_startup(self):
        # Review P3: only the CLI's startup configuration refuses; observing,
        # validating and persisting never raise and never erase the debt.
        from hengbot.warrior_optimization import (
            CharacterCalibration, save_character_calibration)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "character-calibration.json"
            original = json.dumps({"redress_obligation": [["body", "identity"]]})
            path.write_text(original)
            calibration = CharacterCalibration(
                race_id=0, class_id=0, personality_id=0, level=1,
                stat_cur=(10,) * 6, base_stats=(10,) * 6, base_hp=10,
                base_ac_bonus=0, intrinsic_abilities=frozenset())
            save_character_calibration(path, calibration)
            self.assertEqual(path.read_text(), original)
            policy = HengbotPolicy(monrace_knowledge={})
            policy._character_calibration_path = path
            from hengbot.model import parse_snapshot
            fixtures = Path(__file__).parent / "fixtures/calib-equivalence"
            data = json.loads((fixtures / "0917-equipped.json").read_text(encoding="utf-8"))
            self.assertIsNone(policy._validated_character_calibration(parse_snapshot(data, {})))
            self.assertEqual(path.read_text(), original)

    def test_v2_upgrade_removes_inactive_strip_fields_and_supplies_new_defaults(self):
        policy = HengbotPolicy(monrace_knowledge={})
        policy._policy_state_version = 2
        del policy._execution_pending_post
        policy._calibration_phase = None
        policy._calibration_restore_signatures = []
        normalize_policy_state(policy)
        self.assertEqual(set(vars(policy)), set(vars(HengbotPolicy(monrace_knowledge={}))))


class RestoredCalibrationBoundaryTest(unittest.TestCase):
    """Review P2/P3 of the merge: a restore never continues the strip and
    never keeps constants this process did not observe."""

    @staticmethod
    def _session(prefix):
        from hengbot.equipment_transaction_planner import (
            EquipmentTransaction, EquipmentTransactionPlan)
        from hengbot.equipment_transaction_session import EquipmentTransactionSession
        actions = tuple(
            EquipmentTransaction("equip", "takeoff", f"{prefix}{slot}", slot,
                                 f"identity-{slot}", f"move-{slot}")
            for slot in ("body", "head", "feet"))
        session = EquipmentTransactionSession(EquipmentTransactionPlan(actions, (), 20))
        session.index = 1  # mid-takeoff: one item already off
        return session

    def test_restored_strip_session_mid_takeoff_is_cancelled(self):
        from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
        for marker in ("target", "action-id"):
            with self.subTest(marker=marker):
                policy = HengbotPolicy(monrace_knowledge={})
                session = self._session("calibration:" if marker == "action-id" else "x:")
                policy._equipment_transaction_session = session
                policy._equipment_transaction_prepared_key = "tb"
                policy._calibration_phase = "strip"
                policy._calibration_stripped_unrestored = True
                if marker == "target":
                    policy._calibration_session_target = session.target_loadout_id
                policy._open_execution_delegation(
                    "calibration", "equipment-txn", ("session", "strip"),
                    ("calibration", "strip"), "observed-takeoffs", "budget")
                restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
                self.assertIsNone(restored._equipment_transaction_session)
                self.assertIsNone(restored._equipment_transaction_prepared_key)
                self.assertFalse(any(record.parent_family == "calibration"
                                     for record in restored._execution_delegations))
                self.assertNotIn("_calibration_phase", vars(restored))

    def test_ordinary_equipment_session_survives_restore(self):
        from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
        policy = HengbotPolicy(monrace_knowledge={})
        policy._equipment_transaction_session = self._session("pack:")
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertIsNotNone(restored._equipment_transaction_session)
        self.assertEqual(restored._equipment_transaction_session.index, 1)

    def test_restore_drops_constants_this_process_did_not_observe(self):
        from dataclasses import replace
        from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
        from hengbot.policy_calibration import process_calibration_session_id
        from hengbot.warrior_optimization import CharacterCalibration
        legacy = CharacterCalibration(
            race_id=0, class_id=0, personality_id=0, level=1,
            stat_cur=(10,) * 6, base_stats=(10,) * 6, base_hp=10,
            base_ac_bonus=0, intrinsic_abilities=frozenset())
        current = replace(legacy, schema_version=2, source="equipped-c-screen",
                          session_id=process_calibration_session_id())
        foreign = replace(current, session_id="another-process")
        for calibration, kept in ((legacy, False), (foreign, False), (current, True)):
            with self.subTest(schema=calibration.schema_version,
                              session=calibration.session_id[:8]):
                policy = HengbotPolicy(monrace_knowledge={})
                policy._character_calibration = calibration
                policy._character_calibration_loaded = True
                policy._equipment_optimization_signature = ("signature",)
                policy._confirmed_loadout_loaded = True
                policy._calibration_session_id = "recorded-process"
                state = pickle.loads(__import__("base64").b64decode(checkpoint(policy)))
                restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
                self.assertEqual(restored._calibration_session_id,
                                 process_calibration_session_id())
                self.assertEqual(state["_calibration_session_id"], "recorded-process")
                if kept:
                    self.assertEqual(restored._character_calibration, calibration)
                else:
                    self.assertIsNone(restored._character_calibration)
                    self.assertFalse(restored._character_calibration_loaded)
                    self.assertIsNone(restored._equipment_optimization_signature)
                    self.assertIsNone(restored._confirmed_loadout)
                    self.assertFalse(restored._confirmed_loadout_loaded)
