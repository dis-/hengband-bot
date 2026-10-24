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
        policy._town_claim_bar_enforced = True
        policy._town_errand_plan = TownErrandPlan([7])
        self.assertTrue(policy._town_plan_defers("departure"))
        calls = []

        def reaction():
            calls.append("named-close")
            return "reaction"

        self.assertEqual(policy._town_producer_entry(
            "_town_special_key", reaction, family="departure", board=snap), "reaction")
        self.assertEqual(calls, ["named-close"])

    def test_foreign_holder_skips_the_refused_identification_confirmation(self):
        policy, snap, scan = attachment("second")
        policy.consume_skill_knowledge(json.loads(
            (FIXTURE / "skills.json").read_text(encoding="utf8")))
        policy._home_knowledge_invalidated = scan[
            "equipment_optimization"]["home_knowledge_invalidated"]
        policy._town_claim_bar_enforced = True
        terminal = rung_terminal(policy, "town-item-processing", snap)
        self.assertEqual(terminal_admission(policy, snap, terminal).codes,
                         ("no-identification-source",))
        self.assertIsNone(policy._identification_need)
        self.assertIsNone(policy._town_item_processing_key(snap))
        self.assertIsNone(policy._identification_need)
        self.assertEqual(policy._claim_register.current.claim_id, 8583)
        self.assertTrue(any(row["deferred_family"] == "identification"
                            for row in policy._decision_errand_deferred))


if __name__ == "__main__":
    unittest.main()
