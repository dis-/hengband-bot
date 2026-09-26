"""Record-only S3 identity, promotion, and entry-wait regressions."""

from dataclasses import replace
import json
import pickle
from pathlib import Path
from types import SimpleNamespace
import unittest

from hengbot.claim_register import ClaimRegister, observe
from hengbot.claim_goal_typing import GOAL_TYPING, OPERATION_CLAIMS, STORE_ENTRY, goal_typing
from hengbot.claim_ladder import rung_of
from hengbot.ownership_metrics import s3_numbers
from hengbot.model import Position, STORE_HOME
from hengbot.equipment_transaction_planner import EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.home_visit import HomeOperationReport
from hengbot.policy_types import StoreVisit, TownErrandPlan, TownNeed
from hengbot.plan_handoff import is_plan_handoff
from test_ownership_s2b1_ladder import _Decisions


class S3aRecordTest(unittest.TestCase):
    def test_recorded_home_verdict_conflict_is_an_operation_pair(self):
        """Three rows extracted from the 17:30 ownership-claims capture."""
        rows = json.loads((Path(__file__).parent / "fixtures" /
                           "ownership-s3a-verdict-pair.json").read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            {row["decision_sequence"] for row in rows}, {33, 3776, 6627}
        )
        for row in rows:
            closed = row["closed_claim"]
            self.assertIn(closed["owner"], {"home-visit", "calibration"})
            self.assertEqual(closed["goal_kind"], "Observe")
            self.assertEqual((closed["closed"], closed["closed_reason"]),
                             ("complete", "home-withdraw-observed"))
            self.assertIn("home:atomic-withdraw-target-unobserved", row["reason"])

    def test_every_entry_wait_has_the_store_entry_source(self):
        waits = [row for row in GOAL_TYPING if row.prefix.endswith(":await-entry")]
        self.assertTrue(waits)
        self.assertEqual({row.content for row in waits}, {STORE_ENTRY})
        self.assertEqual(
            len({row.operation for row in OPERATION_CLAIMS}),
            len(OPERATION_CLAIMS),
        )

    def test_non_operation_home_reasons_have_explicit_types(self):
        from hengbot.town_arbiter import reason_owner_family
        for reason, kind in (
            ("home:queue-catalogue-shortage", "Terminal"),
            ("home:leave-for-pending-withdraw", "Terminal"),
            ("home:await-fresh-knowledge", "Terminal"),
            ("home:scan-step-off", "Reach"),
            ("home:scan-incomplete-open-page", "Terminal"),
            ("home:atomic-withdraw-page-probe", "Terminal"),
        ):
            with self.subTest(reason=reason):
                row = goal_typing(reason_owner_family(reason), reason)
                self.assertEqual(row.kind, kind)

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

    def test_home_scan_request_release_and_expiry(self):
        released = _Decisions()
        first = released.decide("home:request-knowledge-scan")
        released.policy.settle_home_knowledge_request()
        self.assertEqual(released.register.current.claim_id, first["claim_id"])
        self.assertEqual(released.register.current.closed, "release")
        expired = _Decisions()
        first = expired.decide("home:request-knowledge-scan")
        closed = None
        for _ in range(first["goal"]["within"] + 1):
            closed = expired.decide("home:request-knowledge-scan")["closed_claim"]
            if closed is not None:
                break
        self.assertEqual(closed["claim_id"], first["claim_id"])
        self.assertEqual(closed["closed"], "expired")

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
        visit.__dict__.pop("opened_producer_family")
        restored_visit = pickle.loads(pickle.dumps(visit))
        self.assertIsNone(restored_visit.claim_id)
        self.assertIsNone(restored_visit.claim_owner)
        self.assertIsNone(restored_visit.opened_producer_family)
        session = EquipmentTransactionSession(EquipmentTransactionPlan((), (), 0))
        restored_session = pickle.loads(pickle.dumps(session))
        self.assertIsNone(restored_session.opened_sequence)
        decisions = _Decisions()
        decisions.policy.__dict__.pop("_claim_active_operation_identity", None)
        restored_policy = pickle.loads(pickle.dumps(decisions.policy))
        self.assertIsNone(getattr(restored_policy, "_claim_active_operation_identity", None))
        decisions.policy = restored_policy
        self.assertEqual(decisions.decide("home:atomic-withdraw")["owner"],
                         "home-visit")

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

    def test_equipment_session_expires_at_existing_confirmation_limit(self):
        decisions = _Decisions()
        decisions.policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((), (), 0)
        )
        first = decisions.decide("equipment-transaction:equip")
        closed = None
        for _ in range(first["goal"]["within"] + 1):
            closed = decisions.decide("equipment-transaction:equip")["closed_claim"]
            if closed is not None:
                break
        self.assertEqual(closed["claim_id"], first["claim_id"])
        self.assertEqual(closed["closed"], "expired")

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

    def test_home_withdraw_post_turn_does_not_retarget(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="home-one-shot", purpose="withdraw", store_type=STORE_HOME,
            opened_sequence=4,
        )
        decisions.policy._home_atomic_withdraw_pending = (
            ("healing", 75, 37), 2, None, 1,
        )
        first = decisions.decide("home:atomic-withdraw")
        decisions.policy._home_atomic_withdraw_posted_turn = 123
        second = decisions.decide("home:atomic-withdraw")
        self.assertEqual(first["claim_id"], second["claim_id"])
        self.assertIsNone(second["violation"])

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

    def test_completed_visit_without_post_releases_operation(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="shop-one-shot", purpose="buy", store_type=1,
        )
        first = decisions.decide("shop:buy")
        decisions.policy._close_store_visit("completed")
        current = decisions.register.current
        self.assertEqual(current.claim_id, first["claim_id"])
        self.assertEqual((current.closed, current.closed_reason),
                         ("release", "visit-closed-no-operation"))

    def test_confirmed_effect_completes_even_without_post_flag(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="shop-one-shot", purpose="buy", store_type=1,
            operation_effect_observed=True,
        )
        first = decisions.decide("shop:buy")
        decisions.policy._close_store_visit("completed")
        current = decisions.register.current
        self.assertEqual(current.claim_id, first["claim_id"])
        self.assertEqual(current.closed, "complete")

    def test_shop_operation_identity_survives_post_sequence_change(self):
        decisions = _Decisions()
        visit = StoreVisit(
            owner="shop-one-shot", purpose="buy", store_type=1,
            opened_sequence=4, operation_key="pa1\r\x1b",
        )
        decisions.policy._store_visit = visit
        first = decisions.decide("shop:one-shot-buy", key="5")
        visit.operation_posted = True
        visit.posted_sequence = 12
        second = decisions.decide("shop:one-shot-in-flight", key="pa1")
        self.assertEqual(first["claim_id"], second["claim_id"])
        self.assertIsNone(second["violation"])
        visit.posted_sequence = None
        third = decisions.decide("shop:one-shot-in-flight", key="pa1")
        self.assertEqual(first["claim_id"], third["claim_id"])
        self.assertIsNone(third["violation"])

    def test_home_scan_pending_atomic_is_recorded(self):
        decisions = _Decisions()
        decisions.policy._home_atomic_withdraw_pending = ("item", 1, 1, 1)
        row = decisions.decide("home:request-knowledge-scan")
        self.assertTrue(row["scan-during-pending-atomic"])
        self.assertEqual(s3_numbers([row])["scan-during-pending-atomic"], 1)

    def test_town_errand_visit_owner_uses_opening_claim_family(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="town-errand", purpose="buy", store_type=1,
        )
        row = decisions.decide("shop:buy")
        self.assertIsNone(row["visit_owner_mismatch"])
        self.assertEqual(decisions.policy._store_visit.opened_producer_family,
                         "shop-buy")

    def test_town_errand_mapping_uses_arbiter_selected_producer(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="town-errand", purpose="buy", store_type=1,
        )
        decisions.policy._town_turn_arbiter.telemetry = {
            "producer_owner": "shop-buy",
        }
        row = decisions.decide("shop:travel", cell=decisions.cell(4))
        self.assertEqual(row["visit_owner_mismatch"]["visit_owner"], "shop-buy")
        self.assertEqual(row["visit_owner_mismatch"]["claim_owner"],
                         "store-router")

    def test_non_discardable_handoff_keeps_rewrite_violation(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="town-errand", purpose="buy", store_type=1,
        )
        decisions.policy._home_atomic_withdraw_pending = ("item", 1, 1, 1)
        first = decisions.decide("home:atomic-withdraw")
        self.assertTrue(first["non_discardable"])
        row = decisions.decide("shop:approach", cell=decisions.cell(3))
        if row["violation"] is not None:
            self.assertNotEqual(row["violation"]["kind"], "plan-handoff")

    def test_plan_handoff_requires_changed_plan_and_discardable_holder(self):
        common = dict(holder_family="store-router", next_family="home-scan",
                      holder_kind="Reach", same_rank=True)
        self.assertTrue(is_plan_handoff(
            **common, holder_non_discardable=False, plan_changed=True,
        ))
        self.assertFalse(is_plan_handoff(
            **common, holder_non_discardable=True, plan_changed=True,
        ))
        self.assertFalse(is_plan_handoff(
            **common, holder_non_discardable=False, plan_changed=False,
        ))

    def test_home_atomic_operation_complete_release_and_expire(self):
        for ending in ("complete", "release", "expired"):
            with self.subTest(ending=ending):
                decisions = _Decisions()
                entries = ((("healing", 75, 37), 3, 1),)
                decisions.policy._home_atomic_deposit_pending = (entries, None, 100, 0)
                first = decisions.decide("home:atomic-deposit")
                if ending == "complete":
                    decisions.policy._complete_observed_effect(
                        "home-deposit-observed", owners=("home-visit",),
                        sources=("store-operation",),
                    )
                elif ending == "release":
                    decisions.policy._release_claim_goal(
                        "target-unobserved", owners=("home-visit",),
                        kinds=("Observe",), sources=("store-operation",),
                    )
                else:
                    closed = None
                    for _ in range(first["goal"]["within"] + 1):
                        closed = decisions.decide("home:atomic-deposit")["closed_claim"]
                        if closed is not None:
                            break
                    self.assertEqual(closed["claim_id"], first["claim_id"])
                    self.assertEqual(closed["closed"], "expired")
                    continue
                claim = decisions.register.current
                self.assertEqual(claim.claim_id, first["claim_id"])
                self.assertEqual(claim.closed, ending)

    def test_home_errand_operation_complete_release_and_expire(self):
        for ending in ("complete", "release", "expired"):
            with self.subTest(ending=ending):
                decisions = _Decisions()
                first = decisions.decide("home-errand:withdraw")
                if ending == "complete":
                    decisions.policy._complete_observed_effect(
                        "home-errand-posted", owners=("home-errand",),
                        sources=("store-operation",),
                    )
                elif ending == "release":
                    decisions.policy._release_claim_goal(
                        "home-errand-stopped", owners=("home-errand",),
                        kinds=("Observe",), sources=("store-operation",),
                    )
                else:
                    closed = None
                    for _ in range(first["goal"]["within"] + 1):
                        closed = decisions.decide("home-errand:withdraw")["closed_claim"]
                        if closed is not None:
                            break
                    self.assertEqual(closed["claim_id"], first["claim_id"])
                    self.assertEqual(closed["closed"], "expired")
                    continue
                self.assertEqual(decisions.register.current.claim_id, first["claim_id"])
                self.assertEqual(decisions.register.current.closed, ending)

    def test_calibration_session_complete_release_and_expire(self):
        for ending in ("complete", "release", "expired"):
            with self.subTest(ending=ending):
                decisions = _Decisions()
                session = EquipmentTransactionSession(
                    EquipmentTransactionPlan((), (), 0)
                )
                decisions.policy._equipment_transaction_session = session
                decisions.policy._calibration_session_target = session.target_loadout_id
                first = decisions.decide("calibration:restore-wield")
                self.assertEqual(first["goal"]["source"], "calibration")
                if ending == "complete":
                    decisions.policy._complete_observed_effect(
                        "calibration-restore-observed", owners=("calibration",),
                        sources=("calibration",),
                    )
                elif ending == "release":
                    decisions.policy._release_claim_goal(
                        "calibration-aborted", owners=("calibration",),
                        kinds=("Observe",), sources=("calibration",),
                    )
                else:
                    closed = None
                    for _ in range(first["goal"]["within"] + 1):
                        closed = decisions.decide("calibration:restore-wield")["closed_claim"]
                        if closed is not None:
                            break
                    self.assertEqual(closed["claim_id"], first["claim_id"])
                    self.assertEqual(closed["closed"], "expired")
                    continue
                self.assertEqual(decisions.register.current.claim_id, first["claim_id"])
                self.assertEqual(decisions.register.current.closed, ending)

    def test_completed_claim_conflicting_with_failed_verdict_is_counted(self):
        decisions = _Decisions()
        decisions.policy._home_visit.operation = ("withdraw", "same-item")
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
        decisions.policy._home_visit.operation = ("withdraw", "same-item")
        first = decisions.decide("home:atomic-withdraw")
        decisions.register.complete("home-withdraw-observed")
        decisions.decide("shop:approach", cell=decisions.cell(4))
        verdict = decisions.decide("home:atomic-withdraw-target-unobserved")
        self.assertEqual(
            verdict["claim_verdict_conflict"]["claim_id"], first["claim_id"]
        )

    def test_failed_verdict_for_another_operation_is_not_conflict(self):
        decisions = _Decisions()
        decisions.policy._home_visit.operation = ("withdraw", "first-item")
        decisions.decide("home:atomic-withdraw")
        decisions.register.complete("home-withdraw-observed")
        decisions.policy._home_visit.operation = ("withdraw", "second-item")
        row = decisions.decide("home:atomic-withdraw-target-unobserved")
        self.assertIsNone(row["claim_verdict_conflict"])

    def test_failed_verdict_for_later_generation_is_not_conflict(self):
        decisions = _Decisions()
        visit = decisions.policy._home_visit
        visit.operation = ("withdraw", "same-item")
        visit.operation_generation = 10
        decisions.decide("home:atomic-withdraw")
        decisions.register.complete("home-withdraw-observed")
        visit.operation_generation = 11
        row = decisions.decide("home:atomic-withdraw-target-unobserved")
        self.assertIsNone(row["claim_verdict_conflict"])

    def test_completed_operation_report_matches_after_operation_clears(self):
        decisions = _Decisions()
        visit = decisions.policy._home_visit
        visit.operation = ("take", "same-item")
        visit.operation_generation = 10
        first = decisions.decide("home:atomic-withdraw")
        visit.operation = None
        visit.operation_generation = None
        decisions.decide("home:atomic-withdraw")
        decisions.register.complete("home-withdraw-observed")
        visit.operation_reports.append(HomeOperationReport(
            "take", "same-item", "completed", visit.visit_id, 10, 11,
        ))
        row = decisions.decide("home:atomic-withdraw-target-unobserved")
        self.assertEqual(row["claim_verdict_conflict"]["claim_id"],
                         first["claim_id"])


if __name__ == "__main__":
    unittest.main()
