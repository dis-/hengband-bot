"""The hourly-0700-1103 follow-up stops (n1-c life-115, n1-a life-468/469).

Each class pins one root on its recorded rows; only the game's replies to
newly posted keys are constructed (marked DECLARED CONSTRUCTED) and facts the
capture keeps outside the rows are marked DECLARED RECONSTRUCTED.
Fixture: tests/extract_hourly_0700b_1103_fixtures.py.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from pathlib import Path

from hengbot import me_staff_sequence as sequence
from hengbot.policy_constants import STORE_HOME
from hengbot.policy_types import TownErrandPlan
from tests import test_me_nokey_1031_recorded as _test_me_nokey_1031_recorded
import test_hourly_0700_1102_recorded as _test_hourly_0700_1102_recorded


FIXTURE = Path(__file__).with_name("fixtures") / "hourly-0700b-1103.json.gz"


def _cases():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class HomePassChargesAttemptedWorkTest(_test_hourly_0700_1102_recorded.RecordedTownPolicy, _test_me_nokey_1031_recorded.PostedKey):
    """n1-c life-115 07:21:43 town:blocked:unmet:home_candidate_resolved.

    The Magic-Eater (build 7219d480d) kept an unknown ロング・ソード (2d5) at
    Home all visit and carried five 鑑定の巻物 with eight free slots.  Each
    Home pass did one other operation (overload deposits, an atomic deposit,
    a scan) and left, and each charged the identification-withdrawal need it
    never tried; its one-attempt budget was spent (need_attempts 5), the
    claim retired and the town end stopped.  A Home pass now charges that
    need only when its identification errand was filed for the pass, so the
    visit withdraws the sword to identify it (owner 2026-10-31
    「預けた装備を取り出して鑑定する処理が別途必要」).
    DECLARED CONSTRUCTED: the policy is primed on the stop board and the five
    recorded Home pages are reported as the passes, each under a Home stop
    owning the two categories the stop's ledger charged on every pass
    (space-deposit and identification-withdrawal), each completing its own
    operation (recorded unsatisfied_passes {'7': 0}); the visit's earlier
    decisions are not replayed (the mid-visit replay diverges).
    DECLARED RECONSTRUCTED: the staff sequence record from policy-state.json.
    """

    @classmethod
    def setUpClass(cls):
        cls.case = _cases()["home_candidate"]

    def policy(self):
        case = self.case
        policy = self.primed(case["stop"], case["home"]["knowledge"]["items"], case["skill"])
        policy._in_store_ops_enabled = True  # live argv (--in-store-shop-ops)
        recorded, record = case["sequence"], sequence.state(policy)
        record.absorbed = dict(recorded["absorbed"])
        record.bought = frozenset(recorded["bought"])
        record.stage = recorded["stage"]
        record.powers_read = True
        return policy

    def test_recorded_stop(self):
        step_off, stop = self.case["decisions"]
        self.assertEqual((step_off["key"], step_off["reason"]),
                         ("1", "town:entrance-step-off:town:end-step-off"))
        self.assertEqual((stop["key"], stop["reason"], stop["home_candidate_waiting"]),
                         ("5", "town:blocked:unmet:home_candidate_resolved", True))
        block = stop["departure_block"]
        self.assertEqual(block["failed"], ["home_candidate_resolved"])
        self.assertEqual(block["town_claims"], [])
        self.assertEqual(block["town_ledger"]["need_attempts"]["identification-withdrawal"], 5)
        self.assertTrue(any(item["name"] == "ロング・ソード (2d5)" and not item["known"]
                            for item in self.case["home"]["knowledge"]["items"]))
        self.assertEqual(sum(item["count"] for item in self.case["stop"]["inventory"]
                             if (item["tval"], item["sval"]) == (70, 12)), 5)

    def test_passes_without_the_take_leave_its_budget_and_the_sword_is_taken(self):
        policy = self.policy()
        for page in self.case["passes"]:
            policy._town_errand_plan = TownErrandPlan(stops=[STORE_HOME], need_categories={
                STORE_HOME: ("space-deposit", "identification-withdrawal")})
            policy._report_town_stop_pass(self.board(policy, page), STORE_HOME,
                                          goal_satisfied=False, operation_completed=True)
        attempts = policy._town_visit_ledger.need_attempts
        self.assertNotIn("identification-withdrawal", attempts)
        self.assertEqual(attempts["space-deposit"], 5)  # the passes' own work
        raw = self.case["stop"]
        key = policy.choose_key(self.board(policy, raw))
        # Recorded: '5' town:blocked:unmet:home_candidate_resolved.
        self.assertNotEqual(policy.last_reason, "town:blocked:unmet:home_candidate_resolved")
        self.assertIn("identification-withdrawal", policy._town_claim_categories)
        request = policy._home_errand.request
        self.assertEqual((request.signature[0], request.purpose),
                         ("ロング・ソード (2d5)", "identification-catalog"))
        # The plan keeps Home for the take after the Black Market it stands at.
        self.assertEqual((key, policy.last_reason), ("9", "shop:approach"))
        self.assertIn("identification-withdrawal",
                      policy._town_errand_plan.need_categories[STORE_HOME])
        self.post(policy, raw, key)


if __name__ == "__main__":
    unittest.main()
