"""Round-three public decision and executor pins.

Main independently recognizes bounty arrival as progress. The negative
downstream classifier control exercises the stronger owner contract: an
admitted composite survives even a downstream nonprogress verdict. Producers,
admission, routing and the executor remain real.

Refusal declarations are checked against codes emitted on B's recorded board.
An explicit empty server declaration is part of S2's named-close contract.
"""
import tests  # noqa: F401

from unittest.mock import patch

from hengbot import town_terminal
from tests import test_town_post_s2_r2 as recorded


class AdmittedCompositeAndRefusalTest(recorded.executor_harness.ProductionHarness):
    setUpClass = recorded.PostS2OwnerDecisionTest.__dict__["setUpClass"]
    attached = recorded.PostS2OwnerDecisionTest.attached
    decide = recorded.PostS2OwnerDecisionTest.decide
    cashout = recorded.PostS2OwnerDecisionTest.cashout
    drive_cashout = recorded.PostS2OwnerDecisionTest.drive_cashout

    def test_a1_admitted_operation_survives_downstream_nonprogress(self):
        policy, board, raw = self.cashout()
        policy._town_claim_bar_enforced = False
        # Fault only the downstream judgment; the bounty-specific positive
        # recognition must not mask missing general ADMIT protection.
        progress_judgment = policy._town_result_makes_progress
        with patch.object(
                policy, "_town_result_makes_progress",
                side_effect=lambda snapshot, proposed, **kwargs: (
                    False if proposed == "7cy\x1b"
                    else progress_judgment(snapshot, proposed, **kwargs))) as judgment:
            key = self.decide(policy, board)
        judgment.assert_not_called()
        self.assertEqual((key, policy.last_reason), ("7cy\x1b", "bounty:cashout"))
        game, result = self.drive_cashout(
            raw, policy, key, "Hand wanted remains over? [y/n]")
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(game.accepted, ["7", "c", "y", "\x1b"])
        self.assertFalse(any(item.get("is_bounty") for item in result.board["inventory"]))

    def test_b_real_detector_refusals_have_explicit_declarations(self):
        policy, board, _ = self.attached("b")
        policy._town_store_attempted.update({i: board.turn for i in range(8)})
        policy._recent.extend([board.player.position] * policy._recent.maxlen)
        policy._town_progress_history().append(policy._town_progress_fingerprint(board))
        # Same attachment wall as B's existing pin: the exploration decision
        # rather than the unrelated departure dispatcher.
        with patch.object(policy, "_town_special_key", return_value=None):
            key = self.decide(policy, board)
        records = policy._decision_terminal_admissions
        by_code = {code: row for row in records for code in row["codes"]}
        for code in ("home-recovery-no-work", "store-observation-current"):
            with self.subTest(code=code):
                self.assertIn(code, by_code, (key, policy.last_reason, records))
                self.assertEqual(town_terminal.declared_code(code), code)
                self.assertIn(code, town_terminal.REFUSAL_SERVERS)
                self.assertEqual(town_terminal.REFUSAL_SERVERS[code], ())
                self.assertEqual(by_code[code]["verdict"], "refused")
                self.assertEqual(by_code[code]["closed"],
                                 "terminal-refused-unserved:" + code)
