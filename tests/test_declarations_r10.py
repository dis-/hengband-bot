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
        board = short_route_board()
        policy.prime(board)
        claim = policy._claim_register.declare(
            family, observe(("held-work",), 99, "test"),
            floor=board.floor_key)
        policy._claim_register.declare_execution(
            claim.claim_id, work_id="held-work", producer=family,
            state=state, **fields)
        return policy, board

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


if __name__ == "__main__":
    unittest.main()
