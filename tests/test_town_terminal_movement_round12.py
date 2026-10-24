"""Delegated movement still belongs to the caller's admitted town errand."""
import tests  # noqa: F401

import unittest
from unittest.mock import patch

from hengbot import town_terminal as tt
from test_goldburn_shopping_constructed import board
from test_town_terminal_home_withdraw import withdraw_policy


MOVEMENT = (
    "_step_toward", "_step_toward:departure", "_step_toward:escape",
    "_step_toward:hunt", "_step_toward:positioning",
    "_dig_to_known_downstairs_key", "_entrance_travel_key", "idle-fallback",
    "navigator.decide",
)


class DelegatedMovementTest(unittest.TestCase):
    def test_caller_refusal_stops_the_delegated_walk_and_store_entry(self):
        # Adjacent to the target and on it (activation WAIT): neither key is
        # composed after the caller's exact withdrawal has become unavailable.
        for rung in MOVEMENT:
            for stored in (False, True):
                snap = board()
                origin = snap.player.position
                for step in (type(origin)(origin.y, origin.x + 1), origin):
                    policy = withdraw_policy(stored=stored)
                    policy._build_grid_index(snap)
                    policy._begin_map_predicate_cache(snap)
                    policy._decision_sequence += 1
                    with self.subTest(rung=rung, stored=stored, step=step):
                        decl = tt.TERMINALS[rung]
                        self.assertEqual(decl.mode, tt.NO_REFUSAL)
                        self.assertTrue(decl.no_refusal_reason.startswith(
                            "delegated: caller's terminal governs;"))
                        with patch.object(policy, "_step_toward", wraps=policy._step_toward) as walk:
                            key = policy._town_producer_entry(
                                "_shopping_approach_key", lambda: policy._town_producer_entry(
                                    rung, lambda: policy._step_toward(snap, step), family="store-router"),
                                family="store-router")
                        self.assertEqual(walk.call_count, int(stored))
                        self.assertEqual(key, ("6" if step != origin else "5") if stored else None)
                        if not stored:
                            self.assertIsNone(policy._warning_step_pending)
                            self.assertFalse(getattr(policy, "_intentional_entrance_activation", False))


if __name__ == "__main__":
    unittest.main()
