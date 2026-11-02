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
    def test_town_plan_precedes_boxed_breakout_at_progress_seam(self):
        policy = HengbotPolicy()
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME], requester_families={STORE_HOME: ("home-errand",)})
        policy.last_reason = "breakout:least-visited"
        self.assertEqual(policy._town_procurement_decision(
            short_route_board(), ""), "")
        self.assertEqual(policy.last_reason, "breakout:least-visited")


if __name__ == "__main__":
    unittest.main()
