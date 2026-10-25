"""Constructed available-item control on B's recorded town surface.

The Home catalogue is a declared alternative containing one carried fixture
item. A detector changing its destination from another supplier must judge
that filed identity, before the approach fields have switched to Home.
"""
import tests  # noqa: F401

import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import STORE_HOME, STORE_MAGIC, parse_snapshot
from hengbot.policy import HengbotPolicy
from tests.test_town_terminal_n1a_recorded import _town_maps


class BorrowedVisitMaterialTest(unittest.TestCase):
    def test_available_filed_withdrawal_admits_before_approach_context_changes(self):
        fixture = Path(__file__).parent / "fixtures/town-post-s2-1025-b-state.jsonl.gz"
        with gzip.open(fixture, "rt", encoding="utf-8") as stream:
            board = parse_snapshot(json.loads(next(stream)), {})
        maps = _town_maps()
        policy = HengbotPolicy(town_map=maps[0], town_maps=maps)
        policy.prime(board)
        target = board.inventory[0]
        policy.consume_home_knowledge((target,))
        signature = policy._item_signature(target)
        policy._home_pending_item = signature
        policy._home_pending_quantity = 1
        policy._home_withdrawal_queued = True
        policy._shopping_approach_store_type = STORE_MAGIC
        policy._build_grid_index(board)
        policy._begin_map_predicate_cache(board)
        step = policy._shopping_approach_step(
            board, STORE_HOME, router_plan_stop=True, route_family="detectors")
        self.assertIsNotNone(step)
        self.assertEqual(policy._home_pending_item, signature)
        self.assertEqual(policy._shopping_approach_store_type, STORE_HOME)
        self.assertEqual(policy._decision_terminal_admissions, [])


if __name__ == "__main__":
    unittest.main()
