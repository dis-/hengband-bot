"""Pins for the early S3.3 declaration divergences."""

import inspect
import unittest

import tests  # noqa: F401 -- isolate runtime files
from hengbot.claim_register import observe
from hengbot.model import STORE_HOME, STORE_MAGIC
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase, TownErrandPlan
from test_execution_declaration import short_route_board


class DeclarationR12Test(unittest.TestCase):
    def test_town_probe_calls_enter_the_explore_gate(self):
        policy = HengbotPolicy()
        policy._town_claim_bar_enforced = True
        policy._claim_register.declare(
            "home-visit", observe(("57", "7", "pq5"), 8,
                                  "store-operation"))
        called = []
        for name in ("oscillating-probe", "frontier-probe"):
            with self.subTest(name=name):
                self.assertIsNone(policy._town_producer_entry(
                    name, lambda: called.append(name), family="explore"))
                self.assertEqual(policy._decision_errand_deferred[-1][
                    "deferred_family"], "explore")
        self.assertEqual(called, [])
        source = inspect.getsource(HengbotPolicy._decide)
        for name in ("oscillating-probe", "frontier-probe"):
            self.assertIn(f'"{name}", lambda: self._probe_unknown_step(snapshot),',
                          source)

    def test_town_probe_after_completed_holder_still_yields_to_plan(self):
        # The continuous town replay completes the Home operation at decision
        # entry, leaving a completed parent and a live Home plan stop.  The
        # earlier pin kept the parent open and exercised a different gate.
        policy = HengbotPolicy()
        policy._town_claim_bar_enforced = True
        policy._map_predicate_snapshot = short_route_board()
        policy._claim_register.declare(
            "home-visit", observe(("57", "7", "pq5"), 8,
                                  "store-operation"))
        policy._claim_register.complete("home-operation-observed")
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME], requester_families={STORE_HOME: ("home-errand",)})
        called = []
        for name in ("oscillating-probe", "frontier-probe"):
            self.assertIsNone(policy._town_producer_entry(
                name, lambda: called.append(name), family="explore"))
            self.assertIn("plan-next:7", policy._decision_errand_deferred[-1][
                "deferred_reason"])
        self.assertEqual(called, [])

    def test_finished_home_errand_retires_its_only_plan_stop(self):
        policy = HengbotPolicy()
        policy._town_claim_bar_enforced = True
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME], requester_families={STORE_HOME: ("home-errand",)})
        policy._claim_register.declare(
            "home-visit", observe(("57", "7", "pq5"), 8,
                                  "store-operation"))
        policy._claim_register.complete("home-operation-observed")
        self.assertFalse(policy._home_errand.active)
        policy._retire_finished_home_errand_plan_stop()
        self.assertEqual(policy._town_errand_plan.index, 1)
        self.assertEqual(policy._town_errand_plan.completed_this_visit,
                         [STORE_HOME])
        self.assertEqual(policy._town_producer_entry(
            "_descent_step", lambda: "travel"), "travel")

    def test_town_plan_precedes_boxed_breakout_at_progress_seam(self):
        policy = HengbotPolicy()
        policy._town_claim_bar_enforced = True
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME], requester_families={STORE_HOME: ("home-errand",)})
        policy.last_reason = "breakout:least-visited"
        self.assertEqual(policy._town_procurement_decision(
            short_route_board(), ""), "")
        self.assertEqual(policy.last_reason, "breakout:least-visited")

    def test_unposted_entry_cannot_emit_empty_observation_wait(self):
        policy = HengbotPolicy()
        policy._town_claim_bar_enforced = True
        board = short_route_board()
        claim = policy._claim_register.declare(
            "store-router", observe((STORE_MAGIC, "store-entry"), 8,
                                    "store-entry"), floor=board.floor_key)
        policy._claim_register.declare_execution(
            claim.claim_id, work_id="entry:4", producer="store-router",
            state="awaiting", operation_ref="decision:3705:entry",
            expected_effect="store-page-open",
            continuation="store.entry.observe")
        policy._store_visit = StoreVisit(
            "town-plan", "shopping", STORE_MAGIC,
            opened_sequence=3705, posted_sequence=None)
        policy.last_reason = "store:entry-await-observation"
        self.assertIsNone(policy._enforce_town_claim_result(board, ""))
        self.assertEqual(policy.last_reason,
                         "ownership:declaration-missing:store-router")
        policy._store_entry_posted_owner = STORE_MAGIC
        policy._store_visit.posted_sequence = 3704
        policy.last_reason = "store:entry-await-observation"
        self.assertIsNone(policy._enforce_town_claim_result(board, ""))
        policy._store_visit.posted_sequence = 3705
        policy.last_reason = "store:entry-await-observation"
        self.assertEqual(policy._enforce_town_claim_result(board, ""), "")

    def test_armed_entry_without_operation_reaches_progress_seam(self):
        # Replay 3706 has a store-entry declaration and matching armed/posted
        # sequence, but no posted store operation or operation identity.  The
        # wrapper must run procurement instead of treating its empty key as
        # the holder's finished decision.
        policy = HengbotPolicy()
        policy._town_claim_bar_enforced = True
        board = short_route_board()
        claim = policy._claim_register.declare(
            "store-router", observe((STORE_MAGIC, "store-entry"), 8,
                                    "store-entry"), floor=board.floor_key)
        policy._claim_register.declare_execution(
            claim.claim_id, work_id="entry:4", producer="store-router",
            state="awaiting", operation_ref="decision:3705:entry",
            expected_effect="store-page-open",
            continuation="store.entry.observe")
        policy._store_visit = StoreVisit(
            "town-plan", "shopping", STORE_MAGIC,
            phase=StoreVisitPhase.ENTERING,
            opened_sequence=3705, armed_sequence=3705,
            posted_sequence=3705, claim_id=claim.claim_id)
        policy.last_reason = "store:entry-await-observation"
        self.assertEqual(policy._enforce_town_claim_result(board, ""), "")
        self.assertIsNone(policy._town_held_decision(""))
        policy._store_visit.operation_posted = True
        policy._store_visit.claim_operation_identity = (STORE_MAGIC, 3705, "p")
        self.assertEqual(policy._town_held_decision(""),
                         policy._claim_register.current)


if __name__ == "__main__":
    unittest.main()
