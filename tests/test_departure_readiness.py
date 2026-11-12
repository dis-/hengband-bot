"""The one departure readiness table (town rebuild stage 1, owner 2026-11-12).

Real last boards of tests/fixtures/keep-running-a0 (test_keep_running_a0);
the board changes below are DECLARED CONSTRUCTED.  Pinned: the ordinary
departure gate, the forced departure's minimum, the procurement rows and the
stock-out mining terminal answer every supply from the same table at one depth.
"""
import tests  # noqa: F401

from dataclasses import replace
import unittest
from unittest.mock import patch

from hengbot.departure_readiness import SUPPLY_LEAVES, readiness_table
from hengbot.model import SV_POTION_CURE_CRITICAL, SV_STAFF_IDENTIFY, TVAL_STAFF
from test_keep_running_a0 import ready_board


def removals(board):
    """DECLARED CONSTRUCTED: the ready board with one supply taken away."""
    return {
        "recall": replace(board, inventory=[i for i in board.inventory if not i.is_recall_scroll]),
        "teleport": replace(board, inventory=[i for i in board.inventory if not i.is_teleport_scroll]),
        "cure": replace(board, inventory=[i for i in board.inventory if not (
            i.is_potion and i.sval == SV_POTION_CURE_CRITICAL)]),
        "light": replace(board, inventory=[i for i in board.inventory if not i.is_light],
                         equipment=[i for i in board.equipment if not i.is_light]),
        "identify": replace(board, inventory=[i for i in board.inventory if not (
            i.tval == TVAL_STAFF and i.sval == SV_STAFF_IDENTIFY)]),
    }


class ReadinessTableTest(unittest.TestCase):
    def test_minimum_and_ordinary_gate_read_the_same_supply_leaves(self):
        policy, board, depth = ready_board()
        for name, changed in {"ready": board, **removals(board)}.items():
            for landing in (depth, 1, 40, 60):
                with self.subTest(board=name, landing=landing):
                    minimum = policy._departure_minimum(changed, landing)["values"]
                    gate = policy._recall_town_departure_conjuncts(changed, commit=False)
                    table = readiness_table(policy, changed)
                    for leaf in SUPPLY_LEAVES:
                        self.assertEqual(minimum[leaf], gate[leaf], leaf)
                        self.assertEqual(bool(table.met(leaf)), bool(gate[leaf]), leaf)

    def test_procurement_rows_are_the_table_rows(self):
        policy, board, _ = ready_board()
        for name, changed in {"ready": board, **removals(board)}.items():
            with self.subTest(board=name):
                rows = policy.procurement_requirements(changed)
                table = readiness_table(policy, changed)
                self.assertEqual(rows, table.procurement_rows())
                short = {item.label for item in table.items() if item.short}
                self.assertEqual({row["item"] for row in rows}, short)

    def test_an_absorbed_identify_staff_asks_for_no_charges(self):
        policy, board, _ = ready_board()
        policy._equipment_optimization_last_depth = 30
        bare = removals(board)["identify"]
        labels = [row["item"] for row in policy.procurement_requirements(bare)]
        self.assertIn("Identify staff charges", labels)
        with patch.object(policy, "_identify_staff_absorbed", return_value=True):
            labels = [row["item"] for row in policy.procurement_requirements(bare)]
            self.assertNotIn("Identify staff charges", labels)
            self.assertTrue(readiness_table(policy, bare).met("identify_staff_ready"))

    def test_stock_out_is_a_short_ledger_supply_without_a_source(self):
        policy, board, _ = ready_board()
        bare = removals(board)["recall"]
        table = readiness_table(policy, bare)
        recall = table.leaves["recall_departure_ready"].items[0]
        self.assertTrue(recall.short)
        self.assertEqual(table.stocked_out("recall_departure_ready"), not recall.obtainable)
        blocked = {row["item"] for row in table.procurement_rows()
                   if row.get("blocked_reason") == "no-actionable-supplier"}
        self.assertEqual("Word of Recall scrolls" in blocked, not recall.obtainable)
        self.assertFalse(table.stocked_out("hp_full"))
        self.assertEqual(table.leaf_kinds("recall_departure_ready"), {"recall"})


if __name__ == "__main__":
    unittest.main()
