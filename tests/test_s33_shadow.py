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
    def compare(self, policy, board, key, expected, *, holder_dispatch=False):
        for checkpoint in (False, True):
            with self.subTest(checkpoint=checkpoint):
                off = pickle.loads(pickle.dumps(policy)) if checkpoint else policy
                before = pickle.dumps(off)
                shadow = off._s33_shadow_verdict(board, key)
                self.assertEqual(pickle.dumps(off), before)
                self.assertEqual(shadow["would_stop"], expected)
                on = pickle.loads(before)
                on._town_claim_bar_enforced = True
                if holder_dispatch:
                    result = on._town_holder_ladder_result(
                        on._claim_register.current, board)
                else:
                    result = on._enforce_town_claim_result(board, key)
                stop = on.last_reason if result is None and on.last_reason.startswith(
                    ("ownership:declaration-", "ownership:holder-silent:",
                     "ownership:gate-missing:")) else None
                self.assertEqual(shadow["would_stop"], stop)
        return shadow

    def test_gate_leak_and_exempt_outputs_equal_on_without_state_changes(self):
        board = short_route_board()
        for reason, key, expected in (
                ("town:rumor-batch", "R", "ownership:gate-missing:rumor"),
                ("town:kill-mob-approach", "1", None),
                ("periodic:game-save", "\x13", None)):
            policy = HengbotPolicy()
            policy._claim_register.declare("home-visit", observe(("operation",), 8,
                                                                  "store-operation"))
            policy.last_reason = reason
            shadow = self.compare(policy, board, key, expected)
            self.assertEqual(shadow["holder_family"], "home-visit")
            self.assertTrue(shadow["declaration_gap"])
            self.assertIn("rumor", shadow["would_skip_families"])
            self.assertNotIn("home-visit", shadow["would_skip_families"])


    def test_missing_empty_entry_wait_equals_on(self):
        board = short_route_board()
        policy = HengbotPolicy()
        policy.last_reason = "store:entry-await-observation"
        self.compare(policy, board, "", "ownership:declaration-missing:store-router")

    def test_missing_stale_and_silent_holder_equal_on(self):
        for state, expected in (
                (None, "ownership:declaration-missing:home-visit"),
                ("awaiting", "ownership:declaration-stale:home-visit"),
                ("acting", "ownership:holder-silent:home-visit")):
            policy = HengbotPolicy()
            claim = policy._claim_register.declare("home-visit", observe(("operation",),
                                                        8, "store-operation"))
            if state:
                policy._claim_register.declare_execution(
                    claim.claim_id, producer="home-visit", work_id="home:operation",
                    state=state, next_step="home.unrecognized" if state == "acting" else None)
            policy.last_reason = "home:none"
            self.compare(policy, short_route_board(), None, expected,
                         holder_dispatch=True)

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

    def test_public_off_row_and_cli_row_carry_shadow_after_old_checkpoint(self):
        policy = HengbotPolicy()
        del policy._town_claim_bar_enforced
        policy = pickle.loads(pickle.dumps(policy))
        board = short_route_board()
        policy.prime(board)
        key = policy.choose_key(board)
        row = policy.decision_claim
        self.assertIn("s33_shadow", row)
        self.assertIsInstance(row["s33_shadow"]["declaration_gap"], bool)
        record = _decision_record(board, key, policy.last_reason, claim=row)
        self.assertEqual(record["s33_shadow"], row["s33_shadow"])

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
