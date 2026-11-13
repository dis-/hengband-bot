"""The rescue registry of the departure leaves (town rebuild stage 2, owner 2026-11-12).

Real last boards of tests/fixtures/keep-running-a0 (test_keep_running_a0); the
board changes below are DECLARED CONSTRUCTED.
"""
import tests  # noqa: F401

from dataclasses import replace
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from hengbot import departure_rescues
from hengbot.departure_rescues import RESCUES, Rescue, rescue_key
from hengbot.model import STORE_ALCHEMIST, STORE_TEMPLE
from test_keep_running_a0 import ready_board

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import departure_rescue_lint  # noqa: E402


def no_recall(board):
    """DECLARED CONSTRUCTED: the ready board without its Recall scrolls."""
    return replace(board, inventory=[i for i in board.inventory if not i.is_recall_scroll])


class RescueRegistryLintTest(unittest.TestCase):
    def test_every_gate_leaf_has_a_rescue_row(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(departure_rescue_lint.main(), 0, out.getvalue())
        self.assertIn("0 gap(s)", out.getvalue())

    def test_a_missing_row_and_an_unknown_action_are_gaps(self):
        rows = dict(RESCUES)
        del rows["recall_departure_ready"]
        rows["food_ready"] = Rescue(("no-such-action",))
        rows["hp_full"] = Rescue(())
        with patch.object(departure_rescues, "RESCUES", rows), \
                redirect_stdout(io.StringIO()) as out:
            self.assertEqual(departure_rescue_lint.main(), 1)
        text = out.getvalue()
        self.assertIn("'recall_departure_ready' has no rescue row", text)
        self.assertIn("unknown action 'no-such-action'", text)
        self.assertIn("'hp_full' has neither an action nor a stop reason", text)


class RescueKeyTest(unittest.TestCase):
    def test_short_recall_walks_to_an_untried_supplier(self):
        policy, board, _ = ready_board()
        bare = no_recall(board)
        with redirect_stdout(io.StringIO()):
            key = rescue_key(policy, bare, ("recall_departure_ready",))
        self.assertIsNotNone(key)
        self.assertEqual(policy.last_reason, "shop:travel")
        self.assertEqual(policy._departure_rescue_last, ("recall_departure_ready", "supplier-visit"))
        self.assertEqual(policy._shopping_approach_store_type, STORE_TEMPLE)

    def test_tried_suppliers_fall_through_to_the_named_stop(self):
        policy, board, _ = ready_board()
        bare = no_recall(board)
        policy._town_store_attempted[STORE_TEMPLE] = 1
        policy._town_store_attempted[STORE_ALCHEMIST] = 1
        with patch.object(policy, "_rearm_town_store_for_new_work"), \
                patch.object(policy, "_cross_town_shopping_key", return_value=None), \
                patch.object(policy, "_supply_stockout_mining_key", return_value=None):
            self.assertIsNone(rescue_key(policy, bare, ("recall_departure_ready",)))

    def test_attempts_are_bounded_per_visit(self):
        policy, board, _ = ready_board()
        bare = no_recall(board)
        calls = []

        def visit(_policy, _board, leaf):
            calls.append(leaf)
            return "7"

        with patch.dict(departure_rescues.ACTIONS, {"supplier-visit": visit,
                                                    "cross-town": lambda *a: None,
                                                    "stockout-mining": lambda *a: None}),                 redirect_stdout(io.StringIO()):
            # Two attempts, each separated by another decision.
            for _ in range(2):
                policy._decision_sequence += 5
                self.assertEqual(rescue_key(policy, bare, ("recall_departure_ready",)), "7")
                # A continuation on the next decision costs no attempt.
                policy._decision_sequence += 1
                self.assertEqual(rescue_key(policy, bare, ("recall_departure_ready",)), "7")
            policy._decision_sequence += 5
            self.assertIsNone(rescue_key(policy, bare, ("recall_departure_ready",)))
        self.assertEqual(len(calls), 4)

    def test_stop_only_leaves_have_no_rescue(self):
        policy, board, _ = ready_board()
        self.assertIsNone(rescue_key(policy, board, ("equipment_observed",)))


if __name__ == "__main__":
    unittest.main()
