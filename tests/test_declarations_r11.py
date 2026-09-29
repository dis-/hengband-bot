"""Ruling #5 entry, leak, rewrite, and plan-order pins."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import tests  # noqa: F401 -- isolate runtime files
from hengbot.claim_register import observe
from hengbot.model import Position, STORE_HOME, STORE_MAGIC
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import TownErrandPlan
from test_execution_declaration import short_route_board


class DeclarationR11Test(unittest.TestCase):
    @staticmethod
    def policy_with_holder(family="home-visit"):
        policy = HengbotPolicy()
        policy._town_claim_bar_enforced = True
        policy._claim_register.declare(
            family, observe(("operation",), 8, "store-operation"))
        return policy

    def test_1_entry_gate_never_calls_foreign_producer(self):
        policy = self.policy_with_holder()
        called = []
        self.assertIsNone(policy._town_producer_entry(
            "_town_remove_curse_key", lambda: called.append("curse")))
        self.assertEqual(called, [])
        row = policy._decision_errand_deferred[-1]
        self.assertEqual((row["holder_family"], row["deferred_family"],
                          row["deferred_reason"]),
                         ("home-visit", "curse-enchant",
                          "entry:_town_remove_curse_key"))
        self.assertEqual(policy._town_producer_entry(
            "_home_disposal_processing_key", lambda: "home"), "home")
        self.assertEqual(policy._town_producer_entry(
            "_stat_restore_quaff_key", lambda: "survive"), "survive")

    def test_2_off_counts_final_and_on_stops_gate_leak(self):
        board = SimpleNamespace(
            in_town=True, store=None, visible_monsters=(),
            player=SimpleNamespace(position=Position(1, 1)),
        )
        off = HengbotPolicy()
        off._claim_register.declare(
            "home-visit", observe(("operation",), 8, "store-operation"))
        off.last_reason = "town:rumor-batch"
        self.assertEqual(off._enforce_town_claim_result(board, "R"), "R")
        self.assertEqual(off._decision_gate_final_count, 1)
        on = self.policy_with_holder()
        on.last_reason = "town:rumor-batch"
        self.assertIsNone(on._enforce_town_claim_result(board, "R"))
        self.assertEqual(on.last_reason, "ownership:gate-missing:rumor")
        self.assertEqual(on._decision_gate_final_count, 1)

    def test_3_gate_leak_never_runs_second_ladder_pass(self):
        board = short_route_board()
        policy = HengbotPolicy()
        policy.prime(board)
        policy._town_claim_bar_enforced = True
        policy._claim_register.declare(
            "home-visit", observe(("held-work",), 99, "test"),
            floor=board.floor_key)
        passes = []

        def rogue_result(_board):
            passes.append(len(passes) + 1)
            policy.last_reason = "town:rumor-batch"
            return "6"

        with (patch.object(policy, "_skill_exp_request_key", return_value=None),
              patch.object(policy, "_choose_key_with_latch_capture",
                           side_effect=rogue_result)):
            self.assertIsNone(policy.choose_key(board))
        self.assertEqual(passes, [1])
        self.assertEqual(policy.last_reason, "ownership:gate-missing:rumor")

    def test_4_holder_family_controls_rewrite_refusal(self):
        policy = self.policy_with_holder("store-router")
        policy.last_reason = "shop:approach"
        holder = policy._town_held_decision("6")
        self.assertIs(holder, policy._claim_register.current)
        policy._town_refuse_rewrite("no-progress", holder)
        self.assertEqual(policy._decision_rewrite_refused[-1], {
            "stage": "no-progress", "holder_family": "store-router",
            "holder_claim_id": holder.claim_id,
        })
        policy.last_reason = "town:rumor-batch"
        self.assertIsNone(policy._town_held_decision("R"))

    def test_4_public_holder_key_records_skipped_rewrites(self):
        board = short_route_board()
        policy = HengbotPolicy()
        policy.prime(board)
        policy._town_claim_bar_enforced = True
        policy._claim_register.declare(
            "store-router", observe(("held-work",), 99, "test"),
            floor=board.floor_key)

        def holder_key(_board):
            policy.last_reason = "shop:approach"
            return "6"

        with (patch.object(policy, "_skill_exp_request_key", return_value=None),
              patch.object(policy, "_choose_key_with_latch_capture",
                           side_effect=holder_key)):
            self.assertEqual(policy.choose_key(board), "6")
        stages = {row["stage"] for row in policy._decision_rewrite_refused}
        self.assertIn("no-progress", stages)
        self.assertIn("procurement", stages)

    def test_5_bookkeeping_is_outside_holder_judgement(self):
        policy = self.policy_with_holder()
        policy._periodic_save_requested = True
        with patch.object(policy, "_periodic_filler_is_safe", return_value=True):
            key = policy._periodic_game_save_key(SimpleNamespace(), "6")
        self.assertEqual(key, "\x13")
        self.assertEqual(policy.last_reason, "periodic:game-save")
        board = SimpleNamespace(in_town=True, store=None,
                                visible_monsters=(),
                                player=SimpleNamespace(position=Position(1, 1)))
        self.assertEqual(policy._enforce_town_claim_result(board, key), key)
        self.assertEqual(getattr(policy, "_decision_gate_final_count", 0), 0)
        policy.last_reason = "no-wait:damaged"
        self.assertEqual(policy._enforce_town_claim_result(board, "5"), "5")

    def test_6_store_page_uses_same_town_condition(self):
        policy = self.policy_with_holder()
        board = SimpleNamespace(
            in_town=False, store=object(), visible_monsters=(),
            player=SimpleNamespace(position=Position(1, 1)),
        )
        policy.last_reason = "town:rumor-batch"
        self.assertIsNone(policy._enforce_town_claim_result(board, "R"))
        self.assertEqual(policy.last_reason, "ownership:gate-missing:rumor")

    def test_7_plan_next_gates_other_town_family(self):
        policy = HengbotPolicy()
        policy._town_claim_bar_enforced = True
        policy._town_errand_plan = TownErrandPlan(
            [STORE_HOME, STORE_MAGIC],
            requester_families={STORE_HOME: ("home-visit",),
                                STORE_MAGIC: ("shop-buy",)},
        )
        called = []
        self.assertIsNone(policy._town_producer_entry(
            "_town_remove_curse_key", lambda: called.append("curse")))
        self.assertEqual(called, [])
        self.assertIn("plan-next", policy._decision_errand_deferred[-1][
            "deferred_reason"])
        self.assertIsNone(policy._town_producer_entry(
            "_descent_step", lambda: "descend"))
        self.assertEqual(policy._town_producer_entry(
            "_home_disposal_processing_key", lambda: "home"), "home")
        policy._town_errand_plan.index = 1
        self.assertEqual(policy._town_producer_entry(
            "town-errand:shop-buy", lambda: "buy"), "buy")
        policy._town_errand_plan.requester_families.clear()
        self.assertIsNone(policy._town_producer_entry(
            "_town_remove_curse_key", lambda: "curse"))
        policy._map_predicate_snapshot = SimpleNamespace(
            in_town=False, store=None)
        self.assertEqual(policy._town_producer_entry(
            "_descent_step", lambda: "dungeon-descent"),
            "dungeon-descent")


if __name__ == "__main__":
    unittest.main()
