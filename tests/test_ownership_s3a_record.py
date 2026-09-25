"""Record-only S3 identity, promotion, and entry-wait regressions."""

from dataclasses import replace
import pickle
from types import SimpleNamespace
import unittest

from hengbot.claim_register import ClaimRegister, observe
from hengbot.claim_goal_typing import GOAL_TYPING, OPERATION_CLAIMS, STORE_ENTRY
from hengbot.claim_ladder import rung_of
from hengbot.ownership_metrics import s3_numbers
from hengbot.model import Position, STORE_HOME
from hengbot.equipment_transaction_planner import EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.policy_types import StoreVisit, TownErrandPlan, TownNeed
from test_ownership_s2b1_ladder import _Decisions


class S3aRecordTest(unittest.TestCase):
    def test_every_entry_wait_has_the_store_entry_source(self):
        waits = [row for row in GOAL_TYPING if row.prefix.endswith(":await-entry")]
        self.assertTrue(waits)
        self.assertEqual({row.content for row in waits}, {STORE_ENTRY})
        self.assertEqual(
            len({row.operation for row in OPERATION_CLAIMS}),
            len(OPERATION_CLAIMS),
        )

    def test_non_discardable_promotion_keeps_identity_and_rank(self):
        register = ClaimRegister()
        goal = observe(("equipment", 7), 8, source="transaction")
        ordinary = rung_of("equipment-txn", "equipment-transaction:equip")
        protected = rung_of(
            "equipment-txn", "equipment-transaction:equip",
            non_discardable=True,
        )
        first = register.declare(
            "equipment-txn", goal, rank=ordinary.rank, rung=ordinary.name,
        )
        promoted = register.declare(
            "equipment-txn", goal, non_discardable=True,
            rank=protected.rank, rung=protected.name,
        )
        self.assertEqual(promoted.claim_id, first.claim_id)
        self.assertEqual((promoted.rank, promoted.rung),
                         (protected.rank, protected.name))
        self.assertTrue(promoted.non_discardable)
        continued = register.declare(
            "equipment-txn", goal, rank=ordinary.rank, rung=ordinary.name,
        )
        self.assertEqual(continued.claim_id, first.claim_id)
        self.assertTrue(continued.non_discardable)
        self.assertEqual(continued.rank, protected.rank)
        unranked = ClaimRegister()
        unranked.declare("equipment-txn", goal)
        self.assertEqual(
            unranked.declare(
                "equipment-txn", goal, non_discardable=True
            ).rank,
            protected.rank,
        )

    def test_store_entry_wait_completes_on_target_page(self):
        decisions = _Decisions()
        target = STORE_HOME
        entrance = Position(
            decisions.position.y + 2, decisions.position.x + 2
        )
        decisions.policy._store_visit = StoreVisit(
            owner="store-router", purpose="entry", store_type=target,
            goal=entrance,
        )
        decisions.policy._store_entry_wait_owner = target
        row = decisions.decide("shop:travel:await-entry")
        self.assertEqual(row["goal"]["source"], "store-entry")
        self.assertIn(str(target), row["goal"]["expectation"])
        board = replace(
            decisions.board, store=SimpleNamespace(store_type=target)
        )
        decisions.policy._claim_exit_completion(
            board, decisions.register.current, []
        )
        self.assertEqual(decisions.register.current.closed_reason, "entered-store")

    def test_store_entry_wait_suspends_under_higher_rung(self):
        decisions = _Decisions()
        decisions.policy._store_entry_wait_owner = STORE_HOME
        first = decisions.decide("shop:travel:await-entry")
        decisions.decide("town-progress-invariant:continue-observed-shop")
        self.assertIn(
            first["claim_id"],
            [claim.claim_id for claim in decisions.register.suspended],
        )

    def test_store_entry_wait_expires_at_existing_stuck_bound(self):
        decisions = _Decisions()
        decisions.policy._store_entry_wait_owner = STORE_HOME
        first = decisions.decide("shop:travel:await-entry")
        expired = None
        for _ in range(first["goal"]["within"]):
            row = decisions.decide("shop:travel:await-entry")
            if row["closed_claim"] is not None:
                expired = row["closed_claim"]
                break
        self.assertIsNotNone(expired)
        self.assertEqual(expired["claim_id"], first["claim_id"])
        self.assertEqual(expired["closed"], "expired")

    def test_abandoned_entry_wait_releases_before_terminal(self):
        decisions = _Decisions()
        decisions.policy._store_entry_wait_owner = STORE_HOME
        first = decisions.decide("equipment-transaction:travel-home:await-entry")
        row = decisions.decide("equipment-transaction:withdraw-missing")
        self.assertEqual(row["closed_claim"]["claim_id"], first["claim_id"])
        self.assertEqual(row["closed_claim"]["closed"], "release")
        self.assertIsNone(row["violation"])

    def test_recall_step_off_keeps_floor_change_claim(self):
        decisions = _Decisions()
        first = decisions.decide("town:recall-to-alt-dungeon")
        step_off = decisions.decide("town:wait-recall-step-off",
                                    cell=decisions.cell(1))
        self.assertEqual(first["claim_id"], step_off["claim_id"])
        self.assertEqual(step_off["goal"]["source"], "floor-change")
        self.assertIsNone(step_off["violation"])

    def test_home_scan_completes_on_catalogue_adoption(self):
        decisions = _Decisions()
        first = decisions.decide("home:request-knowledge-scan")
        decisions.policy._adopt_home_catalogue(())
        self.assertEqual(decisions.register.current.claim_id, first["claim_id"])
        self.assertEqual(decisions.register.current.closed_reason,
                         "home-knowledge-current")

    def test_staged_prompt_tail_is_non_discardable_until_posted(self):
        decisions = _Decisions()
        decisions.policy._staged_prompt_chain = {
            "owner": "identify:dungeon-equipment", "key": "uqt",
            "sequence": 1, "turn": decisions.board.turn, "gates":
            ((1, ("source",)), (2, ("target",))),
        }
        row = decisions.decide("identify:dungeon-equipment", key="uqt")
        self.assertEqual(row["goal"]["kind"], "Observe")
        self.assertTrue(row["non_discardable"])
        decisions.policy.commit_staged_prompt_chain({"outcome": "released"})
        self.assertEqual(decisions.register.current.closed_reason,
                         "staged-tail-posted")

    def test_store_operation_identity_ignores_next_step_key(self):
        decisions = _Decisions()
        visit = StoreVisit(
            owner="shop-one-shot", purpose="buy", store_type=1,
            operation_posted=True, operation_key="pa1\r\x1b",
            posted_sequence=12,
        )
        decisions.policy._store_visit = visit
        first = decisions.decide("shop:one-shot-buy", key="5")
        second = decisions.decide("shop:buy", key="pa1")
        self.assertEqual(first["claim_id"], second["claim_id"])
        self.assertEqual(visit.claim_id, second["claim_id"])
        self.assertEqual(visit.claim_owner, "shop-buy")

    def test_visit_alias_mismatch_is_recorded_without_changing_owner(self):
        decisions = _Decisions()
        visit = StoreVisit(
            owner="recovered-store-context", purpose="buy", store_type=1,
            operation_posted=True, operation_key="pa1\r\x1b",
            posted_sequence=12,
        )
        decisions.policy._store_visit = visit
        row = decisions.decide("shop:one-shot-buy")
        self.assertEqual(row["visit_owner_mismatch"]["visit_owner"],
                         "recovered-store-context")
        self.assertEqual(row["visit_owner_mismatch"]["claim_owner"], "shop-buy")
        self.assertEqual(visit.owner, "recovered-store-context")
        self.assertEqual(s3_numbers([row])["visit_owner_mismatch"], 1)
        import ownership_metrics_report
        report = "\n".join(ownership_metrics_report.claim_report([row], None))
        self.assertRegex(report, r"visit_owner_mismatch\s+1")
        self.assertIn("claim_verdict_conflict", report)
        self.assertIn("plan_rebuild_deferred", report)

    def test_old_checkpoint_defaults_for_new_record_fields(self):
        visit = StoreVisit(owner="store-router", purpose="visit", store_type=1)
        visit.__dict__.pop("claim_id")
        visit.__dict__.pop("claim_owner")
        restored_visit = pickle.loads(pickle.dumps(visit))
        self.assertIsNone(restored_visit.claim_id)
        self.assertIsNone(restored_visit.claim_owner)
        session = EquipmentTransactionSession(EquipmentTransactionPlan((), (), 0))
        restored_session = pickle.loads(pickle.dumps(session))
        self.assertIsNone(restored_session.opened_sequence)

    def test_plan_handoff_remains_a_violation(self):
        decisions = _Decisions()
        first = decisions.decide("shop:approach", cell=decisions.cell(5))
        second = decisions.decide("home:request-knowledge-scan")
        self.assertEqual(second["violation"]["kind"], "plan-handoff")
        self.assertEqual(second["violation"]["claim_id"], first["claim_id"])
        self.assertEqual(s3_numbers([second])["plan_handoff"], 1)

    def test_plan_rebuild_wanting_a_new_first_stop_is_counted(self):
        decisions = _Decisions()
        decisions.decide("shop:approach", cell=decisions.cell(5))
        decisions.policy._town_errand_plan = TownErrandPlan([1])
        decisions.policy._decision_plan_rebuild_deferred = 0
        plan = decisions.policy._build_town_errand_plan(
            decisions.board, [TownNeed(STORE_HOME, "knowledge", "ordinary")]
        )
        self.assertEqual(plan.stops, [STORE_HOME])
        self.assertEqual(decisions.policy._decision_plan_rebuild_deferred, 1)
        self.assertEqual(decisions.policy._town_errand_plan.stops, [1])

    def test_equipment_session_keeps_claim_as_owned_items_change(self):
        decisions = _Decisions()
        decisions.policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((), (), 0)
        )
        first = decisions.decide("equipment-transaction:equip")
        decisions.policy._equipment_transaction_owned_items = [("item-a", "main")]
        promoted = decisions.decide("equipment-transaction:equip")
        decisions.policy._equipment_transaction_owned_items.append(("item-b", "sub"))
        continued = decisions.decide("equipment-transaction:equip")
        self.assertEqual(
            (first["claim_id"], promoted["claim_id"]),
            (continued["claim_id"], continued["claim_id"]),
        )
        self.assertFalse(first["non_discardable"])
        self.assertTrue(promoted["non_discardable"])
        self.assertEqual(promoted["goal"], continued["goal"])

    def test_replaced_equipment_session_releases_old_claim_before_new_one(self):
        decisions = _Decisions()
        plan = EquipmentTransactionPlan((), (), 0)
        decisions.policy._equipment_transaction_session = EquipmentTransactionSession(plan)
        first = decisions.decide("equipment-transaction:equip")
        decisions.policy._equipment_transaction_session = EquipmentTransactionSession(plan)
        second = decisions.decide("equipment-transaction:equip")
        self.assertNotEqual(first["claim_id"], second["claim_id"])
        self.assertEqual(second["closed_claim"]["closed_reason"],
                         "abandoned:session-replaced")
        self.assertIsNone(second["violation"])

    def test_equipment_approach_is_a_step_of_the_open_session(self):
        decisions = _Decisions()
        decisions.policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((), (), 0)
        )
        first = decisions.decide("equipment-transaction:equip")
        approach = decisions.decide(
            "equipment-transaction:approach-home", cell=decisions.cell(4)
        )
        self.assertEqual(approach["claim_id"], first["claim_id"])
        self.assertEqual(approach["goal"]["kind"], "Observe")
        self.assertIsNone(approach["violation"])

    def test_home_atomic_wait_counter_does_not_retarget(self):
        decisions = _Decisions()
        entries = ((("healing", 75, 37), 3, 1),)
        decisions.policy._home_atomic_deposit_pending = (entries, None, 100, 0)
        first = decisions.decide("home:atomic-deposit")
        decisions.policy._home_atomic_deposit_pending = (entries, None, 100, 1)
        continued = decisions.decide("home:atomic-deposit")
        self.assertEqual(first["claim_id"], continued["claim_id"])
        self.assertTrue(continued["non_discardable"])
        self.assertIsNone(continued["violation"])

    def test_completed_visit_without_effect_expires_its_operation(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="shop-one-shot", purpose="buy", store_type=1,
            operation_posted=True, operation_key="pa1\r\x1b",
            posted_sequence=7,
        )
        first = decisions.decide("shop:one-shot-buy")
        decisions.policy._close_store_visit("completed")
        current = decisions.register.current
        self.assertEqual(current.claim_id, first["claim_id"])
        self.assertEqual((current.closed, current.closed_reason),
                         ("expired", "completed-unobserved"))

    def test_completed_claim_conflicting_with_failed_verdict_is_counted(self):
        decisions = _Decisions()
        first = decisions.decide("home:atomic-withdraw")
        decisions.register.complete("home-withdraw-observed")
        second = decisions.decide("home:atomic-withdraw-target-unobserved")
        conflict = second["claim_verdict_conflict"]
        self.assertEqual(conflict["claim_id"], first["claim_id"])
        self.assertEqual(conflict["claim_ending"], "complete")
        self.assertEqual(conflict["verdict"], "target-unobserved")
        self.assertEqual(s3_numbers([second])["claim_verdict_conflict"], 1)

    def test_conflict_survives_one_intervening_decision_in_same_visit(self):
        decisions = _Decisions()
        first = decisions.decide("home:atomic-withdraw")
        decisions.register.complete("home-withdraw-observed")
        decisions.decide("shop:approach", cell=decisions.cell(4))
        verdict = decisions.decide("home:atomic-withdraw-target-unobserved")
        self.assertEqual(
            verdict["claim_verdict_conflict"]["claim_id"], first["claim_id"]
        )


if __name__ == "__main__":
    unittest.main()
