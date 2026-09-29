"""Producer offers bind only to the final key and named claim owner."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hengbot.claim_register import observe
from hengbot.policy import HengbotPolicy


class BookkeepingDeclarationTest(unittest.TestCase):
    def test_save_offer_binds_only_its_final_key(self):
        policy = HengbotPolicy()
        policy._periodic_save_requested = True
        board = SimpleNamespace()
        with patch.object(policy, "_periodic_filler_is_safe", return_value=True):
            key = policy._periodic_game_save_key(board, "6")
        self.assertEqual(key, "\x13")
        claim = policy._claim_register.declare(
            "bookkeeping", observe(("save",), 8, "periodic"))
        policy._record_execution_declaration(claim, "6", policy.last_reason)
        self.assertIsNone(policy._claim_register.current.execution)

        policy._periodic_save_requested = True
        with patch.object(policy, "_periodic_filler_is_safe", return_value=True):
            key = policy._periodic_game_save_key(board, "6")
        policy._record_execution_declaration(claim, key, policy.last_reason)
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.next_step),
                         ("bookkeeping", "acting", "game.save.send"))

    def test_skill_request_no_step_has_producer_cause(self):
        policy = HengbotPolicy()
        board = SimpleNamespace(protocol_version=2)
        self.assertIsNone(policy._skill_exp_request_key(board))
        claim = policy._claim_register.declare(
            "bookkeeping", observe(("skill-exp",), 8, "knowledge"))
        policy._record_execution_declaration(claim, None, "periodic:skill-exp")
        declaration = policy._claim_register.current.execution
        self.assertEqual((declaration.producer, declaration.state,
                          declaration.cause),
                         ("bookkeeping", "releasing",
                          "skill-list-protocol-unavailable"))


if __name__ == "__main__":
    unittest.main()
