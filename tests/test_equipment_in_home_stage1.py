import json
import unittest
from pathlib import Path

from hengbot.home_visit import HomeVisitExecutor, HomeVisitKind, HomeVisitRequest
from tests.support.faithful_home import FaithfulHomeGame

ROOT = Path(__file__).resolve().parents[1]
INCIDENT = ROOT / "jsonlog" / "incident-20260914-town0-resume-2305" / "decisions.jsonl"
CAPTURE = ROOT / "jsonlog" / "live-screens" / "25-town0-home-equip-leave-loop.json"


class EquipmentInHomeArtifactFacts(unittest.TestCase):
    def test_rows_7_through_14_freeze_recorded_incident(self):
        rows = [json.loads(x) for x in INCIDENT.read_text(encoding="utf-8").splitlines()][6:14]
        self.assertEqual([r["decision_sequence"] for r in rows], list(range(6, 14)))
        self.assertEqual(sum(r["key"] == "\x1b" for r in rows), 2)
        self.assertEqual(sum(r["reason"] == "equipment-transaction:leave-home-to-equip" for r in rows), 2)
        # Three physical entries total: the initial acquisition and two
        # re-entries after the two recorded voluntary exits.
        self.assertEqual(sum(r["acquire_result"] == "granted-new" for r in rows), 3)
        self.assertEqual(sum(r["store_type"] == 7 for r in rows), 3)
        tx = rows[0]["equipment_optimization"]
        self.assertEqual(tx["transaction_next"], {"phase": "equip", "kind": "takeoff", "item_id": "equipped:0838f45775733b5d:0", "target_slot": "outer"})
        self.assertEqual(tx["transaction_target_loadout_id"], "8dfe4c9a8212d725")
        self.assertEqual(rows[0]["inventory"], {"used": 19, "free": 4})

    def test_post_stop_capture_is_explicitly_not_a_store_barrier(self):
        capture = json.loads(CAPTURE.read_text(encoding="utf-8"))
        state = capture["state"]["result"]
        self.assertNotIn("store", state)
        self.assertEqual(state["type"], "player_turn")

    def test_fake_models_prompt_consumption_reorder_refusal_and_overflow(self):
        worn = {"id": "worn", "slot": "outer"}; carried = {"id": "carry", "slot": "outer"}
        game = FaithfulHomeGame(pack=[carried], equipment={"outer": worn}, pages=[[{"id": "z"}]], pack_limit=1)
        game._consume("ta")
        self.assertNotIn("outer", game.equipment)
        self.assertEqual([x["id"] for x in game.pages[0]], ["worn", "z"])
        self.assertTrue(game.inside)
        full = FaithfulHomeGame(pack=[carried], equipment={"outer": worn}, pages=[[{"id": "z"}]], pack_limit=1, home_limit=1)
        full._consume("ta")
        self.assertFalse(full.inside)


class EquipmentInHomeBehaviorPins(unittest.TestCase):
    def _visit(self):
        visit = HomeVisitExecutor(3)
        visit.file(HomeVisitRequest(HomeVisitKind.EQUIPMENT_MUTATION, "equipment-transaction", ("target",)))
        visit.begin_approach(1); visit.post_entry(1); visit.observe_inside("page", 2)
        return visit

    @unittest.expectedFailure  # Stage 2 must remove: H1 persistent public visit.
    def test_h1_incident_finishes_with_one_exit_and_zero_reentries(self):
        visit = self._visit(); self.assertTrue(visit.record_operation("takeoff", ("old",), 2)); self.assertTrue(visit.record_operation("wear", ("target",), 3))

    @unittest.expectedFailure  # Stage 4 must remove: H2 prompt-owned ring suffix.
    def test_h2_pack_letter_is_not_store_letter_and_ring_suffix_is_prompt_owned(self):
        self.assertEqual(getattr(self._visit(), "prompt_owned_ring_suffix", None), True)

    @unittest.expectedFailure  # Stage 4 must remove: H3 full two-hand reconciliation.
    def test_h3_weapon_switch_confirms_both_hands(self):
        self.assertEqual(getattr(self._visit(), "confirmed_hand_slots", ()), ("main_hand", "sub_hand"))

    @unittest.expectedFailure  # Stage 4 must remove: H4 curse refusal outcome.
    def test_h4_curse_more_refusal_is_terminal_without_repost(self):
        self.assertEqual(getattr(self._visit(), "operation_outcome", None), "curse-refused")

    @unittest.expectedFailure  # Stage 2 must remove: H5 implicit shelving confirmation.
    def test_h5_takeoff_accepts_source_proven_home_overflow_destination(self):
        self.assertIn("home", getattr(self._visit(), "confirmation_destinations", ()))

    @unittest.expectedFailure  # Stage 2 must remove: H6 full refusal/rebind result.
    def test_h6_home_full_is_no_effect_and_invalidates_stale_address(self):
        self.assertEqual(getattr(self._visit(), "operation_outcome", None), "home-full")

    @unittest.expectedFailure  # Stage 4 must remove: H7 in-Home calibration lifecycle.
    def test_h7_calibration_strip_capture_restore_and_rearm_stays_inside(self):
        self.assertTrue(getattr(self._visit(), "calibration_completed_inside", False))

    @unittest.expectedFailure  # Stage 4 must remove: H8 owned viewer settlement.
    def test_h8_owned_knowledge_viewer_settles_once_or_stops_unknown_modal(self):
        self.assertEqual(getattr(self._visit(), "knowledge_settlements", 0), 1)

    @unittest.expectedFailure  # Stage 4 must remove: H9 operation-boundary priority.
    def test_h9_known_surplus_precedes_unknown_identification_and_ammo_topup(self):
        self.assertEqual(getattr(self._visit(), "next_operation", None), "deposit-known-surplus")

    @unittest.expectedFailure  # Stage 3 must remove: H10 entry WAIT and lifecycle.
    def test_h10_completed_operations_continue_visit_without_attempt_reset(self):
        visit = self._visit(); before = visit.attempts_used; visit.record_operation("take", ("target",), 2)
        self.assertEqual(visit.state.value, "inside"); self.assertEqual(visit.attempts_used, before)
