"""Record-only S3 identity, promotion, and entry-wait regressions."""

from dataclasses import replace
import ast
import hashlib
import json
import pickle
from pathlib import Path
from types import SimpleNamespace
import unittest
import tests  # noqa: F401  (bare runs stay isolated from runtime files)

from hengbot.claim_register import ClaimRegister, observe
from hengbot.claim_goal_typing import GOAL_TYPING, OPERATION_CLAIMS, STORE_ENTRY, goal_typing
from hengbot.claim_ladder import rung_of
from hengbot.ownership_metrics import read_records, s3_numbers
from hengbot.model import InventoryItem, Position, STORE_HOME
from hengbot.equipment_transaction_planner import EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.home_visit import HomeOperationReport
from hengbot.home_errand import HomeErrandRequest
from hengbot.policy_types import StoreVisit, TownErrandPlan, TownNeed
from hengbot.plan_handoff import is_plan_handoff
from test_ownership_s2b1_ladder import _Decisions


class S3aRecordTest(unittest.TestCase):
    def test_router_plan_stop_requester_is_recorded_per_reused_visit(self):
        decisions = _Decisions()
        visit = StoreVisit(
            owner="store-router", purpose="town-need", store_type=STORE_HOME,
            opened_sequence=1, opened_for_family="home-scan",
        )
        decisions.policy._store_visit = visit
        decisions.policy._request_store_trip(
            STORE_HOME, "home-visit", structure="router-plan-stop"
        )
        self.assertIs(decisions.policy._store_visit, visit)
        self.assertEqual(visit.opened_for_family, "home-visit")
        self.assertEqual(visit.request_structure, "router-plan-stop")
        restored = pickle.loads(pickle.dumps(decisions.policy))
        self.assertEqual(restored._store_visit.opened_for_family, "home-visit")
        self.assertEqual(restored._store_visit.request_structure,
                         "router-plan-stop")
        restored._store_visit.owner = "town-errand"
        restored._request_store_trip(STORE_HOME, "shop-buy")
        self.assertEqual(restored._store_visit.opened_for_family, "shop-buy")
        self.assertIsNone(restored._store_visit.request_structure)

    def test_router_plan_stop_names_only_unambiguous_family(self):
        decisions = _Decisions()
        policy = decisions.policy
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME], {STORE_HOME: ("weight-overload",)}
        )
        self.assertEqual(policy._router_plan_stop_family(None), "home-visit")
        policy._town_errand_plan.need_categories[STORE_HOME] = (
            "weight-overload", "identification-withdrawal"
        )
        self.assertIsNone(policy._router_plan_stop_family(None))
        policy._town_errand_plan.need_categories[STORE_HOME] = ("unknown-need",)
        self.assertIsNone(policy._router_plan_stop_family(None))

    def test_claim_recording_preserves_decision_attribution(self):
        decisions = _Decisions()
        decisions.policy.decision_attribution = "original-arbiter-owner"
        decisions.policy._store_visit = StoreVisit(
            owner="home-one-shot", purpose="deposit", store_type=STORE_HOME,
            opened_sequence=1, opened_producer_family="calibration",
        )
        decisions.policy._home_atomic_deposit_pending = ("item", 1)
        decisions.decide("home:atomic-deposit")
        self.assertEqual(decisions.policy.decision_attribution,
                         "original-arbiter-owner")

    def test_leave_confirmation_barrier_uses_visit_family(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="store-router", purpose="home", store_type=STORE_HOME,
            opened_sequence=1, opened_for_family="home-errand",
            claim_owner="home-errand", operation_producer_family="shop-buy",
        )
        barrier = decisions.decide("shop:await-leave-confirmation")
        self.assertEqual(barrier["owner"], "home-errand")

    def test_new_store_operation_during_unconfirmed_leave_is_recorded(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="store-router", purpose="home", store_type=STORE_HOME,
            opened_sequence=1, opened_for_family="shop-buy",
        )
        decisions.policy._store_leave_inflight = (1, 1, STORE_HOME)
        decisions.policy._home_errand.file(
            HomeErrandRequest(("weapon", 1, 2), 1, "test", "combat-weapon"),
            knowledge_current=False,
        )
        row = decisions.decide("home-errand:request-knowledge:combat-weapon")
        self.assertEqual(row["violation"]["kind"],
                         "leave-confirmation-interruption")
        self.assertEqual((row["violation"]["from"], row["violation"]["to"]),
                         ("shop-buy", "home-errand"))

    def test_recorded_home_verdict_conflict_is_an_operation_pair(self):
        """Run the detector with the recorded 10:22, 12:53, 17:30 verdicts.

        Source: C:/hengband/bot-client/jsonlog/ownership-claims.jsonl,
        lines 9056, 15691, 22386. The frozen source lines are checked by hash.
        """
        fixture = (Path(__file__).parent / "fixtures" /
                   "ownership-s3a-verdict-recorded.jsonl")
        # Git stores this JSONL with LF; accept either checkout line ending.
        frozen_bytes = fixture.read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(hashlib.sha256(frozen_bytes).hexdigest(),
                         "c7095d63e2a50bd006519c0f2a32d4266505988982da4ba72dfae3e6ea33e5e5")
        rows = read_records(fixture)
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
            decisions = _Decisions()
            decisions.policy._store_visit = StoreVisit(
                owner="home-one-shot", purpose="withdraw", store_type=STORE_HOME,
                opened_sequence=9, operation_key="take",
                opened_producer_family=closed["owner"],
            )
            decisions.policy._home_atomic_withdraw_pending = ("item", 1, 1, 1)
            visit = decisions.policy._home_visit
            visit.operation = ("take", f"recorded-{closed['claim_id']}")
            opened = decisions.decide("home:atomic-withdraw")
            self.assertEqual(opened["owner"], closed["owner"])
            decisions.register.complete("home-withdraw-observed")
            detected = decisions.decide(row["reason"])["claim_verdict_conflict"]
            self.assertEqual(detected["claim_id"], opened["claim_id"])
            self.assertEqual((detected["claim_ending"], detected["verdict"]),
                             ("complete", "target-unobserved"))

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

    def test_emitted_home_literals_do_not_use_the_catch_all(self):
        source = Path(__file__).parents[1] / "src" / "hengbot"
        for path in source.glob("*.py"):
            if path.name == "claim_goal_typing.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                reason = node.value
                if not reason.startswith("home:") or reason.endswith((":", "-")):
                    continue
                if path.name not in {"policy.py", "policy_home.py", "policy_quest.py", "policy_shop.py"}:
                    continue
                typed = [r for r in GOAL_TYPING
                         if r.family in {"home-visit", "home-scan"}
                         and reason.startswith(r.prefix)]
                self.assertTrue(typed, (path.name, node.lineno, reason))
                self.assertNotEqual(max(typed, key=lambda r: len(r.prefix)).prefix,
                                    "home:", (path.name, node.lineno, reason))

    def test_home_exit_continues_pending_deposit_claim(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="home-one-shot", purpose="deposit", store_type=STORE_HOME,
            opened_sequence=9, operation_key="dax",
        )
        decisions.policy._home_atomic_deposit_pending = (("item",), 1, 2)
        posted = decisions.decide("home:atomic-deposit")
        exit_row = decisions.decide("home:leave-after-one-operation")
        self.assertEqual(posted["claim_id"], exit_row["claim_id"])
        self.assertIsNone(exit_row["violation"])
        decisions.policy._claim_store_visit_closed(
            decisions.policy._store_visit, "completed", operation_posted=True
        )
        self.assertEqual(decisions.register.current.closed, "expired")
        self.assertEqual(decisions.register.current.closed_reason,
                         "completed-unobserved")

    def test_home_deposit_keeps_its_composing_family_during_transaction(self):
        decisions = _Decisions()
        decisions.policy._equipment_transaction_session = (
            EquipmentTransactionSession(EquipmentTransactionPlan((), (), 0))
        )
        decisions.policy._store_visit = StoreVisit(
            owner="home-one-shot", purpose="deposit", store_type=STORE_HOME,
            opened_sequence=9, operation_key="da",
            opened_producer_family="home-visit",
        )
        self.assertTrue(decisions.policy._compose_home_operation(
            decisions.board, "5da\x1b", "da", producer_family="home-visit"
        ))
        self.assertEqual(decisions.policy._store_visit.operation_producer_family,
                         "home-visit")
        decisions.policy._home_atomic_deposit_pending = (("item",), 1, 2)
        row = decisions.decide("home:atomic-deposit")
        self.assertEqual(row["owner"], "home-visit")

    def test_non_atomic_transaction_home_exit_uses_visit_requester(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="equipment-transaction", purpose="equipment-work",
            store_type=STORE_HOME,
        )
        row = decisions.decide("home:leave-after-one-operation")
        self.assertEqual(row["owner"], "equipment-txn")

    def test_router_opened_visit_records_transaction_operation_composer(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="store-router", purpose="home", store_type=STORE_HOME,
            opened_producer_family="store-router", opened_sequence=9,
        )
        self.assertTrue(decisions.policy._stage_home_operation(
            decisions.board, "da\x1b", producer_family="equipment-txn"
        ))
        decisions.policy._home_atomic_deposit_pending = (("item",), 1, 2)
        row = decisions.decide("home:atomic-deposit")
        self.assertEqual(row["owner"], "equipment-txn")

    def test_home_errand_request_has_own_identity_during_deposit(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="home-one-shot", purpose="deposit", store_type=STORE_HOME,
            opened_sequence=9, operation_key="dax",
        )
        decisions.policy._home_atomic_deposit_pending = (("item",), 1, 2)
        decisions.policy._home_errand.request = HomeErrandRequest(
            ("weapon", 1, 2), 1, "test", "request-knowledge"
        )
        deposit = decisions.decide("home:atomic-deposit")
        request = decisions.decide("home-errand:request-knowledge:combat-weapon")
        self.assertEqual(request["goal"]["expectation"][1:],
                         ["('weapon', 1, 2)", str(STORE_HOME), "errand"])
        self.assertIn("knowledge", request["goal"]["expectation"][0])
        self.assertNotEqual(deposit["goal"]["expectation"], request["goal"]["expectation"])
        self.assertTrue(request["scan-during-pending-atomic"])
        self.assertFalse(request["non_discardable"])

    def test_home_errand_knowledge_completes_after_the_decision(self):
        decisions = _Decisions()
        decisions.policy._home_errand.request = HomeErrandRequest(
            ("weapon", 1, 2), 1, "test", "request-knowledge"
        )
        decisions.policy._home_knowledge_current = False
        request = decisions.decide("home-errand:request-knowledge:combat-weapon")
        decisions.policy._claim_home_knowledge_observed = True
        next_row = decisions.decide("home-errand:filed:combat-weapon")
        self.assertEqual(next_row["closed_claim"]["claim_id"], request["claim_id"])
        self.assertEqual(next_row["closed_claim"]["closed"], "complete")
        self.assertEqual(next_row["closed_claim"]["closed_reason"],
                         "home-knowledge-current")
        self.assertFalse(decisions.policy._claim_home_knowledge_observed)

    def test_suspended_knowledge_request_completes_on_observed_response(self):
        decisions = _Decisions()
        request = HomeErrandRequest(
            ("weapon", 1, 2), 1, "test", "combat-weapon"
        )
        decisions.policy._home_errand.file(request, knowledge_current=False)
        held = decisions.decide("home-errand:request-knowledge:combat-weapon")
        decisions.decide("town:seek-shelter", cell=decisions.cell(4))
        decisions.policy._claim_home_knowledge_observed = True
        row = decisions.decide("town:seek-shelter", cell=decisions.cell(4))
        self.assertTrue(any(
            closed["claim_id"] == held["claim_id"]
            and closed["closed"] == "complete"
            for closed in row["suspended_closed"] or []
        ))
        self.assertFalse(decisions.policy._claim_home_knowledge_observed)

    def test_filed_home_purpose_duplicates_combat_restore(self):
        decisions = _Decisions()
        request = HomeErrandRequest(
            ("weapon", 1, 2), 1, "test", "combat-weapon"
        )
        decisions.policy._home_errand.file(request, knowledge_current=False)
        row = decisions.decide("town:restore-combat-weapon")
        duplicate = row["violation"]
        self.assertEqual(duplicate["kind"], "purpose-duplicate")
        self.assertEqual(row["purpose_duplicates"], [duplicate])
        self.assertEqual(duplicate["purpose"], ["combat-weapon", "main_hand"])
        self.assertEqual(duplicate["holders"][0]["request_identity"],
                         ["weapon", 1, 2])
        self.assertEqual([holder["family"] for holder in duplicate["holders"]],
                         ["home-errand", row["owner"]])

    def test_filed_combat_weapon_request_detects_no_teleport_replacement(self):
        decisions = _Decisions()
        decisions.policy._home_errand.file(
            HomeErrandRequest(("weapon", 1, 2), 1, "test", "combat-weapon"),
            knowledge_current=False,
        )
        row = decisions.decide("town:replace-no-teleport-weapon")
        self.assertEqual(row["purpose_duplicates"][0]["purpose"],
                         ["combat-weapon", "main_hand"])

    def test_purpose_duplicate_is_recorded_beside_transition_violation(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="home-one-shot", purpose="withdraw", store_type=STORE_HOME,
            opened_sequence=9, operation_key="ga",
        )
        decisions.policy._home_atomic_withdraw_pending = ("item", 1, 1, 1)
        decisions.decide("home:atomic-withdraw")
        decisions.policy._home_errand.file(
            HomeErrandRequest(("weapon", 1, 2), 1, "test", "combat-weapon"),
            knowledge_current=False,
        )
        row = decisions.decide("town:restore-combat-weapon")
        self.assertEqual(row["purpose_duplicates"][0]["kind"],
                         "purpose-duplicate")
        self.assertIsNotNone(row["violation"])
        self.assertNotEqual(row["violation"]["kind"], "purpose-duplicate")

    def test_filed_item_purposes_match_identification_and_experience_work(self):
        for purpose, reason, key in (
            ("identification", "identify:normal", "rba"),
            ("experience-potion", "experience:quaff", "qa"),
        ):
            with self.subTest(purpose=purpose):
                decisions = _Decisions()
                item = InventoryItem(
                    slot="a", name=purpose, count=1, tval=75, sval=1,
                    aware=True, known=True,
                )
                board = replace(decisions.board, inventory=(item,))
                signature = decisions.policy._item_signature(item)
                decisions.policy._home_errand.file(
                    HomeErrandRequest(signature, 1, "test", purpose),
                    knowledge_current=False,
                )
                row = decisions.decide(reason, board=board, key=key)
                self.assertEqual(row["purpose_duplicates"][0]["purpose"],
                                 [purpose, signature])

    def test_filed_item_does_not_duplicate_another_identification_target(self):
        decisions = _Decisions()
        filed = InventoryItem(slot="a", name="filed", count=1, tval=75,
                              sval=1, aware=True, known=True)
        other = InventoryItem(slot="c", name="other", count=1, tval=75,
                              sval=2, aware=True, known=True)
        board = replace(decisions.board, inventory=(filed, other))
        decisions.policy._home_errand.file(
            HomeErrandRequest(decisions.policy._item_signature(filed), 1,
                              "test", "identification"),
            knowledge_current=False,
        )
        row = decisions.decide("identify:normal", board=board, key="rbc\x1b")
        self.assertEqual(row["purpose_duplicates"], [])

    def test_town_damage_response_suspends_transaction_claim(self):
        decisions = _Decisions()
        session = EquipmentTransactionSession(EquipmentTransactionPlan((), (), 0))
        decisions.policy._equipment_transaction_session = session
        decisions.policy._calibration_session_target = session.target_loadout_id
        held = decisions.decide("calibration:restore-wield")
        shelter = decisions.decide("town:seek-shelter", cell=decisions.cell(4))
        self.assertTrue(shelter["survival"])
        self.assertIsNone(shelter["violation"])
        self.assertEqual(shelter["suspended_depth"], 1)
        resumed = decisions.decide("calibration:restore-wield")
        self.assertEqual(resumed["claim_id"], held["claim_id"])
        self.assertIsNone(resumed["violation"])
        self.assertEqual(resumed["closed_claim"]["closed_reason"],
                         "seek-shelter-trigger-gone")

    def test_transaction_entry_wait_keeps_its_separate_observation(self):
        decisions = _Decisions()
        decisions.policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((), (), 0)
        )
        transaction = decisions.decide("equipment-transaction:equip")
        wait = decisions.decide("equipment-transaction:travel-home:await-entry")
        self.assertEqual(transaction["goal"]["source"], "transaction")
        self.assertEqual(wait["goal"]["source"], "store-entry")
        self.assertIsNone(wait["violation"])
        self.assertEqual(wait["suspended_depth"], 1)
        self.assertFalse(wait["non_discardable"])

    def test_stale_transaction_identity_has_named_release(self):
        decisions = _Decisions()
        decisions.policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((), (), 0)
        )
        first = decisions.decide("equipment-transaction:equip")
        stale = decisions.decide(
            "equipment-transaction:stale-identity-invalidated:deposit:item"
        )
        self.assertEqual(stale["closed_claim"]["claim_id"], first["claim_id"])
        self.assertEqual(stale["closed_claim"]["closed"], "release")
        self.assertEqual(stale["closed_claim"]["closed_reason"],
                         "transaction-identity-stale")
        self.assertIsNone(stale["violation"])

    def test_second_transaction_is_recorded_as_contention(self):
        decisions = _Decisions()
        session = EquipmentTransactionSession(EquipmentTransactionPlan((), (), 0))
        decisions.policy._equipment_transaction_session = session
        decisions.policy._calibration_session_target = session.target_loadout_id
        decisions.policy._calibration_stripped_unrestored = True
        held = decisions.decide("calibration:restore-wield")
        self.assertTrue(held["non_discardable"])
        decisions.policy._calibration_session_target = None
        decisions.policy._equipment_transaction_owned_items = ["held-item"]
        next_row = decisions.decide("equipment-transaction:atomic-deposit")
        self.assertEqual(next_row["violation"]["kind"],
                         "transaction-contention")
        self.assertEqual(next_row["violation"]["claim_id"], held["claim_id"])

    def test_withdraw_identity_requires_the_home_visit(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="shop-one-shot", purpose="buy", store_type=1,
            opened_sequence=8, operation_key="pa1",
        )
        decisions.policy._home_atomic_withdraw_pending = ("item", 1, 1, 1)
        other_store = decisions.decide("home:atomic-withdraw")
        self.assertNotIn("pa1", other_store["goal"].get("expectation", ()))
        decisions.policy._store_visit = StoreVisit(
            owner="home-one-shot", purpose="withdraw", store_type=STORE_HOME,
            opened_sequence=9, operation_key="pax",
        )
        home = decisions.decide("home:atomic-withdraw")
        self.assertIn("pax", home["goal"]["expectation"])

    def test_composed_home_identity_survives_visit_close(self):
        decisions = _Decisions()
        visit = StoreVisit(
            owner="home-one-shot", purpose="deposit", store_type=STORE_HOME,
            opened_sequence=9, operation_key="da",
            claim_operation_identity=(STORE_HOME, 9, "da"),
        )
        decisions.policy._store_visit = visit
        decisions.policy._home_atomic_deposit_pending = (("item",), 1, 2)
        first = decisions.decide("home:atomic-deposit")
        visit.close("completed")
        continued = decisions.decide("home:leave-after-one-operation")
        self.assertEqual(first["goal"], continued["goal"])
        self.assertEqual(first["claim_id"], continued["claim_id"])

    def test_home_exit_keeps_composing_family_when_new_session_starts(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="town-errand", purpose="deposit", store_type=STORE_HOME,
            opened_sequence=9, operation_key="da",
            claim_operation_identity=(STORE_HOME, 9, "da"),
        )
        decisions.policy._home_atomic_deposit_pending = (("item",), 1, 2)
        deposit = decisions.decide("home:atomic-deposit")
        decisions.policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((), (), 0)
        )
        exit_row = decisions.decide("home:store-context-exit")
        self.assertEqual(exit_row["owner"], "home-visit")
        self.assertEqual(exit_row["claim_id"], deposit["claim_id"])
        self.assertIsNone(exit_row["violation"])

    def test_transaction_route_unavailable_step_keeps_session_claim(self):
        decisions = _Decisions()
        decisions.policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((), (), 0)
        )
        first = decisions.decide("equipment-transaction:equip")
        blocked = decisions.decide(
            "town:entrance-step-off:equipment-transaction:home-route-unavailable"
        )
        self.assertEqual(blocked["owner"], "equipment-txn")
        self.assertEqual(blocked["claim_id"], first["claim_id"])
        self.assertIsNone(blocked["violation"])

    def test_precursor_steps_do_not_open_store_observation(self):
        decisions = _Decisions()
        inscribe = decisions.decide("shop:batch-inscribe")
        self.assertEqual(inscribe["goal"]["kind"], "Terminal")
        target = decisions.cell(5)
        decisions.policy._store_visit = StoreVisit(
            owner="store-router", purpose="entry", store_type=1,
            goal=Position(*target),
        )
        wait = decisions.decide("store:entry-await-observation")
        self.assertEqual(wait["goal"]["kind"], "Reach")
        self.assertEqual(wait["goal"]["cell"], list(target))

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
        visit.__dict__.pop("opened_for_family")
        visit.__dict__.pop("operation_producer_family")
        visit.__dict__.pop("claim_operation_identity")
        restored_visit = pickle.loads(pickle.dumps(visit))
        self.assertIsNone(restored_visit.claim_id)
        self.assertIsNone(restored_visit.claim_owner)
        self.assertIsNone(restored_visit.opened_producer_family)
        self.assertIsNone(restored_visit.opened_for_family)
        self.assertIsNone(restored_visit.operation_producer_family)
        self.assertIsNone(restored_visit.claim_operation_identity)
        acquired = StoreVisit(
            owner="town-errand", purpose="buy", store_type=1,
            opened_producer_family="shop-buy", opened_for_family="shop-buy",
            operation_producer_family="shop-buy",
            claim_operation_identity=(1, 2, "key"),
        )
        self.assertEqual(pickle.loads(pickle.dumps(acquired)).opened_producer_family,
                         "shop-buy")
        self.assertEqual(pickle.loads(pickle.dumps(acquired)).opened_for_family,
                         "shop-buy")
        self.assertEqual(pickle.loads(pickle.dumps(acquired)).operation_producer_family,
                         "shop-buy")
        self.assertEqual(pickle.loads(pickle.dumps(acquired)).claim_operation_identity,
                         (1, 2, "key"))
        session = EquipmentTransactionSession(EquipmentTransactionPlan((), (), 0))
        restored_session = pickle.loads(pickle.dumps(session))
        self.assertIsNone(restored_session.opened_sequence)
        decisions = _Decisions()
        decisions.policy.__dict__.pop("_claim_active_operation_identity", None)
        decisions.policy.__dict__.pop("_decision_plan_change_evidence", None)
        decisions.policy.__dict__.pop("_decision_displaced_producer", None)
        decisions.policy.__dict__.pop("_claim_last_completed_home", None)
        decisions.policy.__dict__.pop("_claim_home_knowledge_observed", None)
        restored_policy = pickle.loads(pickle.dumps(decisions.policy))
        self.assertIsNone(getattr(restored_policy, "_claim_active_operation_identity", None))
        self.assertIsNone(getattr(restored_policy, "_decision_plan_change_evidence", None))
        self.assertIsNone(getattr(restored_policy, "_decision_displaced_producer", None))
        self.assertIsNone(getattr(restored_policy, "_claim_last_completed_home", None))
        self.assertFalse(getattr(restored_policy, "_claim_home_knowledge_observed", False))
        restored_policy._claim_home_knowledge_observed = True
        self.assertTrue(pickle.loads(pickle.dumps(
            restored_policy))._claim_home_knowledge_observed)
        restored_policy._claim_home_knowledge_observed = False
        decisions.policy = restored_policy
        self.assertEqual(decisions.decide("home:atomic-withdraw")["owner"],
                         "home-visit")

    def test_plan_handoff_remains_a_violation(self):
        decisions = _Decisions()
        first = decisions.decide("shop:approach", cell=decisions.cell(5))
        decisions.policy._decision_plan_change_evidence = {
            "previous_stops": (1,), "previous_index": 0,
            "new_stops": (STORE_HOME,), "previous_stop": 1,
            "new_stop": STORE_HOME,
        }
        second = decisions.decide("home:request-knowledge-scan")
        self.assertEqual(second["violation"]["kind"], "plan-handoff")
        self.assertEqual(second["plan_change_evidence"]["new_stop"], STORE_HOME)
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
        self.assertEqual(
            decisions.policy._decision_plan_change_evidence,
            {"previous_stops": (1,), "previous_index": 0,
             "new_stops": (STORE_HOME,), "previous_stop": 1,
             "new_stop": STORE_HOME,
             "previous_next_stop": None, "new_next_stop": None,
             "previous_categories": (),
             "new_categories": ((STORE_HOME, ("knowledge",)),)},
        )
        self.assertEqual(decisions.policy._town_errand_plan.stops, [1])

    def test_category_only_rebuild_is_not_plan_change_evidence(self):
        decisions = _Decisions()
        decisions.policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME], need_categories={STORE_HOME: ("old",)}
        )
        plan = decisions.policy._build_town_errand_plan(
            decisions.board, [TownNeed(STORE_HOME, "new", "ordinary")]
        )
        self.assertEqual(plan.stops, [STORE_HOME])
        self.assertIsNone(getattr(decisions.policy, "_decision_plan_change_evidence", None))

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

    def test_town_errand_visit_owner_preserves_opening_producer(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="town-errand", purpose="buy", store_type=1,
            opened_producer_family="shop-buy",
        )
        row = decisions.decide("shop:buy")
        self.assertIsNone(row["visit_owner_mismatch"])
        self.assertEqual(decisions.policy._store_visit.opened_producer_family,
                         "shop-buy")

    def test_town_errand_mapping_uses_opening_producer_not_later_telemetry(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="town-errand", purpose="buy", store_type=1,
            opened_producer_family="shop-buy",
        )
        decisions.policy._town_turn_arbiter.telemetry = {
            "producer_owner": "store-router",
        }
        row = decisions.decide("shop:travel", cell=decisions.cell(4))
        self.assertEqual(row["visit_owner_mismatch"]["visit_owner"], "shop-buy")
        self.assertEqual(row["visit_owner_mismatch"]["claim_owner"],
                         "store-router")

    def test_arbiter_records_producer_when_visit_is_acquired(self):
        decisions = _Decisions()
        arbiter = decisions.policy._town_turn_arbiter
        arbiter.telemetry = {"producer_owner": "shop-buy"}
        visit = arbiter.acquire_store_visit(
            store_type=1, owner="town-errand", purpose="buy",
            opened_sequence=11, opened_producer_family="shop-buy",
            close_visit=lambda _outcome: None,
        )
        self.assertEqual(visit.opened_producer_family, "shop-buy")
        arbiter.telemetry = {"producer_owner": "store-router"}
        self.assertEqual(visit.opened_producer_family, "shop-buy")

    def test_router_visit_records_its_opened_for_family(self):
        decisions = _Decisions()
        decisions.policy._home_visit.request = SimpleNamespace(
            requester="home-deposit"
        )
        decisions.policy._request_store_trip(STORE_HOME, "home-visit")
        visit = decisions.policy._store_visit
        self.assertEqual(visit.opened_producer_family, "store-router")
        self.assertEqual(visit.opened_for_family, "home-visit")

    def test_store_trip_requester_is_explicit_for_non_home_stores(self):
        decisions = _Decisions()
        decisions.policy._request_store_trip(1, "shop-buy")
        visit = decisions.policy._store_visit
        self.assertEqual(visit.opened_for_family, "shop-buy")
        self.assertEqual(pickle.loads(pickle.dumps(visit)).opened_for_family,
                         "shop-buy")

    def test_stale_home_request_does_not_supply_router_requester(self):
        decisions = _Decisions()
        decisions.policy._home_visit.request = SimpleNamespace(
            requester="home-deposit"
        )
        decisions.policy._request_store_trip(STORE_HOME, None)
        self.assertIsNone(decisions.policy._store_visit.opened_for_family)
        row = decisions.decide("home:atomic-deposit")
        self.assertTrue(row["requester_missing"])
        self.assertIsNone(row["visit_owner_mismatch"])
        self.assertEqual(s3_numbers([row])["requester_missing"], 1)

    def test_router_does_not_guess_a_home_requester(self):
        decisions = _Decisions()
        decisions.policy._shopping_approach_store_type = STORE_HOME
        self.assertIsNone(decisions.policy._store_visit.opened_for_family)

    def test_router_records_calibration_requester(self):
        decisions = _Decisions()
        session = EquipmentTransactionSession(EquipmentTransactionPlan((), (), 0))
        decisions.policy._equipment_transaction_session = session
        decisions.policy._calibration_session_target = session.target_loadout_id
        decisions.policy._home_visit.request = SimpleNamespace(
            requester="equipment-transaction"
        )
        decisions.policy._request_store_trip(STORE_HOME, "calibration")
        self.assertEqual(decisions.policy._store_visit.opened_for_family,
                         "calibration")

    def test_router_does_not_infer_requester_from_session_presence(self):
        decisions = _Decisions()
        decisions.policy._equipment_transaction_session = (
            EquipmentTransactionSession(EquipmentTransactionPlan((), (), 0))
        )
        decisions.policy._shopping_approach_store_type = STORE_HOME
        self.assertIsNone(decisions.policy._store_visit.opened_for_family)

    def test_home_composer_records_producer_before_claim_row(self):
        decisions = _Decisions()
        policy = decisions.policy
        self.assertTrue(policy._compose_home_operation(
            decisions.board, "5da\x1b", "da\x1b",
            producer_family="home-errand",
        ))
        visit = policy._store_visit
        self.assertEqual(visit.opened_producer_family, "home-errand")
        self.assertEqual(visit.operation_producer_family, "home-errand")
        decisions.decide("home:atomic-deposit")
        self.assertEqual(visit.opened_producer_family, "home-errand")

    def test_router_opening_home_operation_is_structural(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="store-router", purpose="home", store_type=STORE_HOME,
            opened_producer_family="store-router", operation_key="da",
            opened_for_family="home-visit",
            opened_sequence=4,
        )
        decisions.policy._home_atomic_deposit_pending = (("item",), 1, 2)
        row = decisions.decide("home:atomic-deposit")
        self.assertIsNone(row["visit_owner_mismatch"])
        self.assertEqual(row["visit_owner_structure"],
                         "router-opens-family-operates")

    def test_router_purpose_must_match_operating_family(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="store-router", purpose="home", store_type=STORE_HOME,
            opened_producer_family="store-router",
            opened_for_family="home-scan", operation_key="da",
            opened_sequence=4,
        )
        decisions.policy._home_atomic_deposit_pending = (("item",), 1, 2)
        row = decisions.decide("home:atomic-deposit")
        self.assertIsNone(row["visit_owner_structure"])
        self.assertEqual(row["visit_owner_mismatch"]["claim_owner"],
                         "home-visit")

    def test_non_discardable_handoff_keeps_rewrite_violation(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="town-errand", purpose="buy", store_type=STORE_HOME,
        )
        decisions.policy._home_atomic_withdraw_pending = ("item", 1, 1, 1)
        first = decisions.decide("home:atomic-withdraw")
        self.assertTrue(first["non_discardable"])
        row = decisions.decide("shop:approach", cell=decisions.cell(3))
        self.assertIsNotNone(row["violation"])
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

    def test_re_attributed_transaction_completes_under_calibration(self):
        decisions = _Decisions()
        session = EquipmentTransactionSession(EquipmentTransactionPlan((), (), 0))
        decisions.policy._equipment_transaction_session = session
        decisions.policy._calibration_session_target = session.target_loadout_id
        held = decisions.decide("equipment-transaction:deposit")
        self.assertEqual((held["owner"], held["goal"]["source"]),
                         ("calibration", "calibration"))
        decisions.policy._complete_equipment_transaction_claim()
        self.assertEqual(decisions.register.current.closed, "complete")
        self.assertEqual(decisions.register.current.closed_reason,
                         "equipment-transaction-complete")
        exit_row = decisions.decide("home:leave-after-one-operation")
        self.assertEqual(exit_row["goal"]["kind"], "Terminal")
        self.assertEqual(exit_row["closed_claim"]["claim_id"], held["claim_id"])
        self.assertEqual(exit_row["closed_claim"]["closed_reason"],
                         "equipment-transaction-complete")

    def test_transaction_completion_uses_recorded_family_after_session_changes(self):
        decisions = _Decisions()
        session = EquipmentTransactionSession(EquipmentTransactionPlan((), (), 0))
        decisions.policy._equipment_transaction_session = session
        decisions.policy._calibration_session_target = session.target_loadout_id
        held = decisions.decide("equipment-transaction:deposit")
        self.assertEqual(held["owner"], "calibration")
        decisions.policy._calibration_session_target = None
        decisions.policy._complete_equipment_transaction_claim()
        self.assertEqual(decisions.register.current.closed, "complete")

    def test_observed_home_withdraw_closes_matching_suspended_claim(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="home-one-shot", purpose="withdraw", store_type=STORE_HOME,
            opened_sequence=9, operation_key="ga",
        )
        decisions.policy._home_atomic_withdraw_pending = ("item", 1, 1, 1)
        held = decisions.decide("home:atomic-withdraw")
        decisions.register.suspend("survival-preempted")
        decisions.policy._complete_observed_effect(
            "home-withdraw-observed", owners=("home-visit",),
            sources=("store-operation",),
        )
        closed = decisions.register.take_suspended_closings()
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["claim_id"], held["claim_id"])
        self.assertEqual(closed[0]["closed"], "complete")

    def test_observed_operation_exit_has_no_fresh_observe_goal(self):
        decisions = _Decisions()
        decisions.policy._store_visit = StoreVisit(
            owner="shop-one-shot", purpose="buy", store_type=1,
            opened_sequence=9, operation_key="pa",
            operation_effect_observed=True,
        )
        row = decisions.decide("shop:leave")
        self.assertEqual(row["goal"]["kind"], "Terminal")

    def test_observed_transaction_exit_continues_recorded_claim(self):
        decisions = _Decisions()
        decisions.policy._equipment_transaction_session = (
            EquipmentTransactionSession(EquipmentTransactionPlan((), (), 0))
        )
        decisions.policy._store_visit = StoreVisit(
            owner="equipment-transaction", purpose="deposit",
            store_type=STORE_HOME, opened_sequence=9, operation_key="da",
            operation_producer_family="equipment-txn",
        )
        held = decisions.decide("equipment-transaction:deposit")
        decisions.policy._store_visit.operation_effect_observed = True
        exit_row = decisions.decide("home:leave-after-one-operation")
        self.assertEqual(exit_row["claim_id"], held["claim_id"])
        self.assertEqual(exit_row["goal"], held["goal"])

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

    def test_completed_operation_identity_survives_restored_checkpoint(self):
        decisions = _Decisions()
        decisions.policy._home_visit.operation = ("withdraw", "same-item")
        first = decisions.decide("home:atomic-withdraw")
        decisions.register.complete("home-withdraw-observed")
        decisions.decide("shop:approach", cell=decisions.cell(4))
        saved = decisions.policy._claim_last_completed_home
        self.assertEqual(len(saved), 3)
        decisions.policy = pickle.loads(pickle.dumps(decisions.policy))
        self.assertEqual(decisions.policy._claim_last_completed_home[2], saved[2])
        verdict = decisions.decide("home:atomic-withdraw-target-unobserved")
        self.assertEqual(verdict["claim_verdict_conflict"]["claim_id"],
                         first["claim_id"])

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
