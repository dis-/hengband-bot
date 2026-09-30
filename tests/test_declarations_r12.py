"""Pins for the early S3.3 declaration divergences."""

import inspect
import unittest

import tests  # noqa: F401 -- isolate runtime files
from hengbot.claim_register import observe
from hengbot.model import STORE_MAGIC
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit
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


if __name__ == "__main__":
    unittest.main()
