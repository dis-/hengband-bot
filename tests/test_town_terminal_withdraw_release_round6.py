"""Round 6: a refused Home walk releases the visit its approach acquired.

The constructed Home catalogue and request are shared with round 5. The
real approach step acquires a visit and requests travel before the walking
entry. Temporary ENFORCE pins cleanup; production remains SHADOW.
"""

import tests  # noqa: F401

import unittest
from unittest.mock import patch

from hengbot import town_terminal as tt
from hengbot.model import STORE_HOME
from hengbot.policy_types import StoreVisitPhase
from test_goldburn_shopping_constructed import board
from test_town_terminal_home_withdraw import withdraw_policy


class WithdrawReleaseTest(unittest.TestCase):
    def test_refused_walk_releases_acquired_visit_and_trip(self):
        for rung in ("_shopping_approach_key", "_shopping_approach_key#1",
                     "_shopping_approach_key#2"):
            for stored, enforce in ((False, True), (True, True), (False, False)):
                with self.subTest(rung=rung, stored=stored, enforce=enforce):
                    snap = board()
                    policy = withdraw_policy(stored=stored)
                    policy._home_pending_item = policy._home_visit.request.item_identity
                    policy._home_visit.request = None
                    policy._store_visit = None
                    policy._build_grid_index(snap)
                    policy._begin_map_predicate_cache(snap)
                    policy._decision_sequence += 1
                    policy._shopping_approach_step(snap, STORE_HOME, requester="home-errand")
                    visit = policy._store_visit
                    self.assertIsNotNone(visit)
                    self.assertEqual(visit.opened_for_family, "home-errand")
                    self.assertEqual(policy._shopping_approach_store_type, STORE_HOME)
                    decl = tt.TERMINALS[rung]
                    modes = {rung: tt.TerminalDecl(
                        decl.intended_terminal, tt.ENFORCE if enforce else tt.SHADOW)}
                    calls = []
                    with patch.dict(tt.TERMINALS, modes):
                        key = policy._town_producer_entry(
                            rung, lambda: calls.append("walk") or "walk", family="store-router")
                    refused = not stored and enforce
                    self.assertEqual(key, None if refused else "walk")
                    self.assertEqual(calls, [] if refused else ["walk"])
                    if refused:
                        self.assertIsNone(policy._store_visit)
                        self.assertIsNone(policy._town_turn_arbiter.store_visit)
                        self.assertIsNone(policy._shopping_approach_store_type)
                        self.assertIs(policy._store_visit_last_closed, visit)
                        self.assertEqual(visit.phase, StoreVisitPhase.CLOSED)
                        self.assertEqual(visit.outcome, "reservation-unavailable")
                    else:
                        self.assertIs(policy._store_visit, visit)
                        self.assertNotEqual(visit.phase, StoreVisitPhase.CLOSED)


if __name__ == "__main__":
    unittest.main()
