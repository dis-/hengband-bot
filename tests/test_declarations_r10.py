"""S3.3 ruling #5: town producers yield; declarations close the ladder."""

import pickle
import unittest
from unittest.mock import patch

import tests  # noqa: F401
from hengbot.claim_register import observe
from hengbot.policy import HengbotPolicy
from test_execution_declaration import short_route_board


class TownDeclarationRulingTest(unittest.TestCase):
    def holder(self, family, state="acting", **fields):
        policy = HengbotPolicy()
        policy._town_claim_bar_enforced = True
        board = short_route_board()
        policy.prime(board)
        claim = policy._claim_register.declare(
            family, observe(("held-work",), 99, "test"),
            floor=board.floor_key)
        policy._claim_register.declare_execution(
            claim.claim_id, work_id="held-work", producer=family,
            state=state, **fields)
        return policy, board

    def test_admitted_families_emit_in_ladder_after_competitor_skipped(self):
        cases = (
            ("curse-enchant", "town:remove-curse"),
            ("identification", "identify:device"),
            ("home-errand", "home-errand:request-knowledge"),
            ("shop-buy", "shop:buy-food"),
            ("rumor", "town:rumor-batch"),
        )
        for family, reason in cases:
            with self.subTest(family=family):
                policy, board = self.holder(
                    family, next_step="held.step", arguments=(family,))
                restored = pickle.loads(pickle.dumps(policy._claim_register))
                self.assertEqual(restored.current.execution.arguments, (family,))
                self.assertTrue(policy._defer_town_errand(
                    "home-scan" if family != "home-scan" else "rumor",
                    "competing-rung"))
                self.assertFalse(policy._defer_town_errand(
                    family, "own-rung"))
                policy.last_reason = reason
                policy._offer_execution(
                    "6", producer=family, work_id="held-work",
                    next_step="held.step", arguments=(family,))
                self.assertEqual(
                    policy._enforce_town_claim_result(board, "6"), "6")
                self.assertEqual(policy.last_reason, reason)
                self.assertEqual(
                    policy._decision_errand_deferred[-1]["deferred_family"],
                    "home-scan")

    def test_real_town_family_entry_gates_skip_before_selection(self):
        policy, board = self.holder(
            "shop-buy", next_step="shop.purchase.send")
        producers = (
            (policy._town_device_processing_key, "identification"),
            (policy._town_remove_curse_key, "curse-enchant"),
            (policy._cross_town_shopping_key, "cross-town"),
        )
        for producer, family in producers:
            with self.subTest(family=family):
                self.assertIsNone(producer(board))
                self.assertEqual(
                    policy._decision_errand_deferred[-1]["deferred_family"],
                    family)
                self.assertEqual(
                    policy._decision_errand_deferred[-1]["holder_family"],
                    "shop-buy")

    def test_awaiting_posted_operation_uses_typed_wait(self):
        policy, board = self.holder(
            "home-scan", state="awaiting",
            operation_ref="decision:41:scan",
            expected_effect="catalogue-adopted",
            continuation="home.knowledge.observe")
        self.assertEqual(policy._town_holder_ladder_result(
            policy._claim_register.current, board), "5")
        self.assertEqual(policy.last_reason, "home:scan-await-observation")

    def test_no_step_releases_and_second_pass_selects_next_rung(self):
        policy, board = self.holder(
            "curse-enchant", next_step="held.step")
        policy._offer_execution_no_step(
            producer="curse-enchant", work_id="held-work",
            cause="no-town-curse-work")
        self.assertIsNone(policy._town_holder_ladder_result(
            policy._claim_register.current, board))
        self.assertEqual(policy._claim_register.current.closed_reason,
                         "no-step:no-town-curse-work")
        self.assertTrue(policy._decision_no_step_release)
        self.assertIsNone(policy._claim_errand_hold("__none__"))
        self.assertFalse(policy._defer_town_errand("rumor", "second-pass"))

    def test_releasing_declaration_runs_one_more_public_ladder_pass(self):
        policy, board = self.holder(
            "curse-enchant", state="releasing", cause="no-curse")
        passes = []

        def ladder(_board):
            passes.append(len(passes) + 1)
            policy.last_reason = "town:rumor-batch"
            return None if len(passes) == 1 else "6"

        with (patch.object(policy, "_skill_exp_request_key",
                           return_value=None),
              patch.object(policy, "_choose_key_with_latch_capture",
                           side_effect=ladder)):
            key = policy.choose_key(board)
        self.assertEqual(passes, [1, 2])
        self.assertEqual(key, "6")
        self.assertEqual(policy.decision_claim["closed_claim"]["closed_reason"],
                         "no-step:no-curse")
        self.assertEqual(policy.decision_claim["bars_set"][0]["ending"],
                         "release:no-step:no-curse")

    def test_acting_silent_and_missing_are_typed_stops(self):
        policy, board = self.holder(
            "rumor", next_step="rumor.read-batch")
        self.assertIsNone(policy._town_holder_ladder_result(
            policy._claim_register.current, board))
        self.assertEqual(policy.last_reason, "ownership:holder-silent:rumor")
        policy._claim_register.declare(
            "rumor", observe(("missing",), 99, "test"),
            floor=board.floor_key)
        self.assertIsNone(policy._town_holder_ladder_result(
            policy._claim_register.current, board))
        self.assertEqual(policy.last_reason,
                         "ownership:declaration-missing:rumor")

    def test_no_generic_producer_reentry(self):
        policy, board = self.holder(
            "curse-enchant", next_step="curse.remove.send",
            producer_entry="_town_remove_curse_key")
        with patch.object(policy, "_town_remove_curse_key",
                          side_effect=AssertionError("reentered")):
            self.assertIsNone(policy._town_holder_wait_key(
                policy._claim_register.current, board))
        self.assertEqual(policy.last_reason,
                         "ownership:holder-silent:curse-enchant")


if __name__ == "__main__":
    unittest.main()
