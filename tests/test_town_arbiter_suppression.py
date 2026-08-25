"""ARB-2 pins ported from the suppression-release work branch."""

import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / "fixtures" / (
    "incident-postlevel-repetition-turn-1006064.jsonl.gz"
)
CAPTURED_ATTEMPTED = {
    0: 1005386, 1: 1005386, 2: 1005386, 3: 1005386,
    4: 1005386, 5: 1005386, 6: 1005386, 8: 1005386,
}


def _board():
    with gzip.open(FIXTURE, "rt", encoding="utf-8-sig") as rows:
        return parse_snapshot(json.loads(next(rows)), {})


def _incident_policy(*, suppressed: bool):
    policy = HengbotPolicy()
    policy._calibration_phase = "deposit"
    policy._town_store_attempted = dict(CAPTURED_ATTEMPTED)
    policy._town_cycle_breaks = 1
    policy._town_errand_plan = None
    policy._equipment_catalog.home_scan_complete = True
    policy._home_knowledge_current = True
    if suppressed:
        policy._town_restock_suppressed = True
        policy._town_blocked_reason = "repetition"
    return policy


class TownArbiterSuppressionTest(unittest.TestCase):
    def test_postlevel_counterfactual_releases_suppression(self):
        policy = _incident_policy(suppressed=True)
        key = policy.choose_key(_board())
        self.assertFalse(policy._town_restock_suppressed)
        self.assertNotEqual(policy.last_reason, "town:blocked:repetition")
        self.assertTrue(key)

    def test_cycle_break_does_not_suppress_reachable_gate_supplier(self):
        policy = _incident_policy(suppressed=False)
        policy._break_town_cycle(_board())
        self.assertFalse(policy._town_restock_suppressed)

    def test_suppression_implies_no_reachable_gate_supplier(self):
        snapshot = _board()
        for phase in ("deposit", None):
            policy = HengbotPolicy()
            policy._calibration_phase = phase
            policy._town_store_attempted = dict(CAPTURED_ATTEMPTED)
            policy._break_town_cycle(snapshot)
            supplier = policy._departure_supplier_counterfactual(snapshot)
            if policy._town_restock_suppressed:
                self.assertIsNone(supplier)

    def test_repeated_supplier_is_bounded_by_arbiter_vector_budget(self):
        snapshot = _board()
        policy = _incident_policy(suppressed=True)
        budget = policy._town_turn_arbiter.registry["store-router"].budget
        for _ in range(budget + 2):
            policy.choose_key(snapshot)
        telemetry = policy._town_turn_arbiter.telemetry
        self.assertTrue(
            telemetry["retired"] or telemetry["retirement_set"], telemetry
        )


if __name__ == "__main__":
    unittest.main()
