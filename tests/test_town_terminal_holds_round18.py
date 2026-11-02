"""Terminal refusal commits and dispatcher probes respect their actual owners."""

import tests  # noqa: F401

import json
import unittest

from hengbot.policy_types import TownErrandPlan
from hengbot.town_terminal import rung_terminal, terminal_admission
from test_goldburn_shopping_constructed import board
from test_live37_home_scan import attachment, FIXTURE
from test_town_terminal_departure import policy_on


class RefusalHoldTest(unittest.TestCase):
    def test_dispatcher_reaction_is_not_suppressed_by_the_departure_plan_hold(self):
        snap = board()
        policy = policy_on(snap)
        policy._town_errand_plan = TownErrandPlan([7])
        calls = []

        def reaction():
            calls.append("named-close")
            return "reaction"

        self.assertEqual(policy._town_producer_entry(
            "_town_special_key", reaction, family="departure", board=snap), "reaction")
        self.assertEqual(calls, ["named-close"])


if __name__ == "__main__":
    unittest.main()
