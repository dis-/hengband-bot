"""OFF shadow is observational and shares ON town-result predicates."""
import pickle
import unittest
import tests  # noqa: F401
from hengbot.claim_register import Bar, BAR_ERRAND, observe, owner_of, reach
from hengbot.cli import _decision_record
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import TownErrandPlan
from test_execution_declaration import short_route_board


class ShadowVerdictTest(unittest.TestCase):
    def test_plan_entry_and_off_key_reason_identity(self):
        policy = HengbotPolicy()
        policy._town_errand_plan = TownErrandPlan(
            [7], requester_families={7: ("home-visit",)})
        policy.last_reason = "town:rumor-batch"
        before = pickle.dumps(policy)
        shadow = policy._s33_shadow_verdict(short_route_board(), "R")
        self.assertEqual(pickle.dumps(policy), before)
        self.assertIn("rumor", shadow["would_skip_families"])
        self.assertNotIn("store-router", shadow["would_skip_families"])
        calls = []
        self.assertEqual(policy._town_producer_entry(
            "_town_rumor_key", lambda: calls.append("once") or "R", family="rumor"), "R")
        self.assertEqual(calls, ["once"])
        self.assertEqual(policy.last_reason, "town:rumor-batch")

    def test_active_bar_and_missing_checkpoint_delegations_are_pure(self):
        policy = HengbotPolicy()
        board = short_route_board()
        policy.last_reason = "town:rumor-batch"
        clearance = policy._claim_errand_clearance(board, "rumor", policy.last_reason)
        policy._claim_register.set_bar(Bar(
            owner_of("rumor"), observe(("rumor",), 8, "test"), BAR_ERRAND,
            ending="release:no-step:unposted", clearance=clearance,
            reason=policy.last_reason))
        policy.__dict__.pop("_execution_delegations", None)
        before = pickle.dumps(policy)
        shadow = policy._s33_shadow_verdict(board, "R")
        self.assertIn("rumor", shadow["would_skip_families"])
        self.assertEqual(pickle.dumps(policy), before)
        self.assertNotIn("_execution_delegations", policy.__dict__)

    def test_observed_arrival_is_completed_before_recording_shadow(self):
        board = short_route_board()
        policy = HengbotPolicy()
        position = board.player.position
        claim = policy._claim_register.declare(
            "store-router", reach((position.y, position.x)), floor=board.floor_key)
        policy.last_reason = "town:rumor-batch"
        policy._record_decision_claim(board, "R")
        row = policy.decision_claim
        self.assertEqual(row["closed_claim"]["claim_id"], claim.claim_id)
        self.assertIsNone(row["s33_shadow"]["would_stop"])
        self.assertNotEqual(row["s33_shadow"]["holder_claim_id"], claim.claim_id)


if __name__ == "__main__":
    unittest.main()
