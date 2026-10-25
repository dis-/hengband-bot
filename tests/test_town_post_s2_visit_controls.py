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
from unittest.mock import patch

from hengbot.model import STORE_HOME, STORE_MAGIC, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.town_terminal import TerminalRef
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


    def test_refused_fundraising_wait_yields_until_recovery_has_named_close(self):
        fixture = Path(__file__).parent / "fixtures/town-post-s2-1025-a1426-state.jsonl.gz"
        with gzip.open(fixture, "rt", encoding="utf-8") as stream:
            board = parse_snapshot(json.loads(next(stream)), {})
        # Constructed alternatives to the missing process-local recovery state.
        # S2 itself decides whether the survival server is still live.
        for suppressed, live in ((False, False), (True, False), (True, True)):
            with self.subTest(suppressed=suppressed, live=live):
                policy = HengbotPolicy()
                policy._fundraising_mode = "mine"
                policy._planned_mining_runs = 1
                policy._town_restock_suppressed = suppressed
                policy._build_grid_index(board)
                policy._begin_map_predicate_cache(board)
                if live:
                    policy._town_turn_arbiter._vector_by_owner["survival"] = (board.turn,)
                with patch.object(policy, "_fundraising_departure_ready", return_value=False), \
                        patch.object(policy, "_town_restock_wait_key", return_value=None):
                    key = policy._town_special_key(board)
                terminal = TerminalRef("fundraising", ("mine",))
                admission = policy._decision_terminal_admissions[-1]
                self.assertEqual(admission["codes"], ["fundraising-departure-unready"])
                self.assertEqual(admission["verdict"], "refused")
                self.assertEqual(terminal in policy._town_visit_ledger.closed_terminals,
                                 not live)
                if live:
                    self.assertEqual(admission["live"], [["survival", None]])
                    self.assertEqual(admission["yields"], 1)
                else:
                    self.assertEqual(admission["closed"],
                                     "terminal-refused-unserved:fundraising-departure-unready")
                if suppressed and not live:
                    self.assertEqual(key, "5")
                    self.assertEqual(policy.last_reason, "fundraise:departure-blocked")
                    self.assertEqual(policy.prompt_owner_handoff,
                                     "town:blocked:departure-no-light")
                else:
                    self.assertIsNone(key)
                    self.assertIsNone(policy.prompt_owner_handoff)
                self.assertEqual(policy._fundraising_mode, "mine")


if __name__ == "__main__":
    unittest.main()
